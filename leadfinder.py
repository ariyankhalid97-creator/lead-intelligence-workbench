#!/usr/bin/env python3
"""Free local-business lead finder using OpenStreetMap and an optional Maps API."""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
import sqlite3
import sys
import time
import threading
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urljoin, urlparse
from urllib.request import Request, urlopen
from urllib.robotparser import RobotFileParser

APP_USER_AGENT = (
    "FreeLeadFinder/1.0 (local research tool; respectful public-data client)"
)
NOMINATIM = os.environ.get("LEADFINDER_GEOCODER", "https://nominatim.openstreetmap.org")
GEO_LOCK = threading.Lock()
GEO_LAST = 0.0
OVERPASS_ENDPOINTS = (
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass-api.de/api/interpreter",
)
LOCAL_MAPS_API = "http://127.0.0.1:8000"

CATEGORY_FILTERS: dict[str, list[tuple[str, str]]] = {
    "dentist": [("amenity", "dentist")],
    "doctor": [("amenity", "doctors"), ("healthcare", "doctor")],
    "clinic": [("amenity", "clinic"), ("healthcare", "clinic")],
    "hospital": [("amenity", "hospital")],
    "pharmacy": [("amenity", "pharmacy")],
    "restaurant": [("amenity", "restaurant")],
    "cafe": [("amenity", "cafe")],
    "hotel": [("tourism", "hotel"), ("tourism", "guest_house")],
    "barber": [("shop", "hairdresser")],
    "salon": [("shop", "hairdresser"), ("shop", "beauty")],
    "gym": [("leisure", "fitness_centre")],
    "real estate": [("office", "estate_agent")],
    "lawyer": [("office", "lawyer")],
    "accountant": [("office", "accountant")],
    "insurance": [("office", "insurance")],
    "car repair": [("shop", "car_repair")],
    "plumber": [("craft", "plumber")],
    "electrician": [("craft", "electrician")],
    "roofer": [("craft", "roofer")],
    "hvac": [("craft", "hvac")],
    "photographer": [("craft", "photographer")],
    "marketing": [("office", "advertising_agency")],
    "web design": [("office", "it")],
    "school": [("amenity", "school")],
    "kindergarten": [("amenity", "kindergarten")],
}

EMAIL_RE = re.compile(
    r"(?i)(?<![\w.+-])([a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9-]+(?:\.[a-z0-9-]+)+)"
)
PHONE_RE = re.compile(
    r"(?:(?:\+|00)\d{1,3}[\s().-]?)?(?:\(?\d{2,4}\)?[\s.-]?)?\d{3,4}[\s.-]?\d{3,4}"
)
SOCIAL_HOSTS = {
    "facebook.com": "facebook",
    "instagram.com": "instagram",
    "linkedin.com": "linkedin",
    "x.com": "x",
    "twitter.com": "x",
    "youtube.com": "youtube",
    "tiktok.com": "tiktok",
}
GENERIC_EMAIL_PREFIXES = (
    "info@",
    "hello@",
    "contact@",
    "office@",
    "sales@",
    "support@",
    "admin@",
    "booking@",
)


@dataclass
class Lead:
    name: str = ""
    category: str = ""
    address: str = ""
    city: str = ""
    phone: str = ""
    email: str = ""
    website: str = ""
    facebook: str = ""
    instagram: str = ""
    linkedin: str = ""
    latitude: str = ""
    longitude: str = ""
    rating: str = ""
    reviews: str = ""
    opening_hours: str = ""
    source: str = ""
    source_url: str = ""
    source_id: str = ""
    score: int = 0
    emails: str = ""
    phones: str = ""
    evidence: str = "[]"
    sources: str = ""
    match_status: str = "candidate"
    match_reason: str = ""
    contact_status: str = "not_checked"
    checked_at: str = ""
    profile_url: str = ""
    discovery_query: str = ""
    search_location: str = ""
    discovery_intent: str = "business"
    record_type: str = "website_candidate"
    operator_type: str = "unknown"
    operator_confidence: str = "unknown"
    operator_evidence: str = "[]"
    observations: str = "[]"
    facts: str = "[]"
    assumptions: str = "[]"
    quality_flags: str = "[]"
    source_strength: str = "unknown"
    location_evidence: str = "query_only"
    evidence_score: int = 0
    workflow_signals: str = "[]"
    decision_maker: str = ""
    decision_maker_role: str = ""
    research_profile: str = "general"
    opportunity: str = "{}"
    opportunity_score: float = 0
    reference_id: str = ""
    reference_as_of: str = ""
    ai_analysis: str = "{}"
    ai_draft: str = "{}"
    verification: str = "{}"
    email_quality: str = "{}"
    duplicate_summary: str = "[]"

    def identity(self) -> str:
        if self.source_id:
            return f"{self.source}:{self.source_id}"
        phone = re.sub(r"\D", "", self.phone)
        host = (
            urlparse(normalize_website(self.website))
            .netloc.lower()
            .removeprefix("www.")
        )
        base = (
            f"{self.profile_url or host}|{phone}|{self.name}|{self.address}|{self.city}"
        )
        return re.sub(r"\W+", "", base.casefold())


