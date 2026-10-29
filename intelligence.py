"""Durable local lead memory, action queue, outcome learning and safety gates."""

from __future__ import annotations

import hashlib
import json
import re
import threading
from collections import Counter
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import ai_brain
import ai_teaching
import engine
import evidence_compiler
import niche_catalog
import research_packs
import sequence_engine
from contacts import now


def _refresh_brain(niche):
    """Keep memory failures isolated from the lead workflow."""
    try:
        return ai_brain.refresh(niche) if _clean(niche) else None
    except Exception:
        return None

OUTCOMES = {
    "delivered",
    "bounced",
    "opened",
    "replied",
    "positive_reply",
    "not_interested",
    "wrong_contact",
    "meeting_booked",
    "customer_won",
    "unsubscribed",
    "sent",
    "failed",
    "referral",
    "out_of_office",
    "hard_bounce",
}
TERMINAL_SUPPRESSIONS = {"bounced", "hard_bounce", "unsubscribed", "wrong_contact"}
WATCH_STOP = threading.Event()
WATCH_THREAD = None


def init():
    """Tables are created by engine.init; seed useful local defaults."""
    ensure_niche_pack("General local services")
    ensure_niche_pack("Hood Cleaning")
    _seed_niche_catalog()
    with engine.connection() as conn:
        payloads = [
            row[0]
            for row in conn.execute(
                "SELECT payload FROM jobs ORDER BY updated_at DESC LIMIT 100"
            )
        ]
    for raw in payloads:
        try:
            job = json.loads(raw)
        except (TypeError, ValueError):
            continue
        if (
            isinstance(job.get("organization"), dict)
            and int(job.get("intelligence_summary", {}).get("schema_version", 0) or 0)
            < 3
        ):
            job["intelligence_summary"] = compile_job(job)
            engine.save(job)


def _clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _normal(value):
    return re.sub(r"[^a-z0-9]", "", _clean(value).casefold())


def _domain(value):
    try:
        return (
            (urlparse(str(value or "")).hostname or "").casefold().removeprefix("www.")
        )
    except ValueError:
        return ""


def _phone(value):
    digits = re.sub(r"\D", "", str(value or ""))
    return digits[-10:] if len(digits) >= 10 else ""


def _json(value, fallback):
    if isinstance(value, type(fallback)):
        return value
    try:
        parsed = json.loads(value or ("[]" if isinstance(fallback, list) else "{}"))
        return parsed if isinstance(parsed, type(fallback)) else fallback
    except (TypeError, ValueError):
        return fallback


def _slug(value):
    return (
        re.sub(r"[^a-z0-9]+", "-", _clean(value).casefold()).strip("-")[:80]
        or "general"
    )


def _default_pack(niche):
    name = _clean(niche) or "General local services"
    synonyms = [name]
    curated = niche_catalog.lookup(name)
    if curated:
        synonyms = curated["synonyms"]
    hood = bool(re.search(r"hood|kitchen exhaust|restaurant exhaust", name, re.I))
    if hood:
        synonyms = [
            "hood cleaning",
            "kitchen exhaust cleaning",
            "restaurant hood cleaning",
            "commercial hood degreasing",
        ]
    methods = research_packs.for_niche(name)
    synonyms = list(
        dict.fromkeys([*synonyms, *methods.get("vertical_search_terms", [])])
    )[:12]
    return {
        "name": name,
        "synonyms": synonyms,
        "exclusions": ["jobs", "training", "equipment for sale", "directory only"],
        "decision_maker_roles": [
            "owner",
            "founder",
            "president",
            "general manager",
            "operations manager",
        ],
        "ideal_signals": [
            "independent operator",
            "published service evidence",
            "reachable website",
            "recent customer activity",
        ],
        "opportunity_signals": [
            "broken contact path",
            "no booking path",
            "weak mobile page",
            "inconsistent contact data",
            "unanswered reviews",
        ],
        "chain_signals": ["locations", "franchise", "corporate", "national network"],
        "source_types": [
            "Google Maps",
            "business website",
            "OpenStreetMap",
            "official public registries",
            "public directory profiles",
            "startup and product directories",
            "hiring signals",
            "ad transparency centers",
            "LinkedIn company profile",
        ],
        "enrichment_waterfall": [
            "existing library",
            "business website",
            "DNS/domain checks",
            "search discovery",
            "maps",
            "official registries",
            "public directories",
            "startup/product profiles",
            "hiring and ad signals",
            "dedicated browser review",
            "local AI interpretation",
            "manual review",
        ],
        "search_methods": methods["search_methods"],
        "review_signals": methods["review_signals"],
        "technology_signals": methods["technology_signals"],
        "vertical_profiles": methods["vertical_profiles"],
        "vertical_search_terms": methods["vertical_search_terms"],
        "method_source": methods["method_source"],
        "ai_terms": [],
        "ai_avoid": [],
        "ai_notes": "",
        "ai_terms_model": "",
        "ai_terms_updated_at": "",
        "version": 2 if curated else 1,
        "generated_by": "curated_200_niche_catalog"
        if curated
        else "deterministic_local_pack",
    }


def _seed_niche_catalog():
    """Insert the curated library in one transaction so desktop startup stays fast."""
    stamp = now()
    with engine.connection() as conn:
        existing = {
            row[0]: row[1]
            for row in conn.execute(
                "SELECT slug,payload FROM intelligence_niche_packs"
            ).fetchall()
        }
        for entry in niche_catalog.entries():
            pack = _default_pack(entry["name"])
            slug = _slug(pack["name"])
            if slug in existing:
                try:
                    saved = json.loads(existing[slug])
                except (TypeError, ValueError):
                    saved = {}
                changed = False
                for key, value in pack.items():
                    if key not in saved:
                        saved[key] = value
                        changed = True
                if changed:
                    conn.execute(
                        "UPDATE intelligence_niche_packs SET payload=?,updated_at=? WHERE slug=?",
                        (json.dumps(saved, ensure_ascii=False), stamp, slug),
                    )
                continue
            conn.execute(
                "INSERT INTO intelligence_niche_packs(slug,name,payload,created_at,updated_at) VALUES(?,?,?,?,?)",
                (
                    slug,
                    pack["name"],
                    json.dumps(pack, ensure_ascii=False),
                    stamp,
                    stamp,
                ),
            )
            existing[slug] = json.dumps(pack, ensure_ascii=False)


def ensure_niche_pack(niche):
    pack = _default_pack(niche)
    slug = _slug(pack["name"])
    stamp = now()
    with engine.connection() as conn:
        row = conn.execute(
            "SELECT payload FROM intelligence_niche_packs WHERE slug=?", (slug,)
        ).fetchone()
        if row:
            saved = json.loads(row[0])
            changed = False
            for key, value in pack.items():
                if key not in saved:
                    saved[key] = value
                    changed = True
            if changed:
                conn.execute(
                    "UPDATE intelligence_niche_packs SET payload=?,updated_at=? WHERE slug=?",
                    (json.dumps(saved, ensure_ascii=False), stamp, slug),
                )
            return saved
        conn.execute(
            "INSERT INTO intelligence_niche_packs(slug,name,payload,created_at,updated_at) VALUES(?,?,?,?,?)",
            (slug, pack["name"], json.dumps(pack, ensure_ascii=False), stamp, stamp),
        )
    return pack


