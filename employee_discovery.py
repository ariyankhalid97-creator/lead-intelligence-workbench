"""Resumable, browser-assisted LinkedIn company employee discovery."""

from __future__ import annotations

import threading
import re
from datetime import datetime

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
            "companies_total": sum(bool(row.get("linkedin")) for row in job.get("rows", [])),
            "profiles_found": len(employees),
            "message": "Ready after company LinkedIn URLs have been verified.",
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
    for row in job.get("rows", []):
        url = browser_session._canonical_linkedin_company_url(row.get("linkedin", ""))
        if not url or url in seen:
            continue
        seen.add(url)
        companies.append({"name": str(row.get("name", ""))[:180], "linkedin": url})
        if len(companies) >= company_limit:
            break
    if not companies:
        raise ValueError("No verified LinkedIn company URLs are available yet. Finish second-round verification first.")
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
        "message": "Preparing company People pages",
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
            row.get("employee_linkedin"): index
            for index, row in enumerate(employees)
            if row.get("employee_linkedin")
        }
        task.update(status="running", message="Checking visible LinkedIn company People pages", updated_at=_now())
        _save(job, task, employees)
        companies = task.get("companies", [])
        for index in range(int(task.get("next_company_index", 0)), len(companies)):
            if cancel.is_set():
                task.update(status="cancelled", message="Employee discovery stopped; collected profiles were retained")
                break
            company = companies[index]
            result = browser_session.discover_linkedin_employees(
                company.get("linkedin", ""),
                company.get("name", ""),
                int(task.get("per_company", 25)),
                cancel,
            )
            for profile in result.get("profiles", []):
                url = profile.get("employee_linkedin")
                if not url:
                    continue
                profile = _classify_profile(profile)
                existing_index = employee_indexes.get(url)
                if existing_index is None:
                    employee_indexes[url] = len(employees)
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
            if result.get("status") in {"manual_checkpoint", "login_required"}:
                task.update(
                    status="waiting",
                    message=result.get("browser_checkpoint") or result.get("error") or "Complete the LinkedIn browser checkpoint, then continue",
                    next_company_index=index,
                    updated_at=_now(),
                )
                _sync(job, task)
                _save(job, task, employees)
                return
            if result.get("status") in {"failed", "invalid_company_url"}:
                task.setdefault("failures", []).append({"company": company.get("name", ""), "error": result.get("error", result.get("status", "failed"))})
                task["failures"] = task["failures"][-100:]
            task.update(
                companies_checked=index + 1,
                next_company_index=index + 1,
                progress=int(100 * (index + 1) / max(1, len(companies))),
                message=(
                    f"Checked {index + 1} of {len(companies)} companies · "
                    f"retained {len(employees)} profiles · "
                    f"classified {sum(bool(row.get('title')) for row in employees)} titles"
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
                    f"Employee discovery complete · {len(employees)} profiles retained · "
                    f"{sum(bool(row.get('title')) for row in employees)} titles classified"
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
