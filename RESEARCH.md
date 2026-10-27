# GitHub research notes

Research date: 2026-10-21. The application implementation is original. Version 2 uses maintained open-source packages for Chrome, parsing, phone validation and web discovery; no vendor app code or assets were copied. Repository descriptions are documentary research, not claims that every project was installed or benchmarked.

| Repository | Useful approach | Caveat / decision |
|---|---|---|
| [gosom/google-maps-scraper](https://github.com/gosom/google-maps-scraper) | Mature Go worker pool, CSV/JSON export, email extraction, exit/resume patterns | Direct Google scraping remains fragile; used the architectural ideas, not its code |
| [omkarcloud/google-maps-scraper](https://github.com/omkarcloud/google-maps-scraper) | Broad Maps field coverage and a local API boundary | Enrichment can require paid credits; supported only as an optional local provider |
| [RippleCheck/Ripple-Lead-Finder](https://github.com/RippleCheck/Ripple-Lead-Finder) | Nominatim + Overpass gives a genuinely free, keyless baseline; SQLite persistence and lead scoring | OSM coverage is thinner than Google in some locations |
| [its-tahir/presence-zero](https://github.com/its-tahir/presence-zero) | Multi-provider design, website health checks, opportunity scoring | Full product is much larger than this focused CLI |
| [sonagara-vashram/google-maps-scraper](https://github.com/sonagara-vashram/google-maps-scraper) | Grid searches, circuit breakers, exponential backoff, crash-safe resume | Uses an undocumented Google endpoint; unsuitable as the dependable core |
| [zimkk/Lead-Scraper-Google-Maps](https://github.com/zimkk/Lead-Scraper-Google-Maps) | Area/grid depth, Playwright fallback, deduplication, qualified-lead profiles | Browser automation is slower and more block-prone |
| [tejasrishi27/LeadHunter](https://github.com/tejasrishi27/LeadHunter) | JSON-LD/metadata/regex fallback chain for website enrichment and confidence scoring | Narrow website-input workflow rather than discovery |
| [SarmadSalee/LeadEngine](https://github.com/SarmadSalee/LeadEngine) | Provider adapters, streaming, checkpoints, public-page enrichment | Pre-1.0 and considerably more operational complexity |
| [rounak695/YourLeadgen](https://github.com/rounak695/YourLeadgen) | Modular search → enrich → deduplicate → export pipeline | Google results depend on a Serper API key; outbound mail is outside scope |
| [yellowtribeapps/blitzprospector](https://github.com/yellowtribeapps/blitzprospector) | Apollo-like filters, suppression lists, CRM-ready exports | UI is open source but underlying Blitz person/company data is not free |

## Chosen architecture

1. Free/default discovery: Nominatim geocoding plus Overpass/OpenStreetMap.
2. Higher-coverage optional discovery: the installed local Google Maps Extractor API.
3. Enrichment: public homepage plus up to two same-site contact/about/team pages, respecting robots.txt.
4. Data quality: source IDs, normalized identity keys, field merging, scoring, SQLite upserts, CSV/JSON exports.
5. Reliability: multiple Overpass endpoints, bounded retries, backoff, conservative timeouts, and persistent results.

This provides useful business-level leads without pretending that private or named-person data is freely available.

## Expanded evaluation: 20 repositories in total

The ten above plus the ten below were reviewed through public repository documentation. The strongest runtime choice here is a small combination of maintained libraries rather than installing every scraper and inheriting conflicting browsers, proxies and data formats.

| Repository | Capability / approach | Decision |
|---|---|---|
| [microsoft/playwright-python](https://github.com/microsoft/playwright-python) | Real browser automation, installed Chrome channels, persistent contexts | Integrated. Isolated local profile and public Maps DOM; no private Maps endpoints |
| [deedy5/ddgs](https://github.com/deedy5/ddgs) | Multiple web-search engines in one Python API | Integrated as best-effort Brave/DuckDuckGo discovery; failures recorded |
| [scrapy/scrapy](https://github.com/scrapy/scrapy) | Spider scheduling, retries, pipelines and feed export | Reference for separation of discovery/extraction/export; not installed for this small workstation |
| [scrapinghub/extruct](https://github.com/scrapinghub/extruct) | JSON-LD and other structured metadata | Reference. Implemented a focused JSON-LD extractor with page evidence rather than adding all formats |
| [unclecode/crawl4ai](https://github.com/unclecode/crawl4ai) | Browser crawling and structured/Markdown extraction | Considered; heavier than needed for bounded three-page business contact extraction |
| [SeleniumHQ/selenium](https://github.com/SeleniumHQ/selenium) | Standards-based browser control | Considered; Playwright selected to avoid a second automation stack |
| [apify/crawlee](https://github.com/apify/crawlee) | Request queues, browser pools, resilient crawling | Architectural reference; full JS crawling stack not required |
| [apify/crawlee-python](https://github.com/apify/crawlee-python) | Python HTTP/browser crawler abstractions | Architectural reference; bounded threads and SQLite checkpoints cover current requirements |
| [outscraper/outscraper-python](https://github.com/outscraper/outscraper-python) | Official client for Outscraper services | Source catalog only; an SDK's source license does not make the underlying service unlimited/free |
| [omkarcloud/botasaurus](https://github.com/omkarcloud/botasaurus) | Browser/request task organization, caching and export | Considered; no stealth/evasion/proxy tooling incorporated |

The original ten research entries were retained. Their license labels and availability must be rechecked before importing code; none were vendored. Installed package versions are pinned in requirements.txt; test dependencies are locked in package-lock.json.

## Paid-product behavior references

[Outscraper](https://outscraper.com/google-maps-scraper/) provided the business-field/export workflow. [Apify's official Maps actor](https://apify.com/compass/crawler-google-places) documents multiple terms, location targeting, saved run datasets and the risk of over-restrictive categories. [Apollo People Search](https://docs.apollo.io/reference/people-api-search) documents that its search endpoint omits email/phone, even when search itself uses zero credits; contacts are separate enrichment. No authenticated product UI or licensed data was accessed.

## Source coverage and cost matrix

| Source | In app | No key | Strength | Limit |
|---|---|---|---|---|
| Google Maps, visible Chrome | yes | yes | Specialized service discovery and listing contacts | Public UI can change; verification prompts require human action |
| OpenStreetMap / Overpass | yes | yes | Structured categories and coordinates | Sparse service businesses; public endpoint availability varies |
| Web discovery (DDGS) | yes | yes | Business sites missed by maps | Engines can block queries or return noisy candidates |
| Business website input/crawl | yes | yes | Structured business data, mailto/tel, contact/about pages | At most 3 pages; unavailable/disallowed pages are explained |
| Existing local extractor | yes, separate mode | local search | Rich structured listing format | Desktop app must expose API port 8000 |
| Apollo, Google Places, Apify, Outscraper APIs | catalog only | generally account/key | Licensed/managed higher-coverage options | Not connected; no paid calls performed |
| Yelp, Yellow Pages, BBB, industry associations | no specialized adapter | varies | Potential future directory/seed inputs | Per-directory permission/schema review needed; no universal coverage claim |

Bing RSS was probed and rejected for this commercial lead workflow because the feed explicitly restricts reuse to personal non-commercial RSS rendering. A DuckDuckGo HTML probe returned a challenge; it was not bypassed. Browser Maps and the maintained search adapter supplied usable results instead.

## Observed results

Dallas hood-cleaning test, 2026-10-21: first full run requested 8 outputs and returned 8 businesses, 7 phones, 2 emails and 7 websites. Browser Maps read 8 listings; web discovery supplied 4 candidates before merging. Both OSM mirrors timed out, so status was partial with retained results. Contact evidence URLs and extraction methods are saved in the run, not inferred or fabricated. These counts are a limited live sample, not a coverage benchmark or a guarantee.

A broader run collected 20 raw candidates. Review excluded one directory landing page, producing a saved reviewed set of 19 business candidates, 18 phone fields, 6 published email fields and 18 website fields. The original CSV is preserved and the diagnostic report includes the excluded record. One remaining business needs specialty review; the others have matching service text or category evidence, not independently verified service-area coverage. A final Chrome-only one-record smoke test also confirmed rating (4.9), review count (48), and coordinates were parsed.

