"""Durable second-round public verification for saved prospects."""

from __future__ import annotations

import json
import re
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote, urlparse

import engine
import leadfinder as lf
import browser_session
import organizer
import intelligence
from contacts import WebClient, dns_txt_status, mail_domain_status, now

TASK_LOCK = threading.Lock()
SAVE_LOCK = threading.RLock()
EVENTS: dict[str, threading.Event] = {}


def _event(job_id, level, message, **details):
    with engine.connection() as conn:
        conn.execute(
            "INSERT INTO events(job_id,created_at,provider,level,message,details) VALUES(?,?,?,?,?,?)",
            (job_id, now(), "verification", level, message, json.dumps(details, ensure_ascii=False)),
        )


def _save(task):
    with engine.connection() as conn:
        conn.execute(
            "INSERT INTO verification_tasks(id,created_at,updated_at,status,payload) VALUES(?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET updated_at=excluded.updated_at,status=excluded.status,payload=excluded.payload",
            (task["id"], task["created_at"], now(), task["status"], json.dumps(task, ensure_ascii=False)),
        )


def init(recover=True):
    with engine.connection() as conn:
        if recover:
            for task_id, payload in conn.execute(
                "SELECT id,payload FROM verification_tasks WHERE status IN ('queued','running')"
            ).fetchall():
                task = json.loads(payload)
                task.update(status="interrupted", message="The app restarted; completed lead checks remain saved.")
                conn.execute(
                    "UPDATE verification_tasks SET status=?,updated_at=?,payload=? WHERE id=?",
                    (task["status"], now(), json.dumps(task), task_id),
                )


def get_task(task_id):
    if not isinstance(task_id, str) or not re.fullmatch(r"[a-f0-9]{32}", task_id):
        return None
    with engine.connection() as conn:
        row = conn.execute("SELECT payload FROM verification_tasks WHERE id=?", (task_id,)).fetchone()
    return json.loads(row[0]) if row else None


def cancel_task(task_id):
    with TASK_LOCK:
        event = EVENTS.get(task_id)
        if event:
            event.set()
    return bool(event)


def _settings(params):
    if not isinstance(params, dict):
        raise ValueError("Choose valid verification settings")
    job_id = params.get("job_id", "")
    if not isinstance(job_id, str) or not re.fullmatch(r"[a-f0-9]{32}", job_id):
        raise ValueError("Open a finished saved search first")
    scope = params.get("scope", "matches")
    if scope not in ("matches", "all", "unfinished"):
        raise ValueError("Choose confirmed matches, all candidates, or unfinished leads")
    saved = engine.get_job(job_id, events=False)
    if not saved or saved.get("status") in ("queued", "running", "waiting"):
        raise ValueError("Wait for the search to finish before verification")
    return {"job_id": job_id, "scope": scope}


def start(params):
    settings = _settings(params)
    with TASK_LOCK:
        if EVENTS:
            raise ValueError("A verification round is already running")
        task_id = uuid.uuid4().hex
        cancel = threading.Event()
        EVENTS[task_id] = cancel
    task = {
        "id": task_id,
        "created_at": now(),
        "status": "queued",
        "message": "Preparing second-round verification",
        "progress": 0,
        "params": settings,
        "checked": 0,
        "total": 0,
        "summary": {},
    }
    _save(task)
    threading.Thread(target=_run, args=(task, cancel), daemon=True).start()
    return task_id


def _review_sources(name, location):
    try:
        from ddgs import DDGS

        results = DDGS(timeout=12).text(
            f'"{name}" "{location}" reviews Yelp', max_results=6, backend="auto"
        )
    except Exception:
        return []
    allowed = ["yelp.com", "bbb.org", "angi.com", "houzz.com"]
    if browser_session.enabled_services()["facebook"]:
        allowed.append("facebook.com")
    output = []
    for item in results:
        url = item.get("href", "")
        host = (urlparse(url).hostname or "").removeprefix("www.")
        if not any(host == domain or host.endswith("." + domain) for domain in allowed):
            continue
        output.append(
            {
                "source": host,
                "url": url[:1500],
                "title": str(item.get("title", ""))[:180],
                "snippet": str(item.get("body", ""))[:350],
                "basis": "search_result_snippet_unverified",
            }
        )
        if len(output) >= 4:
            break
    return output


