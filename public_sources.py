"""No-key public-data lead providers with explicit niche applicability."""

from __future__ import annotations

import json
import re
import time
from urllib.parse import quote, urlparse

from leadfinder import Lead, fetch, normalize_business_name
from research import add_observation


STATE_CODES = {
    "alabama": "AL",
    "alaska": "AK",
    "arizona": "AZ",
    "arkansas": "AR",
    "california": "CA",
    "colorado": "CO",
    "connecticut": "CT",
    "delaware": "DE",
    "florida": "FL",
    "georgia": "GA",
    "hawaii": "HI",
    "idaho": "ID",
    "illinois": "IL",
    "indiana": "IN",
    "iowa": "IA",
    "kansas": "KS",
    "kentucky": "KY",
    "louisiana": "LA",
    "maine": "ME",
    "maryland": "MD",
    "massachusetts": "MA",
    "michigan": "MI",
    "minnesota": "MN",
    "mississippi": "MS",
    "missouri": "MO",
    "montana": "MT",
    "nebraska": "NE",
    "nevada": "NV",
    "new hampshire": "NH",
    "new jersey": "NJ",
    "new mexico": "NM",
    "new york": "NY",
    "north carolina": "NC",
    "north dakota": "ND",
    "ohio": "OH",
    "oklahoma": "OK",
    "oregon": "OR",
    "pennsylvania": "PA",
    "rhode island": "RI",
    "south carolina": "SC",
    "south dakota": "SD",
    "tennessee": "TN",
    "texas": "TX",
    "utah": "UT",
    "vermont": "VT",
    "virginia": "VA",
    "washington": "WA",
    "west virginia": "WV",
    "wisconsin": "WI",
    "wyoming": "WY",
}

NPI_TAXONOMIES = {
    "dent": "Dentist",
    "orthodont": "Orthodontics and Dentofacial Orthopedics",
    "oral surgeon": "Oral and Maxillofacial Surgery",
    "doctor": "Family Medicine",
    "physician": "Family Medicine",
    "medical clinic": "Clinic/Center",
    "urgent care": "Urgent Care",
    "chiropract": "Chiropractor",
    "physical therap": "Physical Therapist",
    "occupational therap": "Occupational Therapist",
    "speech therap": "Speech-Language Pathologist",
    "psycholog": "Psychologist",
    "psychiatr": "Psychiatry & Neurology",
    "counsel": "Counselor",
    "addiction": "Substance Abuse Rehabilitation Facility",
    "home health": "Home Health",
    "nursing home": "Skilled Nursing Facility",
    "assisted living": "Assisted Living Facility",
    "hospice": "Hospice Care, Community Based",
    "optometr": "Optometrist",
    "ophthalmolog": "Ophthalmology",
    "audiolog": "Audiologist",
    "hearing aid": "Hearing Instrument Specialist",
    "podiatr": "Podiatrist",
    "dermatolog": "Dermatology",
    "plastic surgeon": "Plastic Surgery",
    "massage therap": "Massage Therapist",
    "acupunct": "Acupuncturist",
    "nutrition": "Nutritionist",
    "dietitian": "Dietitian, Registered",
    "pharmac": "Pharmacy",
    "medical laborator": "Clinical Medical Laboratory",
    "diagnostic imaging": "Radiology",
}


def npi_taxonomy(niche: str) -> str:
    value = str(niche or "").casefold()
    return next(
        (taxonomy for term, taxonomy in NPI_TAXONOMIES.items() if term in value), ""
    )


def _location_parts(location: str) -> tuple[str, str]:
    parts = [part.strip() for part in str(location).split(",") if part.strip()]
    city = parts[0] if parts else ""
    state_value = parts[1].casefold() if len(parts) > 1 else ""
    state = (
        state_value.upper()
        if len(state_value) == 2
        else STATE_CODES.get(state_value, "")
    )
    return city, state


