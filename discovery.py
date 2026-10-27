"""Query planning, keyless web discovery and visible Chrome Maps extraction."""

from __future__ import annotations
import json
import re
import threading
import time
from pathlib import Path
from urllib.parse import quote, urlparse, unquote

from leadfinder import (
    Lead,
    CATEGORY_FILTERS,
    fetch,
    normalize_business_name,
    valid_entity_name,
)
import niche_catalog
from research import platform_profile, add_observation

ALIASES = {
    "hood cleaning": [
        "hood cleaning",
        "kitchen exhaust cleaning",
        "restaurant hood cleaning",
        "commercial hood degreasing",
    ],
    "roofing": ["roofer", "roofing contractor", "roof repair"],
    "plumbing": ["plumber", "plumbing contractor"],
    "hvac": ["hvac", "air conditioning contractor", "heating contractor"],
    "pressure washing": ["pressure washing", "power washing", "exterior cleaning"],
    "cleaning": ["cleaning service", "commercial cleaning", "janitorial service"],
    "dentist": ["dentist", "dental clinic"],
    "electrician": ["electrician", "electrical contractor"],
    "landscaping": ["landscaper", "landscaping service", "lawn care"],
    "pest control": ["pest control", "exterminator"],
    "food export": [
        "food exporters",
        "food export companies",
        "food product exporters",
        "food export services",
    ],
    "animal talent agencies": [
        "animal talent agencies",
        "animal actors agency",
        "pet talent agency",
        "animal casting agency",
        "animal talent management",
    ],
}
CATEGORY_NAMES = {
    "roofing": "roofer",
    "plumbing": "plumber",
    "dental clinic": "dentist",
    "dentists": "dentist",
    "restaurants": "restaurant",
    "air conditioning": "hvac",
    "roofing contractor": "roofer",
}
BROWSER_LOCK = threading.Lock()

DIRECTORY_HOSTS = (
    "upwork.com",
    "taskrabbit.com",
    "fiverr.com",
    "yelp.com",
    "yellowpages.com",
    "angi.com",
    "thumbtack.com",
    "bbb.org",
    "mapquest.com",
    "findhoodcleaner.com",
    "houzz.com",
    "homeadvisor.com",
    "bark.com",
    "porch.com",
    "manta.com",
    "chamberofcommerce.com",
)

NEGATIVE_MEDIA_HOSTS = (
    "dallasnews.com",
    "nytimes.com",
    "washingtonpost.com",
    "usatoday.com",
    "reuters.com",
    "apnews.com",
    "cnn.com",
    "foxnews.com",
    "nbcnews.com",
    "cbsnews.com",
    "abcnews.go.com",
    "newsweek.com",
    "forbes.com",
    "businessinsider.com",
    "legacy.com",
    "dignitymemorial.com",
    "echovita.com",
    "tributearchive.com",
    "newspapers.com",
)
_MEDIA_DOMAIN_LABEL_RE = re.compile(
    r"(?:^|[-.])(?:news|times|herald|tribune|gazette|observer|journal)(?:[-.]|$)",
    re.IGNORECASE,
)
_BUSINESS_SCHEMA_RE = re.compile(
    r"(?:schema\.org/(?:LocalBusiness|Organization)|"
    r"[\"']@type[\"']\s*:\s*(?:[\"'](?:LocalBusiness|Organization)[\"']|"
    r"\[[^\]]*[\"'](?:LocalBusiness|Organization)[\"']))",
    re.IGNORECASE,
)


def is_directory(url):
    host = (urlparse(url).hostname or "").removeprefix("www.")
    return any(
        host == domain or host.endswith("." + domain) for domain in DIRECTORY_HOSTS
    )


def is_negative_media_domain(url: str) -> bool:
    host = (urlparse(url).hostname or "").casefold().removeprefix("www.")
    return any(
        host == domain or host.endswith("." + domain) for domain in NEGATIVE_MEDIA_HOSTS
    ) or bool(_MEDIA_DOMAIN_LABEL_RE.search(host))


def has_explicit_business_schema(url: str) -> bool:
    """Allow a media-domain result only when the page identifies an entity."""
    try:
        document = fetch(url, timeout=12, retries=0)[:750_000].decode(
            "utf-8", errors="ignore"
        )
    except Exception:
        return False
    return bool(_BUSINESS_SCHEMA_RE.search(document))


