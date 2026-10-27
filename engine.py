"""Durable search jobs, bounded providers, checkpoints and structured diagnostics."""

from __future__ import annotations
import csv
import importlib.util
import io
import json
import logging
from logging.handlers import RotatingFileHandler
import os
import re
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path

import leadfinder as lf
import public_sources
import reference_library
from contacts import WebClient, enrich, now, public_url
from discovery import plan, relevance, browser_maps, web_search, repair_generic_name
from research import (
    strategy,
    analyze,
    quality_review,
    balanced_select,
    discover_platforms,
)
from prospecting import assess, profile_metadata

SOURCE_ROOT = Path(__file__).resolve().parent
ROOT = Path(os.environ.get("LEAD_EXTRACTOR_HOME", SOURCE_ROOT)).expanduser().resolve()
DB = ROOT / "data" / "workbench.db"
EVENTS: dict[str, threading.Event] = {}
ACTIVE_LOCK = threading.Lock()
STORAGE_LOCK = threading.Lock()
LOG = logging.getLogger("leadfinder")


@contextmanager
def connection():
    DB.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB, timeout=15)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def init(recover=True):
    with connection() as conn:
        conn.executescript(
            (SOURCE_ROOT / "replica" / "schema.sql").read_text(encoding="utf-8")
        )
        for job_id, payload in (
            conn.execute(
                "SELECT id,payload FROM jobs WHERE status IN ('queued','running','waiting')"
            ).fetchall()
            if recover
            else []
        ):
            job = json.loads(payload)
            job.update(
                status="interrupted",
                message="The app restarted before this run finished. Collected leads are retained.",
            )
            conn.execute(
                "UPDATE jobs SET status=?,payload=?,updated_at=? WHERE id=?",
                ("interrupted", json.dumps(job), now(), job_id),
            )
    (ROOT / "logs").mkdir(exist_ok=True)
    if not LOG.handlers:
        handler = RotatingFileHandler(
            ROOT / "logs" / "searches.log",
            maxBytes=2_000_000,
            backupCount=3,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
        LOG.addHandler(handler)
        LOG.setLevel(logging.INFO)


def validate(params):
    if not isinstance(params, dict):
        raise ValueError("Search settings must be an object")
    niche = params.get("niche", "")
    location = params.get("location", "")
    if not isinstance(niche, str) or not 2 <= len(niche.strip()) <= 120:
        raise ValueError("Enter a business type between 2 and 120 characters")
    if not isinstance(location, str) or len(location) > 500:
        raise ValueError("Enter valid locations")
    locations = [x.strip() for x in re.split(r"[\n;]", location) if x.strip()]
    if not 1 <= len(locations) <= 5:
        raise ValueError("Enter between one and five locations, one per line")
    limit = params.get("limit", 100)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500:
        raise ValueError("Lead limit must be from 1 to 500")
    source = params.get("source", "hybrid")
    if source not in ("hybrid", "osm", "google", "browser", "web", "websites"):
        raise ValueError("Choose a supported source")
    for key in ("enrich", "browser", "research_platforms", "prefer_independent"):
        if key in params and not isinstance(params[key], bool):
            raise ValueError(f"{key} must be true or false")
    urls = params.get("urls", "")
    custom = params.get("phrases", "")
    if (
        not isinstance(urls, str)
        or len(urls) > 15000
        or not isinstance(custom, str)
        or len(custom) > 1000
    ):
        raise ValueError("Too many URLs or phrases")
    if len([u for u in urls.splitlines() if u.strip()]) > 100:
        raise ValueError("Maximum 100 website URLs per run")
    if source == "websites" and not urls.strip():
        raise ValueError("Paste at least one public business website")
    settings = {
        "target": ("both", "businesses", "individuals"),
        "coverage": ("exact", "metro", "states", "usa"),
        "depth": ("quick", "balanced", "deep"),
    }
    chosen = {}
    for key, options in settings.items():
        value = params.get(key, options[0] if key != "depth" else "balanced")
        if value not in options:
            raise ValueError(f"Choose a valid {key}")
        chosen[key] = value
    research_profile = params.get("research_profile", "general")
    if research_profile not in ("general", "hood_automation"):
        raise ValueError("Choose a valid research profile")
    if research_profile == "hood_automation" and not re.search(
        r"hood|kitchen.*exhaust|restaurant.*exhaust", niche, re.I
    ):
        raise ValueError(
            "The hood-report profile is for kitchen hood/exhaust services. Choose General research for other niches."
        )
    reference_ids = params.get("reference_ids", [])
    if (
        not isinstance(reference_ids, list)
        or len(reference_ids) > 100
        or any(
            not isinstance(r, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", r)
            for r in reference_ids
        )
    ):
        raise ValueError("Choose valid library references")
    budget = params.get("query_budget", 24)
    if (
        isinstance(budget, bool)
        or not isinstance(budget, int)
        or not 4 <= budget <= 120
    ):
        raise ValueError("Query budget must be from 4 to 120")
    return {
        "niche": niche.strip(),
        "location": "\n".join(locations),
        "locations": locations,
        "limit": limit,
        "source": source,
        "enrich": params.get("enrich", True),
        "browser": params.get("browser", True),
        "urls": urls,
        "phrases": custom,
        **chosen,
        "query_budget": budget,
        "research_platforms": params.get("research_platforms", True),
        "prefer_independent": params.get("prefer_independent", True),
        "research_profile": research_profile,
        "reference_ids": reference_ids,
    }


def save(job):
    with connection() as conn:
        conn.execute(
            "INSERT INTO jobs(id,created_at,updated_at,status,payload) VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET updated_at=excluded.updated_at,status=excluded.status,payload=excluded.payload",
            (
                job["id"],
                job["created_at"],
                now(),
                job["status"],
                json.dumps(job, ensure_ascii=False),
            ),
        )


def get_job(job_id, events=True):
    with connection() as conn:
        row = conn.execute("SELECT payload FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not row:
            return None
        job = json.loads(row[0])
        if events:
            job["events"] = [
                {
                    "time": r[0],
                    "provider": r[1],
                    "level": r[2],
                    "message": r[3],
                    "details": json.loads(r[4]),
                }
                for r in conn.execute(
                    "SELECT created_at,provider,level,message,details FROM events WHERE job_id=? ORDER BY id",
                    (job_id,),
                )
            ]
        return job


def history():
    with connection() as conn:
        jobs = [
            json.loads(x[0])
            for x in conn.execute(
                "SELECT payload FROM jobs ORDER BY updated_at DESC LIMIT 60"
            )
        ]
    return [
        {
            k: j.get(k)
            for k in (
                "id",
                "params",
                "created_at",
                "status",
                "count",
                "message",
                "elapsed",
            )
        }
        for j in jobs
    ]


def catalog():
    chrome = (
        Path("C:/Program Files/Google/Chrome/Application/chrome.exe").exists()
        or Path("C:/Program Files (x86)/Google/Chrome/Application/chrome.exe").exists()
    )
    return [
        {
            "id": "browser",
            "name": "Google Maps · Chrome",
            "state": "ready"
            if chrome and importlib.util.find_spec("playwright")
            else "setup needed",
            "cost": "No API fee",
            "description": "Reads public listings in a dedicated Chrome profile. CAPTCHA needs your action.",
        },
        {
            "id": "osm",
            "name": "OpenStreetMap / Overpass",
            "state": "available",
            "cost": "Free public service",
            "description": "Mapped businesses with location, tags and published contact details. Coverage varies by niche.",
        },
        {
            "id": "web",
            "name": "Web discovery",
            "state": "installed"
            if importlib.util.find_spec("ddgs")
            else "setup needed",
            "cost": "No API key",
            "description": "Best-effort public web search via DDGS. Search engines may restrict automated queries.",
        },
        {
            "id": "websites",
            "name": "Business websites",
            "state": "ready",
            "cost": "Free",
            "description": "Paste URLs or enrich discovered businesses using structured data, contact pages and public links.",
        },
        {
            "id": "google",
            "name": "Local Maps Extractor API",
            "state": "ready" if lf.local_maps_available(0.15) else "not running",
            "cost": "Local search; paid add-ons disabled",
            "description": "Start the desktop extractor API on port 8000. The app never requests paid contact enrichment.",
        },
        {
            "id": "npi",
            "name": "US NPI Registry",
            "state": "available for healthcare niches",
            "cost": "Free official public API",
            "description": "Licensed US healthcare organizations and professionals with public practice addresses, phones and taxonomies.",
        },
        {
            "id": "wikidata",
            "name": "Wikidata organizations",
            "state": "available",
            "cost": "Free public API",
            "description": "Best-effort structured discovery of notable organizations; local-business coverage varies.",
        },
        {
            "id": "directories",
            "name": "Public directory profiles",
            "state": "available through web discovery",
            "cost": "No platform login or paid reveal",
            "description": "Searches public Yelp, Yellow Pages, Manta, Chamber, BBB, MapQuest, Alignable and niche profile URLs, then verifies claims elsewhere.",
        },
        {
            "id": "licensed",
            "name": "Apollo / Places / Apify / Outscraper",
            "state": "not connected",
            "cost": "Account/key or licensed data",
            "description": "Researched in the source report. No paid calls are made; these are not installed providers.",
        },
    ]


def start(params):
    params = validate(params)
    # Every niche uses an explicit, editable intelligence pack. Its synonyms
    # augment discovery while the normal query budget still bounds all work.
    import intelligence

    niche_pack = intelligence.ensure_niche_pack(params["niche"])
    existing_phrases = [item.strip() for item in params.get("phrases", "").splitlines() if item.strip()]
    combined_phrases = list(dict.fromkeys([*existing_phrases, *niche_pack.get("synonyms", [])[1:]]))[:10]
    params["phrases"] = "\n".join(combined_phrases)
    with ACTIVE_LOCK:
        if EVENTS:
            raise ValueError(
                "A search is already running. Cancel it or wait for it to finish."
            )
        job_id = uuid.uuid4().hex
        cancel = threading.Event()
        EVENTS[job_id] = cancel
    job = {
        "id": job_id,
        "created_at": now(),
        "status": "queued",
        "message": "Preparing search",
        "progress": 1,
        "params": params,
        "plan": plan(params["niche"], params["phrases"]),
        "niche_pack": niche_pack,
        "rows": [],
        "count": 0,
        "warnings": [],
        "providers": {},
        "stats": {},
        "elapsed": 0,
    }
    job["strategy"] = strategy(job["plan"], params)
    save(job)
    threading.Thread(target=run, args=(job, cancel), daemon=True).start()
    return job_id


def cancel_job(job_id):
    with ACTIVE_LOCK:
        event = EVENTS.get(job_id)
        if event:
            event.set()
    return bool(event)


def root_cause_analysis(
    params,
    research_plan,
    providers,
    rows,
    events,
    merge_log,
    unavailable_websites,
):
    """Build a deterministic explanation from recorded execution evidence."""
    unique_merges = []
    seen_merges = set()
    for merge in merge_log:
        marker = json.dumps(merge, sort_keys=True, ensure_ascii=False)
        if marker not in seen_merges:
            seen_merges.add(marker)
            unique_merges.append(merge)
    website_errors = [
        str(e.get("details", {}).get("error", ""))
        for e in events
        if e.get("provider") == "website"
        and e.get("message") == "Website page unavailable"
    ]
    website_failure_summary = {
        "dns_resolution": sum("resolve" in error.casefold() or "dns" in error.casefold() for error in website_errors),
        "robots_restriction": sum("robots" in error.casefold() for error in website_errors),
        "http_error": sum(bool(re.search(r"\b(?:HTTP|status)\s*[45]\d\d\b", error, re.I)) and "robots" not in error.casefold() for error in website_errors),
        "timeout": sum("timed out" in error.casefold() or "timeout" in error.casefold() for error in website_errors),
        "other": 0,
    }
    classified = sum(website_failure_summary.values())
    website_failure_summary["other"] = max(0, len(website_errors) - classified)
    provider_failures = [
        {
            "provider": name,
            "error": details.get("error", "Provider did not complete"),
            "records": details.get("count", 0),
        }
        for name, details in providers.items()
        if details.get("failures", 0) or details.get("status") == "failed"
    ]
    map_queries = [q for q in research_plan.get("queries", []) if q["channel"] == "browser"]
    attempted_map_queries = list(
        dict.fromkeys(
            e["details"].get("query")
            for e in events
            if e["provider"] == "browser"
            and e["message"] == "Opening Google Maps in dedicated Chrome"
            and e["details"].get("query")
        )
    )
    map_stops = [
        e["details"]
        for e in events
        if e["provider"] == "browser" and e["message"] == "Maps scrolling stopped"
    ]
    provider_records = sum(int(p.get("count", 0) or 0) for p in providers.values())
    causes = []
    for failure in provider_failures:
        causes.append(
            {
                "kind": "provider_failure",
                "provider": failure["provider"],
                "impact": "No new records from this provider after its failure.",
                "evidence": failure["error"],
            }
        )
    if map_stops:
        for stop in map_stops:
            causes.append(
                {
                    "kind": "maps_stop",
                    "provider": "browser",
                    "impact": f"Maps stopped expanding this query at {stop.get('links_collected', 0)} listing links.",
                    "evidence": stop.get("explanation") or stop.get("reason", "unknown"),
                    "query": stop.get("query", ""),
                    "reason": stop.get("reason", "unknown"),
                }
            )
    if unique_merges:
        causes.append(
            {
                "kind": "deduplication",
                "provider": "quality_controller",
                "impact": f"{len(unique_merges)} unique duplicate merge(s) were recorded.",
                "evidence": "Each merge and matching key is listed in the merge ledger.",
            }
        )
    if unavailable_websites:
        causes.append(
            {
                "kind": "website_enrichment",
                "provider": "website",
                "impact": f"{unavailable_websites} retained lead(s) have no usable website evidence.",
                "evidence": "Exact URL errors are recorded in the search timeline.",
            }
        )
    shortfall = max(0, params["limit"] - len(rows))
    return {
        "requested_maximum": params["limit"],
        "unique_results": len(rows),
        "shortfall": shortfall,
        "conclusion": (
            f"The run found {len(rows)} unique records below the requested ceiling of {params['limit']}. "
            "The causes below are based on recorded provider, scrolling and merge events."
            if shortfall
            else "The requested result ceiling was reached."
        ),
        "provider_records_before_cross_provider_deduplication": provider_records,
        "provider_failures": provider_failures,
        "maps": {
            "planned_queries": len(map_queries),
            "attempted_queries": len(attempted_map_queries),
            "queries": attempted_map_queries,
            "stop_events": map_stops,
        },
        "deduplication": {
            "merged_count": len(unique_merges),
            "merge_ledger": unique_merges,
        },
        "website_evidence_unavailable": unavailable_websites,
        "website_failure_summary": website_failure_summary,
        "causes": causes,
        "limits": [
            "A maximum result setting is a ceiling, not a guarantee.",
            "A normal Maps stop event proves why scrolling stopped, not that no other businesses exist.",
            "Provider counts can overlap before cross-provider deduplication.",
        ],
    }


def run(job, cancel):
    import intelligence

    started = time.monotonic()
    lock = threading.RLock()
    params = job["params"]
    search_plan = job["plan"]
    research_plan = job.setdefault("strategy", strategy(search_plan, params))
    leads = []
    run_events = []

    def persist(**changes):
        with lock:
            job.update(changes)
            job["elapsed"] = round(time.monotonic() - started, 1)
            save(job)

    def emit(provider, level, message, **details):
        event_time = now()
        run_events.append(
            {
                "time": event_time,
                "provider": provider,
                "level": level,
                "message": message,
                "details": details,
            }
        )
        with connection() as conn:
            conn.execute(
                "INSERT INTO events(job_id,created_at,provider,level,message,details) VALUES(?,?,?,?,?,?)",
                (
                    job["id"],
                    event_time,
                    provider,
                    level,
                    message,
                    json.dumps(details, ensure_ascii=False),
                ),
            )
            if provider == "website_fetch" and details.get("url"):
                conn.execute(
                    "INSERT INTO fetch_diagnostics(job_id,company_id,url,fetched_at,fetch_tier,status_code,redirect_chain,elapsed_ms,render_ms,waf_signature,outcome,details) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    (job["id"], str(details.get("company_id", ""))[:80], str(details.get("url", ""))[:1500], event_time, str(details.get("fetch_tier", "http"))[:40], int(details.get("status_code", 0) or 0), json.dumps(details.get("redirect_chain", []), ensure_ascii=False), int(details.get("elapsed_ms", 0) or 0), int(details.get("render_ms", 0) or 0), str(details.get("waf_signature", ""))[:120], str(details.get("outcome", "unknown"))[:120], json.dumps(details, ensure_ascii=False)),
                )
        LOG.info(
            json.dumps(
                {
                    "job": job["id"],
                    "provider": provider,
                    "level": level,
                    "message": message,
                    "details": details,
                },
                ensure_ascii=False,
            )
        )
        if details.get("action_required"):
            persist(message=message, status="waiting")

    def checkpoint(lead):
        with lock:
            leads.append(lead)
            merged = lf.deduplicate(leads)
            persist(
                rows=[asdict(x) for x in merged],
                count=len(merged),
                message=f"{len(merged)} businesses collected",
                status="running",
            )

    def provider(name, fn):
        t = time.monotonic()
        emit(name, "info", "Provider started")
        with lock:
            previous = job["providers"].get(
                name, {"count": 0, "seconds": 0, "failures": 0, "successes": 0}
            )
            job["providers"][name] = {**previous, "status": "running"}
            persist()
        try:
            found = fn()
            with lock:
                # Browser pushes checkpoints as it reads; merge handles repeats.
                leads.extend(found)
                job["providers"][name] = {
                    **previous,
                    "status": "partial" if previous.get("failures") else "complete",
                    "count": previous.get("count", 0) + len(found),
                    "seconds": round(
                        previous.get("seconds", 0) + time.monotonic() - t, 1
                    ),
                    "successes": previous.get("successes", 0) + 1,
                }
                persist(
                    rows=[asdict(x) for x in lf.deduplicate(leads)],
                    count=len(lf.deduplicate(leads)),
                )
            emit(
                name,
                "info",
                "Provider complete",
                count=len(found),
                seconds=round(time.monotonic() - t, 1),
            )
        except Exception as exc:
            with lock:
                job["providers"][name] = {
                    **previous,
                    "status": "partial" if previous.get("successes") else "failed",
                    "count": previous.get("count", 0),
                    "error": str(exc)[:400],
                    "seconds": round(
                        previous.get("seconds", 0) + time.monotonic() - t, 1
                    ),
                    "failures": previous.get("failures", 0) + 1,
                }
            label = {
                "osm": "OpenStreetMap",
                "web": "Web discovery",
                "browser": "Chrome Maps",
                "local_api": "Local Maps API",
                "npi": "US NPI Registry",
                "wikidata": "Wikidata",
            }.get(name, name)
            continuation = " Other configured providers continue independently."
            job["warnings"].append(
                f"{label} failed: {str(exc)[:240]}.{continuation} Collected results are retained."
            )
            persist()
            emit(name, "error", "Provider failed", error=str(exc)[:400])

    try:
        persist(status="running", message="Searching selected sources", progress=8)
        emit(
            "planner",
            "info",
            "Search plan created",
            phrases=search_plan["phrases"],
            locations=params["locations"],
            source=params["source"],
            limit=params["limit"],
        )
        source = params["source"]
        emit(
            "research_strategist",
            "info",
            "Niche terminology and documented sources selected",
            phrases=search_plan["phrases"],
            platforms=[s["domain"] for s in research_plan["platforms"]],
            research_profile=research_plan.get("research_profile"),
        )
        emit(
            "search_planner",
            "info",
            "Geographic query schedule prepared",
            scheduled=len(research_plan["queries"]),
            locations=research_plan["scheduled_locations"],
            unsearched=research_plan["unsearched_locations"],
            budget=research_plan["query_budget"],
        )
        for query in research_plan["queries"]:
            if query["channel"] == "research":
                persist(message="Researching niche-specific platforms", progress=5)
                research_plan["discovered_sources"] = discover_platforms(
                    query["query"], cancel, emit
                )
                persist(strategy=research_plan)
        # Historical references supply geography/provenance only, never fresh contacts or claims.
        reference_lookup = {
            r["website"].rstrip("/").casefold(): r
            for r in reference_library.load().get("records", [])
            if r["id"] in params.get("reference_ids", [])
        }
        # Public website input also supplements discovery mode.
        for raw in params["urls"].splitlines():
            if not raw.strip():
                continue
            try:
                url = public_url(raw.strip())
                reference = reference_lookup.get(url.rstrip("/").casefold(), {})
                reference_city = ", ".join(
                    filter(None, (reference.get("city"), reference.get("state")))
                )
                checkpoint(
                    lf.Lead(
                        name=urlparse_host(url),
                        city=reference_city or params["locations"][0],
                        search_location=reference_city or params["locations"][0],
                        website=url,
                        source="website_input",
                        sources="website_input",
                        source_url=url,
                        reference_id=reference.get("id", ""),
                        reference_as_of=reference.get("as_of", ""),
                    )
                )
            except ValueError as exc:
                emit(
                    "website_input",
                    "warning",
                    "Invalid website skipped",
                    error=str(exc),
                )
        execute_locations = research_plan["scheduled_locations"]
        maps_api_ready = source in ("hybrid", "google") and lf.local_maps_available()
        if source == "hybrid" and not maps_api_ready:
            job["providers"]["local_api"] = {
                "status": "skipped",
                "count": 0,
                "seconds": 0,
                "failures": 0,
                "successes": 0,
                "reason": "The optional local Maps Extractor API is not running on port 8000",
            }
            emit(
                "local_api",
                "info",
                "Optional local Maps API skipped",
                reason="not_running",
                port=8000,
            )
            persist()
        per_location_limit = max(
            1,
            min(
                params["limit"],
                (params["limit"] + len(execute_locations) - 1)
                // max(1, len(execute_locations))
                * 2,
            ),
        )
        for location in execute_locations:
            if cancel.is_set():
                break
            local_plan = {
                **search_plan,
                "web_queries": [
                    q
                    for q in research_plan["queries"]
                    if q["channel"] == "web" and q["location"] == location
                ],
                "map_queries": [
                    q
                    for q in research_plan["queries"]
                    if q["channel"] == "browser" and q["location"] == location
                ],
            }
            tasks = []
            with ThreadPoolExecutor(max_workers=6) as pool:
                if source in ("osm", "hybrid"):
                    tasks.append(
                        pool.submit(
                            provider,
                            "osm",
                            lambda: lf.osm_search(
                                search_plan["category"],
                                location,
                                per_location_limit,
                                emit,
                            ),
                        )
                    )
                if source in ("hybrid", "web") and local_plan["web_queries"]:
                    tasks.append(
                        pool.submit(
                            provider,
                            "web",
                            lambda: web_search(
                                local_plan, location, per_location_limit, cancel, emit
                            ),
                        )
                    )
                if source in ("hybrid", "web"):
                    tasks.append(
                        pool.submit(
                            provider,
                            "wikidata",
                            lambda: public_sources.wikidata_search(
                                local_plan, location, per_location_limit, emit
                            ),
                        )
                    )
                if source == "hybrid" and public_sources.npi_taxonomy(params["niche"]):
                    tasks.append(
                        pool.submit(
                            provider,
                            "npi",
                            lambda: public_sources.npi_search(
                                params["niche"], location, per_location_limit, emit
                            ),
                        )
                    )
                if local_plan["map_queries"] and (
                    source == "browser" or (source == "hybrid" and params["browser"])
                ):
                    tasks.append(
                        pool.submit(
                            provider,
                            "browser",
                            lambda: browser_maps(
                                local_plan,
                                location,
                                per_location_limit,
                                cancel,
                                emit,
                                checkpoint,
                                ROOT / "data" / "chrome-profile",
                            ),
                        )
                    )
                if source == "google" or (source == "hybrid" and maps_api_ready):
                    tasks.append(
                        pool.submit(
                            provider,
                            "local_api",
                            lambda: lf.maps_search(
                                params["niche"], location, per_location_limit
                            ),
                        )
                    )
                for task in as_completed(tasks):
                    task.result()
        discovery_merges = []
        rows = lf.deduplicate(leads, merge_log=discovery_merges)
        if discovery_merges:
            emit(
                "quality_controller",
                "info",
                "Discovery duplicates merged",
                count=len(discovery_merges),
                merges=discovery_merges,
            )
        persist(message="Checking service relevance and public contacts", progress=60)
        client = WebClient()

        def process(lead):
            content = ""
            if params["enrich"] and not cancel.is_set():
                lead, content = enrich(
                    lead,
                    client,
                    cancel,
                    emit,
                    max_pages=5 if params.get("depth") == "deep" else 3,
                )
            repair_generic_name(lead)
            relevance(lead, search_plan, lead.city, content)
            analyze(lead, search_plan, content)
            assess(lead, params.get("research_profile", "general"))
            intelligence.apply_niche_pack(lead, job.get("niche_pack", {}))
            lead.score = lf.score(lead)
            lead.sources = lead.sources or lead.source
            return lead

        # Bound enrichment to output limit, prioritizing service matches.
        for row in rows:
            relevance(row, search_plan, row.city)
            analyze(row, search_plan)
        rows = balanced_select(
            rows,
            min(params["limit"] * 2, 500),
            params.get("prefer_independent", True),
            params.get("target", "both"),
        )
        if not cancel.is_set():
            done = []
            with ThreadPoolExecutor(max_workers=4) as pool:
                future_rows = [pool.submit(process, row) for row in rows]
                for future in as_completed(future_rows):
                    done.append(future.result())
                    persist(
                        rows=[asdict(x) for x in done],
                        count=len(done),
                        progress=60 + int(30 * len(done) / max(1, len(rows))),
                    )
            rows = done
        final_merges = []
        rows = lf.deduplicate(rows, merge_log=final_merges)
        if final_merges:
            emit(
                "quality_controller",
                "info",
                "Post-enrichment duplicates merged",
                count=len(final_merges),
                merges=final_merges,
            )
        for row in rows:
            analyze(row, search_plan)
            assess(row, params.get("research_profile", "general"))
            intelligence.apply_niche_pack(row, job.get("niche_pack", {}))
        rows = balanced_select(
            rows,
            params["limit"],
            params.get("prefer_independent", True),
            params.get("target", "both"),
            prefer_opportunity=params.get("research_profile") == "hood_automation",
        )
        qc = quality_review(rows)
        emit(
            "opportunity_analyst",
            "info",
            "Workflow and offer evidence assessed",
            profile=profile_metadata(params.get("research_profile", "general")),
            assessed=sum(bool(json.loads(r.opportunity).get("coverage")) for r in rows),
            note="Supported points are not predicted conversion or verified budgets. Missing evidence remains unscored.",
        )
        emit(
            "evidence_analyst",
            "info",
            "Facts and assumptions recorded",
            observed_contacts=sum(len(json.loads(r.evidence or "[]")) for r in rows),
            snippet_only=sum(r.source_strength == "search_snippet" for r in rows),
        )
        emit(
            "lead_qualifier",
            "info",
            "Operator types assessed from evidence",
            types={
                kind: sum(r.operator_type == kind for r in rows)
                for kind in (
                    "solo_provider",
                    "independent_business",
                    "chain_or_franchise",
                    "agency",
                    "unknown",
                )
            },
        )
        emit(
            "quality_controller",
            "info",
            "Duplicate and completeness review finished",
            **qc,
        )
        with STORAGE_LOCK:
            store = lf.Store(ROOT / "data" / "leads.db")
            try:
                store.save(rows)
            finally:
                store.close()
        basename = f"{lf.slug(params['niche'])}-{job['id'][:8]}"
        lf.export(rows, ROOT / "leads" / f"{basename}.csv", "csv")
        lf.export(rows, ROOT / "leads" / f"{basename}.json", "json")
        succeeded = any(
            p.get("successes", 0) > 0 for p in job["providers"].values()
        ) or bool(params["urls"].strip())
        failed = any(p.get("failures", 0) > 0 for p in job["providers"].values())
        unavailable_websites = (
            sum(
                r.contact_status in ("unavailable", "no_readable_content") for r in rows
            )
            if params["enrich"]
            else 0
        )
        unavailable_matched_websites = (
            sum(
                r.contact_status in ("unavailable", "no_readable_content")
                and r.match_status != "candidate"
                for r in rows
            )
            if params["enrich"]
            else 0
        )
        status = (
            "cancelled"
            if cancel.is_set()
            else (
                "failed"
                if not succeeded
                else ("partial" if failed or unavailable_websites else "complete")
            )
        )
        diagnostic = ""
        if not rows:
            diagnostic = (
                "No selected source supplied matching businesses. "
                + (
                    "This niche has no dedicated OSM category. Try Chrome Maps, additional phrases, or paste business website URLs. "
                    if not search_plan["osm_mapped"]
                    else "Try another source or a nearby location. "
                )
                + (
                    "Some providers failed; see diagnostics."
                    if failed
                    else "A successful request with zero records does not mean no businesses exist."
                )
            )
        elif len(rows) < params["limit"]:
            diagnostic = f"Returned {len(rows)} unique businesses from available sources; {params['limit']} is a ceiling, not a guaranteed count."
        if unavailable_websites:
            diagnostic += f" {unavailable_websites} retained prospect(s) supplied no usable page evidence, including {unavailable_matched_websites} service/category match(es). See the website failure categories and exact timeline events."
        causes = root_cause_analysis(
            params,
            research_plan,
            job["providers"],
            rows,
            run_events,
            discovery_merges + final_merges,
            unavailable_websites,
        )
        emit(
            "diagnostics",
            "info",
            "Underlying-cause analysis completed",
            shortfall=causes["shortfall"],
            provider_failures=len(causes["provider_failures"]),
            maps_stop_events=len(causes["maps"]["stop_events"]),
            merged_count=causes["deduplication"]["merged_count"],
        )
        persist(
            status=status,
            message=f"{len(rows)} businesses collected"
            if rows
            else "No matching businesses returned",
            progress=100,
            rows=[asdict(x) for x in rows],
            count=len(rows),
            diagnosis=diagnostic,
            export_base=basename,
            quality_report=qc,
            root_cause_analysis=causes,
            stats={
                "phones": sum(bool(x.phone) for x in rows),
                "emails": sum(bool(x.email) for x in rows),
                "websites": sum(bool(x.website) for x in rows),
                "matches": sum(x.match_status != "candidate" for x in rows),
                "individuals": sum(x.operator_type == "solo_provider" for x in rows),
                "independents": sum(
                    x.operator_type in ("solo_provider", "independent_business")
                    for x in rows
                ),
                "profiles": sum(bool(x.profile_url) for x in rows),
            },
        )
        emit(
            "job",
            "info",
            "Search finished",
            status=status,
            count=len(rows),
            seconds=job["elapsed"],
        )
    except Exception as exc:
        persist(
            status="failed",
            message=str(exc),
            rows=[asdict(x) for x in lf.deduplicate(leads)],
            count=len(lf.deduplicate(leads)),
            progress=100,
        )
        emit("job", "error", "Search failed; checkpoints retained", error=str(exc))
    finally:
        with ACTIVE_LOCK:
            EVENTS.pop(job["id"], None)


def urlparse_host(url):
    from urllib.parse import urlparse

    return urlparse(url).hostname or url


def download(job_id, kind):
    job = get_job(job_id)
    if not job:
        return None
    if kind == "log":
        return (
            json.dumps(job, ensure_ascii=False, indent=2).encode(),
            "application/json",
            f"{job_id[:8]}-diagnostics.json",
        )
    if kind == "json":
        return (
            json.dumps(job["rows"], ensure_ascii=False, indent=2).encode(),
            "application/json",
            f"{job_id[:8]}-leads.json",
        )
    if kind == "csv":
        rows = job["rows"]
        names = list(asdict(lf.Lead()))
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=names, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    k: (
                        "'" + str(v)
                        if str(v).lstrip().startswith(("=", "+", "-", "@"))
                        else v
                    )
                    for k, v in row.items()
                }
            )
        return (
            ("\ufeff" + stream.getvalue()).encode(),
            "text/csv",
            f"{job_id[:8]}-leads.csv",
        )
    return None