def npi_search(niche: str, location: str, limit: int, emit=None) -> list[Lead]:
    """Search the official US NPI Registry for applicable healthcare niches."""
    taxonomy = npi_taxonomy(niche)
    city, state = _location_parts(location)
    if not taxonomy:
        return []
    if not city or not state:
        raise RuntimeError("NPI Registry requires a US city and state")
    count = min(max(int(limit), 1), 200)
    url = (
        "https://npiregistry.cms.hhs.gov/api/?version=2.1"
        f"&limit={count}&city={quote(city)}&state={quote(state)}"
        f"&taxonomy_description={quote(taxonomy)}"
    )
    payload = json.loads(fetch(url, timeout=25, retries=1).decode("utf-8"))
    if emit:
        emit(
            "npi",
            "info",
            "Official NPI Registry responded",
            taxonomy=taxonomy,
            city=city,
            state=state,
            count=int(payload.get("result_count", 0) or 0),
        )
    leads = []
    for item in payload.get("results", []):
        basic = item.get("basic") or {}
        addresses = item.get("addresses") or []
        address = next(
            (row for row in addresses if row.get("address_purpose") == "LOCATION"),
            addresses[0] if addresses else {},
        )
        organization = str(basic.get("organization_name") or "").strip()
        person = " ".join(
            filter(
                None,
                (
                    basic.get("first_name"),
                    basic.get("middle_name"),
                    basic.get("last_name"),
                ),
            )
        ).strip()
        name = organization or person
        if not name or str(basic.get("status", "A")) != "A":
            continue
        npi = str(item.get("number") or "")
        categories = [
            row.get("desc", "") for row in item.get("taxonomies", []) if row.get("desc")
        ]
        street = " ".join(
            filter(None, (address.get("address_1"), address.get("address_2")))
        )
        full_address = ", ".join(
            filter(
                None,
                (
                    street,
                    address.get("city"),
                    address.get("state"),
                    address.get("postal_code"),
                ),
            )
        )
        official = " ".join(
            filter(
                None,
                (
                    basic.get("authorized_official_first_name"),
                    basic.get("authorized_official_last_name"),
                ),
            )
        ).strip()
        lead = Lead(
            name=name.title(),
            category=(categories[0] if categories else taxonomy),
            address=full_address.title(),
            city=str(address.get("city") or city).title(),
            search_location=location,
            phone=str(
                address.get("telephone_number")
                or basic.get("authorized_official_telephone_number")
                or ""
            ),
            source="npi_registry",
            source_id=npi,
            source_url=f"https://npiregistry.cms.hhs.gov/provider-view/{npi}",
            sources="npi_registry",
            decision_maker=official.title(),
            decision_maker_role=str(
                basic.get("authorized_official_title_or_position") or ""
            ),
            discovery_query=f"{taxonomy} in {city}, {state}",
            discovery_intent="licensed_provider",
            record_type="licensed_provider",
            source_strength="official_registry",
            location_evidence="official_registry_address",
        )
        add_observation(
            lead,
            "official_registry",
            "; ".join(filter(None, [*categories[:3], full_address, f"NPI {npi}"])),
            lead.source_url,
            "US NPI Registry",
        )
        leads.append(lead)
    return leads