def repair_generic_name(lead: Lead) -> None:
    """Replace navigation-label search titles with an observed page brand."""
    if lead.name.strip().casefold() not in {
        "about",
        "home",
        "contact",
        "for talent",
        "services",
        "our services",
    }:
        return
    try:
        observations = json.loads(lead.observations or "[]")
    except (TypeError, ValueError):
        return
    for observation in observations:
        if observation.get("basis") != "page_text":
            continue
        text = re.sub(r"\s+", " ", str(observation.get("text", ""))).strip()
        match = re.match(
            r"(?:ABOUT|HOME|CONTACT|FOR TALENT|SERVICES|OUR SERVICES)\s*(?:\||—|-)\s*(.{3,80}?)(?:\s+top of page|\s+ABOUT|\s+HOME|\s+FOR BRANDS|\s+FOR TALENT|\s+CONTACT)",
            text,
            re.I,
        )
        if match:
            candidate = match.group(1).strip(" |—-")
            if 1 < len(candidate.split()) <= 10:
                lead.name = candidate
                return


def _accepted_phrase(phrase: str, niche: str, curated: list[str]) -> tuple[bool, str]:
    normalized = re.sub(r"\s+", " ", phrase.casefold()).strip()
    base = re.sub(r"\s+", " ", niche.casefold()).strip()
    curated_set = {item.casefold() for item in curated}
    if normalized in curated_set:
        return True, "curated terminology"
    if (
        re.search(r"hood|kitchen\s+exhaust|restaurant\s+exhaust", base)
        and re.search(r"hood|exhaust", normalized)
        and re.search(r"clean|degreas|grease", normalized)
    ):
        return True, "specialist exhaust-cleaning terminology"
    if normalized in {f"{base} contractor", f"local {base}", f"independent {base}"}:
        return False, "generic modifier does not prove niche relevance"
    base_words = {
        word
        for word in re.findall(r"[a-z0-9]+", base)
        if len(word) > 2 and word not in {"service", "services", "company", "companies"}
    }
    phrase_words = set(re.findall(r"[a-z0-9]+", normalized))
    if base_words and not all(
        any(
            word.startswith(base_word[:4]) or base_word.startswith(word[:4])
            for word in phrase_words
        )
        for base_word in base_words
    ):
        return False, "missing distinctive niche term"
    return True, "user-supplied terminology"


def plan(niche: str, custom: str = "") -> dict:
    term = re.sub(r"\s+", " ", niche.casefold().strip())
    canonical = CATEGORY_NAMES.get(term, term)
    if any(x in term for x in ("hood", "kitchen exhaust", "restaurant exhaust")):
        key = "hood cleaning"
    else:
        key = next((k for k, v in ALIASES.items() if term == k or term in v), term)
    catalog_entry = niche_catalog.lookup(term)
    curated = list(
        dict.fromkeys(
            [*ALIASES.get(key, []), *(catalog_entry or {}).get("synonyms", [])]
        )
    )
    starting = curated if key == "food export" else [niche.strip(), *curated]
    phrases = []
    rejected = []
    for phrase in starting + [
        x.strip() for x in re.split(r"[\n;]", custom) if x.strip()
    ]:
        accepted, reason = _accepted_phrase(phrase, niche, curated)
        if not accepted:
            rejected.append({"phrase": phrase, "reason": reason})
        elif phrase and phrase.casefold() not in {x.casefold() for x in phrases}:
            phrases.append(phrase)
    # Four curated aliases plus up to six local-AI/user tags fit without silently
    # dropping the assistant's normal output. The query budget still bounds work.
    phrases = phrases[:12]
    mapped = canonical in CATEGORY_FILTERS
    return {
        "phrases": phrases,
        "category": canonical,
        "osm_mapped": mapped,
        "specialized": key == "hood cleaning",
        "rejected_phrases": rejected,
        "note": "OSM searches these service phrases in names/descriptions. Web and Maps are recommended for this niche."
        if not mapped
        else "OSM category mapping and expanded web/Maps phrases are available.",
    }


