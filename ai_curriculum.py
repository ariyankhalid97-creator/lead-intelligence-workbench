"""Reviewed education and benchmark definitions for local research models.

The curriculum is fixed application knowledge, not scraped lead data and not
weight training. It is injected in bounded form so every compatible local
model receives the same epistemic and safety education.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

VERSION = "2026.10.30.2"

FOUNDATIONS = [
    "A search phrase names a concrete provider, service, object or method; it does not use empty marketing labels.",
    "Adjacent services are not synonyms. Shared generic words do not establish niche relevance.",
    "A directory claim, search snippet and first-party page observation have different authority and must stay labeled.",
    "Missing evidence means not observed, never absent, false or unavailable.",
    "Company, parent brand, operating location and person are separate entities until evidence links them.",
    "A syntactically plausible email is not proof of mailbox existence or deliverability.",
    "Historical memory and model suggestions guide research; neither is evidence about a current lead.",
    "Outreach must be grounded, specific, modest and unsent until the user approves it.",
]

TASKS = {
    "planning": {
        "objective": "Produce diverse, concrete, niche-faithful discovery phrases without geography or unsupported platform claims.",
        "rules": [
            "Keep the buyer/provider boundary of the supplied niche.",
            "Prefer terminology that a real business would publish as a service or category.",
            "Reject vague words such as solutions, experts, specialists, pros and vendors unless part of a proper name supplied as data.",
            "Return fewer strong phrases instead of padding the list with adjacent trades.",
        ],
        "examples": [
            {"niche": "commercial kitchen exhaust cleaning", "good": "grease duct cleaning", "bad": "house cleaning", "lesson": "same broad industry is not the same service"},
            {"niche": "employment law firms", "good": "wrongful termination attorney", "bad": "recruiting agency", "lesson": "buyer workflow and professional service must remain distinct"},
            {"niche": "property management companies", "good": "multifamily property management", "bad": "real estate photography", "lesson": "use an operating specialty, not an adjacent supplier"},
        ],
    },
    "evidence": {
        "objective": "Separate published facts, weak claims, unknowns and hypotheses with exact evidence support.",
        "rules": [
            "Only a literal supplied excerpt can support a lead-specific claim.",
            "Search snippets are candidate evidence and should be described with lower confidence.",
            "Never infer budget, pain, staff size, software usage, ownership or intent from silence.",
            "When sources conflict, retain the conflict instead of choosing the convenient value.",
        ],
        "examples": [
            {"evidence": "Our Dallas office provides 24-hour plumbing repair.", "supported": "The page states that the Dallas office provides 24-hour plumbing repair.", "unsupported": "The company urgently needs scheduling software."},
            {"evidence": "No CRM name appears in the captured page.", "supported": "A CRM was not observed in the captured evidence.", "unsupported": "The company does not use a CRM."},
        ],
    },
    "contacts": {
        "objective": "Classify public contact labels conservatively without claiming verification or deliverability.",
        "rules": [
            "Named-looking local parts can be possible_direct only, never confirmed personal or deliverable.",
            "info, hello, sales, office and contact are general business inboxes.",
            "support, help, privacy, abuse, noreply, bot and automated addresses are not outreach recommendations.",
            "Role and decision-maker identity require published evidence; do not infer a person from an email string alone.",
        ],
        "examples": [
            {"email": "jane.smith@example.com", "label": "possible_direct"},
            {"email": "info@example.com", "label": "general_business"},
            {"email": "support@example.com", "label": "excluded_support"},
        ],
    },
    "qualification": {
        "objective": "Assess potential fit from observed business evidence while keeping unknowns explicit.",
        "rules": [
            "Describe a potential fit, not a confirmed need, unless the evidence explicitly states the need.",
            "Separate company characteristics from opportunity hypotheses.",
            "Questions should close evidence gaps rather than smuggle assumptions into the wording.",
            "Independent versus chain status requires ownership or brand evidence, not name style.",
        ],
        "examples": [
            {"observation": "The company publishes online rental applications.", "safe": "A digital application workflow is observed; its signing process remains unknown.", "unsafe": "The company needs an e-signature product."},
        ],
    },
    "outreach": {
        "objective": "Draft concise, human, evidence-grounded outreach that remains approval-gated.",
        "rules": [
            "Use one relevant observed fact and one modest question.",
            "Do not claim familiarity, monitoring, guaranteed results, urgency, exclusivity or a problem not stated by the prospect.",
            "Do not repeat scraped contact details or expose research mechanics in the message.",
            "Return a draft only; never imply it was sent, queued or approved.",
        ],
        "examples": [
            {"observed": "The careers page lists three open leasing roles.", "safe": "I noticed you are hiring for leasing roles. Would it be useful to compare how applicant documents are currently signed?", "unsafe": "Your hiring team is overwhelmed and losing candidates."},
        ],
    },
}


def lesson(*names):
    selected = []
    for name in names:
        item = TASKS.get(name)
        if item:
            selected.append({"name": name, **item})
    return {
        "curriculum_version": VERSION,
        "foundations": FOUNDATIONS,
        "lessons": selected,
        "authority_note": "Education guides reasoning but never replaces current lead evidence or deterministic validation.",
    }


def _result_path():
    root = Path(os.environ.get("LEAD_EXTRACTOR_HOME", Path(__file__).resolve().parent))
    return root.expanduser().resolve() / "data" / "ai_benchmarks.json"


def benchmark_results():
    path = _result_path()
    if not path.exists():
        return {"curriculum_version": VERSION, "models": [], "status": "not_run"}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError):
        return {"curriculum_version": VERSION, "models": [], "status": "unreadable"}
    if not isinstance(value, dict) or value.get("curriculum_version") != VERSION:
        return {"curriculum_version": VERSION, "models": [], "status": "outdated"}
    return value


def benchmark_for(model):
    for item in benchmark_results().get("models", []):
        if isinstance(item, dict) and item.get("model") == model:
            return item
    return {}
