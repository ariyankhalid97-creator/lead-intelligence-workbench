"""Repeatable local-model exam for lead-research task routing."""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime

import ai_curriculum
import local_ai

PHRASE_CASES = [
    {"id": "p1", "niche": "commercial kitchen exhaust cleaning", "must": ["hood", "exhaust", "grease duct"], "avoid": ["house cleaning", "air duct", "repair"]},
    {"id": "p2", "niche": "employment law firms", "must": ["employment", "wrongful termination", "labor"], "avoid": ["recruiting", "staffing", "job board"]},
    {"id": "p3", "niche": "multifamily property management", "must": ["property management", "apartment management", "multifamily"], "avoid": ["photography", "real estate agent", "cleaning"]},
]
EVIDENCE_CASES = [
    {"id": "e1", "excerpt": "Our Dallas office provides 24-hour emergency plumbing repair.", "claim": "The Dallas office publishes emergency plumbing repair.", "answer": "supported"},
    {"id": "e2", "excerpt": "The captured page does not mention a CRM.", "claim": "The company does not use a CRM.", "answer": "unsupported"},
    {"id": "e3", "excerpt": "Search result snippet: Acme may serve the North Texas area.", "claim": "Acme definitely serves all of North Texas.", "answer": "unsupported"},
    {"id": "e4", "excerpt": "Applications can be submitted online.", "claim": "Applicants sign documents electronically.", "answer": "unknown"},
]
CONTACT_CASES = [
    {"id": "c1", "email": "jane.smith@example.com", "answer": "possible_direct"},
    {"id": "c2", "email": "info@example.com", "answer": "general_business"},
    {"id": "c3", "email": "support@example.com", "answer": "excluded"},
    {"id": "c4", "email": "noreply@example.com", "answer": "excluded"},
]
IDENTITY_CASES = [
    {"id": "i1", "left": "Acme Roofing | acmeroof.com | 10 Main St Dallas", "right": "Acme Roofing LLC | www.acmeroof.com | 10 Main Street Dallas", "answer": "same_operating_entity"},
    {"id": "i2", "left": "Acme Roofing | acmeroof.com | Dallas", "right": "Acme Roofing | acmeroof.com | Houston", "answer": "same_parent_different_location"},
    {"id": "i3", "left": "Summit Dental | no domain | Austin", "right": "Summit Dental Group | no domain | Round Rock", "answer": "uncertain"},
    {"id": "i4", "left": "Taylor Animal Talent | individual profile", "right": "Taylor Talent Agency | company directory", "answer": "uncertain"},
]
OUTREACH_CASES = [
    {"id": "o1", "evidence": "Careers page lists three leasing openings.", "draft": "I noticed you are hiring for leasing roles. Would comparing your applicant-document signing workflow be useful?", "answer": "safe"},
    {"id": "o2", "evidence": "Careers page lists three leasing openings.", "draft": "Your overwhelmed hiring team is losing candidates because your signing process is broken.", "answer": "unsafe"},
    {"id": "o3", "evidence": "The website publishes an online rental application.", "draft": "I saw your online application option. Is document signing also handled online, or is that still an open question?", "answer": "safe"},
    {"id": "o4", "evidence": "No software names were observed.", "draft": "I know you do not have e-signature software, so you need our platform.", "answer": "unsafe"},
]


def _answer_item(values):
    return {"type": "object", "additionalProperties": False, "required": ["id", "answer"], "properties": {"id": {"type": "string"}, "answer": {"type": "string", "enum": values}}}