def relevance(lead: Lead, search_plan: dict, location: str, content: str = "") -> None:
    # Domain keywords are discovery hints, never proof that an active service exists.
    host = (urlparse(lead.website).hostname or "").removeprefix("www.")
    name = (
        ""
        if lead.name.removeprefix("www.").casefold() == host.casefold()
        else lead.name
    )
    try:
        page_text = " ".join(
            o.get("text", "")
            for o in json.loads(lead.observations or "[]")
            if o.get("basis") == "page_text"
        )
    except (ValueError, TypeError):
        page_text = ""
    text = " ".join((name, lead.category, content, page_text)).casefold()
    phrases = [x.casefold() for x in search_plan["phrases"]]
    animal_talent_niche = any(
        "animal talent" in phrase
        or "animal casting" in phrase
        or "pet talent" in phrase
        for phrase in phrases
    )
    if animal_talent_niche:
        animal_pattern = r"\b(?:animal|animals|pet|pets|dog|dogs|canine|k9)\b"
        talent_pattern = r"\b(?:talent|casting|actor|actors|model|models|modeling)\b"
        if re.search(animal_pattern, page_text, re.I) and re.search(
            talent_pattern, page_text, re.I
        ):
            lead.match_status = "service_match"
            lead.match_reason = "First-party page evidence mentions animals or pets together with talent, casting, acting, or modeling. Confirm geographic coverage separately."
        elif re.search(animal_pattern, name, re.I) and re.search(
            r"talent|model|casting|entertainment", lead.category, re.I
        ):
            lead.match_status = "category_match"
            lead.match_reason = "The public listing name is animal-focused and its listed category is talent/model/casting related; confirm services on the business website."
        else:
            lead.match_status = "candidate"
            lead.match_reason = "A broad talent-agency search returned this record, but retained evidence does not confirm animal or pet talent services."
        return
    words = [
        w
        for w in re.findall(r"[a-z]{3,}", phrases[0])
        if w not in ("service", "services", "contractor", "company")
    ]

    def contains_phrase(phrase):
        return bool(
            re.search(
                r"(?<![a-z0-9])" + re.escape(phrase) + r"(?![a-z0-9])",
                text,
            )
        )

    hit = next((p for p in phrases if contains_phrase(p)), "")
    if search_plan["specialized"]:
        # General maid/carpet companies are not promoted to hood-cleaning results.
        hit = next(
            (
                p
                for p in (
                    "hood cleaning",
                    "exhaust cleaning",
                    "hood cleaner",
                    "hood degreasing",
                    "exhaust degreasing",
                )
                if contains_phrase(p)
            ),
            "",
        )
    word_hit = words and all(contains_phrase(w) for w in words)
    if hit or word_hit:
        lead.match_status = "service_match"
        lead.match_reason = f"Service evidence: {hit or ', '.join(words)}. Location was used in discovery; confirm service coverage."
    elif lead.source == "openstreetmap" and search_plan["osm_mapped"]:
        lead.match_status = "category_match"
        lead.match_reason = "Mapped OSM category inside the searched area."
    else:
        lead.match_status = "candidate"
        lead.match_reason = (
            "Returned by a search phrase; specialty needs manual confirmation."
        )


