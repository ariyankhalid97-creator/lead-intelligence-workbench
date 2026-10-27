"""Post-verification lead cleanup with conservative duplicate and email labels."""

from __future__ import annotations

import json
import re
from urllib.parse import urlparse

import leadfinder as lf
import local_ai

AUTOMATED = {"noreply", "no-reply", "donotreply", "do-not-reply", "mailer-daemon", "postmaster", "webmaster", "bot", "automated", "notifications", "notification", "system"}
SUPPORT = {"support", "help", "helpdesk", "customerservice", "customer-service", "care", "abuse", "privacy", "legal", "security", "complaints"}
GENERAL = {"info", "hello", "contact", "office", "sales", "admin", "booking", "bookings", "quote", "quotes", "estimate", "estimates", "team", "reception", "inquiries", "enquiries"}


def _emails(row):
    values = []
    for value in (row.get("email", ""), row.get("emails", "")):
        values.extend(lf.EMAIL_RE.findall(str(value)))
    try:
        evidence = json.loads(row.get("evidence") or "[]")
    except (ValueError, TypeError):
        evidence = []
    for item in evidence if isinstance(evidence, list) else []:
        if isinstance(item, dict) and item.get("field") == "email":
            values.extend(lf.EMAIL_RE.findall(str(item.get("value", ""))))
    return list(dict.fromkeys(value.casefold() for value in values))


def classify_email(address, decision_maker="", domain_check=None):
    if not lf.EMAIL_RE.fullmatch(str(address).strip()):
        return {"email": address, "type": "invalid", "recommended": False, "basis": "syntax_check", "deliverability": "not_tested"}
    address = address.casefold()
    local = address.split("@", 1)[0]
    compact = re.sub(r"[^a-z0-9]", "", local)
    tokens = {x for x in re.split(r"[._+\-]+", local) if x}
    name_tokens = {x for x in re.findall(r"[a-z]+", decision_maker.casefold()) if len(x) > 1}
    if local in AUTOMATED or compact in {re.sub(r"\W", "", x) for x in AUTOMATED}:
        kind, recommended, basis = "automated", False, "known_automated_local_part"
    elif local in SUPPORT or compact in {re.sub(r"\W", "", x) for x in SUPPORT}:
        kind, recommended, basis = "support", False, "known_support_local_part"
    elif local in GENERAL:
        kind, recommended, basis = "general_business", True, "known_general_business_local_part"
    elif name_tokens and tokens & name_tokens:
        kind, recommended, basis = "possible_direct", True, "published_address_matches_saved_person_name"
    elif len(tokens) >= 2 and all(token.isalpha() and len(token) > 1 for token in tokens):
        kind, recommended, basis = "possible_direct", True, "name_like_local_part"
    else:
        kind, recommended, basis = "uncertain", True, "published_valid_address_not_known_support_or_automated"
    status = (domain_check or {}).get("status", "not_checked")
    if status in {"invalid_domain", "null_mx", "no_mail_route_observed"}:
        kind, recommended, basis = "unsendable_domain", False, "mail_domain_has_no_usable_mx"
        deliverability = "domain_unsendable"
    elif status in {"mx_present", "a_fallback_present"}:
        deliverability = "mail_domain_ready_mailbox_unverified"
    elif status == "temporary_dns_unavailable":
        deliverability = "domain_check_temporary_failure"
    else:
        deliverability = "not_tested"
    return {"email": address, "type": kind, "recommended": recommended, "basis": basis, "deliverability": deliverability, "domain_status": status}


def inferred_permutations(row, published):
    """Generate review-only candidates from an observed domain pattern."""
    name = re.findall(r"[a-z]+", str(row.get("decision_maker", "")).casefold())
    if len(name) < 2 or not published:
        return []
    first, last = name[0], name[-1]
    by_domain = {}
    for address in published:
        local, domain = address.split("@", 1)
        by_domain.setdefault(domain, []).append(local)
    candidates = []
    for domain, locals_ in by_domain.items():
        patterns = []
        if any(re.fullmatch(r"[a-z]+\.[a-z]+", local) for local in locals_): patterns.append(f"{first}.{last}")
        if any(re.fullmatch(r"[a-z][a-z]{2,}", local) for local in locals_): patterns.append(first[0] + last)
        if any(local == first for local in locals_): patterns.append(first)
        for local in patterns:
            address = f"{local}@{domain}"
            if address not in published:
                candidates.append({"email": address, "type": "inferred_permutation", "recommended": False, "basis": "inferred_from_published_domain_pattern_not_observed", "deliverability": "unverified", "domain_status": "not_checked"})
    return list({item["email"]: item for item in candidates}.values())[:3]


def _normal(value):
    return re.sub(r"[^a-z0-9]", "", str(value).casefold())


def _host(value):
    try:
        return (urlparse(value).hostname or "").casefold().removeprefix("www.")
    except Exception:
        return ""


