"""Resumable, browser-assisted LinkedIn company employee discovery."""

from __future__ import annotations

import threading
import re
import json
from datetime import datetime
from urllib.parse import quote_plus

import browser_session
import connections
import engine


LOCK = threading.Lock()
EVENTS: dict[str, threading.Event] = {}

ROLE_GROUPS = (
    ("executive_leadership", r"\b(?:founder|owner|chief|ceo|coo|cfo|cto|president|managing director|general manager|partner)\b"),
    ("recruitment_talent", r"\b(?:recruit|talent acquisition|staffing|headhunt|sourc(?:e|er|ing))\b"),
    ("human_resources", r"\b(?:human resources|people operations|people partner|hrbp|hr manager|hr executive|hr specialist)\b"),
    ("operations", r"\b(?:operations?|workforce management|wfm|delivery manager|project manager|program manager)\b"),
    ("sales_business_development", r"\b(?:sales|business development|account management|account manager|commercial|client partner)\b"),
    ("marketing_growth", r"\b(?:marketing|growth|brand|communications?|public relations)\b"),
    ("finance", r"\b(?:finance|financial|accountant|accounting|payroll|audit|treasury)\b"),
    ("education_student", r"\b(?:student|university|college|school|graduate|undergraduate)\b"),
    ("technology_product_data", r"\b(?:technology|software|engineer|developer|product|data|analytics|information technology|\bit\b)\b"),
    ("customer_success_support", r"\b(?:customer success|customer service|customer support|client success|technical support)\b"),
    ("legal_compliance", r"\b(?:legal|counsel|compliance|risk|governance)\b"),
    ("administration", r"\b(?:administrator|administration|office manager|coordinator|executive assistant|secretary)\b"),
    ("consulting", r"\b(?:consultant|consulting|advisor|advisory)\b"),
)

TITLE_WORDS = re.compile(
    r"\b(?:founder|owner|chief|ceo|coo|cfo|cto|president|director|head|vice president|vp|partner|manager|lead|recruiter|recruitment|talent|human resources|hrbp|specialist|consultant|advisor|executive|officer|analyst|coordinator|administrator|assistant|engineer|developer|designer|sales|marketing|operations|customer|finance|accountant|legal|compliance|product|data|intern|student)\b",
    re.I,
)


def _classify_profile(profile: dict) -> dict:
    """Add evidence-derived title and role tags without asking AI to guess."""
    headline = re.sub(r"\s+", " ", str(profile.get("headline") or "")).strip()[:300]
    parts = [part.strip(" -–—") for part in re.split(r"\s*\|\s*", headline) if part.strip()]
    title = next((part for part in parts if TITLE_WORDS.search(part)), "")
    if title:
        at_split = re.split(r"\s+(?:at|@)\s+", title, maxsplit=1, flags=re.I)
        if at_split and TITLE_WORDS.search(at_split[0]):
            title = at_split[0]
    title = title[:160]
    matched_groups = [
        group for group, pattern in ROLE_GROUPS if re.search(pattern, headline, re.I)
    ]
    role_group = matched_groups[0] if matched_groups else "other"
    if re.search(r"\b(?:founder|owner)\b", headline, re.I):
        seniority = "owner_founder"
    elif re.search(r"\b(?:chief|ceo|coo|cfo|cto|president)\b", headline, re.I):
        seniority = "c_suite"
    elif re.search(r"\b(?:vice president|\bvp\b)\b", headline, re.I):
        seniority = "vice_president"
    elif re.search(r"\b(?:director|head)\b", headline, re.I):
        seniority = "director_head"
    elif re.search(r"\b(?:manager|lead)\b", headline, re.I):
        seniority = "manager_lead"
    elif role_group == "education_student":
        seniority = "student_or_education"
    elif headline:
        seniority = "individual_contributor"
    else:
        seniority = "unknown"
    if seniority in {"owner_founder", "c_suite", "vice_president", "director_head"}:
        priority = "high"
    elif seniority == "manager_lead" or role_group in {
        "recruitment_talent",
        "human_resources",
        "operations",
        "sales_business_development",
    }:
        priority = "medium"
    else:
        priority = "low"
    tags = [role_group, seniority]
    tags.extend(group for group in matched_groups[1:] if group not in tags)
    if priority == "high":
        tags.append("decision_maker")
    return {
        **profile,
        "headline": headline,
        "title": title,
        "role_group": role_group,
        "seniority": seniority,
        "outreach_priority": priority,
        "role_tags": tags,
        "title_status": "observed" if title else "headline_only" if headline else "unavailable",
    }


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _save(job: dict, task: dict, employees: list[dict]) -> None:
    job["employee_discovery"] = task
    job["employees"] = employees[:5000]
    engine.save(job)


