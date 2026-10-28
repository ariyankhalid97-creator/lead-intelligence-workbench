"""One persistent, local Chrome profile shared by Maps and assisted social review."""

from __future__ import annotations

import base64
import json
import re
import subprocess
import threading
import time
from pathlib import Path
from urllib.parse import quote, urlparse, parse_qs
from urllib.request import Request, urlopen

import engine
from contacts import public_url

PROFILE = engine.ROOT / "data" / "chrome-profile"
STATE = engine.ROOT / "data" / "browser-session.json"
DEBUG_PORT = 9223
DEBUG_BASE = f"http://127.0.0.1:{DEBUG_PORT}"
SEARCH_LOCK = threading.Lock()
LAST_GOOGLE_SEARCH = 0.0

DESTINATIONS = {
    "facebook": "https://www.facebook.com/",
    "linkedin": "https://www.linkedin.com/feed/",
    "maps": "https://www.google.com/maps/",
}


def chrome_path() -> Path | None:
    candidates = (
        Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),
        Path("C:/Program Files (x86)/Google/Chrome/Application/chrome.exe"),
    )
    return next((path for path in candidates if path.exists()), None)


def _debug_json(path: str, timeout: float = 0.8):
    with urlopen(DEBUG_BASE + path, timeout=timeout) as response:
        return json.load(response)


def running() -> bool:
    try:
        return bool(_debug_json("/json/version").get("Browser"))
    except Exception:
        return False


def _remember(service: str):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    previous = _state()
    previous.update(
        service=service,
        last_opened=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        profile=str(PROFILE),
        services=previous.get("services", {"facebook": True, "linkedin": True}),
    )
    STATE.write_text(json.dumps(previous, indent=2), encoding="utf-8")


def _state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def enabled_services() -> dict[str, bool]:
    configured = _state().get("services", {})
    return {
        "facebook": configured.get("facebook", True) is True,
        "linkedin": configured.get("linkedin", True) is True,
    }


def set_preferences(params: dict) -> dict:
    if not isinstance(params, dict):
        raise ValueError("Choose valid browser preferences")
    services = enabled_services()
    for name in services:
        if name in params:
            services[name] = params[name] is True
    previous = _state()
    previous.update(services=services, profile=str(PROFILE))
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(previous, indent=2), encoding="utf-8")
    return status()


def status() -> dict:
    previous = _state()
    chrome = chrome_path()
    return {
        "available": bool(chrome),
        "running": running(),
        "persistent": True,
        "profile_exists": PROFILE.exists(),
        "profile_path": str(PROFILE),
        "last_opened": previous.get("last_opened", ""),
        "last_service": previous.get("service", ""),
        "services": enabled_services(),
        "search_checkpoint": search_checkpoint_status(),
        "message": (
            "Dedicated browser is open. Sign-ins made here are retained."
            if running()
            else "Dedicated profile is ready. Open a service and sign in once."
        ),
    }


def _new_tab(url: str):
    request = Request(DEBUG_BASE + "/json/new?" + quote(url, safe=""), method="PUT")
    with urlopen(request, timeout=2) as response:
        return json.load(response)