def _exact_duplicate(a, b):
    same_name = bool(_normal(a.get("name")) and _normal(a.get("name")) == _normal(b.get("name")))
    same_address = bool(_normal(a.get("address")) and _normal(a.get("address")) == _normal(b.get("address")))
    same_city = bool(_normal(a.get("city")) and _normal(a.get("city")) == _normal(b.get("city")))
    emails_a, emails_b = set(_emails(a)), set(_emails(b))
    if emails_a & emails_b and (same_name or same_address):
        return "same_published_email_and_identity"
    phone_a = re.sub(r"\D", "", str(a.get("phone", "")))[-10:]
    phone_b = re.sub(r"\D", "", str(b.get("phone", "")))[-10:]
    if phone_a and phone_a == phone_b and (same_name or same_address):
        return "same_phone_and_identity"
    host_a, host_b = _host(a.get("website", "")), _host(b.get("website", ""))
    if host_a and host_a == host_b and same_name and (same_city or same_address):
        return "same_domain_name_and_location"
    if same_name and same_address:
        return "same_name_and_address"
    return ""


def _merge(canonical, duplicate, reason):
    skip = {"verification", "ai_analysis", "ai_draft", "email_quality", "duplicate_summary"}
    for key, value in duplicate.items():
        if key not in skip and not canonical.get(key) and value:
            canonical[key] = value
    sources = []
    for value in (canonical.get("sources") or canonical.get("source", ""), duplicate.get("sources") or duplicate.get("source", "")):
        sources.extend(str(value).split("; "))
    canonical["sources"] = "; ".join(dict.fromkeys(filter(None, sources)))
    if not json.loads(canonical.get("verification") or "{}").get("status") and json.loads(duplicate.get("verification") or "{}").get("status"):
        canonical["verification"] = duplicate["verification"]
    if not json.loads(canonical.get("email_quality") or "{}").get("recommended") and json.loads(duplicate.get("email_quality") or "{}").get("recommended"):
        canonical["email_quality"] = duplicate["email_quality"]
    try:
        prior = json.loads(canonical.get("duplicate_summary") or "[]")
    except (ValueError, TypeError):
        prior = []
    prior.append({"name": duplicate.get("name", ""), "source": duplicate.get("source", ""), "source_url": duplicate.get("source_url", ""), "reason": reason})
    canonical["duplicate_summary"] = json.dumps(prior, ensure_ascii=False)


def organize_rows(rows, cancel=None):
    working = [dict(row) for row in rows]
    ai_status = "not_needed"
    ai_error = ""
    ambiguous = []
    for index, row in enumerate(working):
        try:
            verification = json.loads(row.get("verification") or "{}")
        except (TypeError, ValueError):
            verification = {}
        domain_checks = {item.get("email", "").casefold(): item for item in verification.get("email_candidates", []) if isinstance(item, dict)}
        candidates = [classify_email(value, row.get("decision_maker", ""), domain_checks.get(value.casefold())) for value in _emails(row)]
        candidates.extend(inferred_permutations(row, [item["email"] for item in candidates]))
        candidates.sort(key=lambda item: ({"possible_direct": 0, "general_business": 1, "uncertain": 2, "support": 3, "automated": 4, "invalid": 5}.get(item["type"], 6), item["email"]))
        usable = [item for item in candidates if item["recommended"]]
        if candidates:
            row["email"] = usable[0]["email"] if usable else ""
            for item in candidates:
                if item["type"] == "uncertain":
                    ambiguous.append({"row": index, "email": item["email"], "local_part": item["email"].split("@", 1)[0], "business": str(row.get("name", ""))[:100]})
        row["email_quality"] = json.dumps({"recommended": [item for item in candidates if item["recommended"]], "excluded": [item for item in candidates if not item["recommended"]], "note": "Published-address classification only; mailbox deliverability was not tested.", "ai_status": "not_requested"}, ensure_ascii=False)

    if ambiguous and not (cancel and cancel.is_set()):
        status = local_ai.status()
        if status.get("available"):
            try:
                suggestions = local_ai.organize_email_locals(ambiguous[:60], status.get("default_model", ""), cancel)
                ai_status = suggestions.get("status", "error")
                by_row_local = {(item.get("row"), item.get("local_part")): item.get("type") for item in suggestions.get("classifications", [])}
                for index, row in enumerate(working):
                    quality = json.loads(row.get("email_quality") or "{}")
                    for item in quality.get("recommended", []):
                        suggestion = by_row_local.get((index, item["email"].split("@", 1)[0]))
                        if item["type"] == "uncertain" and suggestion in ("possible_direct", "general_business", "uncertain"):
                            item.update(type=suggestion, basis="local_ai_local_part_suggestion_reviewed_by_rules")
                    quality.update(ai_status=ai_status, ai_model=suggestions.get("model", ""))
                    row["email_quality"] = json.dumps(quality, ensure_ascii=False)
            except Exception as exc:
                ai_status = "unavailable"
                ai_error = str(exc)[:500]
        else:
            ai_status = "unavailable"
            ai_error = status.get("message", "Local AI status reported unavailable")[:500]

    kept = []
    merged_count = 0
    for row in working:
        match = None
        for canonical in kept:
            reason = _exact_duplicate(canonical, row)
            if reason:
                match = (canonical, reason)
                break
        if match:
            _merge(match[0], row, match[1])
            merged_count += 1
        else:
            kept.append(row)
    return kept, {"input_records": len(rows), "organized_records": len(kept), "duplicates_consolidated": merged_count, "recommended_email_records": sum(bool(json.loads(row.get("email_quality") or "{}").get("recommended")) for row in kept), "ai_status": ai_status, "ai_error": ai_error, "note": "Exact duplicates were consolidated; original source references remain in duplicate_summary. Email labels do not prove deliverability."}