def fetch(
    url: str, *, data: bytes | None = None, timeout: int = 30, retries: int = 2
) -> bytes:
    request = Request(
        url,
        data=data,
        headers={
            "User-Agent": APP_USER_AGENT,
            "Accept": "application/json,text/html,*/*",
        },
    )
    for attempt in range(retries + 1):
        try:
            with urlopen(request, timeout=timeout) as response:
                return response.read()
        except (HTTPError, URLError, TimeoutError) as exc:
            if attempt == retries:
                raise RuntimeError(f"Request failed for {url}: {exc}") from exc
            time.sleep(1.5 * (2**attempt))
    raise RuntimeError("unreachable")


def geocode(location: str) -> dict:
    global GEO_LAST
    cache_path = Path(__file__).resolve().parent / "data" / "geocodes.json"
    with GEO_LOCK:
        try:
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            cache = {}
        key = location.casefold().strip()
        if key in cache:
            return cache[key]
        time.sleep(max(0, 1.1 - (time.monotonic() - GEO_LAST)))
        url = f"{NOMINATIM}/search?format=jsonv2&limit=1&addressdetails=1&q={quote(location)}"
        GEO_LAST = time.monotonic()
        rows = json.loads(fetch(url, timeout=15, retries=0).decode("utf-8"))
        if not rows:
            raise RuntimeError(f"Location not found: {location}")
        cache[key] = rows[0]
        cache_path.parent.mkdir(exist_ok=True)
        cache_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        return rows[0]


def overpass_query(niche: str, bbox: str, limit: int) -> str:
    aliases = CATEGORY_FILTERS.get(niche.casefold().strip())
    selectors: list[str] = []
    if aliases:
        selectors = [f'nwr["{key}"="{value}"]({bbox});' for key, value in aliases]
    else:
        from discovery import plan

        phrases = plan(niche)["phrases"]
        safe = "|".join(re.escape(x) for x in phrases).replace(r"\ ", "[ -]+")
        regex = json.dumps(safe)
        selectors = [
            f'nwr["{key}"~{regex},i]({bbox});' for key in ("name", "description")
        ]
    return f"[out:json][timeout:25];({''.join(selectors)});out center tags {max(limit * 3, 100)};"


def osm_search(niche: str, location: str, limit: int, emit=None) -> list[Lead]:
    place = geocode(location)
    south, north, west, east = place["boundingbox"]
    bbox = f"{south},{west},{north},{east}"
    payload = overpass_query(niche, bbox, limit).encode("utf-8")
    if emit:
        emit(
            "osm",
            "info",
            "Geography resolved and map query prepared",
            area=place.get("display_name"),
            query=payload.decode(),
        )
    result = None
    errors = []
    for endpoint in OVERPASS_ENDPOINTS:
        try:
            result = json.loads(
                fetch(endpoint, data=payload, timeout=32, retries=0).decode("utf-8")
            )
            if result.get("remark"):
                raise RuntimeError(result["remark"])
            if emit:
                emit(
                    "osm",
                    "info",
                    "Map provider responded",
                    endpoint=endpoint,
                    count=len(result.get("elements", [])),
                )
            break
        except RuntimeError as exc:
            errors.append(str(exc))
            if emit:
                emit(
                    "osm",
                    "warning",
                    "Map endpoint unavailable",
                    endpoint=endpoint,
                    error=str(exc)[:300],
                )
    if result is None:
        raise RuntimeError(
            "All Overpass providers failed. Try again later. " + " | ".join(errors)
        )

    leads = []
    for item in result.get("elements", []):
        tags = item.get("tags", {})
        name = tags.get("name") or tags.get("brand")
        if not name:
            continue
        lat = item.get("lat") or item.get("center", {}).get("lat", "")
        lon = item.get("lon") or item.get("center", {}).get("lon", "")
        address = ", ".join(
            filter(
                None,
                [
                    " ".join(
                        filter(
                            None,
                            [tags.get("addr:housenumber"), tags.get("addr:street")],
                        )
                    ),
                    tags.get("addr:suburb"),
                    tags.get("addr:city"),
                    tags.get("addr:postcode"),
                    tags.get("addr:country"),
                ],
            )
        )
        website = (
            tags.get("contact:website") or tags.get("website") or tags.get("url") or ""
        )
        email_addr = tags.get("contact:email") or tags.get("email") or ""
        phone = (
            tags.get("contact:phone")
            or tags.get("phone")
            or tags.get("contact:mobile")
            or ""
        )
        category = next(
            (
                tags.get(k)
                for k in (
                    "amenity",
                    "shop",
                    "office",
                    "craft",
                    "tourism",
                    "healthcare",
                    "leisure",
                )
                if tags.get(k)
            ),
            niche,
        )
        lead = Lead(
            name=name,
            category=category.replace("_", " "),
            address=address,
            city=tags.get("addr:city") or tags.get("addr:town") or location,
            search_location=location,
            phone=phone,
            email=email_addr,
            website=website,
            facebook=tags.get("contact:facebook", ""),
            instagram=tags.get("contact:instagram", ""),
            linkedin=tags.get("contact:linkedin", ""),
            latitude=str(lat),
            longitude=str(lon),
            opening_hours=tags.get("opening_hours", ""),
            source="openstreetmap",
            source_id=f"{item.get('type')}/{item.get('id')}",
            source_url=f"https://www.openstreetmap.org/{item.get('type')}/{item.get('id')}",
        )
        leads.append(lead)
        if len(leads) >= limit:
            break
    return leads