def _market_signals(name, location):
    """Find bounded public hiring/company signals without treating them as new leads."""
    direct = {
        "meta_ad_library": "https://www.facebook.com/ads/library/?active_status=all&ad_type=all&country=US&q=" + quote(name) + "&search_type=keyword_unordered",
        "google_ads_transparency": "https://adstransparency.google.com/?region=US&query=" + quote(name),
    }
    try:
        from ddgs import DDGS

        results = DDGS(timeout=12).text(
            f'"{name}" {location} hiring company Indeed Wellfound RemoteOK',
            max_results=8,
            backend="auto",
        )
    except Exception as exc:
        return {"status": "search_unavailable", "candidates": [], "direct_checks": direct, "error": str(exc)[:220]}
    kinds = {
        "indeed.com": "hiring_signal",
        "remoteok.com": "remote_hiring_signal",
        "wellfound.com": "startup_or_hiring_signal",
        "clutch.co": "agency_profile",
        "goodfirms.co": "agency_profile",
        "ycombinator.com": "startup_profile",
        "producthunt.com": "product_profile",
        "betalist.com": "startup_profile",
    }
    name_words = {word for word in re.findall(r"[a-z0-9]{3,}", name.casefold()) if word not in {"the", "and", "llc", "inc", "company"}}
    candidates = []
    for item in results:
        url = str(item.get("href", ""))
        host = (urlparse(url).hostname or "").casefold().removeprefix("www.")
        domain = next((domain for domain in kinds if host == domain or host.endswith("." + domain)), "")
        if not domain:
            continue
        text = " ".join((str(item.get("title", "")), str(item.get("body", "")))).casefold()
        overlap = sorted(word for word in name_words if word in text)
        if name_words and not overlap:
            continue
        candidates.append({
            "platform": domain,
            "kind": kinds[domain],
            "url": url[:1500],
            "title": str(item.get("title", ""))[:180],
            "snippet": str(item.get("body", ""))[:350],
            "matched_name_terms": overlap,
            "basis": "search_result_snippet_unverified",
        })
        if len(candidates) >= 6:
            break
    return {"status": "complete", "candidates": candidates, "direct_checks": direct}