def init(recover: bool = True) -> None:
    if not recover:
        return
    with engine.connection() as conn:
        rows = conn.execute("SELECT id,payload FROM jobs ORDER BY updated_at DESC LIMIT 250").fetchall()
    for job_id, payload in rows:
        try:
            import json

            job = json.loads(payload)
        except Exception:
            continue
        task = job.get("employee_discovery")
        if isinstance(task, dict) and task.get("status") in {"queued", "running"}:
            task.update(
                status="interrupted",
                message="Employee discovery was interrupted by an app restart. Continue to resume from the saved company.",
                updated_at=_now(),
            )
            _save(job, task, job.get("employees", []))


def get(job_id: str) -> dict:
    job = engine.get_job(job_id, events=False)
    if not job:
        raise ValueError("Search not found")
    task = job.get("employee_discovery")
    employees = [
        _classify_profile(row)
        for row in job.get("employees", [])
        if isinstance(row, dict)
    ]
    if not isinstance(task, dict):
        return {
            "job_id": job_id,
            "status": "not_started",
            "progress": 0,
            "companies_checked": 0,
            "companies_total": sum(bool(row.get("website") or row.get("linkedin")) for row in job.get("rows", [])),
            "profiles_found": len(employees),
            "message": "Ready after company websites or LinkedIn company URLs have been verified.",
            "employees": employees[:50],
        }
    return {
        **task,
        "profiles_found": len(employees),
        "titles_found": sum(bool(row.get("title")) for row in employees),
        "tagged_profiles": sum(bool(row.get("role_tags")) for row in employees),
        "employees": employees[:50],
    }


def _settings(job: dict, params: dict) -> tuple[list[dict], int]:
    if job.get("status") in {"queued", "running", "waiting", "pause_requested"}:
        raise ValueError("Wait for business discovery to finish")
    company_limit = max(1, min(int(params.get("company_limit", 25) or 25), 100))
    per_company = max(1, min(int(params.get("per_company", 25) or 25), 100))
    companies = []
    seen = set()
    for row_index, row in enumerate(job.get("rows", [])):
        url = browser_session._canonical_linkedin_company_url(row.get("linkedin", ""))
        website = str(row.get("website", "")).strip()
        identity = url or website
        if not identity or identity in seen:
            continue
        seen.add(identity)
        companies.append({
            "name": str(row.get("name", ""))[:180],
            "linkedin": url,
            "website": website[:1500],
            "city": str(row.get("city") or row.get("search_location") or "")[:160],
            "row_index": row_index,
        })
        if len(companies) >= company_limit:
            break
    if not companies:
        raise ValueError("No company website or verified LinkedIn company URL is available yet.")
    return companies, per_company


def start(params: dict) -> str:
    job_id = str(params.get("job_id", ""))
    job = engine.get_job(job_id, events=False)
    if not job:
        raise ValueError("Open a saved search first")
    companies, per_company = _settings(job, params)
    with LOCK:
        if EVENTS:
            raise ValueError("Another employee discovery task is already running")
        cancel = threading.Event()
        EVENTS[job_id] = cancel
    task = {
        "job_id": job_id,
        "status": "queued",
        "created_at": _now(),
        "updated_at": _now(),
        "message": "Preparing website-sourced decision-maker review tasks",
        "progress": 0,
        "companies": companies,
        "companies_total": len(companies),
        "companies_checked": 0,
        "next_company_index": 0,
        "per_company": per_company,
        "sheet_status": "pending",
        "sheet_url": "",
        "sheet_worksheet": "",
        "failures": [],
    }
    existing = [
        _classify_profile(row)
        for row in job.get("employees", [])
        if isinstance(row, dict)
    ]
    _save(job, task, existing)
    threading.Thread(target=_run, args=(job_id, cancel), daemon=True).start()
    return job_id