def save_niche_pack(data):
    if not isinstance(data, dict):
        raise ValueError("Enter a valid niche pack")
    name = _clean(data.get("name"))
    if not 2 <= len(name) <= 120:
        raise ValueError("Enter a niche name between 2 and 120 characters")
    slug, stamp = _slug(name), now()
    with engine.connection() as conn:
        old = conn.execute(
            "SELECT created_at,payload FROM intelligence_niche_packs WHERE slug=?",
            (slug,),
        ).fetchone()
    # Start from the saved payload so this form cannot erase AI teaching fields
    # that are edited elsewhere.
    try:
        pack = json.loads(old[1]) if old else {}
    except (TypeError, ValueError):
        pack = {}
    if not isinstance(pack, dict) or not pack:
        pack = _default_pack(name)
    pack["name"] = name
    for key in (
        "synonyms",
        "exclusions",
        "decision_maker_roles",
        "ideal_signals",
        "opportunity_signals",
        "chain_signals",
        "source_types",
        "enrichment_waterfall",
        "search_methods",
        "review_signals",
        "technology_signals",
    ):
        values = data.get(key, pack.get(key, _default_pack(name)[key]))
        if not isinstance(values, list) or len(values) > 30:
            raise ValueError(f"Choose up to 30 {key.replace('_', ' ')}")
        pack[key] = list(
            dict.fromkeys(
                _clean(item) for item in values if 1 < len(_clean(item)) <= 160
            )
        )
    pack.update(version=int(data.get("version", 1) or 1), generated_by="user_approved")
    with engine.connection() as conn:
        conn.execute(
            "INSERT INTO intelligence_niche_packs(slug,name,payload,created_at,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(slug) DO UPDATE SET name=excluded.name,payload=excluded.payload,updated_at=excluded.updated_at",
            (
                slug,
                name,
                json.dumps(pack, ensure_ascii=False),
                old[0] if old else stamp,
                stamp,
            ),
        )
    return slug


def niche_packs():
    with engine.connection() as conn:
        return [
            json.loads(row[0])
            for row in conn.execute(
                "SELECT payload FROM intelligence_niche_packs ORDER BY name"
            )
        ]


def compiled_search_terms(niche, limit=12):
    """Return bounded terminology from already compiled records for this niche."""
    wanted = _clean(niche).casefold()
    terms = []
    with engine.connection() as conn:
        rows = conn.execute(
            "SELECT payload FROM intelligence_companies WHERE lower(niche)=? ORDER BY last_seen DESC LIMIT 200",
            (wanted,),
        ).fetchall()
    for (raw,) in rows:
        row = _json(raw, {})
        value = _clean(row.get("category"))
        if 2 <= len(value) <= 100 and not re.search(
            r"https?://|@|\d{3}[-. )]\d{3}", value, re.I
        ):
            terms.append(value)
    return list(dict.fromkeys(terms))[: max(1, min(int(limit), 20))]


def _save_pack(pack):
    slug, stamp = _slug(pack["name"]), now()
    with engine.connection() as conn:
        conn.execute(
            "UPDATE intelligence_niche_packs SET payload=?,updated_at=? WHERE slug=?",
            (json.dumps(pack, ensure_ascii=False), stamp, slug),
        )
    return pack


def record_ai_search_terms(niche, phrases, model=""):
    """Persist explicitly approved AI terminology for later searches."""
    pack = ensure_niche_pack(niche)
    safe = ai_teaching.clean_terms(phrases, 20)
    pack["synonyms"] = list(dict.fromkeys([*pack.get("synonyms", []), *safe]))[:12]
    pack["ai_terms"] = list(dict.fromkeys([*safe, *pack.get("ai_terms", [])]))[:20]
    pack["ai_terms_model"] = _clean(model)[:120]
    pack["ai_terms_updated_at"] = now()
    return _save_pack(pack)


def ai_teaching_view(niche):
    """Return the effective teaching context for the dashboard."""
    name = _clean(niche)
    if not 2 <= len(name) <= 120:
        raise ValueError("Choose a service between 2 and 120 characters")
    return ai_teaching.for_display(name, ensure_niche_pack(name))


def save_ai_teaching(data):
    """Save reviewed terminology, avoid-list and notes for one niche."""
    if not isinstance(data, dict):
        raise ValueError("Enter valid AI teaching settings")
    niche = _clean(data.get("niche"))
    if not 2 <= len(niche) <= 120:
        raise ValueError("Choose a service between 2 and 120 characters")
    pack = ensure_niche_pack(niche)
    if "terms" in data:
        pack["ai_terms"] = ai_teaching.clean_terms(data.get("terms"), 20)
    if "avoid" in data:
        pack["ai_avoid"] = ai_teaching.clean_terms(data.get("avoid"), 20)
    if "notes" in data:
        pack["ai_notes"] = ai_teaching.clean_notes(data.get("notes"), 800)
    pack["ai_terms_updated_at"] = now()
    _save_pack(pack)
    result = ai_teaching.for_display(niche, pack)
    _refresh_brain(niche)
    return result


def approve_ai_terms(niche, phrases, model="", accepted=True):
    """Record the user's verdict and update the editable niche pack."""
    safe = ai_teaching.clean_terms(phrases, 20)
    if not safe:
        raise ValueError("Choose at least one valid search phrase")
    pack = ensure_niche_pack(niche)
    if accepted:
        pack = record_ai_search_terms(niche, safe, model)
    else:
        pack["ai_avoid"] = list(dict.fromkeys([*safe, *pack.get("ai_avoid", [])]))[:20]
        pack["ai_terms_updated_at"] = now()
        _save_pack(pack)
    ai_teaching.record_feedback(niche, safe, accepted, model)
    result = ai_teaching.for_display(niche, pack)
    _refresh_brain(niche)
    return result


def restore_remembered_contacts(rows):
    """Fill rerun gaps from durable evidence without calling old data freshly verified."""
    restored = 0
    with engine.connection() as conn:
        for row in rows if isinstance(rows, list) else []:
            company_id = _clean(row.get("entity_id"))
            if not company_id:
                for alias in _aliases(row):
                    found = conn.execute(
                        "SELECT company_id FROM intelligence_aliases WHERE alias=?",
                        (alias,),
                    ).fetchone()
                    if found:
                        company_id = found[0]
                        break
            if not company_id:
                continue
            prior = conn.execute(
                "SELECT payload FROM intelligence_companies WHERE id=?", (company_id,)
            ).fetchone()
            contact = conn.execute(
                "SELECT email,phone,name,role,confidence FROM intelligence_contacts WHERE company_id=? AND status='observed' ORDER BY confidence DESC,last_seen DESC LIMIT 1",
                (company_id,),
            ).fetchone()
            if not prior and not contact:
                continue
            prior_row = _json(prior[0], {}) if prior else {}
            restored_fields = []
            if contact:
                for field, value in (
                    ("email", contact[0]),
                    ("phone", contact[1]),
                    ("decision_maker", contact[2]),
                    ("decision_maker_role", contact[3]),
                ):
                    if value and not _clean(row.get(field)):
                        row[field] = value
                        restored_fields.append(field)
                if contact[0] and contact[0] not in str(row.get("emails", "")):
                    row["emails"] = "; ".join(
                        filter(None, [row.get("emails", ""), contact[0]])
                    )
            for field in ("linkedin", "facebook", "instagram"):
                if prior_row.get(field) and not row.get(field):
                    row[field] = prior_row[field]
                    restored_fields.append(field)
            if restored_fields:
                evidence = _json(row.get("evidence"), [])
                for field in restored_fields:
                    evidence.append(
                        {
                            "field": field,
                            "value": row.get(field, ""),
                            "url": prior_row.get("website")
                            or prior_row.get("source_url", ""),
                            "basis": "prior_compiled_evidence_not_rediscovered_on_rerun",
                            "observed_at": prior_row.get("checked_at")
                            or prior_row.get("updated_at", ""),
                        }
                    )
                row["evidence"] = json.dumps(evidence[-200:], ensure_ascii=False)
                row["contact_memory"] = json.dumps(
                    {
                        "status": "restored_from_prior_compiled_evidence",
                        "fields": restored_fields,
                        "company_id": company_id,
                    },
                    ensure_ascii=False,
                )
                restored += 1
    return restored


