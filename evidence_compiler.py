"""Evidence-bound intelligence schemas, trust weighting and output validation."""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timezone

SOURCE_AUTHORITY = {
    "live_official_website": 1.00,
    "website_dom": 0.95,
    "verified_maps_profile": 0.88,
    "dns_mx": 0.85,
    "smtp_verification": 0.95,
    "recent_social_page": 0.72,
    "public_filing": 0.90,
    "third_party_directory": 0.48,
    "serp_snippet": 0.28,
    "inferred_permutation": 0.18,
}

COMPILER_SYSTEM_PROMPT = """You are the Evidence-Bound Lead Intelligence Compiler for a local-first B2B research engine.
Use only the supplied evidence_ledger. Every claim and signal must cite existing source_evidence_ids and copy a literal verbatim_excerpt. Search snippets are discovery-only. Website emails are not mailbox-valid without smtp_verification status valid. MX proves domain mail capability only. Pixels prove tag installation, not active spend. Missing text means not_observed, never confirmed_absent: omit unsupported claims instead of writing 'no evidence', 'not observed', or similar negative claims. Do not repeat claims. A service claim must cite service evidence, a leadership claim must cite leadership evidence, an ad claim must cite ad/tracking evidence, and the claim statement must share concrete terms with its excerpt. If evidence is insufficient, choose manual_browser_review or contact_discovery and state the gap. Return only valid JSON matching the supplied schema. Never invent names, contacts, attributes, citations or delivery states."""

QUEUE_STATES = {"verification", "contact_discovery", "decision_maker_research", "manual_browser_review", "outreach", "reply_follow_up", "suppression", "customer"}
DELIVERABILITY = {"smtp_valid", "catch_all_risk", "mx_only", "unverified", "invalid"}
CLAIM_STATUS = {"verified_observation", "unverified_snippet", "inferred_permutation"}


def _clean(value, limit=1500):
    return " ".join(str(value or "").split())[:limit]


def source_type(item):
    basis = _clean(item.get("basis") or item.get("method") or item.get("source_type")).casefold()
    url = _clean(item.get("url") or item.get("source_url")).casefold()
    if "snippet" in basis:
        return "serp_snippet"
    if "inferred" in basis:
        return "inferred_permutation"
    if "maps" in basis or "google.com/maps" in url:
        return "verified_maps_profile"
    if "filing" in basis:
        return "public_filing"
    if "social" in basis or any(host in url for host in ("linkedin.com", "facebook.com", "instagram.com")):
        return "recent_social_page"
    if "dns" in basis or "mx" in basis:
        return "dns_mx"
    if "smtp" in basis or "provider_verification" in basis:
        return "smtp_verification"
    if "page" in basis or "structured" in basis or "mailto" in basis:
        return "website_dom"
    return "third_party_directory"


