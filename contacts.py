"""Bounded public website extraction with explicit source evidence."""

from __future__ import annotations

import ipaddress
import json
import re
import socket
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.parse import quote, urljoin, urlparse, unquote
from urllib.request import Request, build_opener, HTTPRedirectHandler, urlopen
from urllib.robotparser import RobotFileParser

from bs4 import BeautifulSoup
import phonenumbers
from leadfinder import (
    Lead,
    APP_USER_AGENT,
    EMAIL_RE,
    normalize_website,
    GENERIC_EMAIL_PREFIXES,
)


def now():
    return datetime.now(timezone.utc).isoformat()


DNS_CACHE: dict[str, tuple[float, tuple[str, ...], str]] = {}
MAIL_DNS_CACHE: dict[str, tuple[float, dict]] = {}
DNS_LOCK = threading.Lock()
DNS_CONNECT_LOCK = threading.RLock()
DNS_CONTEXT = threading.local()
SYSTEM_GETADDRINFO = socket.getaddrinfo


def mail_domain_status(domain: str) -> dict:
    """Check public MX records without claiming mailbox deliverability."""
    domain = str(domain or "").casefold().strip().rstrip(".")
    if not re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,}", domain):
        return {"status": "invalid_domain", "mx": [], "basis": "syntax"}
    with DNS_LOCK:
        cached = MAIL_DNS_CACHE.get(domain)
        if cached and cached[0] > time.monotonic():
            return cached[1]
    request = Request(
        "https://8.8.8.8/resolve?name=" + quote(domain) + "&type=MX",
        headers={"Accept": "application/dns-json", "User-Agent": APP_USER_AGENT},
    )
    try:
        with urlopen(request, timeout=5) as response:
            payload = json.loads(response.read(200_000))
        records = [str(item.get("data", ""))[:300] for item in payload.get("Answer", []) if item.get("type") == 15]
        null_mx = any(re.fullmatch(r"\s*0\s+\.\s*", item) for item in records)
        address_records = []
        if payload.get("Status") == 0 and not records:
            fallback_request = Request(
                "https://8.8.8.8/resolve?name=" + quote(domain) + "&type=A",
                headers={"Accept": "application/dns-json", "User-Agent": APP_USER_AGENT},
            )
            with urlopen(fallback_request, timeout=5) as response:
                fallback = json.loads(response.read(200_000))
            address_records = [str(item.get("data", ""))[:100] for item in fallback.get("Answer", []) if item.get("type") in (1, 28)]
        status = (
            "null_mx"
            if null_mx
            else "mx_present"
            if payload.get("Status") == 0 and records
            else "a_fallback_present"
            if address_records
            else "no_mail_route_observed"
        )
        result = {
            "status": status,
            "mx": records[:10],
            "address_fallback": address_records[:10],
            "basis": "google_public_dns_https_mx",
            "note": "A public mail route supports the domain only; it does not verify this mailbox or delivery.",
        }
    except Exception as exc:
        result = {
            "status": "temporary_dns_unavailable",
            "mx": [],
            "basis": "dns_check_failed",
            "note": str(exc)[:200],
        }
    with DNS_LOCK:
        MAIL_DNS_CACHE[domain] = (time.monotonic() + 3600, result)
    return result


def dns_txt_status(domain: str) -> dict:
    """Read public SPF, DMARC and verification tokens without exposing secrets."""
    domain = str(domain or "").casefold().strip().rstrip(".")
    if not re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,}", domain):
        return {"status": "invalid_domain", "spf": [], "dmarc": [], "verification_tokens": []}

    def query(name):
        request = Request("https://8.8.8.8/resolve?name=" + quote(name) + "&type=TXT", headers={"Accept": "application/dns-json", "User-Agent": APP_USER_AGENT})
        with urlopen(request, timeout=5) as response:
            payload = json.loads(response.read(300_000))
        return [str(item.get("data", "")).strip('"')[:1000] for item in payload.get("Answer", []) if item.get("type") == 16]

    try:
        root, dmarc = query(domain), query("_dmarc." + domain)
        spf = [item for item in root if item.casefold().startswith("v=spf1")]
        verification = [item for item in root if re.search(r"(?:verification|site-verification|ms=|atlassian-domain-verification)", item, re.I)]
        return {"status": "complete", "spf": spf[:5], "dmarc": [item for item in dmarc if item.casefold().startswith("v=dmarc1")][:5], "verification_tokens": verification[:10], "basis": "google_public_dns_https_txt"}
    except Exception as exc:
        return {"status": "temporary_dns_unavailable", "spf": [], "dmarc": [], "verification_tokens": [], "note": str(exc)[:200]}


