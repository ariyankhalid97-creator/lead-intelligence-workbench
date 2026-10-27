"""Auditable research planning and evidence-based service-provider qualification.

This is a deterministic workflow using a documented source catalog, public search
results and extraction evidence. It does not claim to be five autonomous AI agents.
"""

from __future__ import annotations
import json
import re
from collections import defaultdict
from urllib.parse import urlparse
from prospecting import profile_metadata

US_ANCHORS = {
    "Texas": ["Dallas", "Houston", "Austin", "San Antonio"],
    "California": ["Los Angeles", "San Diego", "San Francisco", "Sacramento"],
    "Florida": ["Miami", "Tampa", "Orlando", "Jacksonville"],
    "New York": ["New York City", "Buffalo", "Rochester"],
    "Illinois": ["Chicago", "Springfield", "Peoria"],
    "Washington": ["Seattle", "Spokane", "Tacoma"],
    "Colorado": ["Denver", "Colorado Springs", "Fort Collins"],
    "Georgia": ["Atlanta", "Savannah", "Augusta"],
    "Massachusetts": ["Boston", "Worcester", "Springfield"],
    "Arizona": ["Phoenix", "Tucson", "Mesa"],
    "North Carolina": ["Charlotte", "Raleigh", "Greensboro"],
    "Tennessee": ["Nashville", "Memphis", "Knoxville"],
    "Ohio": ["Columbus", "Cleveland", "Cincinnati"],
    "Pennsylvania": ["Philadelphia", "Pittsburgh", "Allentown"],
    "Michigan": ["Detroit", "Grand Rapids", "Lansing"],
    "Alabama": ["Birmingham", "Huntsville", "Mobile"],
    "Alaska": ["Anchorage", "Fairbanks", "Juneau"],
    "Arkansas": ["Little Rock", "Fayetteville", "Fort Smith"],
    "Connecticut": ["Hartford", "New Haven", "Stamford"],
    "Delaware": ["Wilmington", "Dover", "Newark"],
    "Hawaii": ["Honolulu", "Hilo", "Kailua"],
    "Idaho": ["Boise", "Idaho Falls", "Twin Falls"],
    "Indiana": ["Indianapolis", "Fort Wayne", "Evansville"],
    "Iowa": ["Des Moines", "Cedar Rapids", "Davenport"],
    "Kansas": ["Wichita", "Topeka", "Overland Park"],
    "Kentucky": ["Louisville", "Lexington", "Bowling Green"],
    "Louisiana": ["New Orleans", "Baton Rouge", "Shreveport"],
    "Maine": ["Portland", "Bangor", "Augusta"],
    "Maryland": ["Baltimore", "Annapolis", "Frederick"],
    "Minnesota": ["Minneapolis", "Saint Paul", "Duluth"],
    "Mississippi": ["Jackson", "Gulfport", "Hattiesburg"],
    "Missouri": ["Kansas City", "Saint Louis", "Springfield"],
    "Montana": ["Billings", "Missoula", "Bozeman"],
    "Nebraska": ["Omaha", "Lincoln", "Grand Island"],
    "Nevada": ["Las Vegas", "Reno", "Carson City"],
    "New Hampshire": ["Manchester", "Nashua", "Concord"],
    "New Jersey": ["Newark", "Jersey City", "Trenton"],
    "New Mexico": ["Albuquerque", "Santa Fe", "Las Cruces"],
    "North Dakota": ["Fargo", "Bismarck", "Grand Forks"],
    "Oklahoma": ["Oklahoma City", "Tulsa", "Norman"],
    "Oregon": ["Portland", "Salem", "Eugene"],
    "Rhode Island": ["Providence", "Warwick", "Cranston"],
    "South Carolina": ["Charleston", "Columbia", "Greenville"],
    "South Dakota": ["Sioux Falls", "Rapid City", "Aberdeen"],
    "Utah": ["Salt Lake City", "Provo", "Ogden"],
    "Vermont": ["Burlington", "Montpelier", "Rutland"],
    "Virginia": ["Richmond", "Norfolk", "Alexandria"],
    "West Virginia": ["Charleston", "Huntington", "Morgantown"],
    "Wisconsin": ["Milwaukee", "Madison", "Green Bay"],
    "Wyoming": ["Cheyenne", "Casper", "Laramie"],
}
STATE_CODES = dict(
    zip(
        "AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split(),
        "Alabama|Alaska|Arizona|Arkansas|California|Colorado|Connecticut|Delaware|Florida|Georgia|Hawaii|Idaho|Illinois|Indiana|Iowa|Kansas|Kentucky|Louisiana|Maine|Maryland|Massachusetts|Michigan|Minnesota|Mississippi|Missouri|Montana|Nebraska|Nevada|New Hampshire|New Jersey|New Mexico|New York|North Carolina|North Dakota|Ohio|Oklahoma|Oregon|Pennsylvania|Rhode Island|South Carolina|South Dakota|Tennessee|Texas|Utah|Vermont|Virginia|Washington|West Virginia|Wisconsin|Wyoming".split(
            "|"
        ),
    )
)
METROS = {
    "dallas": [
        "Dallas",
        "Fort Worth",
        "Arlington",
        "Plano",
        "Irving",
        "Garland",
        "Carrollton",
        "Grand Prairie",
    ],
    "houston": ["Houston", "Sugar Land", "Katy", "Pearland", "Pasadena"],
    "los angeles": ["Los Angeles", "Long Beach", "Pasadena", "Glendale", "Burbank"],
    "miami": ["Miami", "Miami Beach", "Fort Lauderdale", "Hialeah"],
    "chicago": ["Chicago", "Evanston", "Oak Park", "Naperville"],
    "new york": ["New York City", "Yonkers", "White Plains"],
}
CATALOG = [
    {
        "name": "Clutch service providers",
        "domain": "clutch.co",
        "url": "https://clutch.co/",
        "niches": ["marketing", "software", "web", "design", "IT", "consult", "account", "staff", "cyber", "cloud"],
        "use": "Public B2B agency profiles and review snippets; claimed capabilities require first-party confirmation.",
    },
    {
        "name": "GoodFirms company profiles",
        "domain": "goodfirms.co",
        "url": "https://www.goodfirms.co/",
        "niches": ["marketing", "software", "web", "design", "IT", "consult", "cyber", "cloud"],
        "use": "Public technology and agency profiles; rankings are source claims, not our assessment.",
    },
    {
        "name": "Y Combinator companies",
        "domain": "ycombinator.com",
        "url": "https://www.ycombinator.com/companies",
        "niches": ["software", "startup", "technology", "app", "SaaS", "AI", "cloud", "fintech"],
        "use": "Public startup profiles; batch and company facts are retained with their source.",
    },
    {
        "name": "Product Hunt products",
        "domain": "producthunt.com",
        "url": "https://www.producthunt.com/",
        "niches": ["software", "startup", "technology", "app", "SaaS", "AI", "cloud", "product"],
        "use": "Public product pages used to discover companies; votes and launch claims are not qualification proof.",
    },
    {
        "name": "BetaList startups",
        "domain": "betalist.com",
        "url": "https://betalist.com/",
        "niches": ["software", "startup", "technology", "app", "SaaS", "AI", "cloud", "product"],
        "use": "Public early-stage startup profiles; current operating status requires verification.",
    },
    {
        "name": "Wellfound companies",
        "domain": "wellfound.com",
        "url": "https://wellfound.com/",
        "niches": ["software", "startup", "technology", "app", "SaaS", "AI", "cloud", "product"],
        "use": "Public startup company profiles; jobs are attached later as hiring signals, not separate companies.",
    },
    {
        "name": "Yelp business profiles",
        "domain": "yelp.com",
        "url": "https://www.yelp.com/",
        "niches": ["*"],
        "use": "Public business profile discovery and review metadata; no login or gated-contact access.",
    },
    {
        "name": "Yellow Pages business profiles",
        "domain": "yellowpages.com",
        "url": "https://www.yellowpages.com/",
        "niches": ["*"],
        "use": "Public local-business profile discovery; profile claims require first-party verification.",
    },
    {
        "name": "Manta company profiles",
        "domain": "manta.com",
        "url": "https://www.manta.com/",
        "niches": ["*"],
        "use": "Public small-business company profiles; directory-only records remain weak evidence.",
    },
    {
        "name": "Chamber of Commerce profiles",
        "domain": "chamberofcommerce.com",
        "url": "https://www.chamberofcommerce.com/",
        "niches": ["*"],
        "use": "Public business-directory profiles; chamber membership is not inferred.",
    },
    {
        "name": "BBB business profiles",
        "domain": "bbb.org",
        "url": "https://www.bbb.org/",
        "niches": ["*"],
        "use": "Public company profile discovery; accreditation is retained only when explicitly published.",
    },
    {
        "name": "MapQuest place profiles",
        "domain": "mapquest.com",
        "url": "https://www.mapquest.com/",
        "niches": ["*"],
        "use": "Public place-profile discovery; location facts are compared with first-party evidence.",
    },
    {
        "name": "Alignable business profiles",
        "domain": "alignable.com",
        "url": "https://www.alignable.com/",
        "niches": ["*"],
        "use": "Public business and operator profiles; private network content is not accessed.",
    },
    {
        "name": "IKECA member directory",
        "domain": "ikeca.org",
        "url": "https://www.ikeca.org/search/custom.asp?id=5709",
        "niches": ["hood", "exhaust", "kitchen cleaning"],
        "use": "Kitchen exhaust contractor/member discovery; membership is not inferred from a search hit.",
    },
    {
        "name": "Houzz professionals",
        "domain": "houzz.com",
        "url": "https://www.houzz.com/professionals/",
        "niches": ["roof", "landscap", "remodel", "interior", "plumb", "electric"],
        "use": "Public professional profiles; directories and profile pages are distinguished.",
    },
    {
        "name": "Thumbtack",
        "domain": "thumbtack.com",
        "url": "https://www.thumbtack.com/",
        "niches": ["*"],
        "use": "Public service provider profiles; no gated contact reveal.",
    },
    {
        "name": "Bark",
        "domain": "bark.com",
        "url": "https://www.bark.com/",
        "niches": ["*"],
        "use": "Public provider/company pages; operator size remains unknown without evidence.",
    },
    {
        "name": "Taskrabbit",
        "domain": "taskrabbit.com",
        "url": "https://www.taskrabbit.com/",
        "niches": ["clean", "handyman", "assembl", "moving", "paint"],
        "use": "Tasker profile discovery; a city/category page is not a person record.",
    },
    {
        "name": "Upwork",
        "domain": "upwork.com",
        "url": "https://www.upwork.com/",
        "niches": [
            "web",
            "design",
            "marketing",
            "software",
            "bookkeep",
            "account",
            "writing",
            "video",
            "seo",
            "virtual",
            "developer",
        ],
        "use": "Public freelancer profiles; agency profiles are separate. Contact through the platform.",
    },
    {
        "name": "Fiverr",
        "domain": "fiverr.com",
        "url": "https://www.fiverr.com/",
        "niches": [
            "web",
            "design",
            "marketing",
            "software",
            "writing",
            "video",
            "seo",
            "virtual",
        ],
        "use": "Public seller/gig profiles; no off-platform contact extraction.",
    },
]


