"""Offer-to-prospect planning with reusable, evidence-aware buyer packs."""

from __future__ import annotations

import re


COUNTRIES = {
    "US": {"name": "United States", "locations": ["New York, New York", "Los Angeles, California", "Chicago, Illinois", "Houston, Texas", "Dallas, Texas"], "fit_note": "WhatsApp is not the default US business channel. Prioritize companies publishing a WhatsApp number, serving international/mobile customers, or already using messaging-first workflows."},
    "SG": {"name": "Singapore", "locations": ["Singapore"], "fit_note": "Strong messaging-market fit. Prioritize SMEs with visible WhatsApp contact, multi-party documents, and mobile customers or workers."},
    "MY": {"name": "Malaysia", "locations": ["Kuala Lumpur, Malaysia", "George Town, Penang, Malaysia", "Johor Bahru, Malaysia"], "fit_note": "Strong messaging-market fit. Prioritize repetitive mobile document workflows and businesses that publish a WhatsApp contact path."},
    "AU": {"name": "Australia", "locations": ["Sydney, New South Wales", "Melbourne, Victoria", "Brisbane, Queensland", "Perth, Western Australia"], "fit_note": "Use a selective approach. Prioritize mobile workforces, international customers, visible WhatsApp contact, and repetitive rental or tenancy workflows."},
}


