"""Durable end-to-end research workflow orchestration."""

from __future__ import annotations

import json
import re
import threading
import time
import uuid

import ai_tasks
import engine
import local_ai
import verification
from contacts import now

LOCK = threading.RLock()
EVENTS: dict[str, threading.Event] = {}
ACTIVE = {"queued", "running", "waiting"}
STAGES = (
    ("discovery", "Discover and enrich"),
    ("verification", "Verify qualified prospects"),
    ("organization", "Organize research library"),
    ("compilation", "Compile strict intelligence"),
    ("outreach", "Prepare outreach handoff"),
)


def _save(task):
    task["updated_at"] = now()
    with engine.connection() as conn:
        conn.execute(
            "INSERT INTO workflow_tasks(id,created_at,updated_at,status,payload) VALUES(?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET updated_at=excluded.updated_at,status=excluded.status,payload=excluded.payload",
            (task["id"], task["created_at"], task["updated_at"], task["status"], json.dumps(task, ensure_ascii=False)),
        )


def _stage(task, name, status, message, **details):
    task["stages"][name].update(status=status, message=message, **details)
    task["current_stage"] = name
    task["message"] = message
    _save(task)


def init(recover=True):
    with engine.connection() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS workflow_tasks(id TEXT PRIMARY KEY,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,status TEXT NOT NULL,payload TEXT NOT NULL)"
        )
        rows = conn.execute(
            "SELECT payload FROM workflow_tasks WHERE status IN ('queued','running','waiting') ORDER BY updated_at"
        ).fetchall()
    if not recover:
        return
    for (payload,) in rows:
        try:
            task = json.loads(payload)
        except (TypeError, ValueError):
            continue
        cancel = threading.Event()
        with LOCK:
            EVENTS[task["id"]] = cancel
        task.update(status="queued", message="Resuming linked workflow after dashboard restart")
        _save(task)
        threading.Thread(target=_run, args=(task, cancel), daemon=True).start()


def get_task(task_id):
    if not isinstance(task_id, str) or not re.fullmatch(r"[a-f0-9]{32}", task_id):
        return None
    with engine.connection() as conn:
        row = conn.execute("SELECT payload FROM workflow_tasks WHERE id=?", (task_id,)).fetchone()
    return json.loads(row[0]) if row else None


def current(job_id):
    if not isinstance(job_id, str) or not re.fullmatch(r"[a-f0-9]{32}", job_id):
        return None
    with engine.connection() as conn:
        rows = conn.execute("SELECT payload FROM workflow_tasks ORDER BY updated_at DESC LIMIT 100").fetchall()
    for (payload,) in rows:
        task = json.loads(payload)
        if task.get("job_id") == job_id:
            return task
    return None


def start(params):
    if not isinstance(params, dict):
        raise ValueError("Choose valid workflow settings")
    job_id = params.get("job_id", "")
    if not isinstance(job_id, str) or not re.fullmatch(r"[a-f0-9]{32}", job_id) or not engine.get_job(job_id, events=False):
        raise ValueError("Start a search before linking its workflow")
    existing = current(job_id)
    if existing and existing.get("status") in ACTIVE:
        return existing["id"]
    model = str(params.get("model", ""))[:120]
    task_id = uuid.uuid4().hex
    task = {
        "id": task_id,
        "job_id": job_id,
        "created_at": now(),
        "updated_at": now(),
        "status": "queued",
        "message": "Linked workflow queued",
        "progress": 0,
        "current_stage": "discovery",
        "model": model,
        "verification_task_id": "",
        "ai_task_id": "",
        "stages": {name: {"label": label, "status": "pending", "message": "Waiting"} for name, label in STAGES},
        "result": {},
    }
    cancel = threading.Event()
    with LOCK:
        EVENTS[task_id] = cancel
    _save(task)
    threading.Thread(target=_run, args=(task, cancel), daemon=True).start()
    return task_id


def cancel(task_id):
    with LOCK:
        event = EVENTS.get(task_id)
        if event:
            event.set()
    task = get_task(task_id)
    if task:
        engine.cancel_job(task.get("job_id", ""))
        if task.get("verification_task_id"):
            verification.cancel_task(task["verification_task_id"])
        if task.get("ai_task_id"):
            ai_tasks.cancel_task(task["ai_task_id"])
    return bool(event)


def _wait_for_job(task, cancel):
    while not cancel.is_set():
        job = engine.get_job(task["job_id"], events=False)
        if not job:
            raise ValueError("The linked search no longer exists")
        status = job.get("status", "")
        task["progress"] = min(44, int((job.get("progress", 0) or 0) * 0.44))
        task["status"] = "waiting" if status == "waiting" else "running"
        _stage(task, "discovery", "waiting" if status == "waiting" else "running", job.get("message", "Searching public sources"), records=len(job.get("rows", [])))
        if status not in ACTIVE:
            return job
        cancel.wait(1.2)
    raise InterruptedError("Workflow stopped")