def platform_profile(url):
    parsed = urlparse(url)
    host = (parsed.hostname or "").removeprefix("www.")
    path = parsed.path
    checks = {
        "clutch.co": r"^/profile/[^/]+",
        "goodfirms.co": r"^/company/[^/]+",
        "ycombinator.com": r"^/companies/[^/]+",
        "producthunt.com": r"^/products/[^/]+",
        "betalist.com": r"^/startups/[^/]+",
        "wellfound.com": r"^/company/[^/]+",
        "yelp.com": r"^/biz/[^/]+",
        "yellowpages.com": r"/mip/[^/]+",
        "manta.com": r"^/c/[^/]+",
        "chamberofcommerce.com": r"^/business-directory/.+/.+",
        "bbb.org": r"^/us/.+/profile/[^/]+/.+",
        "mapquest.com": r"^/us/.+/.+",
        "alignable.com": r"^/[^/]+/[^/]+",
        "thumbtack.com": r"/service/\d+",
        "bark.com": r"/en/[a-z]{2}/company/[^/]+/[^/]+",
        "taskrabbit.com": r"/(?:profile|taskers)/[^/]+",
        "upwork.com": r"/freelancers/[^/]+",
        "houzz.com": r"(?:-pf~\d+|^/pro/[^/]+)",
        "fiverr.com": r"^/(?!categories/|search/|pro/|support/|resources/)[a-zA-Z0-9_]+/[^/]+",
    }
    return next(
        (
            domain
            for domain, pattern in checks.items()
            if (host == domain or host.endswith("." + domain))
            and re.search(pattern, path)
        ),
        "",
    )