ESIGNATURE_USE_CASES = [
    {
        "niche": "property management companies",
        "label": "Real estate & property management",
        "reason": "High document frequency across leasing, property management and agent/vendor operations, with several parties often signing remotely.",
        "subsegments": ["residential property management", "commercial property management", "letting and leasing agencies", "student housing operators", "short term rental management", "real estate brokerages with rental divisions", "coworking and serviced office operators"],
        "documents": ["tenancy and lease agreements where locally permitted", "lease renewals and addenda", "property management service agreements", "listing and agency engagement letters", "tenant notices and inspection acknowledgements", "vendor and maintenance approvals", "agent onboarding and independent contractor agreements"],
        "phrases": ["property management company", "residential leasing agency", "rental property manager", "letting agency", "student housing operator", "short term rental management", "serviced office operator", "real estate rental division"],
        "decision_roles": ["Managing director", "Head of property management", "Leasing director", "Operations director", "Property operations manager", "Broker owner", "Office administrator"],
        "fit_signals": ["Manages a visible portfolio of rental units or multiple properties", "Publishes tenant, landlord, leasing or maintenance workflows", "Uses WhatsApp or mobile messaging for inquiries", "Has multiple branches, agents, property managers or remote clients", "Mentions lease renewals, applications, inspections or owner statements"],
        "opportunity_signals": ["downloadable PDF forms", "print scan or email instructions", "manual tenant application", "call office to complete paperwork", "multiple agent or tenant signatures", "visible WhatsApp contact"],
        "exclusions": ["property listings portal", "real estate news", "property training", "mortgage rates", "land registry", "title company"],
        "legal_boundary": "Do not assume electronic-signature suitability for sale deeds, land transfers, conveyancing, notarized instruments or closings. Focus on ordinary operational agreements and verify local tenancy rules.",
    },
    {
        "niche": "staffing and recruitment agencies",
        "label": "Hiring & employee onboarding",
        "reason": "Repeated offers, NDAs, acknowledgements and onboarding packets create a measurable mobile-signing workflow.",
        "subsegments": ["staffing and recruitment agencies", "temporary employment agencies", "BPO and call centers", "hospitality groups", "security companies", "commercial cleaning companies", "home care agencies", "construction labor providers", "retail and franchise groups", "fast growing startups"],
        "documents": ["offer and appointment letters", "employment and contractor agreements", "NDAs and confidentiality agreements", "policy and handbook acknowledgements", "background-check consent where legally suitable", "equipment issue and return forms", "remote-worker and flexible-work agreements", "exit and clearance acknowledgements"],
        "phrases": ["staffing agency", "recruitment agency", "temporary employment agency", "high volume hiring company", "BPO hiring", "call center hiring", "home care agency careers", "security company careers", "hospitality group careers", "multiple open positions"],
        "decision_roles": ["Head of human resources", "Head of talent acquisition", "Recruitment director", "People operations director", "HR operations manager", "Onboarding manager", "Staffing agency owner"],
        "fit_signals": ["Several current openings or recurring recruitment campaigns", "Remote, distributed, temporary, seasonal or high-turnover workforce", "Publishes onboarding, careers, employee forms or candidate instructions", "Multiple branches, departments or hiring managers", "Uses WhatsApp for candidate communication or job applications"],
        "opportunity_signals": ["apply by WhatsApp", "email signed offer letter", "download onboarding forms", "multiple current vacancies", "remote onboarding", "manual employee paperwork"],
        "exclusions": ["job board only", "resume writing", "career coaching", "recruitment training", "university careers office"],
        "legal_boundary": "Use employment documents only where ordinary electronic signatures are permitted; identity, tax, immigration and regulated forms may require a separate compliant process.",
    },
    {
        "niche": "rental companies",
        "label": "Rental & leasing operators",
        "reason": "Rental businesses repeatedly issue time-sensitive agreements at a counter, lot, property or delivery point and benefit from mobile completion.",
        "subsegments": ["car rental companies", "van and truck rental", "equipment and tool rental", "heavy equipment rental", "self storage operators", "party and event rental", "furniture and appliance rental", "bike and scooter rental", "boat and recreational vehicle rental", "vacation rental operators"],
        "documents": ["rental and hire agreements", "vehicle condition and handover forms", "damage waivers and authorized-driver forms", "equipment inspection and return forms", "delivery and collection acknowledgements", "storage agreements and insurance acknowledgements", "extensions, renewals and rental addenda", "deposit and inventory acknowledgements"],
        "phrases": ["car rental company", "van rental company", "equipment rental company", "tool hire company", "heavy equipment rental", "self storage facility", "party rental company", "furniture rental company", "RV rental company", "vacation rental management"],
        "decision_roles": ["Owner or founder", "Rental operations director", "Fleet manager", "Branch manager", "Operations manager", "Customer experience manager", "Contracts administrator"],
        "fit_signals": ["Operates a rental fleet, inventory, storage site or multiple branches", "Offers online reservations, delivery, collection or after-hours pickup", "Publishes rental terms, waivers, deposits or condition forms", "Uses WhatsApp for bookings, quotations or customer support", "Handles remote customers or on-site handovers"],
        "opportunity_signals": ["paper contract at counter", "download rental agreement", "print and sign waiver", "after hours pickup", "delivery acknowledgement", "visible WhatsApp booking", "multiple branches or fleet locations"],
        "exclusions": ["rental listings portal", "classified ads", "rental news", "equipment for sale", "real estate sale"],
        "legal_boundary": "Prioritize ordinary commercial rental documents. Exclude notarized, title-transfer, financing and other documents requiring stronger identity or statutory formalities.",
    },
]


ESIGNATURE_WORKFLOW = {"offer": "Electronic signature workflow", "summary": "Mobile-first electronic signatures, multi-party signing, document delivery, field placement and audit trails for repetitive agreements.", "primary_niche": ESIGNATURE_USE_CASES[0]["niche"], "segments": ESIGNATURE_USE_CASES}

SEARCH_APPROACHES = [
    "Local intent: Maps and local-business profiles for operating companies in each city",
    "Directory identity: official registries and public directories to confirm the entity and location",
    "Workflow evidence: website pages mentioning leases, offers, onboarding, waivers, forms, handovers or renewals",
    "Messaging fit: public WhatsApp links, click-to-chat buttons and mobile-first customer instructions",
    "Volume signals: multiple branches, portfolios, fleets, vacancies, agents, properties or rental inventory",
    "Replacement signals: downloadable PDFs, print/scan instructions, paper-at-counter language and manual follow-up",
    "Technology signals: public references to existing e-signature, ATS, property or rental workflow tools",
    "Contact waterfall: contact/about/team pages, public emails and phones, then exact LinkedIn company-role review",
]