def freshness_weight(captured_at, half_life_days=180):
    try:
        stamp = datetime.fromisoformat(str(captured_at).replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        age = max(0.0, (datetime.now(timezone.utc) - stamp).total_seconds() / 86400)
        return round(max(0.20, math.pow(0.5, age / half_life_days)), 4)
    except (TypeError, ValueError):
        return 0.35


def evidence_claim(company_id, operating_entity_id, job_id, item, captured_at):
    field = _clean(item.get("field") or item.get("kind") or "claim", 80)
    value = _clean(item.get("value") or item.get("text") or item.get("excerpt"))
    url = _clean(item.get("url") or item.get("source_url"), 1500)
    basis = source_type(item)
    observed = _clean(item.get("observed_at") or captured_at, 80)
    excerpt = _clean(item.get("excerpt") or item.get("text") or value, 500)
    seed = "|".join((company_id, field, value, url, basis))
    evidence_id = "ev-" + hashlib.sha256(seed.encode()).hexdigest()[:24]
    authority = SOURCE_AUTHORITY.get(basis, 0.30)
    fresh = freshness_weight(observed)
    return {
        "evidence_id": evidence_id,
        "company_id": company_id,
        "operating_entity_id": operating_entity_id,
        "job_id": job_id,
        "field": field,
        "value": value,
        "source_type": basis,
        "source_url": url,
        "captured_at": observed,
        "verbatim_excerpt": excerpt,
        "selector": _clean(item.get("selector"), 240),
        "authority_weight": authority,
        "freshness_weight": fresh,
        "trust_score": round(authority * fresh, 4),
        "payload": item,
    }


def output_schema():
    citation = {"type": "array", "minItems": 1, "items": {"type": "string"}}
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "canonical_company_id", "operating_location_id", "compiled_claims",
            "contact_readiness", "opportunity_signals", "semantic_change_summary",
            "next_best_action",
        ],
        "properties": {
            "canonical_company_id": {"type": "string"},
            "operating_location_id": {"type": ["string", "null"]},
            "compiled_claims": {
                "type": "array", "maxItems": 30,
                "items": {
                    "type": "object", "additionalProperties": False,
                    "required": ["claim_type", "statement", "verification_status", "confidence_score", "source_evidence_ids", "verbatim_excerpt"],
                    "properties": {
                        "claim_type": {"type": "string", "enum": ["service_offering", "tech_stack", "ad_signal", "hiring_signal", "leadership_change", "review_metric"]},
                        "statement": {"type": "string"},
                        "verification_status": {"type": "string", "enum": sorted(CLAIM_STATUS)},
                        "confidence_score": {"type": "number", "minimum": 0, "maximum": 1},
                        "source_evidence_ids": citation,
                        "verbatim_excerpt": {"type": "string"},
                    },
                },
            },
            "contact_readiness": {
                "type": "object", "additionalProperties": False,
                "required": ["primary_contact_id", "contact_type", "deliverability_state", "eligible_for_outreach"],
                "properties": {
                    "primary_contact_id": {"type": ["string", "null"]},
                    "contact_type": {"type": "string", "enum": ["decision_maker", "generic_role_inbox", "none"]},
                    "deliverability_state": {"type": "string", "enum": sorted(DELIVERABILITY)},
                    "eligible_for_outreach": {"type": "boolean"},
                },
            },
            "opportunity_signals": {
                "type": "array", "maxItems": 20,
                "items": {
                    "type": "object", "additionalProperties": False,
                    "required": ["signal_code", "summary", "source_evidence_ids"],
                    "properties": {"signal_code": {"type": "string"}, "summary": {"type": "string"}, "source_evidence_ids": citation},
                },
            },
            "semantic_change_summary": {
                "type": "object", "additionalProperties": False,
                "required": ["is_material_change", "ignored_noise_fields", "material_changes_detected"],
                "properties": {
                    "is_material_change": {"type": "boolean"},
                    "ignored_noise_fields": {"type": "array", "items": {"type": "string"}},
                    "material_changes_detected": {"type": "array", "items": {"type": "string"}},
                },
            },
            "next_best_action": {
                "type": "object", "additionalProperties": False,
                "required": ["queue_state", "rationale", "recommended_campaign_variant_id"],
                "properties": {
                    "queue_state": {"type": "string", "enum": sorted(QUEUE_STATES)},
                    "rationale": {"type": "string"},
                    "recommended_campaign_variant_id": {"type": ["string", "null"]},
                },
            },
        },
    }