def apply_niche_pack(lead, pack):
    """Apply only strong, user-editable exclusion rules to a discovered lead.

    Website body text is deliberately excluded from this gate because a footer or
    navigation link containing words such as ``jobs`` must not reject a business.
    """
    if not isinstance(pack, dict):
        return lead
    strong_text = " ".join(
        _clean(getattr(lead, field, "")) for field in ("name", "category")
    ).casefold()
    hits = []
    for phrase in pack.get("exclusions", []):
        phrase = _clean(phrase).casefold()
        if phrase and re.search(
            r"(?<![a-z0-9])" + re.escape(phrase) + r"(?![a-z0-9])", strong_text
        ):
            hits.append(phrase)
    if _clean(getattr(lead, "record_type", "")).casefold() in {
        "directory",
        "directory_only",
    }:
        hits.append("directory only")
    if not hits:
        return lead
    try:
        flags = json.loads(getattr(lead, "quality_flags", "[]") or "[]")
    except (TypeError, ValueError):
        flags = []
    flags.extend("niche_exclusion:" + item for item in hits)
    lead.quality_flags = json.dumps(list(dict.fromkeys(flags)), ensure_ascii=False)
    lead.match_status = "candidate"
    reason = "Niche-pack exclusion matched a strong business field: " + ", ".join(
        dict.fromkeys(hits)
    )
    lead.match_reason = (getattr(lead, "match_reason", "") + "; " + reason).strip("; ")
    return lead


def _aliases(row):
    domain = _domain(row.get("website"))
    phone = _phone(row.get("phone"))
    name = _normal(row.get("name"))
    city = _normal(row.get("city") or row.get("search_location"))
    aliases = []
    if domain:
        aliases.append("domain:" + domain)
    if phone and name:
        aliases.append("phone-name:" + phone + ":" + name[:40])
    if name and city:
        aliases.append("name-place:" + name + ":" + city)
    source = _clean(row.get("source_url"))
    if "google." in source and "/maps" in source:
        aliases.append("maps-url:" + hashlib.sha256(source.encode()).hexdigest()[:24])
    return aliases


def _entity_id(conn, row):
    aliases = _aliases(row)
    for alias in aliases:
        found = conn.execute(
            "SELECT company_id FROM intelligence_aliases WHERE alias=?", (alias,)
        ).fetchone()
        if found:
            return found[0], aliases
    seed = (
        aliases[0]
        if aliases
        else "record:"
        + "|".join(
            (
                _normal(row.get("name")),
                _normal(row.get("address")),
                _normal(row.get("city")),
            )
        )
    )
    return "company-" + hashlib.sha256(seed.encode()).hexdigest()[:20], aliases


def _identity_hierarchy(row, company_id):
    domain = _domain(row.get("website"))
    brand_seed = "domain:" + domain if domain else "name:" + _normal(row.get("name"))
    parent_id = "brand-" + hashlib.sha256(brand_seed.encode()).hexdigest()[:20]
    locality = _normal(
        row.get("address") or row.get("city") or row.get("search_location")
    )
    place = (
        _clean(row.get("source_id"))
        if "google" in _clean(row.get("source")).casefold()
        else ""
    )
    operating_seed = "|".join(
        (parent_id, locality, place, _phone(row.get("phone")), company_id)
    )
    operating_id = (
        "operating-" + hashlib.sha256(operating_seed.encode()).hexdigest()[:20]
    )
    operator = _clean(row.get("operator_type")).casefold()
    ownership = (
        "independent"
        if operator in {"independent", "solo", "owner_operator"}
        else "franchise"
        if "franchise" in operator
        else "corporate_branch"
        if operator in {"chain", "corporate"}
        else "unknown"
    )
    return parent_id, operating_id, locality, place, ownership


def website_audit(row):
    report = _json(row.get("verification"), {})
    audit = _json(report.get("website_audit"), {})
    website = (
        report.get("website", {}) if isinstance(report.get("website"), dict) else {}
    )
    if not audit:
        audit = {
            "status": website.get("status", "not_checked"),
            "url": website.get("final_url") or row.get("website", ""),
            "contact_form": "unknown",
            "booking_path": "unknown",
            "mobile_viewport": "unknown",
            "structured_data": "unknown",
            "analytics": "unknown",
            "accessibility_image_alt": "unknown",
            "basis": "verification_summary_only",
        }
    return audit


def _contact_confidence(row):
    quality = _json(row.get("email_quality"), {})
    email = _clean(row.get("email")).casefold()
    recommended = any(
        _clean(item.get("email")).casefold() == email
        and item.get("recommended") is True
        for item in quality.get("recommended", [])
        if isinstance(item, dict)
    )
    score = 0
    reasons = []
    if email:
        score += 25
        reasons.append("published email")
    if recommended:
        score += 25
        reasons.append("recommended email class")
    if email and _domain(row.get("website")) == email.rsplit("@", 1)[-1].removeprefix(
        "www."
    ):
        score += 20
        reasons.append("email matches website domain")
    if _phone(row.get("phone")):
        score += 15
        reasons.append("usable phone")
    if _clean(row.get("decision_maker")):
        score += 15
        reasons.append("published decision-maker")
    return min(100, score), reasons


def _signals(row, audit, changed=False, pack=None):
    signals = []

    def add(kind, label, evidence, strength="candidate"):
        signals.append(
            {"kind": kind, "label": label, "evidence": evidence, "strength": strength}
        )

    if audit.get("status") == "reachable":
        if audit.get("contact_form") is False:
            add(
                "missing_contact_form", "No contact form observed", audit.get("url", "")
            )
        if audit.get("booking_path") is False:
            add(
                "missing_booking",
                "No booking or estimate path observed",
                audit.get("url", ""),
            )
        if audit.get("mobile_viewport") is False:
            add(
                "mobile_gap",
                "Mobile viewport declaration not observed",
                audit.get("url", ""),
            )
        if audit.get("analytics") is False:
            add(
                "analytics_gap",
                "Common analytics tags not observed",
                audit.get("url", ""),
            )
        if audit.get("broken_contact_links"):
            add(
                "broken_contact_path",
                "A contact link appears malformed",
                audit.get("url", ""),
                "supported",
            )
    if changed:
        add(
            "public_data_changed",
            "Public lead evidence changed since the previous compiled snapshot",
            row.get("website") or row.get("source_url"),
            "supported",
        )
    reviews = (
        _json(row.get("verification"), {}).get("reviews", {}).get("google_maps", {})
    )
    try:
        count = int(float(reviews.get("review_count") or row.get("reviews") or 0))
    except (TypeError, ValueError):
        count = 0
    if count:
        add(
            "review_activity",
            f"{count} Google review(s) listed",
            reviews.get("url", ""),
            "observed",
        )
    try:
        rating = float(reviews.get("rating") or row.get("rating") or 0)
    except (TypeError, ValueError):
        rating = 0
    if rating and rating < 4 and count >= 20:
        add(
            "reputation_opportunity",
            f"Observed rating {rating:g} across {count} listed reviews",
            reviews.get("url") or row.get("source_url", ""),
            "observed",
        )
    source_text = " ".join(
        str(row.get(key) or "") for key in ("source", "source_url", "profile_url")
    ).casefold()
    if not _clean(row.get("website")) and any(
        marker in source_text for marker in ("google", "maps", "place")
    ):
        add(
            "website_not_supplied",
            "Collected listing supplied no website; verify before treating it as absent",
            row.get("source_url") or row.get("profile_url", ""),
            "candidate",
        )
    pack = pack if isinstance(pack, dict) else {}
    evidence_payload = " ".join(
        str(row.get(key) or "")
        for key in ("evidence", "observations", "verification", "website_audit")
    )
    for technology in research_packs.observed_technologies(
        evidence_payload, pack.get("technology_signals", [])
    ):
        add(
            "technology_observed",
            f"Published evidence mentions {technology}",
            row.get("website") or row.get("source_url", ""),
            "observed",
        )
    return signals


def _latest_outcomes(conn, company_id, email):
    return [
        row[0]
        for row in conn.execute(
            "SELECT outcome FROM intelligence_outcomes WHERE company_id=? OR (email<>'' AND email=?) ORDER BY created_at DESC,id DESC LIMIT 20",
            (company_id, email.casefold()),
        )
    ]


