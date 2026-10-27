"""Bounded local-AI jobs. No email, browser, shell or remote-provider actions."""

from __future__ import annotations

import hashlib
import json
import re
import threading
import uuid
from dataclasses import fields

import engine
import intelligence
import leadfinder as lf
import local_ai
from contacts import now

TASK_LOCK = threading.RLock()
REVIEW_LOCK = threading.Lock()
EVENTS = {}
ACTIVE = ("queued", "running")


def _save(task):
    with engine.connection() as conn:
        conn.execute(
            "INSERT INTO ai_tasks(id,created_at,updated_at,status,payload) VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET updated_at=excluded.updated_at,status=excluded.status,payload=excluded.payload",
            (
                task["id"],
                task["created_at"],
                now(),
                task["status"],
                json.dumps(task, ensure_ascii=False),
            ),
        )


def init(recover=True):
    if not recover:
        return
    with engine.connection() as conn:
        for (raw,) in conn.execute(
            "SELECT payload FROM ai_tasks WHERE status IN ('queued','running')"
        ).fetchall():
            task = json.loads(raw)
            task.update(
                status="failed",
                message="The app restarted before this AI request finished. Please retry.",
                error="Interrupted by app restart",
            )
            conn.execute(
                "UPDATE ai_tasks SET status=?,updated_at=?,payload=? WHERE id=?",
                (task["status"], now(), json.dumps(task), task["id"]),
            )


def get_task(task_id):
    if not isinstance(task_id, str) or not re.fullmatch(r"[a-f0-9]{32}", task_id):
        return None
    with engine.connection() as conn:
        row = conn.execute(
            "SELECT payload FROM ai_tasks WHERE id=?", (task_id,)
        ).fetchone()
    return json.loads(row[0]) if row else None


def _fingerprint(row):
    identity = {
        k: row.get(k)
        for k in ("name", "website", "source_id", "profile_url", "city", "address")
    }
    return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()


def validate(params):
    if not isinstance(params, dict):
        raise ValueError("Choose valid local AI settings")
    task = params.get("task")
    if task not in ("plan", "review", "compile", "compile_batch"):
        raise ValueError("Choose search suggestions or a saved-lead review")
    model = params.get("model", "")
    if not isinstance(model, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,119}", model
    ):
        raise ValueError("Choose an installed local model")
    chosen = {"task": task, "model": model}
    if task == "plan":
        settings = engine.validate(
            {"niche": params.get("niche", ""), "location": params.get("location", "")}
        )
        chosen.update(niche=settings["niche"], locations=settings["locations"])
    elif task == "compile_batch":
        job_id = params.get("job_id")
        scope = params.get("scope", "all")
        if not isinstance(job_id, str) or not re.fullmatch(r"[a-f0-9]{32}", job_id):
            raise ValueError("Open a saved search before compiling intelligence")
        if scope not in ("all", "verified", "qualified"):
            raise ValueError(
                "Choose all retained leads, verified leads, or qualified verified leads"
            )
        saved = engine.get_job(job_id, events=False)
        if not saved or saved.get("status") in ("queued", "running", "waiting"):
            raise ValueError(
                "Wait for the search to finish before compiling intelligence"
            )
        chosen.update(job_id=job_id, scope=scope)
    else:
        job_id, index = params.get("job_id"), params.get("row_index")
        if not isinstance(job_id, str) or not re.fullmatch(r"[a-f0-9]{32}", job_id):
            raise ValueError("Open a saved search before reviewing a lead")
        if (
            isinstance(index, bool)
            or not isinstance(index, int)
            or not 0 <= index < 500
        ):
            raise ValueError("Choose a saved lead to review")
        offer = params.get("offer", "") if task == "review" else ""
        if not isinstance(offer, str) or len(offer) > 800:
            raise ValueError("Describe your offer in 800 characters or fewer")
        saved = engine.get_job(job_id, events=False)
        if not saved or index >= len(saved.get("rows", [])):
            raise ValueError("The saved lead could not be found")
        if saved["status"] in ("queued", "running", "waiting"):
            raise ValueError("Wait for the search to finish before reviewing its leads")
        chosen.update(
            job_id=job_id,
            row_index=index,
            offer=offer.strip(),
            fingerprint=_fingerprint(saved["rows"][index]),
        )
    return chosen