def _verify(index, row, cancel):
    checked_at = now()
    website = row.get("website", "")
    website_result = {
        "url": website,
        "status": "not_listed" if not website else "unavailable",
        "checked_at": checked_at,
        "final_url": "",
        "error": "",
        "resolver": "system_dns_with_secure_fallback",
    }
    socials = {
        key: {"url": row.get(key, ""), "status": "listed_not_opened" if row.get(key) else "not_found"}
        for key in ("facebook", "instagram", "linkedin")
    }
    if not browser_session.enabled_services()["facebook"]:
        socials["facebook"] = {"url": "", "status": "user_disabled"}
    tracking = []
    landing_parameters = []
    technographics = {"headers": {}, "cookie_names": [], "dns": {}, "robots": "not_checked", "sitemap": "not_checked", "fetch": {}}
    website_audit = {
        "status": "not_checked" if website else "not_listed",
        "url": website,
        "contact_form": "unknown",
        "booking_path": "unknown",
        "mobile_viewport": "unknown",
        "structured_data": "unknown",
        "analytics": "unknown",
        "accessibility_image_alt": "unknown",
        "broken_contact_links": False,
        "basis": "public_html_observation",
    }
    if website and not cancel.is_set():
        try:
            client = WebClient()
            if hasattr(client, "get_with_diagnostics"):
                fetch = client.get_with_diagnostics(website)
                body, final_url = fetch["body"], fetch["final_url"]
                technographics.update(headers=fetch.get("headers", {}), cookie_names=fetch.get("cookie_names", []), fetch={key: fetch.get(key) for key in ("fetch_tier", "status_code", "redirect_chain", "elapsed_ms", "render_ms", "waf_signature", "outcome", "escalated_from") if fetch.get(key) not in (None, "", [])})
            else:
                body, final_url = client.get(website)
            website_result.update(status="reachable", final_url=final_url)
            patterns = {
                "meta_pixel": r"connect\.facebook\.net|\bfbq\s*\(",
                "google_ads_tag": r"googleadservices\.com|\bAW-\d+|googleads\.g\.doubleclick\.net",
                "google_analytics": r"googletagmanager\.com|google-analytics\.com",
                "linkedin_insight_tag": r"snap\.licdn\.com|linkedin\.com/insight",
            }
            for name, pattern in patterns.items():
                if re.search(pattern, body, re.I):
                    tracking.append({"signal": name, "source_url": final_url, "basis": "website_source_pattern"})
            landing_parameters = sorted(set(re.findall(r"[?&](utm_(?:source|medium|campaign)|gclid|fbclid)=", body, re.I)))
            images = re.findall(r"<img\b[^>]*>", body, re.I)
            images_without_alt = sum(not re.search(r"\balt\s*=", tag, re.I) for tag in images)
            website_audit.update(
                status="reachable",
                url=final_url,
                contact_form=bool(re.search(r"<form\b[\s\S]{0,5000}(?:contact|email|phone|message|quote)", body, re.I)),
                booking_path=bool(re.search(r"(?:book|schedule|request\s+(?:a\s+)?(?:quote|estimate)|get\s+(?:a\s+)?quote)", body, re.I)),
                mobile_viewport=bool(re.search(r'<meta[^>]+name=["\']viewport["\']', body, re.I)),
                structured_data=bool(re.search(r"application/ld\+json|schema\.org", body, re.I)),
                analytics=bool(tracking),
                accessibility_image_alt=(
                    {"images": len(images), "missing_alt": images_without_alt}
                    if images
                    else {"images": 0, "missing_alt": 0}
                ),
                broken_contact_links=bool(re.search(r'<a[^>]+href=["\'](?:#|javascript:void\(0\)|)["\'][^>]*>[^<]*(?:contact|quote|book)', body, re.I)),
                html_bytes=len(body.encode("utf-8", errors="ignore")),
            )
            domain = (urlparse(final_url).hostname or "").removeprefix("www.")
            technographics["dns"] = dns_txt_status(domain)
            origin = f"{urlparse(final_url).scheme}://{urlparse(final_url).netloc}"
            for key, path in (("robots", "/robots.txt"), ("sitemap", "/sitemap.xml")):
                try:
                    metadata_body, _ = client.get(origin + path)
                    technographics[key] = {"status": "observed", "bytes": len(metadata_body.encode("utf-8", errors="ignore")), "url": origin + path}
                except Exception as exc:
                    technographics[key] = {"status": "unavailable", "error": str(exc)[:160], "url": origin + path}
            for social, domain in (("facebook", "facebook.com"), ("instagram", "instagram.com"), ("linkedin", "linkedin.com")):
                if social == "facebook" and not browser_session.enabled_services()["facebook"]:
                    continue
                if socials[social]["url"]:
                    continue
                match = re.search(r'https?://(?:www\.)?' + re.escape(domain) + r'/[^"\'<>\s]+', body, re.I)
                if match:
                    socials[social] = {"url": match.group(0)[:1500], "status": "published_on_website"}
        except Exception as exc:
            website_result["error"] = str(exc)[:300]
            if "Temporary DNS failure" in str(exc):
                website_result["status"] = "temporary_dns_failure"
            elif "robots" in str(exc):
                website_result["status"] = "robots_blocked"
            website_audit.update(status=website_result["status"], error=str(exc)[:300])
    location = row.get("search_location") or row.get("city", "")
    review_sources = [] if cancel.is_set() else _review_sources(row.get("name", ""), location)
    market_signals = (
        {"status": "cancelled", "candidates": [], "direct_checks": {}}
        if cancel.is_set()
        else _market_signals(row.get("name", ""), location)
    )
    social_discovery = (
        {"status": "cancelled", "query": "", "candidates": []}
        if cancel.is_set()
        else browser_session.search_company_sources(row.get("name", ""), location, cancel)
    )
    for candidate in social_discovery.get("candidates", []):
        social_key = {"linkedin_company": "linkedin", "instagram": "instagram", "facebook": "facebook"}.get(candidate.get("kind"))
        if social_key and not socials.get(social_key, {}).get("url") and float(candidate.get("confidence", 0)) >= 0.7:
            socials[social_key] = {
                "url": candidate.get("url", ""),
                "status": "chrome_search_candidate_unverified",
                "confidence": candidate.get("confidence", 0),
                "query": candidate.get("query", ""),
                "title": candidate.get("title", ""),
            }
    maps_review = {
        "rating": row.get("rating", ""),
        "review_count": row.get("reviews", ""),
        "url": row.get("source_url", ""),
        "basis": "google_maps_listing",
    }
    ads_status = "tracking_detected_not_campaign_verified" if tracking else "campaign_status_not_verified"
    email_values = []
    for value in (row.get("email", ""), row.get("emails", "")):
        email_values.extend(lf.EMAIL_RE.findall(str(value)))
    try:
        evidence_items = json.loads(row.get("evidence") or "[]")
    except (TypeError, ValueError):
        evidence_items = []
    for item in evidence_items if isinstance(evidence_items, list) else []:
        if isinstance(item, dict) and item.get("field") == "email":
            email_values.extend(lf.EMAIL_RE.findall(str(item.get("value", ""))))
    email_values = list(dict.fromkeys(value.casefold() for value in email_values))[:10]
    email_checks = []
    for address in email_values:
        domain = address.rsplit("@", 1)[-1]
        check = mail_domain_status(domain) if not cancel.is_set() else {"status": "not_checked", "mx": [], "basis": "cancelled"}
        email_checks.append({"email": address, "domain": domain, **check})
    email = str(row.get("email", "")).strip().casefold()
    email_domain = next((item for item in email_checks if item["email"] == email), {"status": "not_checked", "mx": [], "basis": "no_email"})
    verification = {
        "status": "complete",
        "checked_at": checked_at,
        "website": website_result,
        "socials": socials,
        "social_discovery": social_discovery,
        "ads": {
            "status": ads_status,
            "tracking_signals": tracking,
            "landing_parameter_signals": landing_parameters if website_result.get("status") == "reachable" else [],
            "active_campaign_status": "not_corroborated",
            "note": "Tracking code can support advertising but does not prove an active campaign. No signal does not prove no ads.",
            "meta_ad_library": market_signals.get("direct_checks", {}).get("meta_ad_library", ""),
            "google_ads_transparency": market_signals.get("direct_checks", {}).get("google_ads_transparency", ""),
        },
        "market_signals": market_signals,
        "reviews": {"google_maps": maps_review, "other_sources": review_sources},
        "website_audit": website_audit,
        "technographics": technographics,
        "email_domain": email_domain,
        "email_candidates": email_checks,
        "ai": {"status": "available_on_demand", "note": "Use Details + local AI to interpret saved evidence; AI does not verify websites or ads."},
    }
    return index, verification