def _next_action(row, outcomes, confidence):
    if any(item in TERMINAL_SUPPRESSIONS for item in outcomes):
        return (
            "suppress",
            100,
            "A bounce, unsubscribe or wrong-contact outcome requires suppression.",
        )
    if "customer_won" in outcomes:
        return "customer", 5, "This prospect is already recorded as a customer."
    if "meeting_booked" in outcomes:
        return "meeting_booked", 15, "A meeting is already booked."
    if "positive_reply" in outcomes or "replied" in outcomes:
        return "reply_follow_up", 90, "A reply is recorded and needs a human follow-up."
    if "sent" in outcomes or "delivered" in outcomes:
        return (
            "awaiting_reply",
            55,
            "Outreach was sent; avoid starting a duplicate campaign.",
        )
    verification = _json(row.get("verification"), {})
    if verification.get("status") != "complete":
        return (
            "verify_public_sources",
            85,
            "Second-round verification has not completed.",
        )
    if verification.get("website", {}).get("status") not in (
        "reachable",
        "not_provided",
    ):
        return (
            "manual_browser_review",
            80,
            "The website could not be confirmed automatically.",
        )
    if confidence < 50:
        return (
            "contact_discovery",
            75,
            "No sufficiently supported outreach contact is available.",
        )
    if not _clean(row.get("decision_maker")):
        return (
            "decision_maker_verification",
            65,
            "A usable contact exists, but the responsible person is unknown.",
        )
    return (
        "ready_for_outreach",
        70,
        "Verified evidence and a recommended contact are available.",
    )


def _snapshot(row, audit):
    return {
        "name": row.get("name", ""),
        "website": row.get("website", ""),
        "phone": row.get("phone", ""),
        "email": row.get("email", ""),
        "address": row.get("address", ""),
        "rating": row.get("rating", ""),
        "reviews": row.get("reviews", ""),
        "socials": {
            key: row.get(key, "") for key in ("linkedin", "facebook", "instagram")
        },
        "audit": audit,
    }


def compile_job(job):
    """Compile organized rows into canonical local memory and annotate each row."""
    rows = job.get("rows", [])
    niche = job.get("params", {}).get("niche", "General local services")
    pack = ensure_niche_pack(niche)
    stamp = now()
    summary = Counter()
    with engine.connection() as conn:
        for row in rows:
            company_id, aliases = _entity_id(conn, row)
            parent_id, operating_id, locality_key, place_id, ownership_scope = (
                _identity_hierarchy(row, company_id)
            )
            prior = conn.execute(
                "SELECT first_seen,payload FROM intelligence_companies WHERE id=?",
                (company_id,),
            ).fetchone()
            audit = website_audit(row)
            snapshot = _snapshot(row, audit)
            fingerprint = hashlib.sha256(
                json.dumps(snapshot, sort_keys=True, ensure_ascii=False).encode()
            ).hexdigest()
            watch = conn.execute(
                "SELECT fingerprint FROM intelligence_watch_snapshots WHERE company_id=?",
                (company_id,),
            ).fetchone()
            changed = bool(watch and watch[0] != fingerprint)
            score, confidence_reasons = _contact_confidence(row)
            outcomes = _latest_outcomes(conn, company_id, _clean(row.get("email")))
            action, priority, reason = _next_action(row, outcomes, score)
            signals = _signals(row, audit, changed, pack)
            intelligence = {
                "entity_id": company_id,
                "parent_brand_id": parent_id,
                "operating_entity_id": operating_id,
                "identity_aliases": aliases,
                "contact_confidence": score,
                "contact_confidence_reasons": confidence_reasons,
                "next_best_action": action,
                "next_action_reason": reason,
                "opportunity_signals": signals,
                "change_detected": changed,
                "niche_pack": pack.get("name"),
                "compiled_at": stamp,
            }
            row.update(
                entity_id=company_id,
                parent_brand_id=parent_id,
                operating_entity_id=operating_id,
                contact_confidence=score,
                next_best_action=action,
                next_action_reason=reason,
                website_audit=json.dumps(audit, ensure_ascii=False),
                opportunity_signals=json.dumps(signals, ensure_ascii=False),
                intelligence=json.dumps(intelligence, ensure_ascii=False),
            )
            payload = json.dumps(row, ensure_ascii=False)
            conn.execute(
                "INSERT INTO intelligence_companies(id,name,domain,phone,address,city,niche,payload,first_seen,last_seen) VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,domain=excluded.domain,phone=excluded.phone,address=excluded.address,city=excluded.city,niche=excluded.niche,payload=excluded.payload,last_seen=excluded.last_seen",
                (
                    company_id,
                    _clean(row.get("name")),
                    _domain(row.get("website")),
                    _phone(row.get("phone")),
                    _clean(row.get("address")),
                    _clean(row.get("city")),
                    niche,
                    payload,
                    prior[0] if prior else stamp,
                    stamp,
                ),
            )
            conn.execute(
                "INSERT INTO intelligence_parent_brands(id,name,domain,payload,first_seen,last_seen) VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,domain=excluded.domain,payload=excluded.payload,last_seen=excluded.last_seen",
                (
                    parent_id,
                    _clean(row.get("name")),
                    _domain(row.get("website")),
                    json.dumps(
                        {
                            "name": _clean(row.get("name")),
                            "domain": _domain(row.get("website")),
                            "basis": "shared_domain_or_canonical_name",
                        },
                        ensure_ascii=False,
                    ),
                    prior[0] if prior else stamp,
                    stamp,
                ),
            )
            conn.execute(
                "INSERT INTO intelligence_operating_entities(id,parent_brand_id,company_id,locality_key,place_id,ownership_scope,payload,first_seen,last_seen) VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET parent_brand_id=excluded.parent_brand_id,company_id=excluded.company_id,locality_key=excluded.locality_key,place_id=excluded.place_id,ownership_scope=excluded.ownership_scope,payload=excluded.payload,last_seen=excluded.last_seen",
                (
                    operating_id,
                    parent_id,
                    company_id,
                    locality_key,
                    place_id,
                    ownership_scope,
                    json.dumps(
                        {
                            "name": _clean(row.get("name")),
                            "address": _clean(row.get("address")),
                            "city": _clean(row.get("city")),
                            "phone": _phone(row.get("phone")),
                            "source_url": _clean(row.get("source_url")),
                        },
                        ensure_ascii=False,
                    ),
                    prior[0] if prior else stamp,
                    stamp,
                ),
            )
            address = _clean(row.get("address"))
            city = _clean(row.get("city") or row.get("search_location"))
            if address or city:
                location_id = (
                    "location-"
                    + hashlib.sha256(
                        (
                            company_id + ":" + _normal(address) + ":" + _normal(city)
                        ).encode()
                    ).hexdigest()[:20]
                )
                conn.execute(
                    "INSERT INTO intelligence_locations(id,company_id,address,city,source_url,first_seen,last_seen) VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET source_url=excluded.source_url,last_seen=excluded.last_seen",
                    (
                        location_id,
                        company_id,
                        address,
                        city,
                        _clean(row.get("source_url"))[:1500],
                        stamp,
                        stamp,
                    ),
                )
            for alias in aliases:
                conn.execute(
                    "INSERT OR IGNORE INTO intelligence_aliases(alias,company_id,created_at) VALUES(?,?,?)",
                    (alias, company_id, stamp),
                )
            email = _clean(row.get("email")).casefold()
            if email or _phone(row.get("phone")):
                if email:
                    conn.execute(
                        "UPDATE intelligence_contacts SET status='superseded' WHERE company_id=? AND email<>'' AND email<>? AND status='observed'",
                        (company_id, email),
                    )
                contact_seed = email or (
                    _phone(row.get("phone")) + ":" + _normal(row.get("decision_maker"))
                )
                contact_id = (
                    "contact-"
                    + hashlib.sha256(
                        (company_id + ":" + contact_seed).encode()
                    ).hexdigest()[:20]
                )
                contact_payload = {
                    "quality": _json(row.get("email_quality"), {}),
                    "sources": row.get("sources") or row.get("source", ""),
                }
                conn.execute(
                    "INSERT INTO intelligence_contacts(id,company_id,email,phone,name,role,confidence,status,payload,first_seen,last_seen) VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET email=excluded.email,phone=excluded.phone,name=excluded.name,role=excluded.role,confidence=excluded.confidence,status=excluded.status,payload=excluded.payload,last_seen=excluded.last_seen",
                    (
                        contact_id,
                        company_id,
                        email,
                        _phone(row.get("phone")),
                        _clean(row.get("decision_maker")),
                        _clean(row.get("decision_maker_role") or row.get("role")),
                        score,
                        "suppressed" if action == "suppress" else "observed",
                        json.dumps(contact_payload, ensure_ascii=False),
                        stamp,
                        stamp,
                    ),
                )
            evidence = _json(row.get("evidence"), []) + _json(row.get("facts"), [])
            evidence.extend(
                {
                    "field": "opportunity_signal",
                    "value": signal.get("label", ""),
                    "url": signal.get("evidence", ""),
                    "basis": "website_audit_observation",
                    "observed_at": stamp,
                }
                for signal in signals
                if signal.get("label")
            )
            strict_ledger = []
            for item in evidence[:100]:
                if not isinstance(item, dict):
                    continue
                field = _clean(item.get("field") or item.get("kind") or "claim")[:80]
                value = _clean(
                    item.get("value") or item.get("text") or item.get("excerpt")
                )[:1000]
                if not value:
                    continue
                conn.execute(
                    "INSERT OR IGNORE INTO intelligence_evidence(company_id,job_id,field,value,source_url,basis,observed_at) VALUES(?,?,?,?,?,?,?)",
                    (
                        company_id,
                        job.get("id", ""),
                        field,
                        value,
                        _clean(item.get("url"))[:1500],
                        _clean(
                            item.get("basis")
                            or item.get("method")
                            or item.get("status")
                        )[:120],
                        _clean(item.get("observed_at")) or stamp,
                    ),
                )
                claim = evidence_compiler.evidence_claim(
                    company_id, operating_id, job.get("id", ""), item, stamp
                )
                strict_ledger.append(claim)
                conn.execute(
                    "INSERT OR REPLACE INTO intelligence_evidence_claims(evidence_id,company_id,operating_entity_id,job_id,field,value,source_type,source_url,captured_at,verbatim_excerpt,selector,authority_weight,freshness_weight,trust_score,payload) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        claim["evidence_id"],
                        company_id,
                        operating_id,
                        job.get("id", ""),
                        claim["field"],
                        claim["value"],
                        claim["source_type"],
                        claim["source_url"],
                        claim["captured_at"],
                        claim["verbatim_excerpt"],
                        claim["selector"],
                        claim["authority_weight"],
                        claim["freshness_weight"],
                        claim["trust_score"],
                        json.dumps(claim["payload"], ensure_ascii=False),
                    ),
                )
            compiler_output = evidence_compiler.deterministic_output(
                company_id,
                operating_id,
                strict_ledger,
                row,
                action,
                reason,
                signals,
                changed,
            )
            evidence_compiler.validate_output(compiler_output, strict_ledger)
            row["evidence_ids"] = json.dumps(
                [claim["evidence_id"] for claim in strict_ledger], ensure_ascii=False
            )
            row["compiler_output"] = json.dumps(compiler_output, ensure_ascii=False)
            row["source_trust"] = json.dumps(
                sorted(
                    (
                        {
                            "evidence_id": claim["evidence_id"],
                            "source_type": claim["source_type"],
                            "trust_score": claim["trust_score"],
                        }
                        for claim in strict_ledger
                    ),
                    key=lambda item: item["trust_score"],
                    reverse=True,
                ),
                ensure_ascii=False,
            )
            conn.execute(
                "UPDATE intelligence_companies SET payload=? WHERE id=?",
                (json.dumps(row, ensure_ascii=False), company_id),
            )
            conn.execute(
                "INSERT INTO intelligence_queue(company_id,action,priority,reason,status,updated_at) VALUES(?,?,?,?,?,?) ON CONFLICT(company_id) DO UPDATE SET action=excluded.action,priority=excluded.priority,reason=excluded.reason,status=excluded.status,updated_at=excluded.updated_at",
                (
                    company_id,
                    action,
                    priority,
                    reason,
                    "closed" if action in {"customer", "meeting_booked"} else "open",
                    stamp,
                ),
            )
            conn.execute(
                "INSERT INTO intelligence_watch_snapshots(company_id,fingerprint,payload,observed_at,changed_at) VALUES(?,?,?,?,?) ON CONFLICT(company_id) DO UPDATE SET fingerprint=excluded.fingerprint,payload=excluded.payload,observed_at=excluded.observed_at,changed_at=CASE WHEN intelligence_watch_snapshots.fingerprint<>excluded.fingerprint THEN excluded.observed_at ELSE intelligence_watch_snapshots.changed_at END",
                (
                    company_id,
                    fingerprint,
                    json.dumps(snapshot, ensure_ascii=False),
                    stamp,
                    stamp if changed else "",
                ),
            )
            website_url = _clean(row.get("website"))
            if website_url:
                next_run = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
                conn.execute(
                    "INSERT INTO intelligence_watch_schedule(company_id,url,next_run) VALUES(?,?,?) ON CONFLICT(company_id) DO UPDATE SET url=excluded.url",
                    (company_id, website_url, next_run),
                )
            summary[action] += 1
            summary["changes_detected"] += int(changed)
            summary["opportunity_signals"] += len(signals)
    brain = _refresh_brain(niche)
    return {
        "schema_version": 3,
        "compiled_entities": len(rows),
        "actions": dict(summary),
        "changes_detected": summary["changes_detected"],
        "opportunity_signals": summary["opportunity_signals"],
        "niche_pack": pack.get("name"),
        "compiled_at": stamp,
        "consistency_memory": {
            "updated": bool(brain),
            "confidence": (brain or {}).get("confidence", "unavailable"),
            "source_runs": (brain or {}).get("source_runs", 0),
        },
    }