def resume(job_id: str) -> str:
    job = engine.get_job(job_id, events=False)
    task = job.get("employee_discovery") if job else None
    if not isinstance(task, dict) or task.get("status") not in {"waiting", "interrupted", "failed"}:
        raise ValueError("This employee discovery task is not waiting to resume")
    with LOCK:
        if EVENTS:
            raise ValueError("Another employee discovery task is already running")
        cancel = threading.Event()
        EVENTS[job_id] = cancel
    task.update(status="queued", message="Resuming from the saved company", updated_at=_now())
    _save(job, task, job.get("employees", []))
    threading.Thread(target=_run, args=(job_id, cancel), daemon=True).start()
    return job_id


def cancel(job_id: str) -> bool:
    with LOCK:
        event = EVENTS.get(job_id)
        if event:
            event.set()
    return bool(event)


def _sync(job: dict, task: dict) -> None:
    google = next((item for item in connections.statuses().get("providers", []) if item.get("id") == "google_sheets"), {})
    if not google.get("connected"):
        task.update(sheet_status="not_connected", sheet_error="Connect Google Sheets to create the employee worksheet")
        return
    try:
        result = connections.sync_employee_sheet(job)
        task.update(
            sheet_status="synced",
            sheet_url=result.get("url", ""),
            sheet_worksheet=(result.get("worksheets") or [""])[0],
            sheet_error="",
        )
    except Exception as exc:
        task.update(sheet_status="error", sheet_error=str(exc)[:300])


def _normalized_role(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(value or "").casefold()))


def _matching_niche_role(role: str, configured_roles: list[str] | None) -> str:
    """Return the configured niche role supported by a published role, if any."""
    observed = _normalized_role(role)
    if not observed:
        return ""
    roles = [str(item).strip() for item in (configured_roles or []) if str(item).strip()]
    if not roles:
        return observed
    for configured in roles:
        expected = _normalized_role(configured)
        if expected and re.search(rf"\b{re.escape(expected)}\b", observed):
            return configured
    return ""


def _website_people(
    row: dict,
    company: dict,
    configured_roles: list[str] | None = None,
) -> list[dict]:
    try:
        evidence = json.loads(row.get("evidence") or "[]")
    except (ValueError, TypeError):
        evidence = []
    people = {}
    for item in evidence if isinstance(evidence, list) else []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("contact_name") or "").strip()
        role = str(item.get("contact_role") or "").strip()
        if not (name and role):
            continue
        matched_role = _matching_niche_role(role, configured_roles)
        if not matched_role:
            continue
        key = (name.casefold(), role.casefold())
        people[key] = {
            "employee_name": name[:180],
            "headline": role[:300],
            "title": role[:160],
            "company_name": company.get("name", ""),
            "company_linkedin": company.get("linkedin", ""),
            "company_website": company.get("website", ""),
            "source_url": str(item.get("url") or company.get("website") or "")[:1500],
            "source_excerpt": str(item.get("excerpt") or "")[:500],
            "observed_at": str(item.get("observed_at") or _now()),
            "basis": "name_and_role_published_together_on_company_website",
            "manual_review_required": True,
            "niche_role_match": True,
            "configured_role": matched_role,
        }
    if row.get("decision_maker") and row.get("decision_maker_role"):
        matched_role = _matching_niche_role(row["decision_maker_role"], configured_roles)
        if matched_role:
            key = (str(row["decision_maker"]).casefold(), str(row["decision_maker_role"]).casefold())
            people.setdefault(key, {
                "employee_name": str(row["decision_maker"])[:180],
                "headline": str(row["decision_maker_role"])[:300],
                "title": str(row["decision_maker_role"])[:160],
                "company_name": company.get("name", ""),
                "company_linkedin": company.get("linkedin", ""),
                "company_website": company.get("website", ""),
                "source_url": company.get("website", ""),
                "source_excerpt": "Published name and role retained from the company website.",
                "observed_at": row.get("checked_at") or _now(),
                "basis": "published_company_website_role",
                "manual_review_required": True,
                "niche_role_match": True,
                "configured_role": matched_role,
            })
    result = []
    for person in people.values():
        query = " ".join(filter(None, [person.get("employee_name"), company.get("name"), company.get("city")]))
        person["manual_search_url"] = "https://www.linkedin.com/search/results/people/?keywords=" + quote_plus(query)
        result.append(_classify_profile(person))
    if not result:
        query = " ".join(filter(None, [company.get("name"), company.get("city"), "owner OR manager OR director"]))
        result.append(_classify_profile({
            "employee_name": "Decision maker review",
            "headline": "Use LinkedIn Current company and Locations filters",
            "company_name": company.get("name", ""),
            "company_linkedin": company.get("linkedin", ""),
            "company_website": company.get("website", ""),
            "manual_search_url": "https://www.linkedin.com/search/results/people/?keywords=" + quote_plus(query),
            "basis": "manual_linkedin_review_no_published_company_bio",
            "manual_review_required": True,
            "observed_at": _now(),
        }))
    return result


