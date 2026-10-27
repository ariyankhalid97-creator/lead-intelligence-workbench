"""Editable teaching memory for the optional local Ollama model.

This is deliberately not fine-tuning.  It supplies short, reviewed examples,
domain notes and user-approved terminology at prompt time, while the existing
deterministic validators keep final authority.  Everything stays on disk next
to the app and can be edited or removed by the user.
"""

from __future__ import annotations

import json
import os
import re
import threading
from datetime import UTC, datetime
from pathlib import Path

LOCK = threading.Lock()
MAX_FEEDBACK_BYTES = 2_000_000

_EMAIL = re.compile(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", re.I)
_URL = re.compile(
    r"https?://|www\.|\b[a-z0-9\-]+\.(?:com|net|org|io|co|ai|biz|info)\b", re.I
)
_PHONE = re.compile(r"(?<!\w)(?:\+?\d[\d(). \-]{6,}\d)(?!\w)")
_INSTRUCTIONS = re.compile(
    r"(?:ignore|disregard|override|forget)\s+(?:(?:all|any|the|your|previous|prior|above|system|developer)\s+){0,4}(?:instructions?|prompts?|rules?)"
    r"|(?:system|developer)\s+(?:prompt|message|instructions?)"
    r"|(?:^|\s)(?:role\s*:\s*system|<\|(?:system|assistant|im_start)\|>|tool_call)"
    r"|(?:execute|run)\s+(?:this\s+)?(?:command|script|powershell|shell)",
    re.I,
)
_PHRASE = re.compile(r"[\w\s&'’(),.+/\-]+")

# Curated style packs.  They are examples, not facts, and never replace the
# app's 200-entry niche catalog.  Users can override them per niche in the UI.
CURATED = {
    "hood-cleaning": {
        "name": "Hood Cleaning",
        "terms": [
            "kitchen exhaust cleaning",
            "restaurant hood cleaning",
            "commercial hood degreasing",
            "hood duct cleaning",
            "kitchen hood degreasing",
            "grease duct cleaning",
            "exhaust fan cleaning",
            "NFPA 96 hood cleaning",
        ],
        "avoid": [
            "house cleaning",
            "carpet cleaning",
            "air duct cleaning",
            "hood repair",
            "hood replacement",
            "hood installation",
        ],
        "notes": (
            "In this niche, 'hood' means a commercial kitchen exhaust hood. "
            "Prefer specialist kitchen-exhaust terms used by real providers. "
            "Do not drift into general cleaning, air-duct work, or equipment sales and repair."
        ),
    },
    "roofing": {
        "name": "Roofing",
        "terms": [
            "roof repair contractor",
            "shingle roof replacement",
            "flat roof installer",
            "metal roofing contractor",
            "roof leak repair",
            "residential roofing company",
            "commercial roof coating",
        ],
        "avoid": [
            "roof cleaning",
            "gutter cleaning",
            "roofing specialist",
            "roofing solutions",
            "siding contractor",
        ],
        "notes": "Prefer concrete roof systems, materials and repair work. Avoid broad marketing labels and gutter/siding services.",
    },
    "plumbing": {
        "name": "Plumbing",
        "terms": [
            "emergency plumber",
            "drain cleaning service",
            "water heater repair",
            "sewer line repair",
            "leak detection plumber",
            "repiping contractor",
            "commercial plumbing company",
        ],
        "avoid": [
            "plumbing specialist",
            "plumbing solutions",
            "septic pumping",
            "irrigation repair",
        ],
        "notes": "Name the actual plumbing job or system. Septic and irrigation are adjacent trades, not plumbing unless the evidence says so.",
    },
    "hvac": {
        "name": "HVAC",
        "terms": [
            "air conditioning repair",
            "HVAC installation contractor",
            "furnace repair service",
            "heat pump installer",
            "commercial HVAC service",
            "ductless mini split installer",
            "AC tune up service",
        ],
        "avoid": [
            "HVAC specialist",
            "HVAC solutions",
            "air duct cleaning",
            "appliance repair",
        ],
        "notes": "Use equipment and service terms. Air-duct cleaning and appliance repair are separate services.",
    },
    "electricians": {
        "name": "Electricians",
        "terms": [
            "electrical contractor",
            "emergency electrician",
            "panel upgrade electrician",
            "EV charger installation",
            "commercial electrical service",
            "generator installation",
            "lighting installation contractor",
        ],
        "avoid": [
            "electrical specialist",
            "electrical solutions",
            "solar installer",
            "security system installer",
        ],
        "notes": "Prefer concrete electrical work. Solar and security are adjacent trades unless the niche explicitly includes them.",
    },
    "house-cleaning": {
        "name": "House Cleaning",
        "terms": [
            "residential house cleaning",
            "maid service",
            "recurring house cleaner",
            "deep house cleaning",
            "move out cleaning service",
            "apartment cleaning service",
            "eco friendly house cleaning",
        ],
        "avoid": [
            "commercial cleaning",
            "carpet cleaning",
            "window cleaning",
            "pressure washing",
        ],
        "notes": "Keep the phrase residential and inside-the-home. Commercial, carpet and exterior cleaning are different services.",
    },
    "commercial-cleaning": {
        "name": "Commercial Cleaning",
        "terms": [
            "office cleaning service",
            "commercial janitorial service",
            "building cleaning contractor",
            "medical office cleaning",
            "retail store cleaning",
            "day porter service",
            "post construction cleaning",
        ],
        "avoid": [
            "house cleaning",
            "carpet cleaning",
            "window cleaning",
            "pressure washing",
        ],
        "notes": "Name the facility type or the commercial cleaning method. Do not drift to residential or exterior cleaning.",
    },
    "pressure-washing": {
        "name": "Pressure Washing",
        "terms": [
            "pressure washing service",
            "power washing contractor",
            "soft washing service",
            "driveway pressure washing",
            "roof soft washing",
            "commercial pressure washing",
            "concrete cleaning service",
        ],
        "avoid": [
            "house cleaning",
            "window cleaning",
            "gutter cleaning",
            "roof repair",
        ],
        "notes": "Use exterior-cleaning terms and the surface being cleaned. Avoid interior cleaning and repair services.",
    },
    "landscaping": {
        "name": "Landscaping",
        "terms": [
            "landscape design build",
            "landscape maintenance service",
            "lawn care company",
            "sod installation contractor",
            "irrigation installation",
            "hardscape contractor",
            "commercial landscaping service",
        ],
        "avoid": [
            "tree removal",
            "pest control",
            "pressure washing",
            "landscaping solutions",
        ],
        "notes": "Keep the phrase on landscape design, installation or maintenance. Tree removal and pest control are separate trades.",
    },
    "pest-control": {
        "name": "Pest Control",
        "terms": [
            "pest control service",
            "exterminator company",
            "termite treatment",
            "rodent control service",
            "mosquito control service",
            "bed bug treatment",
            "commercial pest control",
        ],
        "avoid": [
            "wildlife removal",
            "lawn care",
            "pest control solutions",
            "exterminator specialist",
        ],
        "notes": "Name the pest or treatment. Wildlife removal is an adjacent service unless the niche includes it.",
    },
    "solar-installers": {
        "name": "Solar Installers",
        "terms": [
            "solar panel installation",
            "residential solar installer",
            "commercial solar contractor",
            "solar battery installation",
            "rooftop solar company",
            "solar system repair",
            "solar panel cleaning",
        ],
        "avoid": [
            "roofing contractor",
            "electrical contractor",
            "solar solutions",
            "solar specialist",
        ],
        "notes": "Use solar system and installation terms. Roofing and general electrical work are adjacent unless the evidence includes them.",
    },
    "dental-implants": {
        "name": "Dental Implants",
        "terms": [
            "dental implant dentist",
            "implant dentistry clinic",
            "tooth implant surgery",
            "dental implant restoration",
            "implant supported dentures",
            "oral surgeon implants",
            "single tooth implant",
        ],
        "avoid": [
            "endosseous implants",
            "titanium tooth roots",
            "dental restoration surgery",
            "general dentistry",
        ],
        "notes": "Use terms patients and implant providers actually use. Avoid obscure clinical material names and general dentistry.",
    },
    "accountants": {
        "name": "Accountants",
        "terms": [
            "CPA firm",
            "small business accountant",
            "bookkeeping and tax service",
            "tax preparation firm",
            "payroll accounting service",
            "audit and assurance firm",
            "virtual accounting firm",
        ],
        "avoid": [
            "financial advisor",
            "tax software",
            "accounting solutions",
            "accountant specialist",
        ],
        "notes": "Name the accounting service and client type. Financial advice and software are adjacent categories.",
    },
    "web-design-agencies": {
        "name": "Web Design Agencies",
        "terms": [
            "web design agency",
            "website development company",
            "WordPress design agency",
            "ecommerce website developer",
            "UX design studio",
            "custom web application agency",
            "local SEO web design",
        ],
        "avoid": [
            "graphic designer",
            "SEO agency",
            "web design solutions",
            "web design specialist",
        ],
        "notes": "Keep the phrase on website design or development. Graphic design and standalone SEO are adjacent services.",
    },
    "auto-repair": {
        "name": "Auto Repair",
        "terms": [
            "auto repair shop",
            "car mechanic",
            "brake repair service",
            "engine repair shop",
            "transmission repair service",
            "auto diagnostics shop",
            "mobile mechanic service",
        ],
        "avoid": ["auto body shop", "tire shop", "car wash", "auto repair solutions"],
        "notes": "Name the mechanical repair job. Body work, tires and washing are separate automotive services.",
    },
}

STYLE_RULES = [
    "Return 3-6 short phrases, usually 2-5 words.",
    "Name the concrete service, object, material or method a provider would put in a Maps or website service title.",
    "Prefer specialist terms already supplied in known_service_phrases, specialist_terms and approved_examples.",
    "Do not use marketing adjectives such as solutions, expert, specialist, pro, vendor, best, affordable or reliable.",
    "Do not include cities, states, postal codes, 'near me', quotes, business names or search operators.",
    "Do not suggest adjacent services, equipment sales, repair, training or jobs unless the niche itself is that service.",
    "Use examples for style only. Do not invent a service when no safe specialist term exists.",
]

COMPILE_RULES = [
    "Return at most 4 compiled_claims.",
    "Each claim must state one distinct fact. Never repeat or rephrase the same excerpt in a second claim.",
    "Keep the statement under 240 characters and quote the shortest exact supporting span.",
    "Only fill opportunity_signals when the cited evidence supports a real signal; otherwise return an empty array.",
    "When evidence is thin, choose manual_browser_review or contact_discovery instead of padding with generic signals.",
]


def _slug(value):
    return (
        re.sub(r"[^a-z0-9]+", "-", str(value or "").casefold()).strip("-")[:80]
        or "general"
    )


def _root():
    return (
        Path(os.environ.get("LEAD_EXTRACTOR_HOME", Path(__file__).resolve().parent))
        .expanduser()
        .resolve()
    )


def _feedback_path():
    return _root() / "data" / "ai_feedback.jsonl"


def _clean(value, limit):
    if not isinstance(value, str):
        return ""
    text = re.sub(r"\s+", " ", value).strip()
    if (
        len(text) > limit
        or _EMAIL.search(text)
        or _URL.search(text)
        or _PHONE.search(text)
    ):
        return ""
    if _INSTRUCTIONS.search(text):
        return ""
    return text


def _phrase(value):
    text = _clean(value, 100)
    if not text or len(text) < 2 or not _PHRASE.fullmatch(text):
        return ""
    return text


def _text(value, limit=800):
    if not isinstance(value, str):
        return ""
    text = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    text = "\n".join(" ".join(line.split()) for line in text.splitlines()).strip()
    if len(text) > limit:
        raise ValueError(f"Teaching notes must be {limit} characters or fewer")
    if (
        _EMAIL.search(text)
        or _URL.search(text)
        or _PHONE.search(text)
        or _INSTRUCTIONS.search(text)
    ):
        raise ValueError(
            "Teaching notes cannot contain contact details, links or model instructions"
        )
    return text


def _values(values, limit=20):
    output = []
    for value in values if isinstance(values, list) else []:
        text = _phrase(value)
        if text and text.casefold() not in {item.casefold() for item in output}:
            output.append(text)
        if len(output) >= limit:
            break
    return output


def clean_terms(values, limit=20):
    """Public sanitizer used by the niche-pack API."""
    return _values(values, limit)


def clean_notes(value, limit=800):
    """Public sanitizer used by the niche-pack API."""
    return _text(value, limit)


def _find_curated(niche):
    wanted = _slug(niche)
    if wanted in CURATED:
        return CURATED[wanted]
    words = set(re.findall(r"[a-z0-9]+", str(niche or "").casefold()))
    best = None
    best_score = 0
    for key, pack in CURATED.items():
        candidate = set(re.findall(r"[a-z0-9]+", f"{key} {pack['name']}".casefold()))
        score = len(words & candidate)
        if score > best_score:
            best, best_score = pack, score
    # Require a meaningful overlap; a single generic word is not a match.
    return best if best_score >= 2 else None


def approved_examples(niche, limit=12):
    """Read recent user-approved phrases for this niche from local feedback."""
    wanted = _slug(niche)
    path = _feedback_path()
    if not path.exists():
        return []
    output = []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[-800:]
    except OSError:
        return []
    for raw in reversed(lines):
        try:
            row = json.loads(raw)
        except (TypeError, ValueError):
            continue
        if not isinstance(row, dict) or row.get("accepted") is not True:
            continue
        if _slug(row.get("niche")) != wanted:
            continue
        for phrase in _values(row.get("phrases"), 20):
            if phrase.casefold() not in {item.casefold() for item in output}:
                output.append(phrase)
            if len(output) >= limit:
                return output
    return output


def record_feedback(niche, phrases, accepted, model="", source="phrase_suggestion"):
    """Append a bounded, local training signal. Returns the safe phrases saved."""
    values = _values(phrases, 20)
    if not values:
        return []
    row = {
        "at": datetime.now(UTC).isoformat(),
        "niche": _clean(str(niche or ""), 120) or "General",
        "accepted": bool(accepted),
        "phrases": values,
        "model": _clean(str(model or ""), 120),
        "source": _clean(str(source or ""), 60),
    }
    path = _feedback_path()
    with LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        try:
            if path.stat().st_size > MAX_FEEDBACK_BYTES:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[
                    -2000:
                ]
                path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        except OSError:
            pass
    return values


def context(niche, pack=None):
    """Build the compact teaching context injected into local prompts."""
    pack = pack if isinstance(pack, dict) else {}
    curated = _find_curated(niche) or {}
    approved = _values(pack.get("ai_terms"), 20)
    for phrase in approved_examples(niche, 12):
        if phrase.casefold() not in {item.casefold() for item in approved}:
            approved.append(phrase)
    specialist = _values(pack.get("synonyms"), 12)
    for phrase in _values(pack.get("vertical_search_terms"), 12):
        if phrase.casefold() not in {item.casefold() for item in specialist}:
            specialist.append(phrase)
    for phrase in _values(curated.get("terms"), 12):
        if phrase.casefold() not in {
            item.casefold() for item in approved
        } and phrase.casefold() not in {item.casefold() for item in specialist}:
            specialist.append(phrase)
    avoid = _values(pack.get("ai_avoid"), 20)
    for phrase in _values(curated.get("avoid"), 12):
        if phrase.casefold() not in {item.casefold() for item in avoid}:
            avoid.append(phrase)
    notes = _clean(pack.get("ai_notes"), 800) or str(curated.get("notes") or "")
    result = {
        "approved_examples": approved[:20],
        "specialist_terms": specialist[:12],
        "avoid_terms": avoid[:20],
        "editor_notes": notes[:800],
        "style_rules": list(STYLE_RULES),
    }
    return {key: value for key, value in result.items() if value}


def compile_context(niche, pack=None):
    """Smaller context for the strict evidence compiler."""
    pack = pack if isinstance(pack, dict) else {}
    curated = _find_curated(niche) or {}
    notes = _clean(pack.get("ai_notes"), 500) or str(curated.get("notes") or "")[:500]
    avoid = _values(pack.get("ai_avoid"), 10) or _values(curated.get("avoid"), 10)
    result = {
        "editor_notes": notes,
        "avoid_claims_about": avoid,
        "research_methods_not_evidence": _values(pack.get("search_methods"), 9),
        "technology_names_to_check_not_assume": _values(
            pack.get("technology_signals"), 12
        ),
        "claim_rules": list(COMPILE_RULES),
    }
    return {key: value for key, value in result.items() if value}


def for_display(niche, pack=None):
    """Full teaching view for the dashboard."""
    pack = pack if isinstance(pack, dict) else {}
    curated = _find_curated(niche) or {}
    return {
        "niche": str(pack.get("name") or niche or "General"),
        "notes": _clean(pack.get("ai_notes"), 800) or str(curated.get("notes") or ""),
        "terms": _values(pack.get("ai_terms"), 20),
        "avoid": _values(pack.get("ai_avoid"), 20),
        "approved_examples": approved_examples(niche, 20),
        "curated_terms": _values(curated.get("terms"), 12),
        "curated_avoid": _values(curated.get("avoid"), 12),
        "model": _clean(pack.get("ai_terms_model"), 120),
        "updated_at": _clean(pack.get("ai_terms_updated_at"), 80),
    }


def stats():
    path = _feedback_path()
    total = accepted = rejected = 0
    niches = set()
    if path.exists():
        try:
            for raw in path.read_text(encoding="utf-8", errors="replace").splitlines()[
                -2000:
            ]:
                try:
                    row = json.loads(raw)
                except (TypeError, ValueError):
                    continue
                if not isinstance(row, dict):
                    continue
                total += 1
                accepted += int(row.get("accepted") is True)
                rejected += int(row.get("accepted") is False)
                niches.add(_slug(row.get("niche")))
        except OSError:
            pass
    return {
        "feedback_events": total,
        "accepted_events": accepted,
        "rejected_events": rejected,
        "niches": len(niches),
        "path": str(path),
    }