def record_outcome(data):
    if not isinstance(data, dict):
        raise ValueError("Enter a valid outcome")
    outcome = _clean(data.get("outcome")).casefold()
    if outcome not in OUTCOMES:
        raise ValueError("Choose a supported outreach outcome")
    company_id = _clean(data.get("company_id"))[:80]
    email = _clean(data.get("email")).casefold()[:320]
    campaign_id = _clean(data.get("campaign_id"))[:80]
    note = _clean(data.get("note"))[:500]
    if not company_id and not email:
        raise ValueError("Choose a company or email for this outcome")
    stamp = now()
    with engine.connection() as conn:
        if not company_id and email:
            row = conn.execute(
                "SELECT company_id FROM intelligence_contacts WHERE email=? ORDER BY last_seen DESC LIMIT 1",
                (email,),
            ).fetchone()
            company_id = row[0] if row else ""
        conn.execute(
            "INSERT INTO intelligence_outcomes(company_id,email,campaign_id,outcome,note,created_at) VALUES(?,?,?,?,?,?)",
            (company_id, email, campaign_id, outcome, note, stamp),
        )
        if outcome in TERMINAL_SUPPRESSIONS and email:
            conn.execute(
                "INSERT INTO outreach_suppressions(email,reason,created_at) VALUES(?,?,?) ON CONFLICT(email) DO UPDATE SET reason=excluded.reason",
                (email, f"Outcome: {outcome}", stamp),
            )
            conn.execute(
                "INSERT INTO outreach_dnc(scope,value,reason,source,created_at) VALUES('email',?,?,?,?) ON CONFLICT(scope,value) DO UPDATE SET reason=excluded.reason,source=excluded.source",
                (email, f"Outcome: {outcome}", "outcome_learning", stamp),
            )
        if company_id:
            if outcome == "referral":
                referred_email = _clean(data.get("referred_email")).casefold()[:320]
                referred_name = _clean(data.get("referred_name"))[:160]
                if referred_email and re.fullmatch(
                    r"[^\s@]+@[^\s@]+\.[^\s@]+", referred_email
                ):
                    contact_id = (
                        "contact-"
                        + hashlib.sha256(
                            (company_id + ":" + referred_email).encode()
                        ).hexdigest()[:20]
                    )
                    conn.execute(
                        "INSERT INTO intelligence_contacts(id,company_id,email,phone,name,role,confidence,status,payload,first_seen,last_seen) VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,role=excluded.role,status=excluded.status,payload=excluded.payload,last_seen=excluded.last_seen",
                        (
                            contact_id,
                            company_id,
                            referred_email,
                            "",
                            referred_name,
                            _clean(data.get("referred_role"))[:160],
                            20,
                            "referred_unverified",
                            json.dumps(
                                {
                                    "source": "reply_referral",
                                    "verification_required": True,
                                },
                                ensure_ascii=False,
                            ),
                            stamp,
                            stamp,
                        ),
                    )
            action_map = {
                "positive_reply": ("reply_follow_up", 100, "Positive reply recorded."),
                "replied": ("reply_follow_up", 95, "Reply recorded."),
                "meeting_booked": ("meeting_booked", 20, "Meeting booked."),
                "customer_won": ("customer", 5, "Customer won."),
                "sent": ("awaiting_reply", 55, "Outreach sent."),
                "referral": (
                    "contact_discovery",
                    90,
                    "Referral captured; verify the referred contact before outreach.",
                ),
                "out_of_office": (
                    "awaiting_reply",
                    45,
                    "Out-of-office reply recorded; sequence paused until the stated return date.",
                ),
            }
            action, priority, reason = (
                action_map.get(
                    outcome,
                    ("suppress", 100, f"Outcome requires suppression: {outcome}."),
                )
                if outcome in TERMINAL_SUPPRESSIONS or outcome in action_map
                else ("review_outcome", 70, f"Review recorded outcome: {outcome}.")
            )
            conn.execute(
                "INSERT INTO intelligence_queue(company_id,action,priority,reason,status,updated_at) VALUES(?,?,?,?,?,?) ON CONFLICT(company_id) DO UPDATE SET action=excluded.action,priority=excluded.priority,reason=excluded.reason,status=excluded.status,updated_at=excluded.updated_at",
                (
                    company_id,
                    action,
                    priority,
                    reason,
                    "closed"
                    if action in {"customer", "meeting_booked", "suppress"}
                    else "open",
                    stamp,
                ),
            )
    sequence_engine.apply_outcome(company_id, email, outcome, data)
    if company_id:
        with engine.connection() as conn:
            niche_row = conn.execute(
                "SELECT niche FROM intelligence_companies WHERE id=?", (company_id,)
            ).fetchone()
        if niche_row:
            _refresh_brain(niche_row[0])
    return {"recorded": True, "company_id": company_id, "outcome": outcome}