def _schema():
    phrase_item = {
        "type": "object",
        "additionalProperties": False,
        "required": ["id", "suggestions"],
        "properties": {
            "id": {"type": "string"},
            "suggestions": {"type": "array", "minItems": 2, "maxItems": 5, "items": {"type": "string", "maxLength": 100}},
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["phrases", "evidence", "contacts", "identity", "outreach"],
        "properties": {
            "phrases": {"type": "array", "minItems": 3, "maxItems": 3, "items": phrase_item},
            "evidence": {"type": "array", "minItems": 4, "maxItems": 4, "items": _answer_item(["supported", "unsupported", "unknown"])},
            "contacts": {"type": "array", "minItems": 4, "maxItems": 4, "items": _answer_item(["possible_direct", "general_business", "excluded", "uncertain"])},
            "identity": {"type": "array", "minItems": 4, "maxItems": 4, "items": _answer_item(["same_operating_entity", "same_parent_different_location", "different", "uncertain"])},
            "outreach": {"type": "array", "minItems": 4, "maxItems": 4, "items": _answer_item(["safe", "unsafe"])},
        },
    }


def _score(raw):
    phrase_rows = {row.get("id"): row for row in raw.get("phrases", []) if isinstance(row, dict)}
    phrase_points = 0
    for case in PHRASE_CASES:
        text = " | ".join(str(value).casefold() for value in phrase_rows.get(case["id"], {}).get("suggestions", []))
        positive = any(term in text for term in case["must"])
        phrase_points += int(positive) + int(positive and not any(term in text for term in case["avoid"]))
    evidence_rows = {row.get("id"): row.get("answer") for row in raw.get("evidence", []) if isinstance(row, dict)}
    contact_rows = {row.get("id"): row.get("answer") for row in raw.get("contacts", []) if isinstance(row, dict)}
    identity_rows = {row.get("id"): row.get("answer") for row in raw.get("identity", []) if isinstance(row, dict)}
    outreach_rows = {row.get("id"): row.get("answer") for row in raw.get("outreach", []) if isinstance(row, dict)}
    tasks = {
        "planning": round(100 * phrase_points / 6),
        "evidence": round(100 * sum(evidence_rows.get(case["id"]) == case["answer"] for case in EVIDENCE_CASES) / 4),
        "contacts": round(100 * sum(contact_rows.get(case["id"]) == case["answer"] for case in CONTACT_CASES) / 4),
        "identity": round(100 * sum(identity_rows.get(case["id"]) == case["answer"] for case in IDENTITY_CASES) / 4),
        "outreach": round(100 * sum(outreach_rows.get(case["id"]) == case["answer"] for case in OUTREACH_CASES) / 4),
    }
    return round(sum(tasks.values()) / len(tasks)), tasks


def run(models=None):
    available = [item["name"] for item in local_ai.status().get("models", [])]
    chosen = [name for name in (models or available) if name in available]
    results = []
    for model in chosen:
        started = time.monotonic()
        try:
            raw = local_ai._generate(
                model,
                "You are taking a closed-book local lead-research competency exam. Return JSON only. Follow the supplied curriculum. Do not browse or add facts. For phrase cases, give concrete niche-faithful provider/service phrases without locations. For evidence cases, supported requires literal support; unsupported means the claim contradicts or exceeds the excerpt; unknown means the excerpt cannot resolve it. For contact cases, support and noreply are excluded. For identity, shared parent branding does not collapse distinct operating locations, and similar names alone remain uncertain. For outreach, reject invented pain, absence claims, guarantees or false familiarity. Preserve every case id.",
                {"curriculum": ai_curriculum.lesson("planning", "evidence", "contacts", "qualification", "outreach"), "phrase_cases": PHRASE_CASES, "evidence_cases": EVIDENCE_CASES, "contact_cases": CONTACT_CASES, "identity_cases": IDENTITY_CASES, "outreach_cases": OUTREACH_CASES},
                _schema(),
                num_predict=1300,
            )
            overall, tasks = _score(raw)
            grade = "excellent" if overall >= 90 else "strong" if overall >= 75 else "developing" if overall >= 55 else "not_recommended"
            results.append({"model": model, "score": overall, "task_scores": tasks, "seconds": round(time.monotonic() - started, 2), "grade": grade, "status": "complete"})
        except Exception as exc:
            results.append({"model": model, "score": 0, "task_scores": {}, "seconds": round(time.monotonic() - started, 2), "grade": "failed", "status": "failed", "error": str(exc)[:240]})
    payload = {"curriculum_version": ai_curriculum.VERSION, "generated_at": datetime.now(UTC).isoformat(), "status": "complete", "models": sorted(results, key=lambda item: (-item["score"], item["seconds"]))}
    path = ai_curriculum._result_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
