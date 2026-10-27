"""Reviewed official business-registry and licensing directory catalog."""

from __future__ import annotations

import re

DIRECTORIES = [
    {
        "id": "us-npi",
        "country": "United States",
        "name": "NPPES NPI Registry",
        "authority": "Centers for Medicare & Medicaid Services",
        "niches": ["healthcare", "dental", "medical", "providers"],
        "access": "free public search and API",
        "mode": "api_available",
        "url": "https://npiregistry.cms.hhs.gov/",
        "search_hint": "Search by provider name, NPI, taxonomy and practice location.",
    },
    {
        "id": "us-sam",
        "country": "United States",
        "name": "SAM.gov Entity Information",
        "authority": "U.S. General Services Administration",
        "niches": ["government contractors", "small business", "all businesses"],
        "access": "public search; API key for integration",
        "mode": "manual_or_key",
        "url": "https://sam.gov/entity-information",
        "search_hint": "Search federal entity registrations by legal name, UEI or CAGE code.",
    },
    {
        "id": "us-sba-dsbs",
        "country": "United States",
        "name": "SBA Dynamic Small Business Search",
        "authority": "U.S. Small Business Administration",
        "niches": ["small business", "government contractors", "all businesses"],
        "access": "free public search",
        "mode": "manual_search",
        "url": "https://dsbs.sba.gov/search/dsp_dsbs.cfm",
        "search_hint": "Search participating small businesses by location, NAICS and ownership program.",
    },
    {
        "id": "us-irs-teos",
        "country": "United States",
        "name": "IRS Tax Exempt Organization Search",
        "authority": "Internal Revenue Service",
        "niches": ["nonprofit", "charity", "associations"],
        "access": "free public search and bulk downloads",
        "mode": "download_available",
        "url": "https://apps.irs.gov/app/eos/",
        "search_hint": "Search tax-exempt organizations by name, EIN, city and state.",
    },
    {
        "id": "sg-acra-open",
        "country": "Singapore",
        "name": "ACRA Open Data",
        "authority": "Accounting and Corporate Regulatory Authority",
        "niches": ["all businesses", "companies", "partnerships", "audit firms"],
        "access": "free monthly datasets and APIs",
        "mode": "download_available",
        "url": "https://www.acra.gov.sg/resources/open-data-initiative/",
        "search_hint": "Use entity name, UEN, status, entity type and SSIC business activity.",
    },
    {
        "id": "sg-bizfile",
        "country": "Singapore",
        "name": "Bizfile Entity Search",
        "authority": "Accounting and Corporate Regulatory Authority",
        "niches": ["all businesses", "companies", "registered entities"],
        "access": "public portal; some products may require payment",
        "mode": "manual_search",
        "url": "https://www.bizfile.gov.sg/",
        "search_hint": "Search and verify a specific registered entity or UEN in the official portal.",
    },
    {
        "id": "my-ssm-einfo",
        "country": "Malaysia",
        "name": "SSM e-Info",
        "authority": "Companies Commission of Malaysia",
        "niches": ["all businesses", "companies", "partnerships", "LLP"],
        "access": "account and paid official information products",
        "mode": "paid_manual",
        "url": "https://www.ssm-einfo.my/",
        "search_hint": "Search a company or business, then review the price before purchasing a profile.",
    },
    {
        "id": "my-ssm-search",
        "country": "Malaysia",
        "name": "SSM Search",
        "authority": "Companies Commission of Malaysia appointed provider",
        "niches": ["all businesses", "companies", "registered businesses"],
        "access": "account and paid official information products",
        "mode": "paid_manual",
        "url": "https://www.ssmsearch.com/",
        "search_hint": "Search by registered name or number; purchase only after reviewing the displayed fee.",
    },
    {
        "id": "au-abn-search",
        "country": "Australia",
        "name": "ABN Lookup",
        "authority": "Australian Business Register",
        "niches": ["all businesses", "companies", "sole traders", "charities"],
        "access": "free public search",
        "mode": "manual_search",
        "url": "https://abr.business.gov.au/Search/Index",
        "search_hint": "Search by ABN, ACN or entity name and refine by state or postcode.",
    },
    {
        "id": "au-abn-api",
        "country": "Australia",
        "name": "ABN Lookup Web Services",
        "authority": "Australian Business Register",
        "niches": ["all businesses", "companies", "identity verification"],
        "access": "free registration; authentication GUID required",
        "mode": "key_required",
        "url": "https://abr.business.gov.au/Tools/WebServices",
        "search_hint": "Register for a GUID to search by ABN, ACN, name, state and postcode through the API.",
    },
    {
        "id": "au-asic",
        "country": "Australia",
        "name": "ASIC Registers",
        "authority": "Australian Securities & Investments Commission",
        "niches": ["companies", "financial services", "credit", "professionals"],
        "access": "basic public search; detailed extracts may cost money",
        "mode": "manual_search",
        "url": "https://connectonline.asic.gov.au/",
        "search_hint": "Search companies, organisations, business names and professional registers.",
    },
]


def list_directories(country: str = "", niche: str = "", query: str = "") -> list[dict]:
    country = re.sub(r"\s+", " ", str(country or "")).strip().casefold()
    niche = re.sub(r"\s+", " ", str(niche or "")).strip().casefold()
    query = re.sub(r"\s+", " ", str(query or "")).strip().casefold()
    result = []
    for item in DIRECTORIES:
        haystack = " ".join(
            [
                item["name"],
                item["authority"],
                item["access"],
                item["search_hint"],
                *item["niches"],
            ]
        ).casefold()
        if country and item["country"].casefold() != country:
            continue
        if niche and not any(niche in value.casefold() for value in item["niches"]):
            continue
        if query and query not in haystack:
            continue
        result.append(dict(item))
    return result


def metadata() -> dict:
    return {
        "countries": sorted({item["country"] for item in DIRECTORIES}),
        "niches": sorted({value for item in DIRECTORIES for value in item["niches"]}),
        "directories": list_directories(),
        "notice": "Directory access varies. The app never bypasses registration, login, fees or official usage limits.",
    }