def _public_addresses(hostname: str, port: int) -> tuple[tuple[str, ...], str]:
    """Resolve a public host, with DNS-over-HTTPS only when system DNS fails."""
    key = hostname.casefold().rstrip(".")
    with DNS_LOCK:
        cached = DNS_CACHE.get(key)
        if cached and cached[0] > time.monotonic():
            return cached[1], cached[2]
    addresses, source = [], "system_dns"
    try:
        addresses = [item[4][0] for item in SYSTEM_GETADDRINFO(hostname, port)]
    except socket.gaierror:
        source = "google_public_dns_https_fallback"
        request = Request(
            "https://8.8.8.8/resolve?name=" + quote(hostname) + "&type=A",
            headers={"Accept": "application/dns-json", "User-Agent": APP_USER_AGENT},
        )
        try:
            with urlopen(request, timeout=8) as response:
                payload = json.loads(response.read(200_000))
            if payload.get("Status") == 0:
                addresses = [
                    item.get("data", "")
                    for item in payload.get("Answer", [])
                    if item.get("type") == 1
                ]
        except Exception as exc:
            raise ValueError(
                "Temporary DNS failure: system DNS and secure fallback did not respond; website not marked dead"
            ) from exc
    checked = []
    for address in dict.fromkeys(addresses):
        try:
            parsed = ipaddress.ip_address(address)
        except ValueError:
            continue
        if not parsed.is_global:
            raise ValueError("Private or local website addresses are not supported")
        checked.append(str(parsed))
    if not checked:
        raise ValueError("Website hostname has no public address")
    result = tuple(checked)
    with DNS_LOCK:
        DNS_CACHE[key] = (time.monotonic() + 900, result, source)
    return result, source