def add_observation(lead, kind, text, url, basis):
    records = json.loads(lead.observations or "[]")
    record = {"kind": kind, "text": str(text)[:1600], "url": url, "basis": basis}
    if record not in records:
        records.append(record)
    lead.observations = json.dumps(records[-8:], ensure_ascii=False)


def platform_query(domain, niche, location):
    """Use a source-specific public profile shape instead of one generic query."""
    paths = {
        "clutch.co": "/profile",
        "goodfirms.co": "/company",
        "ycombinator.com": "/companies",
        "producthunt.com": "/products",
        "betalist.com": "/startups",
        "wellfound.com": "/company",
        "yelp.com": "/biz",
        "yellowpages.com": "/mip",
        "bbb.org": "/us",
        "houzz.com": "/professionals",
        "upwork.com": "/freelancers",
    }
    qualifiers = {
        "clutch.co": "agency company",
        "goodfirms.co": "company services",
        "ycombinator.com": "startup company",
        "producthunt.com": "product maker",
        "betalist.com": "startup",
        "wellfound.com": "startup company",
        "upwork.com": "freelancer",
        "fiverr.com": "seller",
    }
    site = domain + paths.get(domain, "")
    qualifier = qualifiers.get(domain, "business")
    return f'site:{site} "{niche}" "{location}" {qualifier}'


