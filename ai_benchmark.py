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
    {"id": "e5", "excerpt": "Call our Austin office at 512-555-0100.", "claim": "The Austin office publishes a phone number.", "answer": "supported"},
    {"id": "e6", "excerpt": "Serving commercial clients since 2018.", "claim": "The company serves residential customers.", "answer": "unknown"},
    {"id": "e7", "excerpt": "Online booking is temporarily unavailable.", "claim": "Online booking is currently available.", "answer": "unsupported"},
    {"id": "e8", "excerpt": "Licensed in California: C-12345.", "claim": "The company publishes a California license number.", "answer": "supported"},
    {"id": "e9", "excerpt": "Our team works with owners and property managers.", "claim": "The company only works with property managers.", "answer": "unsupported"},
    {"id": "e10", "excerpt": "Contact hello@north.example for general questions.", "claim": "hello@north.example is a named decision maker.", "answer": "unsupported"},
    {"id": "e11", "excerpt": "Locations: Phoenix and Mesa.", "claim": "The business has a Tucson branch.", "answer": "unsupported"},
    {"id": "e12", "excerpt": "Request a free estimate using our form.", "claim": "The website publishes an estimate request path.", "answer": "supported"},
]
CONTACT_CASES = [
    {"id": "c1", "email": "jane.smith@example.com", "answer": "possible_direct"},
    {"id": "c2", "email": "info@example.com", "answer": "general_business"},
    {"id": "c3", "email": "support@example.com", "answer": "excluded"},
    {"id": "c4", "email": "noreply@example.com", "answer": "excluded"},
    {"id": "c5", "email": "billing@example.com", "answer": "excluded"},
    {"id": "c6", "email": "maria.lopez@example.com", "answer": "possible_direct"},
    {"id": "c7", "email": "hello@example.com", "answer": "general_business"},
    {"id": "c8", "email": "privacy@example.com", "answer": "excluded"},
    {"id": "c9", "email": "owner@example.com", "answer": "possible_direct"},
    {"id": "c10", "email": "contact@example.com", "answer": "general_business"},
    {"id": "c11", "email": "do-not-reply@example.com", "answer": "excluded"},
    {"id": "c12", "email": "unknown", "answer": "uncertain"},
]
IDENTITY_CASES = [
    {"id": "i1", "left": "Acme Roofing | acmeroof.com | 10 Main St Dallas", "right": "Acme Roofing LLC | www.acmeroof.com | 10 Main Street Dallas", "answer": "same_operating_entity"},
    {"id": "i2", "left": "Acme Roofing | acmeroof.com | Dallas", "right": "Acme Roofing | acmeroof.com | Houston", "answer": "same_parent_different_location"},
    {"id": "i3", "left": "Summit Dental | no domain | Austin", "right": "Summit Dental Group | no domain | Round Rock", "answer": "uncertain"},
    {"id": "i4", "left": "Taylor Animal Talent | individual profile", "right": "Taylor Talent Agency | company directory", "answer": "uncertain"},
    {"id": "i5", "left": "North Dental | north.example | Phoenix", "right": "North Dental | north.example | Mesa", "answer": "same_parent_different_location"},
    {"id": "i6", "left": "Blue Plumbing | blue.example | Austin | 512-555-0100", "right": "Blue Plumbing LLC | blue.example | Austin | 512-555-0100", "answer": "same_operating_entity"},
    {"id": "i7", "left": "Summit Roofing | summitroof.example | Denver", "right": "Summit Dental | summitdental.example | Denver", "answer": "different"},
    {"id": "i8", "left": "Oak Rentals | no domain | Tampa", "right": "Oak Rentals | no domain | Orlando", "answer": "uncertain"},
    {"id": "i9", "left": "Ace HVAC | ace.example | 1 Main St", "right": "Ace HVAC | ace.example | 1 Main Street", "answer": "same_operating_entity"},
    {"id": "i10", "left": "Bright Clean | bright.example | Dallas", "right": "Bright Clean | other.example | Dallas", "answer": "uncertain"},
    {"id": "i11", "left": "Metro Storage | metro.example | Houston", "right": "Metro Storage | metro.example | Houston West", "answer": "same_parent_different_location"},
    {"id": "i12", "left": "Jane Smith | individual provider", "right": "Jane Smith Consulting | same phone and city", "answer": "uncertain"},
]
OUTREACH_CASES = [
    {"id": "o1", "evidence": "Careers page lists three leasing openings.", "draft": "I noticed you are hiring for leasing roles. Would comparing your applicant-document signing workflow be useful?", "answer": "safe"},
    {"id": "o2", "evidence": "Careers page lists three leasing openings.", "draft": "Your overwhelmed hiring team is losing candidates because your signing process is broken.", "answer": "unsafe"},
    {"id": "o3", "evidence": "The website publishes an online rental application.", "draft": "I saw your online application option. Is document signing also handled online, or is that still an open question?", "answer": "safe"},
    {"id": "o4", "evidence": "No software names were observed.", "draft": "I know you do not have e-signature software, so you need our platform.", "answer": "unsafe"},
    {"id": "o5", "evidence": "The contact page publishes a general estimate form.", "draft": "I saw your estimate form and wondered how signed approvals are handled after a quote.", "answer": "safe"},
    {"id": "o6", "evidence": "The site lists two office locations.", "draft": "Your rapid expansion must be creating document chaos.", "answer": "unsafe"},
    {"id": "o7", "evidence": "A property manager bio names Jordan Lee as operations director.", "draft": "Jordan, your company bio lists you as operations director. Would a short comparison of approval workflows be useful?", "answer": "safe"},
    {"id": "o8", "evidence": "Only a general inbox is published.", "draft": "I spoke with your CEO and they told me to contact you.", "answer": "unsafe"},
    {"id": "o9", "evidence": "The careers page lists a recruiter opening.", "draft": "I noticed the recruiter opening. Is applicant paperwork part of the role's current workload?", "answer": "safe"},
    {"id": "o10", "evidence": "A directory snippet says the company may offer rentals.", "draft": "I know your rental team processes hundreds of leases every week.", "answer": "unsafe"},
    {"id": "o11", "evidence": "The website publishes a tenant application PDF.", "draft": "I found the tenant application PDF on your website. Would a digital signing option be relevant to review?", "answer": "safe"},
    {"id": "o12", "evidence": "No response-time information was observed.", "draft": "You are losing customers because your team responds too slowly.", "answer": "unsafe"},
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
            "evidence": {"type": "array", "minItems": len(EVIDENCE_CASES), "maxItems": len(EVIDENCE_CASES), "items": _answer_item(["supported", "unsupported", "unknown"])},
            "contacts": {"type": "array", "minItems": len(CONTACT_CASES), "maxItems": len(CONTACT_CASES), "items": _answer_item(["possible_direct", "general_business", "excluded", "uncertain"])},
            "identity": {"type": "array", "minItems": len(IDENTITY_CASES), "maxItems": len(IDENTITY_CASES), "items": _answer_item(["same_operating_entity", "same_parent_different_location", "different", "uncertain"])},
            "outreach": {"type": "array", "minItems": len(OUTREACH_CASES), "maxItems": len(OUTREACH_CASES), "items": _answer_item(["safe", "unsafe"])},
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
        "evidence": round(100 * sum(evidence_rows.get(case["id"]) == case["answer"] for case in EVIDENCE_CASES) / len(EVIDENCE_CASES)),
        "contacts": round(100 * sum(contact_rows.get(case["id"]) == case["answer"] for case in CONTACT_CASES) / len(CONTACT_CASES)),
        "identity": round(100 * sum(identity_rows.get(case["id"]) == case["answer"] for case in IDENTITY_CASES) / len(IDENTITY_CASES)),
        "outreach": round(100 * sum(outreach_rows.get(case["id"]) == case["answer"] for case in OUTREACH_CASES) / len(OUTREACH_CASES)),
    }
    return round(sum(tasks.values()) / len(tasks)), tasks