@contextmanager
def _resolved_connection(hostname: str, addresses: tuple[str, ...]):
    """Let urllib keep the original TLS hostname while connecting to validated IPs."""
    with DNS_CONNECT_LOCK:
        resolved = {hostname.casefold().rstrip("."): addresses}
        DNS_CONTEXT.resolved = resolved

        def getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
            values = resolved.get(str(host).casefold().rstrip("."))
            if not values:
                return SYSTEM_GETADDRINFO(host, port, family, type, proto, flags)
            output = []
            for value in values:
                parsed = ipaddress.ip_address(value)
                af = socket.AF_INET6 if parsed.version == 6 else socket.AF_INET
                sockaddr = (value, port, 0, 0) if parsed.version == 6 else (value, port)
                output.append((af, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", sockaddr))
            return output

        socket.getaddrinfo = getaddrinfo
        try:
            yield resolved
        finally:
            socket.getaddrinfo = SYSTEM_GETADDRINFO
            DNS_CONTEXT.resolved = None


def public_url(value: str) -> str:
    if "://" in value and not value.lower().startswith(("http://", "https://")):
        raise ValueError("Only public HTTP or HTTPS websites are supported")
    value = normalize_website(value)
    parsed = urlparse(value)
    if (
        parsed.scheme not in ("http", "https")
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise ValueError("A public HTTP or HTTPS website is required")
    if parsed.port not in (None, 80, 443):
        raise ValueError("Only normal website ports are supported")
    addresses, _ = _public_addresses(parsed.hostname, parsed.port or 443)
    active = getattr(DNS_CONTEXT, "resolved", None)
    if isinstance(active, dict):
        active[parsed.hostname.casefold().rstrip(".")] = addresses
    return value


class SafeRedirect(HTTPRedirectHandler):
    def __init__(self):
        super().__init__()
        self.history = []

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        public_url(newurl)
        self.history.append({"status": code, "url": newurl[:1500]})
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def page_html(url: str, timeout=12) -> tuple[str, str]:
    result = page_html_diagnostic(url, timeout)
    return result["body"], result["final_url"]


def page_html_diagnostic(url: str, timeout=12) -> dict:
    url = public_url(url)
    parsed = urlparse(url)
    addresses, _ = _public_addresses(parsed.hostname, parsed.port or 443)
    request = Request(
        url,
        headers={
            "User-Agent": APP_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    redirector = SafeRedirect()
    started = time.monotonic()
    with _resolved_connection(parsed.hostname, addresses):
        with build_opener(redirector).open(request, timeout=timeout) as response:
            content_type = response.headers.get("Content-Type", "")
            if "html" not in content_type and "text" not in content_type:
                raise ValueError("The URL did not return a web page")
            body = response.read(2_000_000).decode(
                response.headers.get_content_charset() or "utf-8", "replace"
            )
            cookies = []
            for value in response.headers.get_all("Set-Cookie", []):
                name = value.split("=", 1)[0].strip()
                if re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", name):
                    cookies.append(name)
            return {
                "body": body,
                "final_url": response.url,
                "status_code": int(getattr(response, "status", 200) or 200),
                "redirect_chain": redirector.history,
                "elapsed_ms": int((time.monotonic() - started) * 1000),
                "headers": {key.casefold(): str(value)[:500] for key, value in response.headers.items() if key.casefold() in {"server", "content-type", "x-powered-by", "x-cache", "cf-ray", "via", "etag", "last-modified"}},
                "cookie_names": cookies[:50],
                "fetch_tier": "http",
                "render_ms": 0,
            }


def conditional_page_diagnostic(url: str, etag="", last_modified="", timeout=12):
    """Lightweight public-page poll using standard HTTP validators."""
    url = public_url(url)
    parsed = urlparse(url)
    addresses, _ = _public_addresses(parsed.hostname, parsed.port or 443)
    headers = {"User-Agent": APP_USER_AGENT, "Accept": "text/html,application/xhtml+xml"}
    if etag:
        headers["If-None-Match"] = str(etag)[:500]
    if last_modified:
        headers["If-Modified-Since"] = str(last_modified)[:500]
    request = Request(url, headers=headers)
    redirector, started = SafeRedirect(), time.monotonic()
    try:
        with _resolved_connection(parsed.hostname, addresses):
            with build_opener(redirector).open(request, timeout=timeout) as response:
                body = response.read(2_000_000).decode(response.headers.get_content_charset() or "utf-8", "replace")
                return {"not_modified": False, "body": body, "final_url": response.url, "status_code": int(getattr(response, "status", 200) or 200), "etag": response.headers.get("ETag", "")[:500], "last_modified": response.headers.get("Last-Modified", "")[:500], "redirect_chain": redirector.history, "elapsed_ms": int((time.monotonic() - started) * 1000)}
    except HTTPError as exc:
        if exc.code == 304:
            return {"not_modified": True, "body": "", "final_url": url, "status_code": 304, "etag": etag, "last_modified": last_modified, "redirect_chain": redirector.history, "elapsed_ms": int((time.monotonic() - started) * 1000)}
        raise


def _page_state(body, status_code=200):
    lower = body.casefold()
    waf = ""
    for name, pattern in (("cloudflare_challenge", r"cf-chl-|just a moment.*cloudflare"), ("captcha", r"captcha|verify you are human"), ("access_denied", r"access denied|request blocked|web application firewall")):
        if status_code in (401, 403, 429, 503) and re.search(pattern, lower, re.S):
            waf = name
            break
    visible = BeautifulSoup(body, "html.parser").get_text(" ", strip=True)
    shell = len(visible) < 180 and len(re.findall(r"<script\b", body, re.I)) >= 2 and bool(re.search(r'id=["\'](?:root|app|__next|app-root)["\']', body, re.I))
    return waf, shell


def render_page(url, timeout=20):
    """Render a normal public page; WAF challenges are never bypassed."""
    from playwright.sync_api import sync_playwright

    started = time.monotonic()
    safe = public_url(url)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1365, "height": 900}, user_agent=APP_USER_AGENT)
        page = context.new_page()

        def route_request(route):
            target = route.request.url
            if target.startswith(("data:", "blob:")):
                route.continue_()
                return
            try:
                public_url(target)
                route.continue_()
            except Exception:
                route.abort()

        page.route("**/*", route_request)
        response = page.goto(safe, wait_until="domcontentloaded", timeout=timeout * 1000)
        page.wait_for_timeout(800)
        body = page.content()
        final_url = page.url
        status = response.status if response else 0
        browser.close()
    return {"body": body, "final_url": final_url, "status_code": status, "redirect_chain": [], "elapsed_ms": int((time.monotonic() - started) * 1000), "headers": {}, "cookie_names": [], "fetch_tier": "browser_render", "render_ms": int((time.monotonic() - started) * 1000)}


class WebClient:
    def __init__(self):
        self.robots: dict[str, RobotFileParser | None] = {}
        self.lock = threading.Lock()
        self.host_locks: dict[str, threading.Lock] = {}

    def get(self, url: str) -> tuple[str, str]:
        result = self.get_with_diagnostics(url)
        return result["body"], result["final_url"]

    def get_with_diagnostics(self, url: str) -> dict:
        parsed = urlparse(public_url(url))
        origin = f"{parsed.scheme}://{parsed.netloc}"
        with self.lock:
            host_lock = self.host_locks.setdefault(origin, threading.Lock())
        with host_lock:
            if origin not in self.robots:
                robot = RobotFileParser()
                try:
                    body, _ = page_html(origin + "/robots.txt", timeout=7)
                    robot.parse(body.splitlines())
                    self.robots[origin] = robot
                except HTTPError as exc:
                    if exc.code in (401, 403, 429) or exc.code >= 500:
                        raise ValueError(
                            f"robots.txt unavailable ({exc.code}); website skipped"
                        ) from exc
                    self.robots[origin] = None
                except (TimeoutError, OSError):
                    raise ValueError("robots.txt unavailable; website skipped")
            robot = self.robots[origin]
            if robot and not robot.can_fetch(APP_USER_AGENT, url):
                raise ValueError("Website disallows this page in robots.txt")
            time.sleep(
                min(
                    max(
                        (
                            robot.crawl_delay(APP_USER_AGENT)
                            or robot.crawl_delay("*")
                            or 0.5
                        )
                        if robot
                        else 0.5,
                        0.5,
                    ),
                    10,
                )
            )
            result = page_html_diagnostic(url)
            waf, shell = _page_state(result["body"], result["status_code"])
            result.update(waf_signature=waf, outcome="blocked_manual_review" if waf else "http_complete")
            if shell and not waf:
                try:
                    rendered = render_page(url)
                    rendered_waf, _ = _page_state(rendered["body"], rendered["status_code"])
                    rendered.update(waf_signature=rendered_waf, outcome="blocked_manual_review" if rendered_waf else "render_complete", escalated_from="javascript_shell")
                    result = rendered
                except Exception as exc:
                    result.update(outcome="render_failed_http_retained", render_error=str(exc)[:300], escalated_from="javascript_shell")
            return result


def walk_json(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_json(child)


def extract_document(body: str, url: str, lead: Lead) -> tuple[str, list[str]]:
    soup = BeautifulSoup(body, "html.parser")
    records = json.loads(lead.evidence or "[]")
    emails, phones = (
        set(filter(None, lead.emails.split("; "))),
        set(filter(None, lead.phones.split("; "))),
    )
    from research import STATE_CODES

    location = (lead.search_location or lead.city).casefold()
    location_parts = {p.strip() for p in location.split(",")}
    us_state = bool(location_parts & {s.casefold() for s in STATE_CODES}) or bool(
        location_parts & {s.casefold() for s in STATE_CODES.values()}
    )
    region = (
        "US"
        if us_state
        or any(s in location for s in ("texas", "dallas", "usa", "united states"))
        else ("PK" if "pakistan" in location else None)
    )

    def evidence(field, value, method):
        item = {
            "field": field,
            "value": value,
            "url": url,
            "method": method,
            "observed_at": now(),
        }
        if not any(
            e.get("field") == field and e.get("value") == value and e.get("url") == url
            for e in records
        ):
            records.append(item)

    def add_email(value, method):
        for email in EMAIL_RE.findall(unquote(str(value))):
            email = email.strip(".,;:").casefold()
            if not email.endswith(
                (".png", ".jpg", ".webp", ".svg", ".js", ".css")
            ) and not email.split("@")[1] in (
                "example.com",
                "sentry.io",
                "wixpress.com",
            ):
                emails.add(email)
                evidence("email", email, method)

    def add_phone(value, method):
        try:
            for match in phonenumbers.PhoneNumberMatcher(str(value), region):
                if phonenumbers.is_valid_number(match.number):
                    phone = phonenumbers.format_number(
                        match.number, phonenumbers.PhoneNumberFormat.E164
                    )
                    phones.add(phone)
                    evidence("phone", phone, method)
        except Exception:
            pass

    structured_people = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            for node in walk_json(json.loads(script.string or script.get_text())):
                kind = str(node.get("@type", ""))
                if any(
                    x in kind
                    for x in (
                        "Business",
                        "Organization",
                        "Corporation",
                        "Dentist",
                        "Restaurant",
                        "Plumber",
                        "Service",
                        "Store",
                        "Contractor",
                    )
                ):
                    if node.get("name") and (
                        not lead.name or lead.name == urlparse(url).hostname
                    ):
                        lead.name = str(node["name"])
                    add_email(node.get("email", ""), "structured data")
                    add_phone(node.get("telephone", ""), "structured data")
                    for role_key in ("founder", "founders"):
                        people = node.get(role_key, [])
                        if not isinstance(people, list):
                            people = [people]
                        for person in people:
                            if isinstance(person, dict) and person.get("name"):
                                structured_people.append(
                                    {"name": person["name"], "role": "Founder"}
                                )
                    address = node.get("address")
                    if not lead.address and isinstance(address, dict):
                        lead.address = ", ".join(
                            str(address[k])
                            for k in (
                                "streetAddress",
                                "addressLocality",
                                "addressRegion",
                                "postalCode",
                            )
                            if address.get(k)
                        )
        except (ValueError, TypeError):
            continue
    links = []
    for anchor in soup.find_all("a", href=True):
        href = str(anchor["href"]).strip()
        if href.startswith("mailto:"):
            add_email(href[7:].split("?")[0], "mailto link")
        if href.startswith("tel:"):
            add_phone(href[4:], "telephone link")
        absolute = urljoin(url, href).split("#")[0]
        host = urlparse(absolute).hostname or ""
        for social in ("facebook", "instagram", "linkedin"):
            if host == social + ".com" or host.endswith("." + social + ".com"):
                if not getattr(lead, social):
                    setattr(lead, social, absolute)
        if urlparse(absolute).hostname == urlparse(url).hostname and re.search(
            r"contact|about|team|staff|leadership|management|press|news|services?|portfolio|testimonials?|reviews?|report|documentation|inspection",
            href,
            re.I,
        ):
            links.append(absolute)
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    visible = soup.get_text(" ", strip=True)
    roles = r"Owner|Founder|President|Chief Executive Officer|CEO|General Manager|Operations Manager|Managing Director|Partner"
    person_patterns = (
        rf"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){{1,3}})\s*[,|\-–]\s*({roles})\b",
        rf"\b({roles})\s*[:|\-–]\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+){{1,3}})\b",
    )
    if not lead.decision_maker:
        for pattern_index, pattern in enumerate(person_patterns):
            match = re.search(pattern, visible)
            if not match:
                continue
            name, role = (match.group(1), match.group(2)) if pattern_index == 0 else (match.group(2), match.group(1))
            lead.decision_maker = name
            lead.decision_maker_role = role
            evidence("decision_maker", name, "visible page role pattern")
            evidence("decision_maker_role", role, "visible page role pattern")
            break
    if not lead.decision_maker and structured_people:
        person = structured_people[0]
        lead.decision_maker = str(person.get("name", ""))[:160]
        lead.decision_maker_role = str(person.get("role", "Founder"))[:80]
        evidence("decision_maker", lead.decision_maker, "structured data")
        evidence("decision_maker_role", lead.decision_maker_role, "structured data")
    from prospecting import collect_signals

    collect_signals(lead, visible, url, structured_people=structured_people)
    add_email(visible, "visible page text")
    add_phone(visible, "visible page text")
    host = (urlparse(url).hostname or "").removeprefix("www.")
    ordered = sorted(
        emails,
        key=lambda e: (
            not e.endswith("@" + host),
            not e.startswith(GENERIC_EMAIL_PREFIXES),
            len(e),
        ),
    )
    lead.email = lead.email or (ordered[0] if ordered else "")
    lead.phone = lead.phone or (sorted(phones)[0] if phones else "")
    lead.emails = "; ".join(ordered)
    lead.phones = "; ".join(sorted(phones))
    lead.evidence = json.dumps(records, ensure_ascii=False)
    from research import add_observation

    excerpts = [visible[:450]]
    for match in re.finditer(
        r"owner[- ]operated|family[- ]owned|independently owned|one[- ]person|sole proprietor|self[- ]employed|work alone|solo operator|our agency|agency team|franchise|locations nationwide",
        visible,
        re.I,
    ):
        excerpts.append(visible[max(0, match.start() - 80) : match.end() + 150])
        if sum(map(len, excerpts)) > 1250:
            break
    if visible.strip():
        add_observation(lead, "public_page", " … ".join(excerpts), url, "page_text")

    def link_priority(value):
        path = urlparse(value).path
        return (
            0
            if re.search("contact", path, re.I)
            else 1
            if re.search("about|team", path, re.I)
            else 2
            if re.search("report|documentation|inspection", path, re.I)
            else 3,
            len(value),
        )

    return visible, sorted(dict.fromkeys(links), key=link_priority)


def enrich(
    lead: Lead, client: WebClient, cancel, emit, max_pages=3
) -> tuple[Lead, str]:
    if lead.profile_url:
        lead.contact_status = "platform_profile_only"
        return lead, ""
    if not lead.website:
        lead.contact_status = "no_website"
        return lead, ""
    queue = [normalize_website(lead.website)]
    seen, content, successes, empty_pages = set(), [], 0, 0
    for url in queue:
        if cancel.is_set() or len(seen) >= max_pages:
            break
        if url in seen:
            continue
        seen.add(url)
        try:
            if hasattr(client, "get_with_diagnostics"):
                diagnostic = client.get_with_diagnostics(url)
                body, final_url = diagnostic["body"], diagnostic["final_url"]
                emit("website_fetch", "warning" if diagnostic.get("waf_signature") else "info", "Website fetch diagnostic", url=url, final_url=final_url, **{key: diagnostic.get(key) for key in ("fetch_tier", "status_code", "redirect_chain", "elapsed_ms", "render_ms", "waf_signature", "outcome", "headers", "cookie_names", "escalated_from", "render_error") if diagnostic.get(key) not in (None, "", [], {})})
            else:
                body, final_url = client.get(url)
            visible, links = extract_document(body, final_url, lead)
            if not visible.strip():
                empty_pages += 1
                emit(
                    "website",
                    "warning",
                    "Website returned no readable page text",
                    url=final_url,
                    response_bytes=len(body.encode("utf-8")),
                    note="May require rendering or may be empty. No service, ownership or workflow is inferred from the domain.",
                )
                continue
            content.append(visible)
            successes += 1
            for link in links:
                if link not in queue and len(queue) < max_pages:
                    queue.append(link)
        except Exception as exc:
            emit(
                "website",
                "warning",
                "Website page unavailable",
                url=url,
                error=str(exc)[:240],
            )
    lead.checked_at = now()
    lead.contact_status = (
        "published_contacts"
        if (lead.email or lead.phone) and successes
        else (
            "no_contacts_found"
            if successes
            else "no_readable_content"
            if empty_pages
            else "unavailable"
        )
    )
    return lead, " ".join(content)