def expand_locations(inputs, coverage):
    if coverage == "usa":
        return [f"{cities[0]}, {state}, USA" for state, cities in US_ANCHORS.items()]
    output = []
    for location in inputs:
        state = next(
            (s for s in US_ANCHORS if location.casefold().strip() == s.casefold()),
            STATE_CODES.get(location.upper().strip()),
        )
        if coverage == "states" and state:
            output.extend(f"{city}, {state}, USA" for city in US_ANCHORS[state])
        elif (
            coverage == "metro"
            and location.split(",")[0].strip().casefold() in METROS
            and len(location.split(",")) > 1
        ):
            base = location.split(",")[0].strip().casefold()
            suffix = ",".join(location.split(",")[1:]).strip()
            output.extend(f"{city}, {suffix}" for city in METROS[base])
        else:
            output.append(location)
    return list(dict.fromkeys(output))


def strategy(search_plan, params):
    niche = params["niche"]
    mode = params.get("target", "both")
    depth = params.get("depth", "balanced")
    budget = params.get("query_budget", 24)
    profile_id = params.get("research_profile", "general")
    profile = profile_metadata(profile_id)
    locations = expand_locations(params["locations"], params.get("coverage", "exact"))
    local_service = bool(re.search(r"clean|roof|plumb|hvac|heating|cooling|electric|landscap|lawn|pest|paint|moving|handyman|repair|wash|dent|remodel|contract", niche, re.I))
    directory_suitable = local_service or bool(
        re.search(
            r"restaurant|cafe|bakery|cater|food truck|bar\b|hotel|doctor|clinic|health|therap|pharmac|vet|"
            r"auto|car\b|truck|taxi|limo|courier|logistic|account|bookkeep|tax prep|law|attorney|insurance|"
            r"real estate|property manage|notary|photograph|video|event|wedding|gym|yoga|pilates|martial|"
            r"salon|barber|spa\b|massage|acupunct|storage|security|locksmith",
            niche,
            re.I,
        )
    )
    platforms = [
        {**s, "status": "documented_source"}
        for s in CATALOG
        if ("*" in s["niches"] and directory_suitable)
        or any(term != "*" and term.casefold() in niche.casefold() for term in s["niches"])
    ]
    source = params["source"]
    web = source in ("hybrid", "web")
    maps = source == "browser" or (source == "hybrid" and params.get("browser", True))
    individual_words = (
        "freelance"
        if any(
            term in niche.casefold()
            for term in (
                "design",
                "web",
                "software",
                "marketing",
                "writing",
                "video",
                "seo",
                "virtual",
                "developer",
            )
        )
        else "owner operated" if local_service else "founder"
    )
    layers = []
    first = []
    solo = []
    profiles = []
    web_alternates = []
    map_alternates = []
    workflow_queries = []
    for location in locations:
        primary = search_plan["phrases"][0]
        if mode != "individuals":
            if maps:
                first.append(
                    {
                        "channel": "browser",
                        "intent": "business",
                        "location": location,
                        "phrase": primary,
                        "query": f"{primary} in {location}",
                    }
                )
            elif web:
                first.append(
                    {
                        "channel": "web",
                        "intent": "business",
                        "location": location,
                        "query": f"{primary} {location}",
                    }
                )
        if mode != "businesses":
            if web:
                solo.append(
                    {
                        "channel": "web",
                        "intent": "individual",
                        "location": location,
                        "query": f'"{primary}" {individual_words} {location}',
                    }
                )
            elif maps:
                solo.append(
                    {
                        "channel": "browser",
                        "intent": "individual",
                        "location": location,
                        "phrase": f"{individual_words} {primary}",
                        "query": f"{individual_words} {primary} in {location}",
                    }
                )
        if web:
            if profile_id == "hood_automation":
                for term in (
                    "NFPA 96",
                    "service report",
                    "hinge kit",
                    "access panel",
                    "grease containment",
                    "owner technician",
                ):
                    workflow_queries.append(
                        {
                            "channel": "web",
                            "intent": "workflow_research",
                            "location": location,
                            "query": f'"{primary}" "{term}" {location}',
                        }
                    )
            for platform in platforms:
                profiles.append(
                    {
                        "channel": "web",
                        "intent": "profile",
                        "location": location,
                        "platform": platform["domain"],
                        "query": platform_query(platform["domain"], primary, location),
                    }
                )
            for phrase in search_plan["phrases"][1:]:
                web_alternates.append(
                    {
                        "channel": "web",
                        "intent": "service_variant",
                        "location": location,
                        "query": f"{phrase} {location}",
                    }
                )
            if mode == "individuals":
                web_alternates.append(
                    {
                        "channel": "web",
                        "intent": "individual",
                        "location": location,
                        "query": f'"{primary}" "self employed" {location}',
                    }
                )
        # In balanced and deep modes, send every accepted service phrase to Maps.
        # This includes phrases the user explicitly applied from the local-AI helper.
        # Quick mode intentionally keeps one Maps query.
        if maps and depth in ("balanced", "deep"):
            map_alternates.extend(
                {
                    "channel": "browser",
                    "intent": "service_variant",
                    "location": location,
                    "phrase": phrase,
                    "query": f"{phrase} in {location}",
                }
                for phrase in search_plan["phrases"][1:]
            )
    # Spread each intent across locations before spending on another intent.
    paired = []
    for index in range(max(len(first), len(solo))):
        if index < len(first):
            paired.append(first[index])
        if index < len(solo):
            paired.append(solo[index])
    # Two workflow queries early; preserve base/individual discovery and platform variety.
    # Maps variants come before web variants so a normal query budget preserves
    # every applied local-AI/user tag even when public web engines are unavailable.
    layers = (
        paired
        + workflow_queries[:2]
        + profiles
        + map_alternates
        + web_alternates
        + workflow_queries[2:]
    )
    if depth == "quick":
        layers = paired
    queries = []
    if web and params.get("research_platforms", True):
        queries.append(
            {
                "channel": "research",
                "intent": "platform_research",
                "location": "",
                "query": (
                    f'"{niche}" professional association contractor directory'
                    if local_service
                    else f'"{niche}" trade association business directory'
                ),
            }
        )
    for query in layers:
        if len(queries) >= budget:
            break
        if query["query"].casefold() not in {q["query"].casefold() for q in queries}:
            queries.append(query)
    scheduled = list(dict.fromkeys(q["location"] for q in queries if q["location"]))
    if source in ("osm", "google", "websites"):
        scheduled = locations[: min(len(locations), budget)]
    return {
        "method": "Documented source catalog + deterministic query planner + best-effort public web research",
        "target": mode,
        "research_profile": profile,
        "depth": depth,
        "coverage": params.get("coverage", "exact"),
        "platforms": platforms,
        "locations": locations,
        "scheduled_locations": scheduled,
        "unsearched_locations": [x for x in locations if x not in scheduled],
        "queries": queries,
        "query_budget": budget,
        "planned_queries": len(queries),
        "total_possible_queries": len(layers)
        + (1 if web and params.get("research_platforms", True) else 0),
        "coverage_note": "US/state searches sample named city anchors. They do not enumerate every city or guarantee statewide coverage.",
        "stages": [
            {
                "name": "Research strategist",
                "purpose": "Choose niche terminology and platform candidates.",
            },
            {
                "name": "Search planner",
                "purpose": "Schedule distinct business, individual and profile queries across the selected geography.",
            },
            {
                "name": "Evidence analyst",
                "purpose": "Separate observed listing/page facts, snippet claims and assumptions.",
            },
            {
                "name": "Lead qualifier",
                "purpose": "Label solo/independent, chain/franchise, agency or unknown using evidence.",
            },
            {
                "name": "Quality controller",
                "purpose": "Merge duplicates and flag missing fields, weak sources and uncertainty.",
            },
        ],
    }