def _wait_for_verification(task, cancel):
    job = engine.get_job(task["job_id"], events=False) or {}
    qualified = [row for row in job.get("rows", []) if row.get("match_status") != "candidate"]
    if job.get("organization") and all(_verification_complete(row) for row in qualified):
        return {"status": "complete", "progress": 100, "message": f"Reused {len(qualified)} completed qualified verification report(s)", "summary": {"verified": len(qualified), "reused": len(qualified)}}
    task_id = task.get("verification_task_id", "")
    existing = verification.get_task(task_id) if task_id else None
    if not existing or existing.get("status") not in ACTIVE | {"complete"}:
        scope = "unfinished" if existing else "matches"
        task_id = verification.start({"job_id": task["job_id"], "scope": scope})
        task["verification_task_id"] = task_id
        _save(task)
    while not cancel.is_set():
        state = verification.get_task(task_id)
        if not state:
            raise ValueError("Verification task disappeared")
        task["status"] = "running"
        task["progress"] = 45 + int((state.get("progress", 0) or 0) * 0.34)
        _stage(task, "verification", "running" if state.get("status") in ACTIVE else state.get("status", "failed"), state.get("message", "Verifying prospects"), checked=state.get("checked", 0), total=state.get("total", 0))
        if state.get("status") not in ACTIVE:
            return state
        cancel.wait(1.2)
    raise InterruptedError("Workflow stopped")


def _selected_model(task):
    status = local_ai.status()
    names = {item.get("name") for item in status.get("models", [])}
    if task.get("model") in names:
        return task["model"]
    default = status.get("default_model", "")
    return default if status.get("available") and default in names else ""


def _verification_complete(row):
    try:
        return json.loads(row.get("verification") or "{}").get("status") == "complete"
    except (TypeError, ValueError):
        return False


def _outreach_review_count(job):
    """Count only qualified leads with a rules-reviewed recommended address."""
    eligible = 0
    for row in job.get("rows", []):
        if row.get("match_status") == "candidate":
            continue
        try:
            recommended = json.loads(row.get("email_quality") or "{}").get("recommended", [])
        except (TypeError, ValueError):
            recommended = []
        if any(isinstance(item, dict) and item.get("email") and item.get("recommended", True) for item in recommended):
            eligible += 1
    return eligible


def _wait_for_ai(task, cancel, model):
    task_id = task.get("ai_task_id", "")
    existing = ai_tasks.get_task(task_id) if task_id else None
    if not existing or existing.get("status") not in ACTIVE | {"complete"}:
        task_id = ai_tasks.start({"task": "compile_batch", "model": model, "job_id": task["job_id"], "scope": "qualified"})
        task["ai_task_id"] = task_id
        _save(task)
    while not cancel.is_set():
        state = ai_tasks.get_task(task_id)
        if not state:
            raise ValueError("AI compilation task disappeared")
        task["progress"] = 80 + int((state.get("progress", 0) or 0) * 0.18)
        _stage(task, "compilation", "running" if state.get("status") in ACTIVE else state.get("status", "failed"), state.get("message", "Compiling evidence"), completed=state.get("completed", 0), total=state.get("total", 0))
        if state.get("status") not in ACTIVE:
            return state
        cancel.wait(1.2)
    raise InterruptedError("Workflow stopped")


def _run(task, cancel):
    try:
        task["status"] = "running"
        job = _wait_for_job(task, cancel)
        if job.get("status") == "cancelled":
            raise InterruptedError("Search cancelled; saved results were retained")
        if job.get("status") == "failed" and not job.get("rows"):
            raise ValueError(job.get("message") or "Search failed without saved results")
        _stage(task, "discovery", "complete", f"Discovery retained {len(job.get('rows', []))} prospects", records=len(job.get("rows", [])))
        task["progress"] = 45

        verified = _wait_for_verification(task, cancel)
        if verified.get("status") == "failed":
            raise ValueError(verified.get("message") or "Verification failed")
        if verified.get("status") == "cancelled":
            raise InterruptedError("Verification stopped; completed checks were retained")
        _stage(task, "verification", "complete", verified.get("message", "Verification complete"), **verified.get("summary", {}))
        task["progress"] = 80
        organized = engine.get_job(task["job_id"], events=False) or {}
        organization = organized.get("organization", {})
        _stage(task, "organization", "complete", "Organized result saved to the research library", records=len(organized.get("rows", [])), duplicates=organization.get("duplicates_consolidated", 0))

        model = _selected_model(task)
        if model:
            compiled = _wait_for_ai(task, cancel, model)
            if compiled.get("status") == "complete":
                _stage(task, "compilation", "complete", compiled.get("message", "Strict intelligence compiled"), **compiled.get("result", {}))
            else:
                _stage(task, "compilation", "warning", "Local AI did not finish; organized research remains usable", error=compiled.get("error", ""))
        else:
            _stage(task, "compilation", "skipped", "No compatible local model was available; organized research remains usable")

        final = engine.get_job(task["job_id"], events=False) or {}
        eligible = _outreach_review_count(final)
        _stage(
            task,
            "outreach",
            "ready",
            f"{eligible} qualified lead(s) with a recommended email ready for campaign review; deliverability and sending approval remain required",
            eligible=eligible,
        )
        task.update(status="complete", progress=100, message="Linked workflow complete · research organized · outreach approval required", result={"records": len(final.get("rows", [])), "outreach_ready": eligible})
    except InterruptedError as exc:
        task.update(status="cancelled", message=str(exc), progress=min(99, task.get("progress", 0)))
    except Exception as exc:
        task.update(status="failed", message=str(exc)[:500], error=str(exc)[:500], progress=min(99, task.get("progress", 0)))
    finally:
        _save(task)
        with LOCK:
            EVENTS.pop(task["id"], None)