def _generic_plan(offer: str) -> dict:
    value = offer.strip()
    if re.search(r"e-?sign|electronic sign|document sign|whatsapp sign", value, re.I):
        return {**ESIGNATURE_WORKFLOW, "offer": value}
    segment = {
        "niche": value, "label": value, "reason": "Direct niche match supplied by the user; buyer fit still needs public evidence.", "subsegments": [value], "documents": [],
        "phrases": [value, f"{value} company", f"{value} provider"],
        "decision_roles": ["Founder or owner", "Managing director", "Operations director", "Department head"],
        "fit_signals": ["Public evidence of a relevant operational need", "Active company website", "Reachable decision-making role"],
        "opportunity_signals": ["manual workflow", "published contact path"], "exclusions": ["directory only", "news", "training"],
        "legal_boundary": "Keep unknown facts marked unknown and verify suitability before outreach.",
    }
    return {"offer": value, "summary": f"Prospecting plan for {value}.", "primary_niche": value, "segments": [segment]}


def plan(offer: str, country: str = "US", segment: str = "") -> dict:
    if not isinstance(offer, str) or not 2 <= len(offer.strip()) <= 120:
        raise ValueError("Enter a product, service or target niche between 2 and 120 characters")
    country = country if country in COUNTRIES else "US"
    profile = _generic_plan(offer)
    selected = next((item for item in profile["segments"] if item["niche"] == segment.strip()), profile["segments"][0])
    country_data = COUNTRIES[country]
    return {**profile, **selected, "segments": profile["segments"], "country": country, "country_name": country_data["name"], "country_fit_note": country_data["fit_note"], "locations": country_data["locations"], "selected_segment": selected["niche"], "search_approaches": SEARCH_APPROACHES, "linkedin_queries": [f'"{{company}}" "{role}" site:linkedin.com/in' for role in selected["decision_roles"][:5]], "method": "Run maps, web, directories and applicable registries; resolve websites; inspect workflow evidence; retain public contacts; then prepare exact company/role LinkedIn searches for manual signed-in review."}


def activate(offer: str) -> dict:
    """Save reusable e-signature research packs into local intelligence memory."""
    if not re.search(r"e-?sign|electronic sign|document sign|whatsapp sign", offer, re.I):
        return {"saved": [], "offer": offer.strip()}
    import intelligence

    saved = []
    for segment in ESIGNATURE_USE_CASES:
        data = {
            "name": segment["niche"],
            "synonyms": [segment["niche"], *segment["subsegments"], *segment["phrases"]][:30],
            "exclusions": segment["exclusions"],
            "decision_maker_roles": segment["decision_roles"],
            "ideal_signals": segment["fit_signals"],
            "opportunity_signals": segment["opportunity_signals"],
            "chain_signals": ["multiple branches", "multiple locations", "franchise", "portfolio", "fleet"],
            "source_types": ["Google Maps", "business website", "official registries", "public directories", "job and careers pages", "LinkedIn company profile", "public social profiles"],
            "enrichment_waterfall": ["maps and public web", "official registry identity", "business website", "contact and about pages", "careers or rental workflow pages", "public social profiles", "LinkedIn manual review", "local AI evidence analysis"],
            "search_methods": ["maps and local listings", "exact service queries", "workflow and document queries", "careers and hiring signals", "technology and WhatsApp signals", "official registry verification"],
            "review_signals": [*segment["fit_signals"], *segment["opportunity_signals"]][:30],
            "technology_signals": ["WhatsApp", "DocuSign", "Adobe Sign", "Dropbox Sign", "HelloSign", "PandaDoc", "paper forms", "downloadable PDF"],
            "version": 3,
        }
        saved.append(intelligence.save_niche_pack(data))
        intelligence.record_ai_search_terms(segment["niche"], segment["phrases"][:12], "researched-esignature-pack")
        intelligence.save_ai_teaching({"niche": segment["niche"], "terms": segment["phrases"][:20], "avoid": segment["exclusions"][:20], "notes": f"Electronic-signature fit: {segment['reason']} Documents: {', '.join(segment['documents'])}. Boundary: {segment['legal_boundary']}"})
    return {"saved": saved, "offer": offer.strip()}