def _run(task, cancel):
    try:
        task.update(status="running", message="Checking public websites, social links, ad signals and review sources")
        _save(task)
        saved = engine.get_job(task["params"]["job_id"], events=False)
        rows = saved.get("rows", [])
        restored_contacts = intelligence.restore_remembered_contacts(rows)
        if restored_contacts:
            saved["rows"] = rows
            engine.save(saved)
        def needs_verification(row):
            try:
                report = json.loads(row.get("verification") or "{}")
            except (TypeError, ValueError):
                return True
            discovery_status = str(report.get("social_discovery", {}).get("status", ""))
            return report.get("status") != "complete" or not discovery_status or discovery_status in {"cancelled", "failed", "not_run"}

        scope = task["params"]["scope"]
        selected = [
            (index, row)
            for index, row in enumerate(rows)
            if scope == "all"
            or (scope == "matches" and row.get("match_status") != "candidate")
            or (scope == "unfinished" and needs_verification(row))
        ]
        task["total"] = len(selected)
        task["scope_count"] = len(selected)
        task["retained_count"] = len(rows)
        _event(task["params"]["job_id"], "info", "Verification scope resolved", scope=task["params"]["scope"], selected=len(selected), retained=len(rows))
        _save(task)
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = [pool.submit(_verify, index, row, cancel) for index, row in selected]
            for future in as_completed(futures):
                if cancel.is_set():
                    break
                index, result = future.result()
                with engine.STORAGE_LOCK, SAVE_LOCK:
                    latest = engine.get_job(task["params"]["job_id"], events=False)
                    latest["rows"][index]["verification"] = json.dumps(result, ensure_ascii=False)
                    engine.save(latest)
                task["checked"] += 1
                task["progress"] = int(100 * task["checked"] / max(1, task["total"]))
                task["message"] = f"Verified {task['checked']} of {task['total']} prospects"
                _save(task)
        latest = engine.get_job(task["params"]["job_id"], events=False)
        organized_rows, organization = organizer.organize_rows(latest.get("rows", []), cancel)
        latest["rows"] = organized_rows
        latest["count"] = len(organized_rows)
        latest["organization"] = organization
        latest["intelligence_summary"] = intelligence.compile_job(latest)
        latest.setdefault("stats", {})["emails"] = sum(bool(row.get("email")) for row in organized_rows)
        engine.save(latest)
        if organization.get("ai_error"):
            _event(task["params"]["job_id"], "warning", "Email classification AI unavailable", error=organization["ai_error"])
        reports = [json.loads(row.get("verification") or "{}") for row in latest.get("rows", [])]
        complete = [report for report in reports if report.get("status") == "complete"]
        task["summary"] = {
            "verified": len(complete),
            "websites_reachable": sum(r.get("website", {}).get("status") == "reachable" for r in complete),
            "social_profiles_listed": sum(any(v.get("url") for v in r.get("socials", {}).values()) for r in complete),
            "ad_tracking_signals": sum(bool(r.get("ads", {}).get("tracking_signals")) for r in complete),
            "review_sources_found": sum(bool(r.get("reviews", {}).get("other_sources")) for r in complete),
            "duplicates_consolidated": organization["duplicates_consolidated"],
            "recommended_email_records": organization["recommended_email_records"],
            "email_ai_status": organization["ai_status"],
            "contacts_restored_from_memory": restored_contacts,
            "chrome_social_searches": sum(bool(r.get("social_discovery", {}).get("query")) for r in complete),
            "chrome_social_candidates": sum(len(r.get("social_discovery", {}).get("candidates", [])) for r in complete),
            "chrome_manual_checkpoints": sum(str(r.get("social_discovery", {}).get("status", "")).startswith("manual_checkpoint") for r in complete),
            "market_signal_candidates": sum(len(r.get("market_signals", {}).get("candidates", [])) for r in complete),
        }
        task.update(
            status="cancelled" if cancel.is_set() else "complete",
            progress=100 if not cancel.is_set() else task["progress"],
            message="Verification stopped; completed checks were retained" if cancel.is_set() else f"Verification complete · {organization['duplicates_consolidated']} duplicates consolidated · {organization['recommended_email_records']} recommended email records",
        )
    except Exception as exc:
        task.update(status="failed", message=str(exc)[:400])
        _event(task.get("params", {}).get("job_id", ""), "warning", "Verification task failed", error=str(exc)[:500])
    finally:
        _save(task)
        with TASK_LOCK:
            EVENTS.pop(task["id"], None)
