"""Conservative, source-linked prospect research adapted from the user's Tedt method.

Opportunity points describe collected evidence under an explicit sales profile.
They are neither a probability of conversion nor a prediction of purchasing power.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

WEIGHTS = {"pain": 25, "fit": 20, "access": 20, "capacity": 20, "underserved": 15}
PROFILES = {
    "general": {
        "id": "general",
        "name": "General service research",
        "description": "Collect published workflow and owner signals without applying a sales-offer rubric.",
        "weights": {},
    },
    "hood_automation": {
        "id": "hood_automation",
        "name": "Hood-report automation opportunity",
        "description": "Evidence-backed opportunity points for a photo/report/repair-quote automation offer, adapted from your Tedt research.",
        "weights": WEIGHTS,
    },
}


def profile_metadata(profile_id="general"):
    if profile_id not in PROFILES:
        raise ValueError("Choose a supported research profile")
    return {**PROFILES[profile_id], "weights": dict(PROFILES[profile_id]["weights"])}


def _records(value):
    try:
        records = json.loads(value or "[]")
        return (
            [r for r in records if isinstance(r, dict)]
            if isinstance(records, list)
            else []
        )
    except (ValueError, TypeError):
        return []


def _host(url):
    return (urlparse(url or "").hostname or "").casefold().removeprefix("www.")


def _name(value):
    """Only an explicit personal name, not a role, company, or navigation label."""
    value = re.sub(r"\s+", " ", str(value)).strip()
    words = value.split()
    if words and words[0] in ("Meet", "Contact", "Call"):
        words = words[1:]
        value = " ".join(words)
    rejected = {
        "about",
        "contact",
        "company",
        "cleaning",
        "cleaners",
        "hood",
        "exhaust",
        "services",
        "service",
        "team",
        "owner",
        "founder",
        "president",
        "manager",
        "our",
        "your",
        "support",
        "staff",
        "login",
        "unknown",
        "us",
        "inc",
        "llc",
        "customer",
        "sales",
    }
    if not 2 <= len(words) <= 4 or any(
        w.casefold().strip(".,") in rejected for w in words
    ):
        return ""
    if not all(
        re.fullmatch(r"[A-Z][A-Za-z'’\-]{1,25}", w) and re.search("[a-z]", w)
        for w in words
    ):
        return ""
    return value


def collect_signals(lead, visible, url, structured_people=None):
    """Persist compact first-party-page claims, independently of capped observations.

    Call only for a business page that was actually fetched. A named software
    mention is not proof of adoption; a missing software mention proves nothing.
    Named people additionally require the page to match the business website host.
    """
    text = re.sub(r"\s+", " ", str(visible or ""))
    records = _records(getattr(lead, "workflow_signals", "[]"))

    def add(kind, value, start=0, end=0, excerpt=None):
        item = {
            "kind": kind,
            "value": str(value),
            "excerpt": (
                excerpt if excerpt is not None else text[max(0, start - 75) : end + 100]
            )[:300],
            "url": url,
            "basis": "published_page_claim",
        }
        if not any(
            all(r.get(k) == item[k] for k in ("kind", "value", "url")) for r in records
        ):
            records.append(item)

    patterns = {
        "hood_service": r"\b(?:hood[- ]clean(?:ing|ers?)|(?:kitchen|restaurant) exhaust clean(?:ing|ers?))\b",
        "phone_quotes": r"\b(?:quotes?|estimates?)\s+(?:(?:available|provided|offered)\s+)?(?:over|by|on)\s+(?:the\s+)?phone\b",
        "reporting": r"\b(?:(?:written|service|inspection|detailed|photo[- ]documented)\s+)?reports?\b",
        "photos": r"\b(?:before\s*(?:and|&|/|-)\s*after\s+(?:photos?|pictures?)|photo[- ]document(?:ed|ation)|photographic evidence)\b",
        "repairs": r"\b(?:hinge kits?|access panels?|grease containment|exhaust[- ]fan repairs?|deficiency repair(?:s| quotes)?)\b",
        "recurring": r"\b(?:recurring (?:service|cleaning|maintenance)|maintenance plans?|scheduled (?:hood |exhaust )?cleaning|monthly cleaning|quarterly cleaning)\b",
        "automated_reporting": r"\b(?:(?:automated|automatic|auto[- ]generated) (?:NFPA[- ]?96 |compliance |service )?(?:reports?|reporting|certificates?)|automatically (?:generat\w*|creat\w*|produc\w*)[^.!?]{0,55}\b(?:reports?|certificates?))\b",
        "customer_portal": r"\b(?:customer|client) portal\b",
    }
    for kind, pattern in patterns.items():
        for match in re.finditer(pattern, text, re.I):
            preceding = text[max(0, match.start() - 40) : match.start()]
            if re.search(r"\b(?:no|not|without|never)\b[^.!?]{0,35}$", preceding, re.I):
                continue
            add(kind, match.group(0), match.start(), match.end())
            break

    artifact = r"(?:reports?|quotes?|estimates?)"
    verb = r"(?:writ\w*|prepar\w*|assembl\w*|creat\w*|compil\w*|produc\w*|complet\w*)"
    modifiers = r"(?:\s+(?:the|our|each|every|service|inspection|repair|NFPA|96|customer|written|and)){0,6}\s+"
    # Manual cleaning plus a nearby mention of reports is NOT manual paperwork.
    manual = rf"(?:manually {verb}{modifiers}{artifact}|(?:hand[- ]?written|paper[- ]based|manual)(?: (?:service|inspection|repair|customer))? {artifact}|{artifact}(?: (?:are|is|were|prepared|written|assembled|created|completed|produced|by|us)){{0,4}} (?:written by hand|hand[- ]?written|manually)|manual (?:preparation|assembly|creation|compilation|production|completion|writing) of{modifiers}{artifact})"
    for match in re.finditer(rf"\b{manual}\b", text, re.I):
        context = text[max(0, match.start() - 45) : match.end()]
        subject_context = re.split(
            r"[.!?]", text[max(0, match.start() - 100) : match.start()]
        )[-1]
        others = list(
            re.finditer(
                r"\b(?:competitors?|other (?:companies|providers|contractors|cleaners|businesses)|our customers|their team)\b",
                subject_context,
                re.I,
            )
        )
        self_subject = list(
            re.finditer(
                r"\b(?:we|our team|our technicians|our staff)\b", subject_context, re.I
            )
        )
        if others and (
            not self_subject or others[-1].start() > self_subject[-1].start()
        ):
            continue
        if not re.search(
            r"\b(?:no|not|without|eliminat\w*|replac\w*|automates?)\b[^.!?]{0,45}\b(?:manual(?:ly)?|hand[- ]?written|written by hand|paper[- ]based)",
            context,
            re.I,
        ):
            add("manual_workflow", match.group(0), match.start(), match.end())
            break

    for vendor in (
        "Jobber",
        "Housecall Pro",
        "CompanyCam",
        "QuoteIQ",
        "HoodOps",
        "HoodClean Pro",
        "ServiceTrade",
        "Hood Cleaning Report",
        "Kickserv",
        "ServiceTitan",
        "Workiz",
        "Markate",
    ):
        match = re.search(r"\b" + re.escape(vendor) + r"\b", text, re.I)
        if match:
            add("software", vendor, match.start(), match.end())
    for match in re.finditer(
        r"\b(?:since|founded(?: in)?|established(?: in)?)\s+((?:18|19|20)\d{2})\b",
        text,
        re.I,
    ):
        year = int(match.group(1))
        if 1800 <= year <= datetime.now(timezone.utc).year:
            add("established_year", year, match.start(), match.end())
            break

    # A company page's explicit role association is required. No names are
    # invented from emails, contact form labels, or personal-looking brands.
    if _host(url) and _host(url) == _host(getattr(lead, "website", "")):
        roles = r"(?:co[- ]owner|owner|co[- ]founder|founder|CEO|president)"
        name = r"[A-Z][A-Za-z'’\-]{1,25}(?:\s+[A-Z][A-Za-z'’\-]{1,25}){1,3}"
        for pattern in (
            rf"\b(?P<name>{name})\s*(?:,|\(|[-–])\s*(?P<role>(?i:{roles}))\b",
            rf"\b(?P<role>(?i:{roles}))\s*[:–-]\s*(?P<name>{name})(?=$|[,.!?;()|]|\s+[a-z])",
            rf"\b(?P<name>{name})\s+(?i:is (?:the |our )?)(?P<role>(?i:{roles}))\b",
        ):
            for match in re.finditer(pattern, text):
                person = _name(match.group("name"))
                if person:
                    add("named_person", person, match.start(), match.end())
                    add(
                        "person_role",
                        person + " | " + match.group("role"),
                        match.start(),
                        match.end(),
                    )
        for person in structured_people or []:
            if not isinstance(person, dict):
                continue
            person_name = _name(person.get("name", ""))
            role = str(person.get("role", ""))[:100]
            if person_name and re.fullmatch(
                rf"(?i:{roles})(?: / [A-Za-z ]{{2,40}})?", role.strip()
            ):
                excerpt = person_name + " — " + role + " (published structured data)"
                add("named_person", person_name, excerpt=excerpt)
                add("person_role", person_name + " | " + role, excerpt=excerpt)

    # Protect person/manual evidence from a large collection of software mentions.
    priority = {"named_person": 0, "person_role": 0, "manual_workflow": 1}
    records = sorted(records, key=lambda r: priority.get(r.get("kind"), 2))[:24]
    lead.workflow_signals = json.dumps(records, ensure_ascii=False)
    person = next((r for r in records if r.get("kind") == "named_person"), None)
    if person and not getattr(lead, "decision_maker", ""):
        lead.decision_maker = person["value"]
        association = next(
            (
                r["value"]
                for r in records
                if r.get("kind") == "person_role"
                and r.get("value", "").startswith(person["value"] + " | ")
            ),
            "",
        )
        lead.decision_maker_role = association.split(" | ", 1)[1] if association else ""
    return records


def assess(lead, profile_id="general"):
    profile = profile_metadata(profile_id)
    lead.research_profile = profile_id
    records = _records(getattr(lead, "workflow_signals", "[]"))
    refs = lambda kind: [i for i, r in enumerate(records) if r.get("kind") == kind]
    assumptions = [
        "Published workflow and owner statements are source claims, not independent verification.",
        "Missing website mentions do not prove absence of software, manual work, team size, or purchasing budget.",
    ]
    base = {
        "profile": profile_id,
        "version": 1,
        "weights": profile["weights"],
        "dimensions": {},
        "supported_points": 0,
        "coverage": 0,
        "status": "not_requested",
        "note": "Supported evidence points, not conversion probability or a purchasing-budget prediction. Unknown dimensions contribute no points; compare coverage too.",
        "assumptions": assumptions,
    }
    if profile_id != "general":
        dimensions = {}

        def dimension(key, value, reason, source_refs):
            dimensions[key] = {
                "value": value,
                "weight": WEIGHTS[key],
                "reason": reason,
                "signal_refs": sorted(set(source_refs)),
            }

        manual, phone = refs("manual_workflow"), refs("phone_quotes")
        dimension(
            "pain",
            8 if manual else 3 if phone else None,
            "Explicit manual report/quote workflow; pain severity still needs a conversation."
            if manual
            else "Phone quotes are a published workflow signal, not confirmed dissatisfaction or manual report assembly."
            if phone
            else "No explicit manual report/quote or phone-quote workflow found.",
            manual or phone,
        )
        hood = refs("hood_service")
        fit_refs = (
            hood
            + refs("reporting")
            + refs("photos")
            + refs("repairs")
            + refs("recurring")
        )
        fit = (
            min(
                10,
                4
                + 2 * bool(refs("reporting"))
                + bool(refs("photos"))
                + 2 * bool(refs("repairs"))
                + bool(refs("recurring")),
            )
            if hood
            else None
        )
        dimension(
            "fit",
            fit,
            "Published hood-cleaning and relevant report/photo/repair/recurring vocabulary; mentions do not prove a need for this product."
            if hood
            else "No hood-cleaning statement was captured on checked pages.",
            fit_refs,
        )
        people = refs("named_person")
        channels = int(bool(getattr(lead, "email", ""))) + int(
            bool(getattr(lead, "phone", ""))
        )
        access = (
            7 + channels
            if people and channels
            else 3
            if people
            else 3 + channels
            if channels
            else None
        )
        dimension(
            "access",
            access,
            "Named role-associated person and listed contact channels; a company channel is not confirmed direct access to that person."
            if people
            else "Listed company contact channels only; no named decision-maker established."
            if channels
            else "No named decision-maker or listed email/phone established.",
            people + refs("person_role"),
        )
        years = refs("established_year")
        age = (
            max(0, datetime.now(timezone.utc).year - int(records[years[0]]["value"]))
            if years
            else None
        )
        capacity = (
            (7 if age >= 30 else 6 if age >= 15 else 4 if age >= 5 else 2)
            if age is not None
            else None
        )
        dimension(
            "capacity",
            capacity,
            "Published establishment year is a longevity/capacity proxy only. Revenue, cash flow, and ability to pay are unknown."
            if years
            else "No supported capacity proxy captured; purchasing budget remains unknown.",
            years,
        )
        solved = refs("automated_reporting") + refs("customer_portal")
        underserved = (
            1
            if refs("automated_reporting")
            else 3
            if refs("customer_portal")
            else 7
            if manual
            else None
        )
        dimension(
            "underserved",
            underserved,
            "Published automated reporting/portal is a counter-signal, but scope and actual use need confirmation."
            if solved
            else "Explicit manual workflow supports a potential gap; unobserved tools may still exist."
            if manual
            else "No evidence establishes an unsolved reporting gap. Named software alone neither proves nor disproves one.",
            solved or manual,
        )
        supported = round(
            sum(
                d["value"] / 10 * d["weight"]
                for d in dimensions.values()
                if d["value"] is not None
            ),
            2,
        )
        coverage = sum(
            d["weight"] for d in dimensions.values() if d["value"] is not None
        )
        base.update(
            dimensions=dimensions,
            supported_points=supported,
            coverage=coverage,
            status="assessed"
            if coverage == 100
            else "partial"
            if coverage
            else "not_enough_evidence",
        )
    lead.opportunity_score = base["supported_points"]
    lead.opportunity = json.dumps(base, ensure_ascii=False)
    try:
        existing = json.loads(getattr(lead, "assumptions", "[]") or "[]")
    except (ValueError, TypeError):
        existing = []
    lead.assumptions = json.dumps(
        list(
            dict.fromkeys(
                (existing if isinstance(existing, list) else []) + assumptions
            )
        ),
        ensure_ascii=False,
    )
    return lead
