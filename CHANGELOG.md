# Changelog

## 2.4.2 — 2026-10-28

### Search-method packs

- Adapt reusable lead-discovery and review-monitoring methods from the reviewed MIT-licensed Maps actor catalog without importing affiliate links or enabling paid calls.
- Add editable city/category, nearby-coverage, website-gap, reputation, identity-resolution, contact-enrichment and cross-source comparison methods to every niche pack.
- Add vertical terminology and technology-verification packs for childcare, construction, dental, fitness, funeral, healthcare, hospitality, legal, pet services, real estate, restaurants and salons/spas.
- Feed the new terminology into deterministic and local-AI query planning while keeping technology names as hypotheses rather than evidence.
- Add evidence-labeled reputation, listing-website and observed-technology signals to compiled research.

### Business registry workspace

- Add a separate Business Registries menu and country/niche/capability directory finder.
- Seed reviewed official routes for the United States, Singapore, Malaysia and Australia, including NPI, SAM.gov, SBA DSBS, IRS TEOS, ACRA, Bizfile, SSM, ABN Lookup and ASIC.
- Label every route as free, registration/key required, or paid/manual and link only to the official or officially appointed portal.
- Keep registry discovery separate from lead evidence; opening a directory does not claim that a company is registered or verified.

## 2.4.1 — 2026-10-27

### Data sources layout

- Restore immediate visibility of every data-source card by placing the source grid before optional account connections.
- Replace the oversized always-open credentials area with a compact, collapsed Connections & API keys drawer and connected-provider count.
- Add an Electron regression check for source-card count, ordering and drawer behavior.

### Apify catalog review

- Document a safe use of `cporter202/google-maps-scraping-apis` as an actor-discovery catalog rather than executable scraper code.
- Require live official actor schema/pricing validation, explicit cost confirmation, spend bounds, normalized output and provenance before future paid actor execution.

## 2.4.0 — 2026-10-27

### Phase 2 foundation

- Add an in-app Connections panel backed by Windows Credential Manager for Google Sheets, Google Places, Apollo, Apify, and Outscraper.
- Add Google desktop OAuth with the narrow `drive.file` scope and one-click synchronization of the organized research library to an app-created spreadsheet.
- Add verified, explicitly enabled Google Places Text Search to the normal all-sources waterfall, including billing diagnostics and bounded queries.
- Add connection health checks for Apollo, Apify, Outscraper, and Google Places without returning secret values to the browser or diagnostics.
- Add a persistent country source catalog seeded for the United States, Singapore, Malaysia, and Australia.
- Add country context to search planning while retaining manual city/region/country entry for unsupported countries.

## 2.3.0 — 2026-10-27

### Data quality

- Normalize directory and public-profile titles before identity matching, including location and directory boilerplate removal.
- Reject probable multi-listing containers with unbounded names or repeated phone patterns.
- Exclude news, obituary, and general-media domains unless the page carries explicit `LocalBusiness` or `Organization` schema metadata.
- Run a targeted name/taxonomy/city website waterfall for applicable NPI Registry providers and force a published-contact check on discovered practice sites.

### Desktop maintenance

- Add GitHub release checks, update download progress, restart-to-install, and periodic background checks for installed builds.
- Add a recoverable local-runtime repair action that preserves saved searches, lead data, browser preferences, and outreach settings.
- Configure Electron Builder to emit GitHub updater metadata for future releases.

## 2.2.0 — 2026-10-27

First public Windows release.

### Included

- Linked discovery, verification, organization, intelligence, and outreach-preparation workflow.
- Google Maps dedicated Chrome profile, OpenStreetMap, public web discovery, Wikidata, NPI, public directories, startup/product sources, hiring signals, and advertising-transparency review paths.
- 200 curated niche packs.
- Automatic detection of compatible local Ollama chat models.
- Clear non-blocking behavior when local AI is unavailable.
- Approval-gated Zoho Mail campaigns with suppression and pacing controls.
- Borderless Electron desktop interface and an NSIS installer with an explicit Chrome-integration choice.

### Verification

- 134 backend tests passed.
- Browser workflow tests passed; the optional live-AI check is skipped when no configured model is available.
- Electron desktop smoke test passed.
- npm audit and pip-audit found no known dependency vulnerabilities.
- Project-owned Python code had no high-severity Bandit finding.

The Windows installer is unsigned, so Windows SmartScreen may display an unknown-publisher warning.
