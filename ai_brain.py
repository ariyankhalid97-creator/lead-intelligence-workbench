"""Private, durable consistency memory for the optional local AI.

This module does not fine-tune a model. It turns completed local runs and
explicit user feedback into a compact, niche-scoped snapshot that can be
retrieved at prompt time. Contact details and business identities are never
stored in or returned from this memory layer.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import UTC, datetime

import ai_teaching
import engine

CONSISTENCY_RULES = [
    "Treat memory as historical guidance, never as evidence about a lead.",
    "Prefer user-approved niche terms and avoid rejected terminology.",
    "Do not infer facts, contacts, source coverage or current availability from memory.",
    "Evidence saved in the current run remains the only authority for lead claims.",
]


def _clean(value, limit=120):
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _slug(value):
    return re.sub(r"[^a-z0-9]+", "-", _clean(value).casefold()).strip("-") or "general"


def _object(value, fallback=None):
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value or "{}")
    except (TypeError, ValueError):
        return {} if fallback is None else fallback
    return parsed if isinstance(parsed, dict) else ({} if fallback is None else fallback)


def _feedback(niche):
    wanted = _slug(niche)
    path = ai_teaching._feedback_path()
    accepted, rejected = Counter(), Counter()
    events = 0
    if path.exists():
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[-2000:]
        except OSError:
            lines = []
        for raw in lines:
            try:
                row = json.loads(raw)
            except (TypeError, ValueError):
                continue
            if not isinstance(row, dict) or _slug(row.get("niche")) != wanted:
                continue
            events += 1
            bucket = accepted if row.get("accepted") is True else rejected
            for phrase in ai_teaching.clean_terms(row.get("phrases"), 20):
                bucket[phrase] += 1
    return accepted, rejected, events


def refresh(niche):
    """Rebuild one niche snapshot from aggregate local history."""
    niche = _clean(niche)
    if not 2 <= len(niche) <= 120:
        raise ValueError("Choose a service between 2 and 120 characters")
    slug = _slug(niche)
    provider_totals = {}
    coverage = Counter()
    source_runs = result_total = 0
    outcome_counts = Counter()
    with engine.connection() as conn:
        raw_jobs = conn.execute(
            "SELECT payload FROM jobs ORDER BY updated_at DESC LIMIT 250"
        ).fetchall()
        pack_row = conn.execute(
            "SELECT payload FROM intelligence_niche_packs WHERE slug=?", (slug,)
        ).fetchone()
        for (raw,) in raw_jobs:
            job = _object(raw)
            if _slug(_object(job.get("params")).get("niche")) != slug:
                continue
            if job.get("status") not in {"complete", "partial"}:
                continue
            source_runs += 1
            result_total += int(job.get("count") or len(job.get("rows") or []))
            stats = _object(job.get("stats"))
            for key in ("emails", "phones", "websites", "matches"):
                coverage[key] += int(stats.get(key) or 0)
            for provider, item in _object(job.get("providers")).items():
                if not isinstance(item, dict):
                    continue
                total = provider_totals.setdefault(
                    _clean(provider, 60),
                    {"runs": 0, "successes": 0, "failures": 0, "records": 0},
                )
                total["runs"] += 1
                total["successes"] += int(item.get("successes") or 0)
                total["failures"] += int(item.get("failures") or 0)
                total["records"] += int(item.get("count") or 0)
        outcome_rows = conn.execute(
            "SELECT o.outcome,COUNT(*) FROM intelligence_outcomes o "
            "JOIN intelligence_companies c ON c.id=o.company_id "
            "WHERE lower(c.niche)=lower(?) GROUP BY o.outcome",
            (niche,),
        ).fetchall()
        outcome_counts.update({str(name): int(count) for name, count in outcome_rows})
    pack = _object(pack_row[0]) if pack_row else {}
    guidance = ai_teaching.context(niche, pack)
    accepted, rejected, feedback_events = _feedback(niche)
    providers = []
    for name, values in provider_totals.items():
        attempts = values["successes"] + values["failures"]
        providers.append(
            {
                "provider": name,
                **values,
                "historical_success_rate": round(values["successes"] / attempts, 3) if attempts else 0,
            }
        )
    providers.sort(
        key=lambda item: (item["historical_success_rate"], item["records"], item["runs"]),
        reverse=True,
    )
    evidence_units = source_runs + feedback_events + sum(outcome_counts.values())
    confidence = "high" if evidence_units >= 15 else "developing" if evidence_units >= 4 else "new"
    payload = {
        "schema_version": 1,
        "niche": niche,
        "confidence": confidence,
        "source_runs": source_runs,
        "results_observed": result_total,
        "feedback_events": feedback_events,
        "approved_phrases": [name for name, _ in accepted.most_common(12)] or guidance.get("approved_examples", [])[:12],
        "avoid_phrases": [name for name, _ in rejected.most_common(12)] or guidance.get("avoid_terms", [])[:12],
        "specialist_terms": guidance.get("specialist_terms", [])[:12],
        "historical_provider_performance": providers[:12],
        "historical_contact_coverage": dict(coverage),
        "outcome_counts": dict(outcome_counts),
        "consistency_rules": CONSISTENCY_RULES,
        "privacy": "Aggregate niche memory only; no lead names, contacts, URLs or page text.",
        "updated_at": datetime.now(UTC).isoformat(),
    }
    with engine.connection() as conn:
        conn.execute(
            "INSERT INTO ai_memory_snapshots(niche_slug,niche,payload,source_runs,feedback_events,updated_at) "
            "VALUES(?,?,?,?,?,?) ON CONFLICT(niche_slug) DO UPDATE SET niche=excluded.niche,payload=excluded.payload,"
            "source_runs=excluded.source_runs,feedback_events=excluded.feedback_events,updated_at=excluded.updated_at",
            (slug, niche, json.dumps(payload, ensure_ascii=False), source_runs, feedback_events, payload["updated_at"]),
        )
    return payload


def snapshot(niche=""):
    """Return one snapshot, or a compact overview of all learned niches."""
    niche = _clean(niche)
    with engine.connection() as conn:
        if niche:
            row = conn.execute(
                "SELECT payload FROM ai_memory_snapshots WHERE niche_slug=?", (_slug(niche),)
            ).fetchone()
            return _object(row[0]) if row else refresh(niche)
        rows = conn.execute(
            "SELECT niche,payload,updated_at FROM ai_memory_snapshots ORDER BY updated_at DESC"
        ).fetchall()
    memories = []
    for name, raw, updated_at in rows:
        item = _object(raw)
        memories.append(
            {
                "niche": name,
                "confidence": item.get("confidence", "new"),
                "source_runs": item.get("source_runs", 0),
                "feedback_events": item.get("feedback_events", 0),
                "results_observed": item.get("results_observed", 0),
                "updated_at": updated_at,
            }
        )
    return {"memories": memories, "count": len(memories), "privacy": "Local aggregate memory; no lead contact data."}


def prompt_context(niche):
    """Return the bounded, non-evidentiary fragment allowed in model prompts."""
    item = snapshot(niche)
    return {
        "confidence": item.get("confidence", "new"),
        "approved_phrases": item.get("approved_phrases", [])[:12],
        "avoid_phrases": item.get("avoid_phrases", [])[:12],
        "specialist_terms": item.get("specialist_terms", [])[:12],
        "historical_provider_preferences": item.get("historical_provider_performance", [])[:8],
        "historical_contact_coverage": item.get("historical_contact_coverage", {}),
        "consistency_rules": CONSISTENCY_RULES,
    }
