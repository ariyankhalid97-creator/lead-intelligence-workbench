"""Deterministic research methods inspired by the reviewed Maps actor catalog.

These are search and verification hypotheses, never evidence.  They do not call
Apify, copy actor outputs, or promote a missing field into a factual claim.
"""

from __future__ import annotations

import re

SOURCE = (
    "cporter202/google-maps-scraping-apis (MIT); concepts adapted, no actor execution"
)

BASE_METHODS = [
    "category plus city/state Maps discovery",
    "nearby-radius coverage check for missed branches",
    "no website or social-only listing review",
    "rating below 4.0 with at least 20 reviews",
    "review recency and unanswered low-rating review check",
    "exact Place ID or Maps URL identity resolution",
    "business website contact and published email enrichment",
    "cross-source domain, phone and address comparison",
    "rating and review-count snapshot comparison",
]

REVIEW_SIGNALS = [
    "new one or two star review",
    "material rating change",
    "review velocity drop",
    "competitor review-count spike",
    "unanswered low-rating review",
]

# Technology names are hypotheses to look for in retained first-party evidence.
# Their presence must be observed; their absence must never be inferred.
VERTICALS = {
    "childcare": {
        "match": r"child\s*care|daycare|preschool|montessori|after.school",
        "terms": [
            "childcare center",
            "daycare center",
            "preschool",
            "Montessori school",
        ],
        "technologies": [
            "Brightwheel",
            "Procare",
            "Lillio",
            "Kangarootime",
            "KidKare",
            "SmartCare",
        ],
    },
    "construction": {
        "match": r"general contractor|construction|home builder|remodel",
        "terms": [
            "construction contractor",
            "general contractor",
            "home builder",
            "remodeling contractor",
        ],
        "technologies": ["Procore", "Buildertrend", "JobTread", "CoConstruct"],
    },
    "dental": {
        "match": r"dentist|dental|orthodont|oral surgeon",
        "terms": [
            "dental practice",
            "dental office",
            "dentist",
            "orthodontic practice",
        ],
        "technologies": [
            "Dentrix",
            "Eaglesoft",
            "Open Dental",
            "Curve Dental",
            "Weave",
        ],
    },
    "fitness": {
        "match": r"fitness|gym|yoga|pilates|martial arts|personal trainer",
        "terms": [
            "independent fitness studio",
            "fitness center",
            "yoga studio",
            "Pilates studio",
        ],
        "technologies": [
            "Mindbody",
            "Mariana Tek",
            "Glofox",
            "Zen Planner",
            "ClubReady",
        ],
    },
    "funeral": {
        "match": r"funeral|mortuar|cremator|cemeter",
        "terms": ["funeral home", "mortuary", "cremation service", "cemetery"],
        "technologies": [
            "Tribute Technology",
            "Frazer",
            "Passare",
            "FuneralOne",
            "Halcyon",
            "ASD",
        ],
    },
    "healthcare": {
        "match": r"medical|healthcare|doctor|physician|clinic|chiropract|veterinar",
        "terms": [
            "private medical practice",
            "health clinic",
            "physician practice",
            "veterinary practice",
        ],
        "technologies": [
            "athenahealth",
            "Kareo",
            "Tebra",
            "ezyVet",
            "AVImark",
            "Weave",
        ],
    },
    "hospitality": {
        "match": r"hotel|motel|lodging|bed and breakfast|hospitality",
        "terms": ["independent hotel", "boutique hotel", "motel", "bed and breakfast"],
        "technologies": [
            "Cloudbeds",
            "Mews",
            "SiteMinder",
            "RoomRaccoon",
            "Hotelogix",
            "Little Hotelier",
        ],
    },
    "legal": {
        "match": r"lawyer|law firm|attorney|legal practice",
        "terms": ["law firm", "legal practice", "attorney office"],
        "technologies": [
            "Clio",
            "MyCase",
            "PracticePanther",
            "Smokeball",
            "Filevine",
            "LawPay",
        ],
    },
    "pet_services": {
        "match": r"pet groom|dog train|pet service|animal hospital|veterinar",
        "terms": ["pet grooming", "dog daycare", "pet boarding", "dog training"],
        "technologies": [
            "Gingr",
            "Time To Pet",
            "PawPartner",
            "DaySmart Pet",
            "PetExec",
            "K9Sky",
        ],
    },
    "real_estate": {
        "match": r"real estate|realtor|property management|mortgage broker",
        "terms": [
            "independent real estate brokerage",
            "real estate team",
            "property management company",
            "mortgage broker",
        ],
        "technologies": [
            "kvCORE",
            "BoomTown",
            "Follow Up Boss",
            "Sierra Interactive",
            "dotloop",
            "Chime",
        ],
    },
    "restaurant": {
        "match": r"restaurant|cafe|coffee shop|bakery|bar|cater|food truck",
        "terms": ["restaurant", "local restaurant", "cafe", "catering company"],
        "technologies": [
            "Toast",
            "Square",
            "Clover",
            "Lightspeed",
            "TouchBistro",
            "Revel",
            "OpenTable",
            "Resy",
            "Tock",
        ],
    },
    "salon_spa": {
        "match": r"salon|barber|spa|lash|brow|beauty",
        "terms": ["hair salon", "barbershop", "nail salon", "day spa", "medical spa"],
        "technologies": [
            "Vagaro",
            "Boulevard",
            "Booksy",
            "Fresha",
            "GlossGenius",
            "Mindbody",
        ],
    },
}


def for_niche(niche: str) -> dict:
    """Return a bounded, deterministic method pack for a niche."""
    value = re.sub(r"\s+", " ", str(niche or "")).strip()
    selected = []
    terms = []
    technologies = []
    for name, profile in VERTICALS.items():
        if re.search(profile["match"], value, re.IGNORECASE):
            selected.append(name)
            terms.extend(profile["terms"])
            technologies.extend(profile["technologies"])
    return {
        "search_methods": list(BASE_METHODS),
        "review_signals": list(REVIEW_SIGNALS),
        "vertical_profiles": selected[:3],
        "vertical_search_terms": list(dict.fromkeys(terms))[:12],
        "technology_signals": list(dict.fromkeys(technologies))[:20],
        "method_source": SOURCE,
    }


def observed_technologies(payload, technologies: list[str]) -> list[str]:
    """Match known names only in saved evidence text, never from missing data."""
    text = str(payload or "")[:500_000]
    return [
        name
        for name in technologies[:30]
        if re.search(
            r"(?<![a-z0-9])" + re.escape(name) + r"(?![a-z0-9])", text, re.IGNORECASE
        )
    ]