def add_dnc(scope, value, reason="Manual do-not-contact"):
    scope = _clean(scope).casefold()
    value = _clean(value).casefold()
    if scope not in {"email", "domain", "parent_brand", "operating_entity"}:
        raise ValueError("Choose a valid DNC scope")
    if scope == "email" and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
        raise ValueError("Enter a valid email address")
    if scope == "domain":
        value = value.removeprefix("www.")
        if not re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,}", value):
            raise ValueError("Enter a valid domain")
    with engine.connection() as conn:
        conn.execute(
            "INSERT INTO outreach_dnc(scope,value,reason,source,created_at) VALUES(?,?,?,?,?) ON CONFLICT(scope,value) DO UPDATE SET reason=excluded.reason,source=excluded.source",
            (scope, value, _clean(reason)[:300], "manual", now()),
        )
    return {"scope": scope, "value": value, "suppressed": True}


def dnc_entries():
    with engine.connection() as conn:
        return [
            dict(zip(("scope", "value", "reason", "source", "created_at"), row))
            for row in conn.execute(
                "SELECT scope,value,reason,source,created_at FROM outreach_dnc ORDER BY created_at DESC"
            )
        ]


def record_email_verification(data):
    if not isinstance(data, dict):
        raise ValueError("Enter a valid verification result")
    email = _clean(data.get("email")).casefold()
    status = _clean(data.get("status")).casefold()
    provider = _clean(data.get("provider"))[:120]
    if (
        not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email)
        or status not in {"valid", "invalid", "catch_all", "spam_trap", "unknown"}
        or not provider
    ):
        raise ValueError(
            "Email, provider and supported verification status are required"
        )
    with engine.connection() as conn:
        conn.execute(
            "INSERT INTO email_verifications(email,status,provider,checked_at,evidence) VALUES(?,?,?,?,?)",
            (
                email,
                status,
                provider,
                now(),
                json.dumps(data.get("evidence", {}), ensure_ascii=False),
            ),
        )
        if status in {"invalid", "spam_trap"}:
            conn.execute(
                "INSERT INTO outreach_dnc(scope,value,reason,source,created_at) VALUES('email',?,?,?,?) ON CONFLICT(scope,value) DO UPDATE SET reason=excluded.reason,source=excluded.source",
                (email, f"Mailbox verification: {status}", provider, now()),
            )
    return {"email": email, "status": status, "provider": provider}


def queue(limit=200):
    limit = max(1, min(int(limit), 500))
    with engine.connection() as conn:
        rows = conn.execute(
            "SELECT q.company_id,c.name,c.city,c.niche,c.payload,q.action,q.priority,q.reason,q.status,q.updated_at FROM intelligence_queue q JOIN intelligence_companies c ON c.id=q.company_id ORDER BY CASE q.status WHEN 'open' THEN 0 ELSE 1 END,q.priority DESC,q.updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [
        {
            "company_id": r[0],
            "name": r[1],
            "city": r[2],
            "niche": r[3],
            "lead": json.loads(r[4]),
            "action": r[5],
            "priority": r[6],
            "reason": r[7],
            "status": r[8],
            "updated_at": r[9],
        }
        for r in rows
    ]


def entity(company_id):
    with engine.connection() as conn:
        row = conn.execute(
            "SELECT payload,first_seen,last_seen FROM intelligence_companies WHERE id=?",
            (company_id,),
        ).fetchone()
        if not row:
            return None
        contacts = [
            dict(
                zip(
                    (
                        "id",
                        "email",
                        "phone",
                        "name",
                        "role",
                        "confidence",
                        "status",
                        "first_seen",
                        "last_seen",
                    ),
                    item,
                )
            )
            for item in conn.execute(
                "SELECT id,email,phone,name,role,confidence,status,first_seen,last_seen FROM intelligence_contacts WHERE company_id=? ORDER BY confidence DESC,last_seen DESC",
                (company_id,),
            )
        ]
        locations = [
            dict(
                zip(
                    ("id", "address", "city", "source_url", "first_seen", "last_seen"),
                    item,
                )
            )
            for item in conn.execute(
                "SELECT id,address,city,source_url,first_seen,last_seen FROM intelligence_locations WHERE company_id=? ORDER BY last_seen DESC",
                (company_id,),
            )
        ]
        evidence = [
            dict(
                zip(
                    ("field", "value", "source_url", "basis", "observed_at", "job_id"),
                    item,
                )
            )
            for item in conn.execute(
                "SELECT field,value,source_url,basis,observed_at,job_id FROM intelligence_evidence WHERE company_id=? ORDER BY CASE WHEN field IN ('email','phone','decision_maker','decision_maker_role') THEN 0 WHEN field='opportunity_signal' THEN 2 ELSE 1 END,id DESC LIMIT 200",
                (company_id,),
            )
        ]
        outcomes = [
            dict(zip(("outcome", "email", "campaign_id", "note", "created_at"), item))
            for item in conn.execute(
                "SELECT outcome,email,campaign_id,note,created_at FROM intelligence_outcomes WHERE company_id=? ORDER BY created_at DESC,id DESC LIMIT 100",
                (company_id,),
            )
        ]
        checkpoints = [
            dict(zip(("service", "url", "status", "detail", "updated_at"), item))
            for item in conn.execute(
                "SELECT service,url,status,detail,updated_at FROM intelligence_browser_checkpoints WHERE company_id=? ORDER BY updated_at DESC,id DESC LIMIT 50",
                (company_id,),
            )
        ]
        hierarchy = [
            dict(
                zip(
                    (
                        "operating_entity_id",
                        "parent_brand_id",
                        "locality_key",
                        "place_id",
                        "ownership_scope",
                        "payload",
                        "first_seen",
                        "last_seen",
                    ),
                    item,
                )
            )
            for item in conn.execute(
                "SELECT id,parent_brand_id,locality_key,place_id,ownership_scope,payload,first_seen,last_seen FROM intelligence_operating_entities WHERE company_id=? ORDER BY last_seen DESC",
                (company_id,),
            )
        ]
        strict_evidence = [
            dict(
                zip(
                    (
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
                    ),
                    item,
                )
            )
            for item in conn.execute(
                "SELECT evidence_id,field,value,source_type,source_url,captured_at,verbatim_excerpt,authority_weight,freshness_weight,trust_score FROM intelligence_evidence_claims WHERE company_id=? ORDER BY trust_score DESC,captured_at DESC LIMIT 300",
                (company_id,),
            )
        ]
    return {
        "company": json.loads(row[0]),
        "first_seen": row[1],
        "last_seen": row[2],
        "locations": locations,
        "operating_entities": hierarchy,
        "contacts": contacts,
        "evidence": evidence,
        "evidence_claims": strict_evidence,
        "outcomes": outcomes,
        "browser_checkpoints": checkpoints,
    }