def first_present(row: dict, *names: str):
    for name in names:
        if row.get(name) not in (None, "", []):
            return row[name]
    return ""


def local_maps_available(timeout: float = 0.5) -> bool:
    """Return quickly when the installed Maps Extractor API is listening."""
    try:
        fetch(LOCAL_MAPS_API + "/", timeout=timeout, retries=0)
        return True
    except RuntimeError:
        return False


def maps_search(niche: str, location: str, limit: int) -> list[Lead]:
    query = f"{niche} in {location}"
    url = f"{LOCAL_MAPS_API}/search?query={quote(query)}&limit={limit}"
    raw = json.loads(fetch(url, timeout=180, retries=0).decode("utf-8"))
    rows = raw.get("results", raw.get("data", raw)) if isinstance(raw, dict) else raw
    if isinstance(rows, dict):
        rows = rows.get("results", [])
    leads = []
    for row in rows or []:
        place_id = str(first_present(row, "place_id", "placeId", "id"))
        leads.append(
            Lead(
                name=str(first_present(row, "name", "title")),
                category=str(first_present(row, "main_category", "category", "type")),
                address=str(first_present(row, "address", "complete_address")),
                city=location,
                phone=str(first_present(row, "phone", "phone_number")),
                email=str(first_present(row, "email", "emails")),
                website=str(first_present(row, "website", "website_url")),
                rating=str(first_present(row, "rating", "reviews_average")),
                reviews=str(
                    first_present(row, "reviews", "reviews_count", "review_count")
                ),
                latitude=str(first_present(row, "latitude", "lat")),
                longitude=str(first_present(row, "longitude", "lng", "lon")),
                opening_hours=json.dumps(
                    first_present(row, "opening_hours", "hours"), ensure_ascii=False
                )
                if isinstance(
                    first_present(row, "opening_hours", "hours"), (dict, list)
                )
                else str(first_present(row, "opening_hours", "hours")),
                source="google_maps_local",
                source_id=place_id,
                source_url=str(
                    first_present(row, "link", "url", "google_maps_url", "maps_url")
                ),
            )
        )
    return leads[:limit]