def discover_platforms(query, cancel, emit):
    if cancel.is_set():
        return []
    from ddgs import DDGS

    try:
        results = list(
            DDGS(timeout=12).text(query, max_results=6, backend="brave,duckduckgo")
        )
        sources = [
            {
                "name": r.get("title", ""),
                "url": r.get("href", ""),
                "domain": urlparse(r.get("href", "")).hostname,
                "status": "unverified_search_candidate",
                "excerpt": r.get("body", "")[:350],
            }
            for r in results
            if urlparse(r.get("href", "")).scheme in ("http", "https")
        ]
        emit(
            "research",
            "info",
            "Niche platform candidates discovered",
            query=query,
            count=len(sources),
        )
        return sources
    except Exception as exc:
        emit(
            "research",
            "warning",
            "Platform discovery unavailable; documented catalog retained",
            query=query,
            error=str(exc)[:250],
        )
        return []


def analyze(lead, search_plan, content=""):
    observations = json.loads(lead.observations or "[]")
    if (
        content
        and lead.website
        and not any(o["basis"] == "page_text" for o in observations)
    ):
        add_observation(lead, "page", content, lead.website, "page_text")
        observations = json.loads(lead.observations)
    platform = platform_profile(lead.source_url or lead.website)
    lead.record_type = (
        "seller_profile"
        if platform
        else (
            "business_listing"
            if lead.source
            in ("google_maps_browser", "google_maps_local", "openstreetmap")
            else "website_candidate"
        )
    )
    facts = []
    assumptions = []
    flags = []
    for e in json.loads(lead.evidence or "[]"):
        facts.append(
            {
                "field": e.get("field"),
                "value": e.get("value"),
                "status": "observed_published",
                "url": e.get("url"),
                "basis": e.get("method"),
            }
        )
    if lead.source in ("google_maps_browser", "google_maps_local", "openstreetmap"):
        for field in ("name", "phone", "address", "category", "website"):
            if getattr(lead, field):
                facts.append(
                    {
                        "field": field,
                        "value": getattr(lead, field),
                        "status": "observed_listing",
                        "url": lead.source_url,
                        "basis": "public listing; not independently verified",
                    }
                )
    for o in observations:
        if o["basis"] == "search_snippet":
            facts.append(
                {
                    "field": "search_description",
                    "value": o["text"],
                    "status": "snippet_claim",
                    "url": o["url"],
                    "basis": "Search snippet may be stale or incomplete",
                }
            )
    # Classification requires source text, never just a personal-looking name or query.
    patterns = [
        (
            "solo_provider",
            r"\b(?:sole (?:trader|proprietor)|one[- ]person (?:business|operation|team)|solo (?:operator|professional|business)|independent freelancer|self[- ]employed (?:cleaner|contractor|professional|designer|developer)|i (?:personally|work alone))\b",
        ),
        (
            "independent_business",
            r"\b(?:owner[- ]operated|independently owned|locally owned and operated|family[- ]owned|not a franchise)\b",
        ),
        (
            "chain_or_franchise",
            r"\b(?:our franchise (?:network|locations|owners)|franchise opportunities|locations nationwide|national chain|franchisee of)\b",
        ),
        (
            "agency",
            r"\b(?:we are (?:an? )?(?:digital |marketing |creative |staffing )?agency|our agency|agency team)\b",
        ),
    ]
    claims = []
    for o in observations:
        text = o["text"]
        for kind, pattern in patterns:
            match = re.search(pattern, text, re.I)
            if match:
                claims.append(
                    {
                        "type": kind,
                        "status": "self_reported"
                        if o["basis"] == "page_text"
                        else "snippet_only",
                        "url": o["url"],
                        "excerpt": text[max(0, match.start() - 65) : match.end() + 100],
                        "basis": o["basis"],
                    }
                )
    kinds = {c["type"] for c in claims}
    # Conflicting claims stay reviewable rather than silently selecting one.
    conflict = "chain_or_franchise" in kinds and bool(
        kinds & {"solo_provider", "independent_business"}
    )
    lead.operator_type = (
        "unknown"
        if conflict or not claims
        else next((k for k, _ in patterns if k in kinds), "unknown")
    )
    lead.operator_confidence = (
        "conflicting_evidence"
        if conflict
        else (
            "self_reported"
            if any(
                c["status"] == "self_reported" and c["type"] == lead.operator_type
                for c in claims
            )
            else ("snippet_only" if claims else "unknown")
        )
    )
    lead.operator_evidence = json.dumps(claims, ensure_ascii=False)
    if lead.operator_type == "unknown":
        assumptions.append(
            "Operator ownership, independence and team size are unknown."
        )
        flags.append("operator_unconfirmed")
    if lead.operator_confidence == "snippet_only":
        flags.append("operator_snippet_only")
    if conflict:
        flags.append("conflicting_operator_claims")
    if platform:
        assumptions.append(
            "A seller profile does not prove the provider is a solo operator."
        )
        flags.append("contact_via_platform")
    page_observed = any(
        o["basis"] == "page_text" and o.get("text", "").strip() for o in observations
    )
    lead.source_strength = (
        "marketplace_profile"
        if platform
        else (
            "first_party_page"
            if page_observed
            else (
                "public_listing"
                if lead.source
                in ("google_maps_browser", "google_maps_local", "openstreetmap")
                else "search_snippet"
                if lead.source == "web"
                else "unknown"
            )
        )
    )
    if not page_observed and lead.source == "web":
        flags.append("snippet_only_source")
    if not lead.email:
        flags.append("missing_email")
    if not lead.phone:
        flags.append("missing_phone")
    if lead.contact_status in ("no_readable_content", "unavailable"):
        flags.append("website_evidence_unavailable")
    if lead.match_status == "candidate":
        flags.append("service_unconfirmed")
    location_words = [
        x.strip().casefold()
        for x in (lead.search_location or lead.city).split(",")
        if len(x.strip()) > 2
    ]
    geo = next(
        (
            o
            for o in observations
            if o["basis"] == "page_text"
            and location_words
            and location_words[0] in o["text"].casefold()
        ),
        None,
    )
    if lead.address:
        lead.location_evidence = (
            "address_mentions_search_city"
            if location_words and location_words[0] in lead.address.casefold()
            else "address_city_needs_review"
        )
        if lead.location_evidence == "address_city_needs_review":
            flags.append("office_outside_or_unconfirmed_query_city")
    else:
        lead.location_evidence = "place_mentioned_on_page" if geo else "query_only"
    assumptions.append(
        "Mentioning a city or searching within it does not independently confirm the full service area."
    )
    if lead.location_evidence == "query_only":
        flags.append("geography_query_only")
    lead.facts = json.dumps(facts, ensure_ascii=False)
    lead.assumptions = json.dumps(assumptions, ensure_ascii=False)
    lead.quality_flags = json.dumps(flags)
    lead.evidence_score = min(
        100,
        (
            35
            if page_observed
            else 15
            if lead.source_strength == "public_listing"
            else 5
            if lead.source_strength == "search_snippet"
            else 0
        )
        + min(35, 5 * len(facts))
        + (15 if lead.match_status != "candidate" else 0)
        + (15 if lead.operator_confidence == "self_reported" else 0),
    )
    return lead