def browser_checkpoint(data):
    if not isinstance(data, dict):
        raise ValueError("Enter a valid browser checkpoint")
    service = _clean(data.get("service")).casefold()
    status = _clean(data.get("status")).casefold()
    allowed = {
        "opened",
        "login_required",
        "security_check",
        "data_found",
        "not_found",
        "manual_review",
        "failed",
        "complete",
    }
    if (
        service not in {"maps", "linkedin", "facebook", "website", "other"}
        or status not in allowed
    ):
        raise ValueError("Choose a valid browser service and checkpoint status")
    with engine.connection() as conn:
        cursor = conn.execute(
            "INSERT INTO intelligence_browser_checkpoints(company_id,service,url,status,detail,updated_at) VALUES(?,?,?,?,?,?)",
            (
                _clean(data.get("company_id"))[:80],
                service,
                _clean(data.get("url"))[:1500],
                status,
                _clean(data.get("detail"))[:500],
                now(),
            ),
        )
        company_id = _clean(data.get("company_id"))[:80]
        if company_id:
            company = conn.execute(
                "SELECT payload FROM intelligence_companies WHERE id=?", (company_id,)
            ).fetchone()
            if company:
                lead = json.loads(company[0])
                if status in {"complete", "data_found"}:
                    if int(lead.get("contact_confidence") or 0) >= 50:
                        action, priority, reason = (
                            "ready_for_outreach",
                            70,
                            "Manual browser review completed; retained contact evidence is ready for campaign review.",
                        )
                    else:
                        action, priority, reason = (
                            "contact_discovery",
                            75,
                            "Manual browser review completed, but no sufficiently supported contact is available.",
                        )
                elif status == "not_found":
                    action, priority, reason = (
                        "contact_discovery",
                        75,
                        "Manual review found no usable public contact.",
                    )
                elif status in {"login_required", "security_check", "failed"}:
                    action, priority, reason = (
                        "manual_browser_review",
                        85,
                        f"Browser review paused: {status.replace('_', ' ')}.",
                    )
                else:
                    action = priority = reason = None
                if action:
                    conn.execute(
                        "UPDATE intelligence_queue SET action=?,priority=?,reason=?,status='open',updated_at=? WHERE company_id=?",
                        (action, priority, reason, now(), company_id),
                    )
    return cursor.lastrowid


def experiment_results(campaign_id):
    with engine.connection() as conn:
        rows = conn.execute(
            "SELECT e.variant,o.outcome,count(*) FROM intelligence_experiments e LEFT JOIN intelligence_outcomes o ON o.campaign_id=e.campaign_id AND o.company_id=e.company_id WHERE e.campaign_id=? GROUP BY e.variant,o.outcome ORDER BY e.variant,o.outcome",
            (campaign_id,),
        ).fetchall()
    variants = {}
    for variant, outcome, count in rows:
        item = variants.setdefault(variant, {"assigned": 0, "outcomes": {}})
        if outcome:
            item["outcomes"][outcome] = count
        else:
            item["assigned"] += count
    # A company with outcomes does not appear in the NULL row, so count assignments separately.
    with engine.connection() as conn:
        assigned = dict(
            conn.execute(
                "SELECT variant,count(*) FROM intelligence_experiments WHERE campaign_id=? GROUP BY variant",
                (campaign_id,),
            ).fetchall()
        )
    for variant, count in assigned.items():
        variants.setdefault(variant, {"assigned": 0, "outcomes": {}})["assigned"] = (
            count
        )
    return {
        "campaign_id": campaign_id,
        "variants": variants,
        "note": "Observed outcomes by persistently assigned campaign variant; small samples are not conclusive.",
    }


def run_due_watches(limit=3):
    """Revisit a few due public websites while the local app is running."""
    from contacts import conditional_page_diagnostic

    current = now()
    limit = max(1, min(int(limit), 10))
    with engine.connection() as conn:
        due = conn.execute(
            "SELECT company_id,url,fingerprint,interval_days FROM intelligence_watch_schedule WHERE enabled=1 AND next_run<=? ORDER BY next_run LIMIT ?",
            (current, limit),
        ).fetchall()
    results = []
    for company_id, url, previous, interval_days in due:
        status, error, changed, fingerprint = "complete", "", False, previous
        try:
            with engine.connection() as conn:
                old_http = conn.execute(
                    "SELECT etag,last_modified,semantic_payload FROM intelligence_watch_http WHERE company_id=?",
                    (company_id,),
                ).fetchone()
            etag, last_modified, previous_semantic = (
                old_http if old_http else ("", "", "{}")
            )
            response = conditional_page_diagnostic(url, etag, last_modified)
            if response["not_modified"]:
                status = "not_modified"
                semantic = _json(previous_semantic, {})
            else:
                body = response["body"]
                visible = re.sub(
                    r"<script\b[\s\S]*?</script>|<style\b[\s\S]*?</style>",
                    " ",
                    body,
                    flags=re.I,
                )
                visible = re.sub(
                    r"\b(?:19|20)\d{2}\b|\b\d{1,2}:\d{2}(?::\d{2})?\b|(?:session|nonce|cache|timestamp)[-_=:]\w+",
                    " ",
                    visible,
                    flags=re.I,
                )
                semantic = {
                    "emails": sorted(
                        set(
                            re.findall(
                                r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}",
                                visible,
                                re.I,
                            )
                        )
                    )[:50],
                    "phones": sorted(
                        set(re.findall(r"(?:\+?\d[\d(). \-]{6,}\d)", visible))
                    )[:50],
                    "leadership": sorted(
                        set(
                            re.findall(
                                r"[A-Z][a-z]+\s+[A-Z][a-z]+\s*[,|\-–]\s*(?:Owner|Founder|President|CEO|General Manager|Operations Manager)",
                                visible,
                            )
                        )
                    )[:30],
                    "service_headings": sorted(
                        set(
                            re.findall(
                                r"<h[1-3][^>]*>(.*?)</h[1-3]>", visible, re.I | re.S
                            )
                        )
                    )[:50],
                    "tech": sorted(
                        name
                        for name, pattern in (
                            ("meta_pixel", r"connect\.facebook\.net|\bfbq\s*\("),
                            (
                                "google_tag",
                                r"googletagmanager\.com|google-analytics\.com|\bAW-\d+",
                            ),
                            ("linkedin_insight", r"snap\.licdn\.com"),
                        )
                        if re.search(pattern, body, re.I)
                    ),
                }
                semantic["service_headings"] = [
                    re.sub(r"<[^>]+>|\s+", " ", value).strip()[:240]
                    for value in semantic["service_headings"]
                ]
                old_semantic = _json(previous_semantic, {})
                changed = bool(old_http and semantic != old_semantic)
                fingerprint = hashlib.sha256(
                    json.dumps(semantic, sort_keys=True).encode()
                ).hexdigest()
                url = response["final_url"]
                with engine.connection() as conn:
                    conn.execute(
                        "INSERT INTO intelligence_watch_http(company_id,etag,last_modified,semantic_payload,checked_at) VALUES(?,?,?,?,?) ON CONFLICT(company_id) DO UPDATE SET etag=excluded.etag,last_modified=excluded.last_modified,semantic_payload=excluded.semantic_payload,checked_at=excluded.checked_at",
                        (
                            company_id,
                            response.get("etag", ""),
                            response.get("last_modified", ""),
                            json.dumps(semantic, ensure_ascii=False),
                            current,
                        ),
                    )
        except Exception as exc:
            status, error = "failed", str(exc)[:300]
        next_run = (
            datetime.now(timezone.utc)
            + timedelta(days=max(1, min(int(interval_days), 365)))
        ).isoformat()
        with engine.connection() as conn:
            conn.execute(
                "UPDATE intelligence_watch_schedule SET url=?,fingerprint=?,last_run=?,next_run=?,status=?,last_error=? WHERE company_id=?",
                (url, fingerprint, current, next_run, status, error, company_id),
            )
            if changed:
                conn.execute(
                    "UPDATE intelligence_watch_snapshots SET changed_at=? WHERE company_id=?",
                    (current, company_id),
                )
                conn.execute(
                    "UPDATE intelligence_queue SET action='manual_browser_review',priority=90,reason='The monitored public website changed; review new evidence before outreach.',status='open',updated_at=? WHERE company_id=?",
                    (current, company_id),
                )
        results.append(
            {
                "company_id": company_id,
                "url": url,
                "status": status,
                "changed": changed,
                "error": error,
                "phase": "conditional_http_then_semantic_diff",
            }
        )
    return results


