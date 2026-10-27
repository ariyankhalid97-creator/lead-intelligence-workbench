"""No-key public-data lead providers with explicit niche applicability."""

from __future__ import annotations

import json
import re
from urllib.parse import quote

from leadfinder import Lead, fetch
from research import add_observation


STATE_CODES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV",
    "wisconsin": "WI", "wyoming": "WY",
}

NPI_TAXONOMIES = {
    "dent": "Dentist",
    "orthodont": "Orthodontics and Dentofacial Orthopedics",
    "oral surgeon": "Oral and Maxillofacial Surgery",
    "doctor": "Family Medicine",
    "physician": "Family Medicine",
    "medical clinic": "Clinic/Center",
    "urgent care": "Urgent Care",
    "chiropract": "Chiropractor",
    "physical therap": "Physical Therapist",
    "occupational therap": "Occupational Therapist",
    "speech therap": "Speech-Language Pathologist",
    "psycholog": "Psychologist",
    "psychiatr": "Psychiatry & Neurology",
    "counsel": "Counselor",
    "addiction": "Substance Abuse Rehabilitation Facility",
    "home health": "Home Health",
    "nursing home": "Skilled Nursing Facility",
    "assisted living": "Assisted Living Facility",
    "hospice": "Hospice Care, Community Based",
    "optometr": "Optometrist",
    "ophthalmolog": "Ophthalmology",
    "audiolog": "Audiologist",
    "hearing aid": "Hearing Instrument Specialist",
    "podiatr": "Podiatrist",
    "dermatolog": "Dermatology",
    "plastic surgeon": "Plastic Surgery",
    "massage therap": "Massage Therapist",
    "acupunct": "Acupuncturist",
    "nutrition": "Nutritionist",
    "dietitian": "Dietitian, Registered",
    "pharmac": "Pharmacy",
    "medical laborator": "Clinical Medical Laboratory",
    "diagnostic imaging": "Radiology",
}


def npi_taxonomy(niche: str) -> str:
    value = str(niche or "").casefold()
    return next((taxonomy for term, taxonomy in NPI_TAXONOMIES.items() if term in value), "")


def _location_parts(location: str) -> tuple[str, str]:
    parts = [part.strip() for part in str(location).split(",") if part.strip()]
    city = parts[0] if parts else ""
    state_value = parts[1].casefold() if len(parts) > 1 else ""
    state = state_value.upper() if len(state_value) == 2 else STATE_CODES.get(state_value, "")
    return city, state


def npi_search(niche: str, location: str, limit: int, emit=None) -> list[Lead]:
    """Search the official US NPI Registry for applicable healthcare niches."""
    taxonomy = npi_taxonomy(niche)
    city, state = _location_parts(location)
    if not taxonomy:
        return []
    if not city or not state:
        raise RuntimeError("NPI Registry requires a US city and state")
    count = min(max(int(limit), 1), 200)
    url = (
        "https://npiregistry.cms.hhs.gov/api/?version=2.1"
        f"&limit={count}&city={quote(city)}&state={quote(state)}"
        f"&taxonomy_description={quote(taxonomy)}"
    )
    payload = json.loads(fetch(url, timeout=25, retries=1).decode("utf-8"))
    if emit:
        emit(
            "npi",
            "info",
            "Official NPI Registry responded",
            taxonomy=taxonomy,
            city=city,
            state=state,
            count=int(payload.get("result_count", 0) or 0),
        )
    leads = []
    for item in payload.get("results", []):
        basic = item.get("basic") or {}
        addresses = item.get("addresses") or []
        address = next((row for row in addresses if row.get("address_purpose") == "LOCATION"), addresses[0] if addresses else {})
        organization = str(basic.get("organization_name") or "").strip()
        person = " ".join(
            filter(None, (basic.get("first_name"), basic.get("middle_name"), basic.get("last_name")))
        ).strip()
        name = organization or person
        if not name or str(basic.get("status", "A")) != "A":
            continue
        npi = str(item.get("number") or "")
        categories = [row.get("desc", "") for row in item.get("taxonomies", []) if row.get("desc")]
        street = " ".join(filter(None, (address.get("address_1"), address.get("address_2"))))
        full_address = ", ".join(
            filter(None, (street, address.get("city"), address.get("state"), address.get("postal_code")))
        )
        official = " ".join(
            filter(None, (basic.get("authorized_official_first_name"), basic.get("authorized_official_last_name")))
        ).strip()
        lead = Lead(
            name=name.title(),
            category=(categories[0] if categories else taxonomy),
            address=full_address.title(),
            city=str(address.get("city") or city).title(),
            search_location=location,
            phone=str(address.get("telephone_number") or basic.get("authorized_official_telephone_number") or ""),
            source="npi_registry",
            source_id=npi,
            source_url=f"https://npiregistry.cms.hhs.gov/provider-view/{npi}",
            sources="npi_registry",
            decision_maker=official.title(),
            decision_maker_role=str(basic.get("authorized_official_title_or_position") or ""),
            discovery_query=f"{taxonomy} in {city}, {state}",
            discovery_intent="licensed_provider",
            record_type="licensed_provider",
            source_strength="official_registry",
            location_evidence="official_registry_address",
        )
        add_observation(
            lead,
            "official_registry",
            "; ".join(filter(None, [*categories[:3], full_address, f"NPI {npi}"])),
            lead.source_url,
            "US NPI Registry",
        )
        leads.append(lead)
    return leads


def wikidata_search(search_plan: dict, location: str, limit: int, emit=None) -> list[Lead]:
    """Best-effort discovery of notable organizations from Wikidata's public API."""
    phrase = (search_plan.get("phrases") or [""])[0]
    query = f"{phrase} {location}".strip()
    url = (
        "https://www.wikidata.org/w/api.php?action=wbsearchentities&format=json"
        f"&language=en&type=item&limit={min(max(int(limit), 1), 25)}&search={quote(query)}"
    )
    payload = json.loads(fetch(url, timeout=20, retries=1).decode("utf-8"))
    records = payload.get("search", [])
    if emit:
        emit("wikidata", "info", "Wikidata entity search responded", query=query, count=len(records))
    niche_words = {
        word for word in re.findall(r"[a-z]{4,}", phrase.casefold())
        if word not in {"service", "services", "company", "contractor", "contractors"}
    }
    place_words = {word for word in re.findall(r"[a-z]{3,}", location.casefold()) if word not in {"usa"}}
    leads = []
    for item in records:
        text = " ".join((str(item.get("label", "")), str(item.get("description", "")))).casefold()
        if niche_words and not any(word in text for word in niche_words):
            continue
        if place_words and not any(word in text for word in place_words):
            continue
        entity_id = str(item.get("id") or "")
        lead = Lead(
            name=str(item.get("label") or entity_id),
            category=str(item.get("description") or ""),
            city=location,
            search_location=location,
            source="wikidata",
            source_id=entity_id,
            source_url=str(item.get("concepturi") or f"https://www.wikidata.org/wiki/{entity_id}"),
            sources="wikidata",
            discovery_query=query,
            discovery_intent="open_knowledge_entity",
            record_type="organization_entity",
            source_strength="public_structured_data",
            location_evidence="description_match",
        )
        add_observation(lead, "structured_entity", item.get("description", ""), lead.source_url, "Wikidata")
        leads.append(lead)
    return leads