def web_search(search_plan, location, limit, cancel, emit):
    from ddgs import DDGS

    rows = []
    seen = set()
    successful = 0
    errors = []
    excluded = (
        "yelp.com",
        "yellowpages.com",
        "facebook.com",
        "instagram.com",
        "linkedin.com",
        "youtube.com",
        "angi.com",
        "thumbtack.com",
        "bbb.org",
        "mapquest.com",
        "google.com",
        "bing.com",
        "wikipedia.org",
    )
    queries = search_plan.get("web_queries")
    if queries is None:
        queries = [
            {"query": f"{phrase} {location}", "intent": "business"}
            for phrase in search_plan["phrases"]
        ]
    for query_plan in queries:
        if cancel.is_set():
            break
        query = query_plan["query"]
        started = time.monotonic()
        try:
            # Use ordinary keyless engines through the maintained MIT adapter.
            results = list(
                DDGS(timeout=12).text(
                    query,
                    max_results=min(max(limit, 4), 20),
                    backend="auto",
                )
            )
            successful += 1
            emit(
                "web",
                "info",
                "Web phrase returned",
                query=query,
                count=len(results),
                seconds=round(time.monotonic() - started, 2),
                intent=query_plan.get("intent"),
                backend="auto",
            )
        except Exception as exc:
            errors.append(str(exc))
            emit(
                "web",
                "warning",
                "Web search unavailable",
                query=query,
                error=str(exc)[:300],
            )
            continue
        for result in results:
            url = result.get("href", "")
            host = (urlparse(url).hostname or "").removeprefix("www.")
            profile = platform_profile(url)
            if is_negative_media_domain(url) and not has_explicit_business_schema(url):
                emit(
                    "web",
                    "info",
                    "News, obituary or general-media result excluded",
                    url=url,
                    reason="negative_media_domain_without_business_schema",
                )
                continue
            if query_plan.get("intent") == "profile" and not profile:
                emit(
                    "web",
                    "info",
                    "Platform landing page skipped; no supported provider profile detected",
                    url=url,
                )
                continue
            if is_directory(url) and not profile:
                emit(
                    "web",
                    "info",
                    "Directory result excluded from business list",
                    url=url,
                )
                continue
            key = host + urlparse(url).path if profile else host
            if (
                not host
                or key in seen
                or (
                    not profile
                    and any(host == x or host.endswith("." + x) for x in excluded)
                )
            ):
                continue
            seen.add(key)
            title = normalize_business_name(result.get("title", ""), location)
            if not valid_entity_name(title):
                emit(
                    "web",
                    "info",
                    "Probable multi-listing container excluded",
                    url=url,
                    reason="invalid_entity_name_boundary",
                    title=str(result.get("title", ""))[:180],
                )
                continue
            lead = Lead(
                name=title or host,
                category="",
                city=location,
                search_location=location,
                website="" if profile else url,
                profile_url=url if profile else "",
                source="public_profile" if profile else "web",
                source_id=key if profile else "",
                discovery_query=query,
                discovery_intent=query_plan.get("intent", "business"),
                source_url=url,
                sources="public_profile" if profile else "web",
            )
            # Do not treat query category as proof of the site's actual service.
            lead.category = ""
            add_observation(
                lead, "search_result", result.get("body", ""), url, "search_snippet"
            )
            relevance(lead, search_plan, location, result.get("body", ""))
            rows.append(lead)
    if not successful and errors:
        raise RuntimeError(
            "Web engines returned no usable response: " + errors[-1][:180]
        )
    return rows