def _ledger(company_id):
    with engine.connection() as conn:
        columns = (
            "evidence_id",
            "field",
            "value",
            "source_type",
            "source_url",
            "captured_at",
            "verbatim_excerpt",
            "authority_weight",
            "freshness_weight",
            "trust_score",
        )
        return [
            dict(zip(columns, item))
            for item in conn.execute(
                "SELECT evidence_id,field,value,source_type,source_url,captured_at,verbatim_excerpt,authority_weight,freshness_weight,trust_score FROM intelligence_evidence_claims WHERE company_id=? ORDER BY trust_score DESC LIMIT 80",
                (company_id,),
            )
        ]


def _evidence_fingerprint(ledger):
    value = [
        (item.get("evidence_id"), item.get("trust_score"), item.get("captured_at"))
        for item in ledger
    ]
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def _compile_saved_row(job_id, row_index, model, cancel, force=False):
    import evidence_compiler

    saved = engine.get_job(job_id, events=False)
    if not saved or row_index >= len(saved.get("rows", [])):
        raise ValueError("Saved lead changed. Reopen the search and retry.")
    row = saved["rows"][row_index]
    company_id = row.get("entity_id", "")
    niche = (saved.get("params") or {}).get("niche", "")
    teaching = intelligence.ensure_niche_pack(niche) if niche else None
    ledger = _ledger(company_id)
    fingerprint = _evidence_fingerprint(ledger)
    try:
        prior_meta = json.loads(row.get("ai_compiler_metadata") or "{}")
    except (TypeError, ValueError):
        prior_meta = {}
    if (
        not force
        and prior_meta.get("evidence_fingerprint") == fingerprint
        and row.get("ai_compiler_output")
    ):
        return {
            "status": "skipped_unchanged",
            "row_index": row_index,
            "company_id": company_id,
        }
    error = ""
    errors = []
    retries = 0
    failure_kind = ""
    mode = "local_ai_validated"
    result = None
    for attempt in range(2):
        try:
            result = local_ai.compile_intelligence(
                ledger,
                company_id,
                row.get("operating_entity_id", ""),
                {
                    "next_best_action": row.get("next_best_action", ""),
                    "contact_confidence": row.get("contact_confidence", 0),
                },
                model,
                cancel,
                teaching=teaching,
                niche=niche,
            )
            break
        except Exception as exc:
            errors.append(str(exc)[:500])
            failure_kind = (
                "validation_rejected"
                if isinstance(exc, ValueError)
                else "model_or_transport_failure"
            )
            if attempt == 0 and not cancel.is_set():
                retries += 1
                continue
    if result is None:
        error = " | retry: ".join(errors)[:500]
        mode = "deterministic_fallback"
        try:
            result = json.loads(row.get("compiler_output") or "{}")
        except (TypeError, ValueError):
            result = {}
        if not result:
            result = evidence_compiler.deterministic_output(
                company_id,
                row.get("operating_entity_id", ""),
                ledger,
                row,
                row.get("next_best_action", "manual_browser_review"),
                row.get(
                    "next_action_reason",
                    "Local AI did not return a valid evidence-bound result.",
                ),
                [],
                False,
            )
        evidence_compiler.validate_output(result, ledger)
    if cancel.is_set():
        raise ValueError("AI compiler cancelled; saved intelligence was not changed")
    with REVIEW_LOCK:
        latest = engine.get_job(job_id, events=False)
        if (
            not latest
            or row_index >= len(latest.get("rows", []))
            or _fingerprint(latest["rows"][row_index]) != _fingerprint(row)
        ):
            raise ValueError("Saved lead changed. Reopen the search and retry.")
        latest_row = latest["rows"][row_index]
        latest_row["ai_compiler_output"] = json.dumps(result, ensure_ascii=False)
        latest_row["ai_compiler_metadata"] = json.dumps(
            {
                "model": model
                if mode == "local_ai_validated"
                else "deterministic rules",
                "generated_at": now(),
                "validation": "all_citations_excerpts_and_semantic_guards_passed"
                if mode == "local_ai_validated"
                else "deterministic_fallback_no_ai_interpretation",
                "mode": mode,
                "error": error,
                "evidence_fingerprint": fingerprint,
            },
            ensure_ascii=False,
        )
        engine.save(latest)
    return {
        "status": "complete" if mode == "local_ai_validated" else "fallback",
        "row_index": row_index,
        "company_id": company_id,
        "mode": mode,
        "error": error,
        "failure_kind": failure_kind,
        "retries": retries,
        "output": result,
    }