def _run(job_id: str, cancel: threading.Event) -> None:
    try:
        job = engine.get_job(job_id, events=False)
        task = job["employee_discovery"]
        employees = [
            _classify_profile(row)
            for row in job.get("employees", [])
            if isinstance(row, dict)
        ]
        employee_indexes = {
            (row.get("company_name", "").casefold(), row.get("employee_name", "").casefold()): index
            for index, row in enumerate(employees)
        }
        task.update(status="running", message="Building a manual LinkedIn review queue from company website evidence", updated_at=_now())
        _save(job, task, employees)
        companies = task.get("companies", [])
        configured_roles = (job.get("niche_pack") or {}).get("decision_maker_roles", [])
        for index in range(int(task.get("next_company_index", 0)), len(companies)):
            if cancel.is_set():
                task.update(status="cancelled", message="Review-queue preparation stopped; retained tasks were saved")
                break
            company = companies[index]
            row_index = int(company.get("row_index", -1))
            source_row = job.get("rows", [])[row_index] if 0 <= row_index < len(job.get("rows", [])) else {}
            for profile in _website_people(
                source_row,
                company,
                configured_roles,
            )[: int(task.get("per_company", 25))]:
                key = (str(profile.get("company_name", "")).casefold(), str(profile.get("employee_name", "")).casefold())
                existing_index = employee_indexes.get(key)
                if existing_index is None:
                    employee_indexes[key] = len(employees)
                    employees.append(profile)
                    continue
                existing = employees[existing_index]
                merged = {
                    **existing,
                    **{
                        key: value
                        for key, value in profile.items()
                        if value not in (None, "", [])
                    },
                }
                employees[existing_index] = _classify_profile(merged)
            task.update(
                companies_checked=index + 1,
                next_company_index=index + 1,
                progress=int(100 * (index + 1) / max(1, len(companies))),
                message=(
                    f"Prepared {index + 1} of {len(companies)} company reviews · "
                    f"{len(employees)} decision-maker tasks · "
                    f"{sum(bool(row.get('title')) for row in employees)} published roles"
                ),
                updated_at=_now(),
            )
            _save(job, task, employees)
            if len(employees) >= 5000:
                task.update(
                    status="complete",
                    progress=100,
                    message="Employee discovery reached the 5,000-profile safety limit",
                    updated_at=_now(),
                )
                _save(job, task, employees)
                break
        else:
            task.update(
                status="complete",
                progress=100,
                message=(
                    f"Review queue complete · {len(employees)} decision-maker tasks · "
                    f"{sum(bool(row.get('title')) for row in employees)} published roles"
                ),
                updated_at=_now(),
            )
        _sync(job, task)
        _save(job, task, employees)
    except Exception as exc:
        job = engine.get_job(job_id, events=False) or {"id": job_id}
        task = job.get("employee_discovery", {"job_id": job_id})
        task.update(status="failed", message=str(exc)[:400], updated_at=_now())
        _save(job, task, job.get("employees", []))
    finally:
        with LOCK:
            EVENTS.pop(job_id, None)