def validate_output(value, ledger):
    if not isinstance(value, dict):
        raise ValueError("Compiler output must be an object")
    required = set(output_schema()["required"])
    if not required.issubset(value):
        raise ValueError("Compiler output is missing required fields")
    evidence = {item["evidence_id"]: item for item in ledger}
    seen_claims = set()
    allowed_fields = {
        "service_offering": {"service", "service_match", "match_reason", "fact", "claim", "description"},
        "tech_stack": {"technology", "technographic", "analytics", "software", "fact", "claim"},
        "ad_signal": {"ad_signal", "advertising", "analytics", "tracking", "fact", "claim"},
        "hiring_signal": {"hiring", "job", "careers", "fact", "claim"},
        "leadership_change": {"leadership", "decision_maker", "decision_maker_role", "owner", "founder", "fact", "claim"},
        "review_metric": {"rating", "reviews", "review_metric", "fact", "claim"},
    }
    negative_without_observation = re.compile(r"\b(?:no evidence|not observed|none found|does not appear|no indication|not found)\b", re.I)
    stop = {"the", "and", "for", "with", "that", "this", "from", "was", "were", "has", "have", "been", "observed", "evidence", "company", "business"}
    for claim in value.get("compiled_claims", []):
        ids = claim.get("source_evidence_ids") or []
        if not ids or any(item not in evidence for item in ids):
            raise ValueError("Compiler claim lacks a valid evidence pointer")
        excerpt = _clean(claim.get("verbatim_excerpt"), 500)
        if not excerpt or not any(excerpt in evidence[item]["verbatim_excerpt"] for item in ids):
            raise ValueError("Compiler claim excerpt is not literal evidence")
        if claim.get("verification_status") not in CLAIM_STATUS:
            raise ValueError("Compiler claim has an invalid verification status")
        statement = _clean(claim.get("statement"), 1000)
        signature = (claim.get("claim_type"), statement.casefold(), tuple(sorted(ids)))
        if signature in seen_claims:
            raise ValueError("Compiler returned a duplicate claim")
        seen_claims.add(signature)
        if negative_without_observation.search(statement):
            raise ValueError("Compiler converted missing evidence into a negative claim")
        permitted = allowed_fields.get(claim.get("claim_type"), set())
        cited_fields = {_clean(evidence[item].get("field"), 80).casefold() for item in ids}
        if permitted and not any(any(token in field for token in permitted) for field in cited_fields):
            raise ValueError("Compiler claim type is not supported by the cited evidence field")
        statement_tokens = {token for token in re.findall(r"[a-z0-9]{4,}", statement.casefold()) if token not in stop}
        excerpt_tokens = {token for token in re.findall(r"[a-z0-9]{4,}", excerpt.casefold()) if token not in stop}
        if statement_tokens and not statement_tokens.intersection(excerpt_tokens):
            raise ValueError("Compiler statement is not textually supported by its cited excerpt")
    for signal in value.get("opportunity_signals", []):
        ids = signal.get("source_evidence_ids") or []
        if not ids or any(item not in evidence for item in ids):
            raise ValueError("Opportunity signal lacks a valid evidence pointer")
    action = value.get("next_best_action", {})
    if action.get("queue_state") not in QUEUE_STATES:
        raise ValueError("Compiler next action is invalid")
    if value.get("contact_readiness", {}).get("deliverability_state") not in DELIVERABILITY:
        raise ValueError("Compiler deliverability state is invalid")
    return value


def deterministic_output(company_id, operating_id, ledger, row, next_action, reason, signals, changed):
    email_quality = row.get("email_quality", {})
    if isinstance(email_quality, str):
        try: email_quality = json.loads(email_quality)
        except ValueError: email_quality = {}
    recommended = email_quality.get("recommended", [])
    chosen = recommended[0] if recommended else {}
    delivery = chosen.get("deliverability", "not_tested")
    delivery_state = "smtp_valid" if delivery == "smtp_valid" else "catch_all_risk" if "catch_all" in delivery else "mx_only" if delivery == "mail_domain_ready_mailbox_unverified" else "invalid" if delivery == "domain_unsendable" else "unverified"
    cited_signals = []
    for signal in signals:
        label = _clean(signal.get("label"))
        source_url = _clean(signal.get("evidence"), 1500)
        match = next((item for item in ledger if item["field"] == "opportunity_signal" and item["value"] == label and (not source_url or item["source_url"] == source_url)), None)
        if match:
            cited_signals.append({"signal_code": signal.get("kind", "observed_signal"), "summary": label, "source_evidence_ids": [match["evidence_id"]]})
    action_map = {"ready_for_outreach": "outreach", "verify_public_sources": "verification", "decision_maker_verification": "decision_maker_research", "suppress": "suppression", "customer": "customer", "reply_follow_up": "reply_follow_up", "contact_discovery": "contact_discovery", "manual_browser_review": "manual_browser_review", "awaiting_reply": "outreach"}
    return {
        "canonical_company_id": company_id,
        "operating_location_id": operating_id or None,
        "compiled_claims": [],
        "contact_readiness": {"primary_contact_id": None, "contact_type": "decision_maker" if row.get("decision_maker") else "generic_role_inbox" if row.get("email") else "none", "deliverability_state": delivery_state, "eligible_for_outreach": bool(chosen and delivery_state not in {"invalid", "catch_all_risk", "unverified"})},
        "opportunity_signals": cited_signals,
        "semantic_change_summary": {"is_material_change": bool(changed), "ignored_noise_fields": ["timestamps", "session_ids", "rotating_reviews", "copyright_years", "ad_nonces"], "material_changes_detected": ["high_signal_public_evidence_changed"] if changed else []},
        "next_best_action": {"queue_state": action_map.get(next_action, next_action if next_action in QUEUE_STATES else "manual_browser_review"), "rationale": reason, "recommended_campaign_variant_id": None},
    }