def quality_review(rows):
    weak_pairs = []
    shared_operator_signals = []
    for i, a in enumerate(rows):
        for b in rows[i + 1 :]:
            clean = lambda name: re.sub(
                r"\b(llc|inc|ltd|services?)\b|\W+", "", name.casefold()
            )
            if clean(a.name) and clean(a.name) == clean(b.name) and a.city == b.city:
                weak_pairs.append(
                    {
                        "names": [a.name, b.name],
                        "urls": [a.source_url, b.source_url],
                        "status": "possible_duplicate_not_auto_merged",
                    }
                )
                for row in (a, b):
                    row.quality_flags = json.dumps(
                        list(
                            dict.fromkeys(
                                json.loads(row.quality_flags) + ["possible_duplicate"]
                            )
                        )
                    )
            host_a = (urlparse(a.website).hostname or "").removeprefix("www.")
            host_b = (urlparse(b.website).hostname or "").removeprefix("www.")
            if host_a and host_b and host_a != host_b:
                emails_a = set(
                    filter(None, (a.emails or a.email).casefold().split("; "))
                )
                emails_b = set(
                    filter(None, (b.emails or b.email).casefold().split("; "))
                )

                def page_words(row):
                    return set(
                        re.findall(
                            r"[a-z]{3,}",
                            " ".join(
                                o.get("text", "")
                                for o in json.loads(row.observations or "[]")
                                if o.get("basis") == "page_text"
                            ).casefold(),
                        )
                    )

                words_a, words_b = page_words(a), page_words(b)
                near_copy = (
                    min(len(words_a), len(words_b)) >= 60
                    and len(words_a & words_b) / max(1, len(words_a | words_b)) >= 0.92
                )
                reason = (
                    "shared_published_email"
                    if emails_a & emails_b
                    else "near_identical_checked_page_excerpts"
                    if near_copy
                    else ""
                )
                if reason:
                    shared_operator_signals.append(
                        {
                            "names": [a.name, b.name],
                            "urls": [a.website, b.website],
                            "reason": reason,
                            "status": "review_only_not_proof_of_common_ownership",
                        }
                    )
                    for row in (a, b):
                        row.quality_flags = json.dumps(
                            list(
                                dict.fromkeys(
                                    json.loads(row.quality_flags)
                                    + ["possible_shared_operator_review"]
                                )
                            )
                        )
    missing = defaultdict(int)
    for row in rows:
        for flag in json.loads(row.quality_flags or "[]"):
            missing[flag] += 1
    return {
        "missing_or_weak": dict(missing),
        "possible_duplicates": weak_pairs,
        "shared_operator_signals": shared_operator_signals,
        "note": "Exact domain/phone matches are merged upstream. Ambiguous name matches remain flagged to preserve separate branches.",
    }


def balanced_select(
    rows, limit, prefer_independent=True, target="both", prefer_opportunity=False
):
    groups = defaultdict(list)
    ranks = {
        "solo_provider": 0,
        "independent_business": 1,
        "unknown": 2,
        "agency": 3,
        "chain_or_franchise": 4,
    }
    for row in sorted(
        rows,
        key=lambda r: (
            r.match_status == "candidate",
            ranks.get(r.operator_type, 2) if prefer_independent else 0,
            -float(r.opportunity_score or 0) if prefer_opportunity else 0,
            -r.score,
        ),
    ):
        bucket = (
            "provider"
            if row.profile_url or row.discovery_intent in ("individual", "profile")
            else "business"
        )
        groups[(row.city, bucket) if target == "both" else row.city].append(row)
    selected = []
    while len(selected) < limit and any(groups.values()):
        for group in groups.values():
            if group and len(selected) < limit:
                selected.append(group.pop(0))
    return selected