def watcher_status():
    with engine.connection() as conn:
        total, due, changed = conn.execute(
            "SELECT count(*),sum(CASE WHEN enabled=1 AND next_run<=? THEN 1 ELSE 0 END),sum(CASE WHEN status='complete' THEN 1 ELSE 0 END) FROM intelligence_watch_schedule",
            (now(),),
        ).fetchone()
    return {
        "scheduled": total or 0,
        "due": due or 0,
        "checked": changed or 0,
        "running": bool(WATCH_THREAD and WATCH_THREAD.is_alive()),
        "note": "Public websites are rechecked every 30 days while the desktop app is running.",
    }


def start_watcher():
    global WATCH_THREAD
    if WATCH_THREAD and WATCH_THREAD.is_alive():
        return
    WATCH_STOP.clear()

    def loop():
        while not WATCH_STOP.is_set():
            try:
                run_due_watches()
            except Exception:
                pass
            WATCH_STOP.wait(3600)

    WATCH_THREAD = threading.Thread(
        target=loop, name="lead-intelligence-watcher", daemon=True
    )
    WATCH_THREAD.start()


def variant_index(row, campaign_id, count, position=None):
    if count <= 1:
        return 0
    company_id = (
        _clean(row.get("entity_id"))
        or hashlib.sha256(
            (_clean(row.get("email")) + _clean(row.get("name"))).encode()
        ).hexdigest()[:20]
    )
    # The recipient list is frozen with the campaign. Round-robin assignment is
    # balanced for small campaigns and the persisted row makes it stable.
    index = (
        position % count
        if isinstance(position, int)
        else int(
            hashlib.sha256((campaign_id + ":" + company_id).encode()).hexdigest()[:8],
            16,
        )
        % count
    )
    with engine.connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO intelligence_experiments(campaign_id,company_id,variant,created_at) VALUES(?,?,?,?)",
            (campaign_id, company_id, chr(65 + index), now()),
        )
    return index


def preflight(row, address, job_id="", exclude_campaign_id=""):
    issues = []
    company_id = _clean(row.get("entity_id"))
    if _clean(row.get("next_best_action")) in {
        "suppress",
        "customer",
        "meeting_booked",
        "awaiting_reply",
    }:
        issues.append(f"next action is {row.get('next_best_action')}")
    with engine.connection() as conn:
        domain = address.casefold().rsplit("@", 1)[-1] if "@" in address else ""
        dnc = conn.execute(
            "SELECT scope,reason FROM outreach_dnc WHERE (scope='email' AND value=?) OR (scope='domain' AND value=?) OR (scope='parent_brand' AND value=?) OR (scope='operating_entity' AND value=?) LIMIT 1",
            (
                address.casefold(),
                domain,
                _clean(row.get("parent_brand_id")),
                _clean(row.get("operating_entity_id")),
            ),
        ).fetchone()
        if dnc:
            issues.append(f"do-not-contact {dnc[0]} suppression: {dnc[1]}")
        mailbox = conn.execute(
            "SELECT status,provider FROM email_verifications WHERE email=? ORDER BY checked_at DESC,id DESC LIMIT 1",
            (address.casefold(),),
        ).fetchone()
        if mailbox and mailbox[0] in {"invalid", "spam_trap", "unknown"}:
            issues.append(f"mailbox verification is {mailbox[0]} ({mailbox[1]})")
        if mailbox and mailbox[0] == "catch_all":
            corroborated = conn.execute(
                "SELECT 1 FROM intelligence_outcomes WHERE email=? AND outcome IN ('replied','positive_reply','meeting_booked','customer_won') LIMIT 1",
                (address.casefold(),),
            ).fetchone()
            if not corroborated:
                issues.append(
                    "catch-all mailbox requires manual review or a corroborating reply"
                )
        outcomes = _latest_outcomes(conn, company_id, address)
        if any(item in TERMINAL_SUPPRESSIONS for item in outcomes):
            issues.append("terminal contact outcome recorded")
        if company_id:
            recent = conn.execute(
                "SELECT 1 FROM outreach_messages m JOIN outreach_campaigns c ON c.id=m.campaign_id WHERE lower(m.recipient)=? AND m.status IN ('draft','queued','drafting','sent') AND m.campaign_id<>? LIMIT 1",
                (address.casefold(), exclude_campaign_id),
            ).fetchone()
            if recent:
                issues.append("recipient already exists in an active or sent campaign")
    return {
        "eligible": not issues,
        "issues": issues,
        "company_id": company_id,
        "job_id": job_id,
    }


def overview():
    with engine.connection() as conn:
        companies = conn.execute(
            "SELECT count(*) FROM intelligence_companies"
        ).fetchone()[0]
        contacts = conn.execute(
            "SELECT count(*) FROM intelligence_contacts"
        ).fetchone()[0]
        evidence = conn.execute(
            "SELECT count(*) FROM intelligence_evidence"
        ).fetchone()[0]
        changes = conn.execute(
            "SELECT count(*) FROM intelligence_watch_snapshots WHERE changed_at<>''"
        ).fetchone()[0]
        actions = dict(
            conn.execute(
                "SELECT action,count(*) FROM intelligence_queue WHERE status='open' GROUP BY action"
            ).fetchall()
        )
        outcomes = dict(
            conn.execute(
                "SELECT outcome,count(*) FROM intelligence_outcomes GROUP BY outcome"
            ).fetchall()
        )
        by_niche = {}
        for niche, outcome, count in conn.execute(
            "SELECT COALESCE(NULLIF(c.niche,''),'Unknown'),o.outcome,count(*) FROM intelligence_outcomes o LEFT JOIN intelligence_companies c ON c.id=o.company_id GROUP BY COALESCE(NULLIF(c.niche,''),'Unknown'),o.outcome"
        ):
            by_niche.setdefault(niche, {})[outcome] = count
        packs = conn.execute(
            "SELECT count(*) FROM intelligence_niche_packs"
        ).fetchone()[0]
        experiments = conn.execute(
            "SELECT count(DISTINCT campaign_id) FROM intelligence_experiments"
        ).fetchone()[0]
    sent = outcomes.get("sent", 0) + outcomes.get("delivered", 0)
    positive = (
        outcomes.get("positive_reply", 0)
        + outcomes.get("meeting_booked", 0)
        + outcomes.get("customer_won", 0)
    )
    return {
        "companies": companies,
        "contacts": contacts,
        "evidence_claims": evidence,
        "changes_detected": changes,
        "open_actions": actions,
        "outcomes": outcomes,
        "performance": {
            "sent_or_delivered": sent,
            "positive_outcomes": positive,
            "positive_rate": round(100 * positive / sent, 1) if sent else None,
            "by_niche": by_niche,
            "note": "Observed campaign outcomes only; not a prediction.",
        },
        "niche_packs": packs,
        "experiments": experiments,
        "watcher": watcher_status(),
    }