def npi_secondary_enrichment(
    leads: list[Lead],
    niche: str,
    location: str,
    limit: int,
    cancel=None,
    emit=None,
) -> list[Lead]:
    """Find likely practice sites for registry-only provider records.

    The NPI Registry is authoritative for identity/taxonomy but intentionally
    does not provide a practice website.  This bounded second waterfall uses
    an exact name + taxonomy + city query.  The normal website enrichment pass
    then extracts published contact evidence from the selected site.
    """
    from ddgs import DDGS
    from discovery import (
        has_explicit_business_schema,
        is_directory,
        is_negative_media_domain,
    )

    taxonomy = npi_taxonomy(niche)
    if not taxonomy or not leads:
        return leads
    excluded = (
        "npiregistry.cms.hhs.gov",
        "healthgrades.com",
        "vitals.com",
        "zocdoc.com",
        "doximity.com",
        "linkedin.com",
        "facebook.com",
        "instagram.com",
        "yelp.com",
        "yellowpages.com",
    )
    budget = min(len(leads), max(1, min(int(limit), 50)))
    enriched = 0
    failures = 0
    for lead in leads[:budget]:
        if cancel is not None and cancel.is_set():
            break
        city = lead.city or _location_parts(location)[0]
        query = f'"{lead.name}" "{taxonomy}" "{city}"'
        try:
            results = list(DDGS(timeout=10).text(query, max_results=6, backend="auto"))
        except Exception as exc:
            failures += 1
            if emit:
                emit(
                    "npi_enrichment",
                    "warning",
                    "Targeted provider website query failed; registry record retained",
                    provider_name=lead.name,
                    query=query,
                    error=str(exc)[:240],
                )
            continue
        name_words = {
            word
            for word in re.findall(r"[a-z0-9]+", lead.name.casefold())
            if len(word) > 2 and word not in {"the", "inc", "llc", "clinic", "center"}
        }
        candidates = []
        for result in results:
            url = str(result.get("href") or "")
            host = (urlparse(url).hostname or "").casefold().removeprefix("www.")
            if not host or any(
                host == item or host.endswith("." + item) for item in excluded
            ):
                continue
            if is_directory(url):
                continue
            if is_negative_media_domain(url) and not has_explicit_business_schema(url):
                continue
            haystack = " ".join(
                (str(result.get("title") or ""), str(result.get("body") or ""), host)
            ).casefold()
            overlap = sum(word in haystack for word in name_words)
            if name_words and overlap < max(1, min(2, len(name_words))):
                continue
            candidates.append((overlap, url, result))
        if not candidates:
            if emit:
                emit(
                    "npi_enrichment",
                    "info",
                    "No confident practice website found; registry record retained",
                    provider_name=lead.name,
                    query=query,
                )
            continue
        _, website, result = sorted(candidates, key=lambda row: -row[0])[0]
        lead.website = website
        add_observation(
            lead,
            "secondary_web_discovery",
            " ".join(
                filter(
                    None,
                    (
                        normalize_business_name(result.get("title", ""), city),
                        str(result.get("body") or "")[:500],
                    ),
                )
            ),
            website,
            "NPI targeted web waterfall",
        )
        enriched += 1
        if emit:
            emit(
                "npi_enrichment",
                "info",
                "Practice website found for NPI provider",
                provider_name=lead.name,
                taxonomy=taxonomy,
                city=city,
                query=query,
                website=website,
            )
        time.sleep(0.15)
    if emit:
        emit(
            "npi_enrichment",
            "info",
            "NPI secondary website waterfall complete",
            attempted=min(budget, len(leads)),
            websites_found=enriched,
            query_failures=failures,
            retained_without_website=sum(not lead.website for lead in leads),
        )
    return leads


def wikidata_search(
    search_plan: dict, location: str, limit: int, emit=None
) -> list[Lead]:
    """Best-effort discovery of notable organizations from Wikidata's public API."""
    phrase = (search_plan.get("phrases") or [""])[0]
    query = f"{phrase} {location}".strip()
    url = (
        "https://www.wikidata.org/w/api.php?action=wbsearchentities&format=json"
        f"&language=en&type=item&limit={min(max(int(limit), 1), 25)}&search={quote(query)}"
    )
    payload = json.loads(fetch(url, timeout=20, retries=1).decode("utf-8"))
    records = payload.get("search", [])
    if emit:
        emit(
            "wikidata",
            "info",
            "Wikidata entity search responded",
            query=query,
            count=len(records),
        )
    niche_words = {
        word
        for word in re.findall(r"[a-z]{4,}", phrase.casefold())
        if word not in {"service", "services", "company", "contractor", "contractors"}
    }
    place_words = {
        word
        for word in re.findall(r"[a-z]{3,}", location.casefold())
        if word not in {"usa"}
    }
    leads = []
    for item in records:
        text = " ".join(
            (str(item.get("label", "")), str(item.get("description", "")))
        ).casefold()
        if niche_words and not any(word in text for word in niche_words):
            continue
        if place_words and not any(word in text for word in place_words):
            continue
        entity_id = str(item.get("id") or "")
        lead = Lead(
            name=str(item.get("label") or entity_id),
            category=str(item.get("description") or ""),
            city=location,
            search_location=location,
            source="wikidata",
            source_id=entity_id,
            source_url=str(
                item.get("concepturi") or f"https://www.wikidata.org/wiki/{entity_id}"
            ),
            sources="wikidata",
            discovery_query=query,
            discovery_intent="open_knowledge_entity",
            record_type="organization_entity",
            source_strength="public_structured_data",
            location_evidence="description_match",
        )
        add_observation(
            lead,
            "structured_entity",
            item.get("description", ""),
            lead.source_url,
            "Wikidata",
        )
        leads.append(lead)
    return leads