def open_service(service: str) -> dict:
    if service not in DESTINATIONS and service != "all":
        raise ValueError("Choose Facebook, LinkedIn, Maps, or all services")
    chrome = chrome_path()
    if not chrome:
        raise ValueError("Google Chrome is not installed in a supported location")
    PROFILE.mkdir(parents=True, exist_ok=True)
    enabled = enabled_services()
    if service in enabled and not enabled[service]:
        raise ValueError(f"{service.title()} is disabled in this research profile")
    urls = [
        DESTINATIONS[name]
        for name in ("facebook", "linkedin")
        if service == "all" and enabled[name]
    ] if service == "all" else [DESTINATIONS[service]]
    if not urls:
        raise ValueError("No social services are enabled in this research profile")
    if running():
        for url in urls:
            _new_tab(url)
    else:
        subprocess.Popen(
            [
                str(chrome),
                f"--user-data-dir={PROFILE}",
                f"--remote-debugging-port={DEBUG_PORT}",
                "--remote-debugging-address=127.0.0.1",
                "--no-first-run",
                "--no-default-browser-check",
                "--new-window",
                *urls,
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        )
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline and not running():
            time.sleep(0.2)
        if not running():
            raise RuntimeError(
                "Chrome did not open the dedicated profile. Close any older dedicated Chrome window and try again."
            )
    _remember(service)
    try:
        import intelligence

        for name in (("facebook", "linkedin") if service == "all" else (service,)):
            if name in DESTINATIONS and (name not in enabled or enabled.get(name, True)):
                intelligence.browser_checkpoint(
                    {
                        "service": name,
                        "url": DESTINATIONS[name],
                        "status": "opened",
                        "detail": "Dedicated persistent Chrome profile opened; login state is retained locally.",
                    }
                )
    except Exception:
        pass
    return status()


def open_url(value: str, company_id: str = "") -> dict:
    """Open one validated public URL in the persistent research profile."""
    url = public_url(value)
    host = (urlparse(url).hostname or "").casefold()
    if "facebook.com" in host and not enabled_services()["facebook"]:
        raise ValueError("Facebook is disabled in this research profile")
    if "linkedin.com" in host and not enabled_services()["linkedin"]:
        raise ValueError("LinkedIn is disabled in this research profile")
    chrome = chrome_path()
    if not chrome:
        raise ValueError("Google Chrome is not installed in a supported location")
    PROFILE.mkdir(parents=True, exist_ok=True)
    if running():
        _new_tab(url)
    else:
        subprocess.Popen(
            [
                str(chrome),
                f"--user-data-dir={PROFILE}",
                f"--remote-debugging-port={DEBUG_PORT}",
                "--remote-debugging-address=127.0.0.1",
                "--no-first-run",
                "--no-default-browser-check",
                "--new-window",
                url,
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        )
    _remember("website")
    try:
        import intelligence

        intelligence.browser_checkpoint(
            {
                "company_id": company_id,
                "service": "linkedin" if "linkedin.com" in host else "website",
                "url": url,
                "status": "opened",
                "detail": "Opened in the persistent dedicated Chrome profile for manual evidence review.",
            }
        )
    except Exception:
        pass
    return {**status(), "opened_url": url}


def _pause_public_search(reason: str, seconds: int = 900):
    state = _state()
    state.update(search_paused=True, search_pause_until=time.time() + seconds, search_pause_reason=reason[:400], profile=str(PROFILE))
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def search_checkpoint_status() -> dict:
    state = _state()
    remaining = max(0, int(float(state.get("search_pause_until", 0) or 0) - time.time()))
    paused = state.get("search_paused") is True or remaining > 0
    return {"paused": paused, "manual_resume_required": state.get("search_paused") is True, "remaining_seconds": remaining, "reason": state.get("search_pause_reason", "") if paused else ""}


def clear_search_checkpoint() -> dict:
    state = _state()
    state.pop("search_pause_until", None)
    state.pop("search_pause_reason", None)
    state.pop("search_paused", None)
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return search_checkpoint_status()


def _fallback_candidates(tokens, targeted_queries, enabled, cancel=None):
    output, error, seen = [], "", set()
    try:
        from ddgs import DDGS
        for targeted_query in targeted_queries:
            if cancel and cancel.is_set():
                break
            try:
                results = DDGS(timeout=12).text(targeted_query, max_results=8, backend="auto")
            except Exception as exc:
                error = str(exc)[:220]
                continue
            for item in results:
                href = str(item.get("href", ""))
                host = (urlparse(href).hostname or "").casefold().removeprefix("www.")
                kind = ""
                if host.endswith("linkedin.com"):
                    kind = "linkedin_person" if "/in/" in href else "linkedin_company" if "/company/" in href else ""
                elif host.endswith("instagram.com"):
                    kind = "instagram"
                elif host.endswith("facebook.com") and enabled.get("facebook"):
                    kind = "facebook"
                elif host.endswith("yelp.com"):
                    kind = "yelp"
                elif host.endswith("bbb.org"):
                    kind = "bbb"
                if not kind or href in seen:
                    continue
                seen.add(href)
                title = re.sub(r"\s+", " ", str(item.get("title", ""))).strip()[:300]
                excerpt = re.sub(r"\s+", " ", str(item.get("body", ""))).strip()[:500]
                haystack = (href + " " + title + " " + excerpt).casefold()
                overlap = len([token for token in tokens if token in haystack])
                confidence = 0.88 if overlap >= 2 else 0.68 if overlap == 1 else 0.3
                output.append({"kind": kind, "url": href[:1500], "title": title, "excerpt": excerpt, "query": targeted_query, "source": "public_search_fallback_after_chrome", "confidence": confidence, "confirmation_state": "candidate_needs_review"})
                if len(output) >= 15:
                    return output, error
    except Exception as exc:
        error = str(exc)[:220]
    return output, error


def _canonical_linkedin_company_url(value: str) -> str:
    """Return only a public LinkedIn company-page URL, never a person profile."""
    try:
        parsed = urlparse(str(value or ""))
    except ValueError:
        return ""
    host = (parsed.hostname or "").casefold().removeprefix("www.")
    match = re.match(r"^/company/([^/?#]+)", parsed.path or "", re.I)
    if host not in {"linkedin.com", "www.linkedin.com"} or not match:
        return ""
    slug = match.group(1).strip()
    return f"https://www.linkedin.com/company/{slug}/" if slug else ""


def _google_linkedin_company(name: str, cancel=None) -> dict:
    """Type one exact company lookup in visible Chrome and retain its public URL.

    This is intentionally narrow: it does not read employee profiles, bypass a
    checkpoint, or collect private LinkedIn data. A Google security challenge
    is left open in Chrome and reported to the workflow for manual resumption.
    """
    global LAST_GOOGLE_SEARCH
    query = f'"{name}" LinkedIn'
    if cancel and cancel.is_set():
        return {"status": "cancelled", "query": query, "candidates": []}
    with SEARCH_LOCK:
        if cancel and cancel.is_set():
            return {"status": "cancelled", "query": query, "candidates": []}
        checkpoint = search_checkpoint_status()
        if checkpoint["paused"]:
            return {
                "status": "manual_checkpoint",
                "query": query,
                "candidates": [],
                "browser_checkpoint": checkpoint["reason"],
                "browser_retry_after_seconds": checkpoint["remaining_seconds"],
            }
        try:
            if not running():
                open_service("linkedin")
            # Keep searches serial and moderately paced. This is normal browser
            # operation, not an attempt to conceal automation or evade controls.
            remaining = 2.5 - (time.monotonic() - LAST_GOOGLE_SEARCH)
            if remaining > 0:
                time.sleep(remaining)
            from playwright.sync_api import sync_playwright

            pw = sync_playwright().start()
            browser = pw.chromium.connect_over_cdp(DEBUG_BASE)
            context = browser.contexts[0]
            page = context.new_page()
            keep_open = False
            try:
                page.goto("https://www.google.com/", wait_until="domcontentloaded", timeout=18000)
                box = page.locator('textarea[name="q"], input[name="q"]').first
                box.click(timeout=5000)
                box.press_sequentially(query, delay=45)
                box.press("Enter")
                page.wait_for_load_state("domcontentloaded", timeout=18000)
                page.wait_for_timeout(900)
                LAST_GOOGLE_SEARCH = time.monotonic()
                response_text = page.locator("body").inner_text(timeout=3000)[:8000]
                if re.search(
                    r"unusual traffic|not a robot|captcha|verify you are human|security check",
                    response_text,
                    re.I,
                ):
                    reason = "Google security checkpoint is open in the dedicated Chrome profile; complete it manually, then resume verification"
                    _pause_public_search(reason)
                    keep_open = True
                    return {
                        "status": "manual_checkpoint",
                        "query": query,
                        "candidates": [],
                        "browser_checkpoint": reason,
                        "browser_retry_after_seconds": 900,
                    }
                anchors = page.locator("a").evaluate_all(
                    "els => els.map(a => ({href:a.href || '', title:(a.innerText || a.textContent || '').trim()}))"
                )
                name_tokens = {
                    token
                    for token in re.findall(r"[a-z0-9]{3,}", name.casefold())
                    if token not in {"the", "and", "llc", "inc", "company", "corp"}
                }
                candidates = []
                seen = set()
                for anchor in anchors:
                    url = _canonical_linkedin_company_url(anchor.get("href", ""))
                    if not url or url in seen:
                        continue
                    seen.add(url)
                    title = re.sub(r"\s+", " ", str(anchor.get("title", ""))).strip()[:300]
                    haystack = (url + " " + title).casefold()
                    overlap = sorted(token for token in name_tokens if token in haystack)
                    confidence = 0.94 if len(overlap) >= 2 else 0.76 if overlap else 0.35
                    candidates.append(
                        {
                            "kind": "linkedin_company",
                            "url": url,
                            "title": title,
                            "excerpt": title,
                            "query": query,
                            "source": "google_typed_company_lookup",
                            "confidence": confidence,
                            "matched_name_terms": overlap,
                            "confirmation_state": "public_company_url_candidate",
                        }
                    )
                accepted = next(
                    (item for item in candidates if item["confidence"] >= 0.7), None
                )
                if accepted:
                    # Open the public result once, as requested, but retain the
                    # canonical result URL even if LinkedIn shows an auth wall.
                    page.goto(accepted["url"], wait_until="domcontentloaded", timeout=18000)
                    page.wait_for_timeout(500)
                return {
                    "status": "complete",
                    "query": query,
                    "candidates": candidates[:4],
                    "candidate_count": len(candidates[:4]),
                }
            finally:
                if not keep_open:
                    page.close()
                pw.stop()
        except Exception as exc:
            return {
                "status": "failed",
                "query": query,
                "candidates": [],
                "error": f"Exact Google LinkedIn lookup could not finish: {str(exc)[:260]}",
            }


def search_company_sources(name: str, location: str, cancel=None) -> dict:
    """Use the persistent visible Chrome profile for one bounded public Google search."""
    name = re.sub(r"\s+", " ", str(name or "")).strip()[:160]
    location = re.sub(r"\s+", " ", str(location or "")).strip()[:160]
    location_query = re.sub(r"[^A-Za-z0-9 ]+", " ", location.split(",", 1)[0] if "," in location else location)
    location_query = re.sub(r"\s+", " ", location_query).strip()
    if not name:
        return {"status": "not_run", "query": "", "candidates": [], "error": "Business name missing"}
    enabled = enabled_services()
    domains = ["linkedin.com/company", "linkedin.com/in", "instagram.com", "yelp.com", "bbb.org"]
    if enabled.get("facebook"):
        domains.append("facebook.com")
    query = f'"{name}" "{location}" social profiles reviews'.strip()
    search_url = "https://www.google.com/search?q=" + quote(query) + "&num=20"
    targeted_queries = [
        f'"{name}" {location_query} LinkedIn',
        f'"{name}" {location_query} Instagram',
        f'"{name}" {location_query} Yelp BBB',
    ]
    fallback_search_urls = ["https://www.bing.com/search?q=" + quote(item) + "&count=12" for item in targeted_queries]
    tokens = {token for token in re.findall(r"[a-z0-9]{3,}", name.casefold()) if token not in {"the", "and", "llc", "inc", "company", "corp"}}
    if cancel and cancel.is_set():
        return {"status": "cancelled", "query": query, "candidates": []}
    checkpoint = search_checkpoint_status()
    if checkpoint["paused"]:
        output, fallback_error = _fallback_candidates(tokens, targeted_queries, enabled, cancel)
        return {"status": "manual_checkpoint_with_fallback" if output else "manual_checkpoint", "query": query, "targeted_queries": targeted_queries, "search_url": search_url, "fallback_search_urls": fallback_search_urls, "search_engines": ["google", "bing"], "anchors_examined": 0, "decoded_host_counts": {}, "browser_checkpoint": checkpoint["reason"], "browser_retry_after_seconds": checkpoint["remaining_seconds"], "fallback_error": fallback_error, "candidates": output, "candidate_count": len(output)}
    exact_linkedin = _google_linkedin_company(name, cancel)
    if exact_linkedin.get("status") == "manual_checkpoint":
        output, fallback_error = _fallback_candidates(tokens, targeted_queries, enabled, cancel)
        return {
            **exact_linkedin,
            "status": "manual_checkpoint_with_fallback" if output else "manual_checkpoint",
            "targeted_queries": targeted_queries,
            "search_engines": ["google_typed_company_lookup", "public_search_adapter"],
            "fallback_error": fallback_error,
            "candidates": output,
            "candidate_count": len(output),
        }
    # Other social/review sources still use the bounded public-search adapter
    # unless the optional broad browser mode was explicitly enabled.
    if _state().get("automated_web_search_enabled") is not True:
        output, fallback_error = _fallback_candidates(tokens, targeted_queries, enabled, cancel)
        combined = []
        for item in [*exact_linkedin.get("candidates", []), *output]:
            if item.get("url") and item.get("url") not in {row.get("url") for row in combined}:
                combined.append(item)
        return {"status": "complete_with_fallback" if combined else exact_linkedin.get("status", "complete"), "query": query, "linkedin_query": exact_linkedin.get("query", ""), "targeted_queries": targeted_queries, "search_url": "", "fallback_search_urls": [], "search_engines": ["google_typed_company_lookup", "public_search_adapter"], "anchors_examined": 0, "decoded_host_counts": {}, "browser_checkpoint": "", "browser_automation_disabled": True, "exact_linkedin_status": exact_linkedin.get("status", ""), "exact_linkedin_error": exact_linkedin.get("error", ""), "fallback_error": fallback_error, "candidates": combined, "candidate_count": len(combined)}
    browser_checkpoint = ""
    fallback_error = ""
    with SEARCH_LOCK:
        try:
            if not running():
                open_service("linkedin")
            from playwright.sync_api import sync_playwright

            pw = sync_playwright().start()
            browser = pw.chromium.connect_over_cdp(DEBUG_BASE)
            context = browser.contexts[0]
            page = context.new_page()
            try:
                response = page.goto(search_url, wait_until="domcontentloaded", timeout=18000)
                page.wait_for_timeout(900)
                body_text = page.locator("body").inner_text(timeout=3000)[:8000]
                if (response and response.status in (403, 429)) or re.search(r"unusual traffic|not a robot|captcha|verify you are human", body_text, re.I):
                    reason = f"Google returned {response.status if response else 'a security checkpoint'}; complete the challenge manually before resuming browser search"
                    _pause_public_search(reason)
                    output, fallback_error = _fallback_candidates(tokens, targeted_queries, enabled, cancel)
                    return {"status": "manual_checkpoint_with_fallback" if output else "manual_checkpoint", "query": query, "targeted_queries": targeted_queries, "search_url": search_url, "fallback_search_urls": fallback_search_urls, "search_engines": ["google", "bing"], "anchors_examined": 0, "decoded_host_counts": {}, "browser_checkpoint": reason, "browser_retry_after_seconds": 900, "fallback_error": fallback_error, "candidates": output, "candidate_count": len(output)}
                try:
                    anchors = page.locator("a").evaluate_all("els => els.map(a => ({href:a.href || '', title:(a.innerText || a.textContent || '').trim(), search_engine:'google'}))")
                except Exception:
                    anchors = []
                for query_index, fallback_search_url in enumerate(fallback_search_urls):
                    if cancel and cancel.is_set():
                        break
                    page.goto(fallback_search_url, wait_until="domcontentloaded", timeout=18000)
                    page.wait_for_timeout(700)
                    try:
                        bing_text = page.locator("body").inner_text(timeout=2500)[:3000]
                    except Exception:
                        bing_text = ""
                    if re.search(r"one last step|solve the challenge|verify you are human|captcha", bing_text, re.I):
                        browser_checkpoint = "Bing security checkpoint requires manual completion in the dedicated Chrome profile"
                        _pause_public_search(browser_checkpoint)
                        break
                    try:
                        found = page.locator("li.b_algo h2 a").evaluate_all("els => els.map(a => ({href:a.href || '', title:(a.innerText || a.textContent || '').trim(), search_engine:'bing'}))")
                    except Exception:
                        page.wait_for_timeout(700)
                        try:
                            found = page.locator("li.b_algo h2 a").evaluate_all("els => els.map(a => ({href:a.href || '', title:(a.innerText || a.textContent || '').trim(), search_engine:'bing'}))")
                        except Exception:
                            continue
                    for item in found:
                        item["query"] = targeted_queries[query_index]
                    anchors.extend(found)
            finally:
                page.close()
                pw.stop()
        except Exception as exc:
            browser_checkpoint = f"Chrome search could not finish: {str(exc)[:260]}"
            output, fallback_error = _fallback_candidates(tokens, targeted_queries, enabled, cancel)
            return {"status": "complete_with_fallback" if output else "failed", "query": query, "targeted_queries": targeted_queries, "search_url": search_url, "fallback_search_urls": fallback_search_urls, "search_engines": ["google", "bing"], "anchors_examined": 0, "decoded_host_counts": {}, "browser_checkpoint": browser_checkpoint, "fallback_error": fallback_error, "error": browser_checkpoint if not output else "", "candidates": output, "candidate_count": len(output)}
    output = []
    seen = set()
    host_counts = {}
    for anchor in anchors:
        href = str(anchor.get("href", ""))
        if "google.com/url?" in href:
            href = parse_qs(urlparse(href).query).get("q", [href])[0]
        if "bing.com/ck/a" in href:
            encoded = parse_qs(urlparse(href).query).get("u", [""])[0]
            if encoded.startswith("a1"):
                try:
                    raw = encoded[2:] + "=" * (-len(encoded[2:]) % 4)
                    href = base64.urlsafe_b64decode(raw).decode("utf-8")
                except (ValueError, UnicodeDecodeError):
                    continue
        try:
            host = (urlparse(href).hostname or "").casefold().removeprefix("www.")
        except ValueError:
            continue
        host_counts[host or "missing"] = host_counts.get(host or "missing", 0) + 1
        kind = ""
        if host.endswith("linkedin.com"):
            kind = "linkedin_person" if "/in/" in href else "linkedin_company" if "/company/" in href else ""
        elif host.endswith("instagram.com"):
            kind = "instagram"
        elif host.endswith("facebook.com") and enabled.get("facebook"):
            kind = "facebook"
        elif host.endswith("yelp.com"):
            kind = "yelp"
        elif host.endswith("bbb.org"):
            kind = "bbb"
        if not kind or href in seen:
            continue
        seen.add(href)
        title = re.sub(r"\s+", " ", str(anchor.get("title", ""))).strip()[:300]
        haystack = (href + " " + title).casefold()
        overlap = len([token for token in tokens if token in haystack])
        confidence = 0.9 if overlap >= 2 else 0.7 if overlap == 1 else 0.35
        output.append({"kind": kind, "url": href[:1500], "title": title, "excerpt": title, "query": anchor.get("query", query), "source": f"{anchor.get('search_engine', 'web')}_chrome_result", "confidence": confidence, "confirmation_state": "candidate_needs_review"})
        if len(output) >= 15:
            break
    if not output and not (cancel and cancel.is_set()):
        output, fallback_error = _fallback_candidates(tokens, targeted_queries, enabled, cancel)
    used_fallback = any(item.get("source") == "public_search_fallback_after_chrome" for item in output)
    status_value = "manual_checkpoint_with_fallback" if browser_checkpoint and output else "manual_checkpoint" if browser_checkpoint else "complete_with_fallback" if used_fallback else "complete"
    return {"status": status_value, "query": query, "targeted_queries": targeted_queries, "search_url": search_url, "fallback_search_urls": fallback_search_urls, "search_engines": ["google", "bing"], "anchors_examined": len(anchors), "decoded_host_counts": host_counts, "browser_checkpoint": browser_checkpoint, "fallback_error": fallback_error, "candidates": output, "candidate_count": len(output)}