def normalize_website(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    return value if value.startswith(("http://", "https://")) else "https://" + value


def allowed_by_robots(url: str) -> bool:
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    parser = RobotFileParser()
    parser.set_url(robots_url)
    try:
        parser.read()
        return parser.can_fetch(APP_USER_AGENT, url)
    except Exception:
        return True


def enrich_lead(lead: Lead, delay: float = 0.4) -> Lead:
    lead.website = normalize_website(lead.website)
    if not lead.website or not allowed_by_robots(lead.website):
        return lead
    queue = [lead.website]
    seen = set()
    emails = set(filter(None, [lead.email]))
    phones = set(filter(None, [lead.phone]))
    social: dict[str, str] = {}
    for url in queue:
        if url in seen or len(seen) >= 3:
            continue
        seen.add(url)
        try:
            text = fetch(url, timeout=15, retries=1).decode("utf-8", errors="ignore")
        except RuntimeError:
            continue
        clean = html.unescape(text)
        emails.update(
            e
            for e in EMAIL_RE.findall(clean)
            if not e.lower().endswith((".png", ".jpg", ".webp", ".svg"))
        )
        phones.update(
            p.strip()
            for p in PHONE_RE.findall(re.sub(r"<[^>]+>", " ", clean))
            if len(re.sub(r"\D", "", p)) >= 7
        )
        for href in re.findall(r'(?i)href=["\']([^"\']+)', clean):
            absolute = urljoin(url, href)
            host = urlparse(absolute).netloc.lower().removeprefix("www.")
            for social_host, key in SOCIAL_HOSTS.items():
                if host == social_host or host.endswith("." + social_host):
                    social.setdefault(key, absolute)
            if (
                len(queue) < 3
                and urlparse(absolute).netloc == urlparse(lead.website).netloc
                and re.search(r"(?i)/(contact|about|team)", absolute)
            ):
                queue.append(absolute.split("#", 1)[0])
        time.sleep(delay)
    if emails:
        lead.email = sorted(
            emails,
            key=lambda e: (not e.lower().startswith(GENERIC_EMAIL_PREFIXES), len(e)),
        )[0]
    if phones and not lead.phone:
        lead.phone = sorted(phones, key=len)[0]
    lead.facebook = lead.facebook or social.get("facebook", "")
    lead.instagram = lead.instagram or social.get("instagram", "")
    lead.linkedin = lead.linkedin or social.get("linkedin", "")
    return lead


def score(lead: Lead) -> int:
    value = 10
    value += 25 if lead.phone else 0
    value += 30 if lead.email else 0
    value += 15 if lead.website else 0
    value += 8 if (lead.facebook or lead.instagram or lead.linkedin) else 0
    value += 5 if lead.address else 0
    try:
        value += 7 if float(lead.rating) >= 4 else 0
    except (TypeError, ValueError):
        pass
    return min(value, 100)


class Store:
    def __init__(self, path: Path):
        self.db = sqlite3.connect(path)
        numeric = {
            "score": "INTEGER",
            "evidence_score": "INTEGER",
            "opportunity_score": "REAL",
        }
        columns = ", ".join(
            f'"{f.name}" {numeric.get(f.name, "TEXT")}' for f in fields(Lead)
        )
        self.db.execute(
            f"CREATE TABLE IF NOT EXISTS leads (identity TEXT PRIMARY KEY, {columns}, updated_at TEXT DEFAULT CURRENT_TIMESTAMP)"
        )
        existing = {row[1] for row in self.db.execute("PRAGMA table_info(leads)")}
        for field in fields(Lead):
            if field.name not in existing:
                self.db.execute(
                    f'ALTER TABLE leads ADD COLUMN "{field.name}" {numeric.get(field.name, "TEXT")}'
                )

    def save(self, leads: Iterable[Lead]) -> None:
        names = [f.name for f in fields(Lead)]
        placeholders = ",".join("?" for _ in range(len(names) + 1))
        quoted = ",".join(["identity"] + [f'"{n}"' for n in names])
        updates = ",".join(f'"{n}"=excluded."{n}"' for n in names)
        sql = f"INSERT INTO leads ({quoted}) VALUES ({placeholders}) ON CONFLICT(identity) DO UPDATE SET {updates}, updated_at=CURRENT_TIMESTAMP"
        self.db.executemany(
            sql,
            (
                [lead.identity()] + [getattr(lead, n) for n in names]
                for lead in leads
                if lead.identity()
            ),
        )
        self.db.commit()

    def close(self):
        self.db.close()


def deduplicate(leads: Iterable[Lead], merge_log: list[dict] | None = None) -> list[Lead]:
    merged: dict[str, Lead] = {}
    for lead in leads:
        # Match same-domain records only when branch location is compatible.
        host = (
            urlparse(normalize_website(lead.website))
            .netloc.lower()
            .removeprefix("www.")
        )
        phone = re.sub(r"\D", "", lead.phone)[-10:]
        key = lead.identity()
        merge_reason = ""
        for old_key, old in merged.items():
            old_host = (
                urlparse(normalize_website(old.website))
                .netloc.lower()
                .removeprefix("www.")
            )
            old_phone = re.sub(r"\D", "", old.phone)[-10:]
            branch_ok = not (
                lead.address
                and old.address
                and lead.address.casefold() != old.address.casefold()
            )
            same_city = (
                lead.city.casefold() == old.city.casefold()
                or not lead.city
                or not old.city
            )
            if phone and phone == old_phone and branch_ok:
                merge_reason = "same_normalized_phone"
                key = old_key
                break
            if host and host == old_host and branch_ok and same_city:
                merge_reason = "same_normalized_domain"
                key = old_key
                break
        if not key:
            continue
        if key not in merged:
            merged[key] = lead
        else:
            old = merged[key]
            if merge_log is not None and old is not lead:
                merge_log.append(
                    {
                        "kept_name": old.name,
                        "merged_name": lead.name,
                        "reason": merge_reason or "same_identity",
                        "phone": phone if merge_reason == "same_normalized_phone" else "",
                        "domain": host if merge_reason == "same_normalized_domain" else "",
                        "kept_source": old.source,
                        "merged_source": lead.source,
                    }
                )
            for field in fields(Lead):
                if not getattr(old, field.name) and getattr(lead, field.name):
                    setattr(old, field.name, getattr(lead, field.name))
            old.sources = "; ".join(
                dict.fromkeys(
                    filter(
                        None,
                        (old.sources or old.source).split("; ")
                        + (lead.sources or lead.source).split("; "),
                    )
                )
            )
            try:
                for list_field in ("evidence", "observations", "workflow_signals"):
                    combined = json.loads(getattr(old, list_field)) + json.loads(
                        getattr(lead, list_field)
                    )
                    setattr(
                        old,
                        list_field,
                        json.dumps(
                            list(
                                {
                                    json.dumps(e, sort_keys=True): e for e in combined
                                }.values()
                            ),
                            ensure_ascii=False,
                        ),
                    )
            except (ValueError, TypeError):
                pass
    return list(merged.values())


def export(leads: list[Lead], path: Path, fmt: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [asdict(lead) for lead in leads]
    if fmt == "json":
        path.write_text(
            json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    else:
        with path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=[f.name for f in fields(Lead)])
            writer.writeheader()
            # Prevent a public listing from turning into a spreadsheet formula.
            writer.writerows(
                {
                    key: (
                        "'" + str(value)
                        if str(value).lstrip().startswith(("=", "+", "-", "@"))
                        else value
                    )
                    for key, value in row.items()
                }
                for row in rows
            )


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")[:60]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Find public local-business leads for free."
    )
    parser.add_argument("niche", help='Business type, e.g. "dentist" or "plumber"')
    parser.add_argument("location", help='City/area, e.g. "Lahore, Pakistan"')
    parser.add_argument(
        "--limit", type=int, default=100, choices=range(1, 501), metavar="1-500"
    )
    parser.add_argument(
        "--source", choices=("hybrid", "osm", "google"), default="hybrid"
    )
    parser.add_argument(
        "--enrich",
        action="store_true",
        help="Visit public business websites for email/social links",
    )
    parser.add_argument("--format", choices=("csv", "json"), default="csv")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--database", type=Path, default=Path("data/leads.db"))
    args = parser.parse_args(argv)
    args.database.parent.mkdir(parents=True, exist_ok=True)
    leads: list[Lead] = []
    if args.source in ("google", "hybrid"):
        try:
            print("Trying local Google Maps Extractor…", file=sys.stderr)
            leads.extend(maps_search(args.niche, args.location, args.limit))
        except Exception as exc:
            if args.source == "google":
                print(
                    f"Google source unavailable: {exc}\nOpen Google Maps Extractor and start its API server on port 8000.",
                    file=sys.stderr,
                )
                return 2
            print(
                "Local Maps API is unavailable; continuing with OpenStreetMap.",
                file=sys.stderr,
            )
    if args.source in ("osm", "hybrid") and len(leads) < args.limit:
        print("Searching OpenStreetMap…", file=sys.stderr)
        leads.extend(osm_search(args.niche, args.location, args.limit))
    leads = deduplicate(leads)[: args.limit]
    if args.enrich:
        for index, lead in enumerate(leads, 1):
            print(f"Enriching {index}/{len(leads)}: {lead.name}", file=sys.stderr)
            enrich_lead(lead)
    for lead in leads:
        lead.score = score(lead)
    leads.sort(key=lambda item: item.score, reverse=True)
    store = Store(args.database)
    try:
        store.save(leads)
    finally:
        store.close()
    output = (
        args.output
        or Path("leads") / f"{slug(args.niche)}-{slug(args.location)}.{args.format}"
    )
    export(leads, output, args.format)
    with_email = sum(bool(x.email) for x in leads)
    with_phone = sum(bool(x.phone) for x in leads)
    print(
        f"Saved {len(leads)} leads to {output} ({with_phone} phones, {with_email} emails)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