def _blind(rows, *fields):
    """Return only exam inputs; grading labels never enter the model prompt."""
    return [{key: row[key] for key in ("id", *fields) if key in row} for row in rows]


def _task_schema(name):
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [name],
        "properties": {name: _schema()["properties"][name]},
    }


EVAL_TASKS = (
    ("phrases", PHRASE_CASES, ("niche",), "Give concrete niche-faithful provider or service search phrases without locations."),
    ("evidence", EVIDENCE_CASES, ("excerpt", "claim"), "Use supported only for literal support, unsupported for contradiction or an overclaim, and unknown when the excerpt cannot resolve the claim."),
    ("contacts", CONTACT_CASES, ("email",), "Classify a plausible person-specific address as possible_direct, a role-neutral business inbox as general_business, support/automated/compliance mailboxes as excluded, and malformed or unresolved values as uncertain."),
    ("identity", IDENTITY_CASES, ("left", "right"), "Keep a parent brand separate from its operating locations. Matching strong branch evidence may be same_operating_entity; a shared brand with different locations is same_parent_different_location; use different only with clear conflict and uncertain when evidence is insufficient."),
    ("outreach", OUTREACH_CASES, ("evidence", "draft"), "Safe drafts stay within the supplied evidence and ask rather than inventing pain, scale, absence, guarantees, relationships or private knowledge."),
)


def run(models=None):
    available = [item["name"] for item in local_ai.status().get("models", [])]
    chosen = [name for name in (models or available) if name in available]
    results = []
    for model in chosen:
        started = time.monotonic()
        try:
            raw = {}
            for task_name, cases, fields, instruction in EVAL_TASKS:
                answer = local_ai._generate(
                    model,
                    "You are taking one task from a closed-book lead-research evaluation. Return JSON only. Do not browse or add facts. Preserve every case id. " + instruction,
                    {
                        "evaluation_set": "eval-2026-11",
                        "task": task_name,
                        "cases": _blind(cases, *fields),
                    },
                    _task_schema(task_name),
                    num_predict=650 if task_name == "phrases" else 500,
                )
                raw[task_name] = answer.get(task_name, [])
            overall, tasks = _score(raw)
            grade = "excellent" if overall >= 90 else "strong" if overall >= 75 else "developing" if overall >= 55 else "not_recommended"
            results.append({"model": model, "score": overall, "task_scores": tasks, "seconds": round(time.monotonic() - started, 2), "grade": grade, "status": "complete"})
        except Exception as exc:
            results.append({"model": model, "score": 0, "task_scores": {}, "seconds": round(time.monotonic() - started, 2), "grade": "failed", "status": "failed", "error": str(exc)[:240]})
    payload = {
        "curriculum_version": ai_curriculum.VERSION,
        "evaluation_set": "eval-2026-11",
        "case_count": len(PHRASE_CASES) + len(EVIDENCE_CASES) + len(CONTACT_CASES) + len(IDENTITY_CASES) + len(OUTREACH_CASES),
        "blind": True,
        "separation": {
            "development": "local teaching memory and user corrections",
            "evaluation": "frozen hand-reviewed cases; labels withheld from prompts",
            "grouping": "case-family and evaluation-set date",
        },
        "generated_at": datetime.now(UTC).isoformat(),
        "status": "complete",
        "models": sorted(results, key=lambda item: (-item["score"], item["seconds"])),
    }
    path = ai_curriculum._result_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
