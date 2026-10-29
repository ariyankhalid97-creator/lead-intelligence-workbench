# Changelog

## 2.5.1 — 2026-10-29

### LinkedIn and Google Sheets continuity

- Refresh the current lead worksheet automatically after second-round verification so newly resolved company LinkedIn URLs reach Sheets.
- Add resumable, browser-assisted employee discovery for verified LinkedIn company People pages with explicit login and checkpoint handling.
- Create a separate, deduplicated employee worksheet containing visible professional names, headlines, profile URLs, company evidence and observation time.
- Preserve the richest visible People-card headline, normalize supported job titles, and group the same worksheet by outreach priority, role, seniority and evidence-derived tags.
- Narrow checkpoint detection to real challenge URLs and explicit verification messages so ordinary company names containing “challenge” cannot pause a run.
- Restore employee title and tag totals correctly after reopening a saved run.
- Prevent the two-column discovery workspace from overflowing at tablet-sized desktop windows.
- Continue repeated niche-and-location searches after earlier batches, skip previously retained identities across sources, scan deeper in Maps, and label exhausted result pools.
- Keep large verification reports collapsed below the employee controls so the next workflow stage is available without scrolling through every lead.
- Bound employee collection to 100 companies, 100 visible profiles per company and 5,000 retained profiles; no invitations, messages, private contact extraction or checkpoint bypassing.

## 2.5.0 — 2026-10-28

### Connected workflow and recovery

- Link planning, discovery, enrichment, verification, compilation, research-library storage, Sheets synchronization and approval-gated outreach into one visible workflow.
- Add durable pause, continue and interrupted-run recovery with explicit checkpoint and provider diagnostics.
- Resolve public company LinkedIn URLs through an exact-name browser query while keeping people-profile research manual.

### Google Sheets and OAuth

- Switch Google authorization to the installed-app flow with loopback redirects, state validation, PKCE and the narrow `drive.file` scope.
- Show the exact OAuth callback in Connections, explain the required Desktop app client type and provide a copy control.
- Add titled worksheet creation and optional live updates for organized research collections.

### Local intelligence and extraction

- Route compatible installed Ollama models between fast planning and deeper evidence analysis, with a deterministic fallback when no model is available.
- Add compact, source-linked Markdown extraction for bounded public business pages and retain exact failure evidence.
- Improve name normalization, entity-boundary checks, duplicate consolidation, email quality classification and secondary NPI enrichment.

### Interface, sources and privacy

- Reorganize data sources, connections, business registries and intelligence cards into readable, responsive sections with collapsed detail groups.
- Expand reusable niche terminology and country-aware official-directory metadata for the United States, Singapore, Malaysia and Australia.
- Keep credentials, local searches, leads, logs and generated research out of the public repository while retaining reusable niche and directory knowledge.
- Remove private campaign branding from the distributable code and documentation.

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