def start(params):
    settings = validate(params)
    task_id = uuid.uuid4().hex
    task = {
        "id": task_id,
        "created_at": now(),
        "status": "queued",
        "message": "Waiting for the local model",
        "params": settings,
    }
    event = threading.Event()
    with TASK_LOCK:
        with engine.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            pending = conn.execute(
                "SELECT count(*) FROM ai_tasks WHERE status IN ('queued','running')"
            ).fetchone()[0]
            if pending >= 4:
                raise ValueError(
                    "The local AI queue is full. Wait for an existing request to finish."
                )
            conn.execute(
                "INSERT INTO ai_tasks VALUES(?,?,?,?,?)",
                (task_id, task["created_at"], now(), "queued", json.dumps(task)),
            )
        EVENTS[task_id] = event
    threading.Thread(target=run, args=(task, event), daemon=True).start()
    return task_id


def cancel_task(task_id):
    with TASK_LOCK:
        event = EVENTS.get(task_id)
        if event:
            event.set()
    return bool(event)


def _log(job_id, level, message, **details):
    if job_id:
        with engine.connection() as conn:
            conn.execute(
                "INSERT INTO events(job_id,created_at,provider,level,message,details) VALUES(?,?,?,?,?,?)",
                (job_id, now(), "local_ai", level, message, json.dumps(details)),
            )
    engine.LOG.info(
        json.dumps(
            {
                "provider": "local_ai",
                "job": job_id,
                "level": level,
                "message": message,
                "details": details,
            }
        )
    )