def browser_maps(search_plan, location, limit, cancel, emit, checkpoint, profile: Path):
    from playwright.sync_api import sync_playwright, TimeoutError as BrowserTimeout
    import browser_session

    if not BROWSER_LOCK.acquire(blocking=False):
        raise RuntimeError("The dedicated Chrome profile is busy with another search")
    existing_checkpoint = browser_session.search_checkpoint_status()
    if existing_checkpoint["paused"]:
        try:
            browser_session.open_service("maps")
            emit(
                "browser",
                "warning",
                "Chrome opened for the saved Google checkpoint. Complete any challenge, then choose Resume after CAPTCHA; this run waits up to 3 minutes.",
                action_required=True,
                reason=existing_checkpoint.get("reason", "security_checkpoint"),
            )
            deadline = time.monotonic() + 180
            while time.monotonic() < deadline and not cancel.wait(1):
                if not browser_session.search_checkpoint_status()["paused"]:
                    emit(
                        "browser",
                        "info",
                        "Saved browser checkpoint cleared; Maps search resumed",
                    )
                    break
            else:
                raise RuntimeError(
                    "Google browser search remains paused. Complete the visible Chrome checkpoint, then choose Resume after CAPTCHA."
                )
        except Exception:
            BROWSER_LOCK.release()
            raise
    rows = []
    seen = set()

    def check_pause(page):
        def needs_action():
            challenged = (
                "/sorry/" in page.url
                or "accounts.google.com/" in page.url
                or page.locator(
                    'iframe[src*="recaptcha"], form[action*="sorry"]'
                ).count()
            )
            if challenged:
                return True
            try:
                return bool(
                    re.search(
                        r"unusual traffic|verify you are human|not a robot|captcha|access denied",
                        page.locator("body").inner_text(timeout=1200)[:4000],
                        re.I,
                    )
                )
            except Exception:
                return False

        if needs_action():
            browser_session._pause_public_search(
                "Google Maps displayed a CAPTCHA or traffic-security checkpoint; complete it manually before resuming"
            )
            wait_started = time.monotonic()
            emit(
                "browser",
                "warning",
                "Chrome needs your attention. Complete the challenge in its window; this search waits up to 3 minutes.",
                action_required=True,
            )
            deadline = time.monotonic() + 180
            while time.monotonic() < deadline and not cancel.wait(1):
                if not needs_action():
                    browser_session.clear_search_checkpoint()
                    emit(
                        "browser",
                        "info",
                        "Chrome challenge cleared; search resumed",
                        paused_seconds=round(time.monotonic() - wait_started, 1),
                        reason="browser_challenge_cleared",
                    )
                    return
            emit(
                "browser",
                "error",
                "Chrome challenge wait ended",
                reason="cancelled" if cancel.is_set() else "challenge_timeout",
                paused_seconds=round(time.monotonic() - wait_started, 1),
                limit_seconds=180,
            )
            raise RuntimeError(
                "Browser challenge still requires your action; partial results were retained"
            )

    try:
        with sync_playwright() as p:
            shared_browser = None
            if (
                browser_session.running()
                and profile.resolve() == browser_session.PROFILE.resolve()
            ):
                shared_browser = p.chromium.connect_over_cdp(browser_session.DEBUG_BASE)
                context = shared_browser.contexts[0]
                emit(
                    "browser",
                    "info",
                    "Reusing the open dedicated Chrome session",
                    profile=str(profile),
                    persistent_login=True,
                )
            else:
                context = p.chromium.launch_persistent_context(
                    str(profile),
                    channel="chrome",
                    headless=False,
                    locale="en-US",
                    viewport={"width": 1280, "height": 900},
                )
            context.set_default_timeout(8000)
            try:
                page = context.pages[0] if context.pages else context.new_page()
                queries = search_plan.get("map_queries")
                if queries is None:
                    queries = [
                        {"phrase": p, "query": f"{p} in {location}"}
                        for p in search_plan["phrases"]
                    ]
                quota = max(
                    1, (limit + max(1, len(queries)) - 1) // max(1, len(queries))
                )
                for query_plan in queries:
                    if cancel.is_set():
                        break
                    query = query_plan["query"]
                    target = len(rows) + quota
                    emit(
                        "browser",
                        "info",
                        "Opening Google Maps in dedicated Chrome",
                        query=query,
                    )
                    page.goto(
                        "https://www.google.com/maps/search/" + quote(query) + "?hl=en",
                        wait_until="domcontentloaded",
                        timeout=35000,
                    )
                    check_pause(page)
                    # Handle only a normal public consent choice. The dedicated profile
                    # retains the user's own session between searches.
                    for label in ("Reject all", "Accept all"):
                        consent = page.get_by_role("button", name=label, exact=True)
                        if consent.count():
                            consent.first.click()
                            break
                    try:
                        page.locator('a[href*="/maps/place/"]').first.wait_for(
                            timeout=18000
                        )
                    except BrowserTimeout:
                        check_pause(page)
                        emit(
                            "browser",
                            "warning",
                            "No public Maps listings appeared",
                            query=query,
                            reason="no_public_listings_timeout",
                            waited_seconds=18,
                        )
                        continue
                    links = []
                    stale = 0
                    scroll_cycles = 0
                    stop_reason = "iteration_limit"
                    stop_detail = "Reached the 30-scroll safety limit"
                    link_threshold = max(quota * 2, 5)
                    for _ in range(30):
                        scroll_cycles += 1
                        if cancel.is_set():
                            stop_reason = "cancelled"
                            stop_detail = "The user stopped the search"
                            break
                        current = page.locator('a[href*="/maps/place/"]').evaluate_all(
                            '(els)=>els.map(e=>({url:e.href,name:e.getAttribute("aria-label")}))'
                        )
                        before = len(links)
                        for row in current:
                            if row["url"] not in {x["url"] for x in links}:
                                links.append(row)
                        stale = stale + 1 if len(links) == before else 0
                        if len(links) >= link_threshold:
                            stop_reason = "link_threshold_reached"
                            stop_detail = f"Collected the per-query link threshold of {link_threshold}"
                            break
                        if stale >= 3:
                            stop_reason = "no_new_links_after_three_scrolls"
                            stop_detail = "Three consecutive scroll checks added no new listing links"
                            break
                        feed = page.get_by_role("feed")
                        if not feed.count():
                            stop_reason = "results_feed_missing"
                            stop_detail = (
                                "Google Maps did not expose a scrollable results feed"
                            )
                            break
                        feed.evaluate("(e)=>e.scrollBy(0,900)")
                        if cancel.wait(1.1):
                            stop_reason = "cancelled"
                            stop_detail = "The user stopped the search while scrolling"
                            break
                    emit(
                        "browser",
                        "info" if stop_reason != "results_feed_missing" else "warning",
                        "Maps scrolling stopped",
                        query=query,
                        reason=stop_reason,
                        explanation=stop_detail,
                        scroll_cycles=scroll_cycles,
                        links_collected=len(links),
                        stale_checks=stale,
                        requested_query_quota=quota,
                        link_threshold=link_threshold,
                    )
                    emit(
                        "browser",
                        "info",
                        "Maps listing links collected",
                        query=query,
                        count=len(links),
                    )
                    query_start_count = len(rows)
                    listing_attempts = 0
                    listing_failures = 0
                    processing_stop_reason = "all_collected_links_processed"
                    for item in links:
                        if cancel.is_set() or len(rows) >= target:
                            processing_stop_reason = (
                                "cancelled"
                                if cancel.is_set()
                                else "per_query_quota_reached"
                            )
                            break
                        # Prefer stable place data in URL where available.
                        key = (
                            unquote(item["url"]).split("!1s")[-1].split("!")[0]
                            if "!1s" in item["url"]
                            else item["url"].split("?")[0]
                        )
                        if key in seen:
                            continue
                        seen.add(key)
                        listing_attempts += 1
                        try:
                            page.goto(
                                item["url"],
                                wait_until="domcontentloaded",
                                timeout=25000,
                            )
                            check_pause(page)
                            page.locator("h1").first.wait_for(timeout=9000)

                            def attr(selector, name="aria-label"):
                                el = page.locator(selector)
                                return (
                                    (el.first.get_attribute(name) or "")
                                    if el.count()
                                    else ""
                                )

                            name = page.locator("h1").first.inner_text()
                            phone = attr('[data-item-id^="phone:tel:"]').removeprefix(
                                "Phone: "
                            )
                            address = attr('[data-item-id="address"]').removeprefix(
                                "Address: "
                            )
                            site = attr('a[data-item-id="authority"]', "href")
                            category_el = page.locator('button[jsaction*="category"]')
                            category = (
                                category_el.first.inner_text()
                                if category_el.count()
                                else ""
                            )
                            rating_label = attr('[role="img"][aria-label*="stars"]')
                            rating_match = re.search(r"([\d.]+) stars", rating_label)
                            review_button = page.get_by_role(
                                "button", name=re.compile(r"[\d,]+ reviews", re.I)
                            )
                            review_label = (
                                (
                                    review_button.first.get_attribute("aria-label")
                                    or review_button.first.inner_text()
                                )
                                if review_button.count()
                                else ""
                            )
                            review_match = re.search(
                                r"([\d,]+)\s+reviews", review_label, re.I
                            )
                            row = Lead(
                                name=name,
                                category=category,
                                address=address,
                                city=location,
                                search_location=location,
                                phone=phone,
                                website=site,
                                source="google_maps_browser",
                                sources="google_maps_browser",
                                source_id=key,
                                source_url=item["url"],
                                rating=rating_match[1] if rating_match else "",
                                discovery_query=query,
                                discovery_intent=query_plan.get("intent", "business"),
                            )
                            row.reviews = (
                                review_match[1].replace(",", "") if review_match else ""
                            )
                            coordinates = re.search(
                                r"!3d(-?[\d.]+)!4d(-?[\d.]+)", item["url"]
                            )
                            if coordinates:
                                row.latitude, row.longitude = coordinates.groups()
                            relevance(row, search_plan, location)
                            rows.append(row)
                            checkpoint(row)
                            emit(
                                "browser", "info", "Business collected", count=len(rows)
                            )
                        except Exception as exc:
                            listing_failures += 1
                            emit(
                                "browser",
                                "warning",
                                "Listing details unavailable",
                                error=str(exc)[:220],
                            )
                        if cancel.wait(0.7):
                            processing_stop_reason = "cancelled"
                            break
                    emit(
                        "browser",
                        "info",
                        "Maps listing processing stopped",
                        query=query,
                        reason=processing_stop_reason,
                        links_available=len(links),
                        listing_attempts=listing_attempts,
                        listing_failures=listing_failures,
                        new_businesses=len(rows) - query_start_count,
                        requested_query_quota=quota,
                    )
            finally:
                if shared_browser is not None:
                    shared_browser.close()
                else:
                    context.close()
    finally:
        BROWSER_LOCK.release()
    return rows