def run(task, cancel):
    params = task["params"]
    job_id = params.get("job_id")
    try:
        if cancel.is_set():
            raise ValueError("AI request cancelled")
        task.update(status="running", message="Working with the model on your computer")
        _save(task)
        _log(
            job_id,
            "info",
            "Local AI request started",
            task=task["id"],
            kind=params["task"],
            model=params["model"],
        )
        if params["task"] == "plan":
            compiled_terms = intelligence.compiled_search_terms(params["niche"])
            teaching = intelligence.ensure_niche_pack(params["niche"])
            result = local_ai.plan(
                params["niche"],
                params["locations"],
                params["model"],
                cancel=cancel,
                observed_terms=compiled_terms,
                teaching=teaching,
            )
            if result.get("status") in ("error", "cancelled"):
                raise ValueError(
                    result.get("message")
                    or result.get("notes")
                    or "The local model could not suggest search terms"
                )
            if result.get("status") == "complete" and result.get("phrases"):
                # Suggestions remain proposals. The user applies them to the visible
                # form and reviews the exact plan before they can affect a search.
                result["saved_to_niche_pack"] = False
                result["compiled_terms_used"] = compiled_terms
        elif params["task"] == "review":
            saved = engine.get_job(job_id, events=False)
            if not saved or params["row_index"] >= len(saved.get("rows", [])):
                raise ValueError("Saved lead changed. Reopen the lead and try again.")
            row = saved["rows"][params["row_index"]]
            if _fingerprint(row) != params["fingerprint"]:
                raise ValueError("Saved lead changed. Reopen the lead and try again.")
            allowed = {f.name for f in fields(lf.Lead)}
            lead = lf.Lead(**{k: v for k, v in row.items() if k in allowed})
            niche = (saved.get("params") or {}).get("niche", "")
            teaching = intelligence.ensure_niche_pack(niche) if niche else None
            result = local_ai.review(
                lead,
                params["model"],
                params["offer"],
                cancel=cancel,
                teaching=teaching,
                niche=niche,
            )
            if result.get("analysis", {}).get("status") in ("error", "cancelled"):
                raise ValueError(
                    result["analysis"].get("message")
                    or result["analysis"].get("summary")
                    or "The local model could not review this lead"
                )
            if cancel.is_set():
                raise ValueError("AI request cancelled; saved lead was not changed")
            with REVIEW_LOCK:
                latest = engine.get_job(job_id, events=False)
                if (
                    not latest
                    or latest["status"] in ("queued", "running", "waiting")
                    or params["row_index"] >= len(latest.get("rows", []))
                    or _fingerprint(latest["rows"][params["row_index"]])
                    != params["fingerprint"]
                ):
                    raise ValueError(
                        "Saved lead changed. Reopen the lead and try again."
                    )
                latest_row = latest["rows"][params["row_index"]]
                latest_row["ai_analysis"] = json.dumps(
                    result["analysis"], ensure_ascii=False
                )
                latest_row["ai_draft"] = json.dumps(result["draft"], ensure_ascii=False)
                engine.save(latest)
        elif params["task"] == "compile":
            result = _compile_saved_row(
                job_id, params["row_index"], params["model"], cancel, force=True
            )
            if result.get("status") == "fallback":
                _log(
                    job_id,
                    "warning",
                    "Local AI compiler rejected or failed; deterministic fallback saved",
                    row_index=params["row_index"],
                    error=result.get("error", ""),
                )
        else:
            saved = engine.get_job(job_id, events=False)
            indices = []
            for index, row in enumerate(saved.get("rows", [])):
                if params["scope"] in ("verified", "qualified"):
                    try:
                        report = json.loads(row.get("verification") or "{}")
                    except (TypeError, ValueError):
                        report = {}
                    if report.get("status") != "complete":
                        continue
                if (
                    params["scope"] == "qualified"
                    and row.get("match_status") == "candidate"
                ):
                    continue
                indices.append(index)
            task.update(
                total=len(indices),
                completed=0,
                failed=0,
                fallback=0,
                rejected=0,
                retries=0,
                skipped=0,
                items=[],
            )
            _save(task)
            for position, index in enumerate(indices, 1):
                if cancel.is_set():
                    raise ValueError(
                        "Batch compilation cancelled; completed leads were retained"
                    )
                task.update(
                    message=f"Compiling lead {position} of {len(indices)}",
                    current_row=index,
                )
                _save(task)
                try:
                    item = _compile_saved_row(job_id, index, params["model"], cancel)
                    state = item.get("status", "complete")
                    task["skipped"] += int(state == "skipped_unchanged")
                    task["fallback"] += int(state == "fallback")
                    task["rejected"] += int(
                        item.get("failure_kind") == "validation_rejected"
                    )
                    task["retries"] += int(item.get("retries", 0))
                    task["completed"] += int(state in ("complete", "fallback"))
                    if state == "fallback":
                        _log(
                            job_id,
                            "warning",
                            "Batch AI compiler used deterministic fallback",
                            row_index=index,
                            error=item.get("error", ""),
                        )
                except Exception as exc:
                    item = {
                        "status": "failed",
                        "row_index": index,
                        "error": str(exc)[:500],
                    }
                    task["failed"] += 1
                    _log(
                        job_id,
                        "warning",
                        "Batch AI compiler lead failed",
                        row_index=index,
                        error=str(exc)[:500],
                    )
                task["items"] = (task.get("items", []) + [item])[-100:]
                task["progress"] = int(100 * position / max(1, len(indices)))
                _save(task)
            result = {
                key: task.get(key, 0)
                for key in (
                    "total",
                    "completed",
                    "fallback",
                    "rejected",
                    "retries",
                    "skipped",
                    "failed",
                    "progress",
                )
            }
        if cancel.is_set():
            raise ValueError("AI request cancelled")
        task.update(
            status="complete",
            message=(
                f"Batch compilation complete · {result.get('completed', 0)} compiled · {result.get('skipped', 0)} unchanged · {result.get('rejected', 0)} rejected · {result.get('retries', 0)} retries · {result.get('fallback', 0)} deterministic fallback · {result.get('failed', 0)} failed"
                if params["task"] == "compile_batch"
                else "Local AI suggestions ready — review before use"
            ),
            result=result,
        )
        _log(
            job_id,
            "info",
            "Local AI request complete",
            task=task["id"],
            model=params["model"],
            kind=params["task"],
            note="Suggestions only. No contacts, scores or qualification facts overwritten; no email sent.",
        )
    except Exception as exc:
        task.update(
            status="failed",
            message="Local AI request did not finish",
            error=str(exc)[:500],
        )
        _log(
            job_id,
            "warning",
            "Local AI request failed; scraped data unchanged",
            task=task["id"],
            error=str(exc)[:500],
        )
    finally:
        _save(task)
        with TASK_LOCK:
            EVENTS.pop(task["id"], None)
