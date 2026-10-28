# Lead Extractor

### Local-first business discovery, evidence-backed lead intelligence, and approval-gated outreach

Lead Extractor is a free Windows desktop workspace that turns a niche and location into an organized research collection. It discovers public business records, enriches published contacts, verifies company evidence, consolidates duplicates, compiles local-AI intelligence, synchronizes approved data to Google Sheets, and prepares outreach for human review.

The application runs locally. A paid AI key and subscription are not required.

![Lead Extractor desktop interface](docs/lead-extractor-ui.jpg)

## What the workflow does

One search can move through the complete pipeline without changing tabs:

1. **Plan** — expand the niche with curated terminology, country context, and optional local AI.
2. **Discover** — search applicable Maps, open-data, website, directory, registry, and public-profile sources.
3. **Enrich** — visit bounded public business pages and retain published websites, phones, emails, and social links.
4. **Verify** — perform a second pass for websites, email-domain signals, company LinkedIn URLs, reviews, hiring signals, advertising review paths, and technographic evidence.
5. **Organize** — normalize names, consolidate strong duplicates, retain conflicts, classify contact quality, and save a grouped research collection.
6. **Compile** — use a compatible local Ollama model to interpret retained evidence without inventing missing facts.
7. **Export or outreach** — update a titled Google Sheets worksheet or prepare a Zoho campaign that still requires explicit approval.

Searches have durable checkpoints. Pause, continue, application-restart recovery, provider failures, CAPTCHA waits, and partial results remain visible in the same saved run.

## Main capabilities

### Discovery and source planning

- Google Maps through a persistent, dedicated Chrome profile.
- OpenStreetMap and Overpass public data.
- Best-effort public web discovery with source URLs and negative-domain filtering.
- Business websites with robots-aware retrieval and bounded JavaScript rendering.
- Wikidata organizations and the US NPI Registry where relevant.
- Country-aware official-directory workspace for the United States, Singapore, Malaysia, and Australia.
- Public profile strategies for Yelp, Yellow Pages, Manta, Chamber of Commerce, BBB, MapQuest, Alignable, Houzz, Thumbtack, Bark, Taskrabbit, Clutch, GoodFirms, Y Combinator, Product Hunt, BetaList, Wellfound, and other niche-relevant sources.
- Hiring and market signals from applicable public Indeed, RemoteOK, Wellfound, Meta Ad Library, and Google Ads Transparency routes.
- Optional Google Places, Apollo, Apify, and Outscraper connections. Paid or licensed providers stay off until configured and explicitly enabled.

### Reusable research knowledge

- 200 curated niche packs covering local services, healthcare, professional services, automotive, hospitality, property, hiring, rentals, and specialist businesses.
- Editable aliases, exclusion terms, decision-maker roles, source priorities, review signals, and technology hypotheses.
- Search-method packs for city/category discovery, nearby coverage, website gaps, reputation, identity resolution, contact enrichment, and cross-source comparison.
- A neutral offer-to-buyer planner that converts a product or service into likely buyer segments and an evidence-aware search configuration.
- Niche packs and directory definitions are versioned with the project because they improve results for every user. Personal searches, local model history, credentials, exports, and campaign records are not.

### Evidence and data quality

- Directory boilerplate, location suffixes, and host labels are removed before deduplication.
- Unbounded multi-listing containers and repeated-phone title blocks are rejected.
- News, obituary, and general-media pages are excluded unless they publish explicit `LocalBusiness` or `Organization` metadata.
- Every retained claim distinguishes first-party observations, directory claims, search snippets, model suggestions, and unknown values.
- Exact duplicates are merged while source history and conflicting fields remain reviewable.
- Email addresses are classified as possible-direct, general-business, support, automated, or uncertain.
- DNS and MX observations describe the mail domain only; they never claim mailbox deliverability.

### Local extraction waterfall

The website layer uses a free, bounded escalation path:

1. Validate the public URL and inspect `robots.txt`.
2. Fetch ordinary HTML with pacing, timeouts, redirect checks, and diagnostics.
3. Render a JavaScript shell only when normal HTML has no usable page content.
4. Stop and retain diagnostics when a WAF or human-verification challenge appears.
5. Convert readable content into compact, boilerplate-reduced Markdown.
6. Extract structured organization data, published contacts, social URLs, workflow signals, and literal evidence excerpts.

This follows the useful clean-content and typed-extraction patterns found in modern open-source crawlers while keeping the default runtime small and local. It does not embed Firecrawl's AGPL server or require a hosted crawling key.

### LinkedIn-assisted verification

After discovery, the verification stage can type an exact public Google query for each retained business:

```text
"Business Name" LinkedIn
```

Only public `linkedin.com/company/...` candidates are accepted. A matching company URL is saved in the lead, research library, exports, and Google Sheets. The app provides a separate manual decision-maker search link; it does not scrape authenticated personal profiles. Google or LinkedIn security checkpoints are never bypassed.

## Local AI

Lead Extractor reads the Ollama model inventory from `http://127.0.0.1:11434`, rejects cloud and embedding-only models, and offers locally installed GGUF completion models.

The current task routing favors:

- a faster compatible model for query and phrase planning;
- a stronger compatible model for qualification, strict intelligence, email judgment, and outreach drafting.

If no model is available, discovery, verification, organization, exports, Google Sheets, and manual templates continue to work. AI output is advisory and cannot browse independently, promote a snippet into a verified fact, or send outreach without approval.

## Google Sheets setup

An API key cannot create or edit a private spreadsheet. Lead Extractor uses Google OAuth with the limited `drive.file` scope, which allows it to manage files the app creates or opens.

1. In Google Cloud, enable **Google Sheets API** and **Google Drive API**.
2. Configure the OAuth consent screen and add your Google account as a test user when the app remains in testing.
3. Create an OAuth client with application type **Desktop app**. Do not use a Web application client.
4. In Lead Extractor, open **Data sources → Connections & API keys**.
5. Save the Desktop client ID and secret, then select **Connect Google**.

The app displays the exact loopback callback used by the current installation—normally:

```text
http://127.0.0.1:8788
```

Authorization uses PKCE, a short-lived state value, and the same callback during the token exchange. A `redirect_uri_mismatch` error normally means a Web client or a different loopback address was used; create and save a Desktop app client instead.

Each organized collection can receive its own sanitized worksheet title. Optional live sync updates the current worksheet while results arrive, then performs a final sync after verification and organization.

## Zoho outreach

Zoho Mail integration uses OAuth and the official API. Client credentials and refresh tokens are stored in Windows Credential Manager.

- Templates can be reused across niches.
- Local AI can produce evidence-bounded drafts.
- Support and automated addresses are excluded from campaign preparation.
- Suppressions, prior outcomes, campaign limits, and randomized pacing are checked before delivery.
- Sending requires explicit campaign approval.
- Provider failures pause the campaign instead of silently skipping recipients.

Users remain responsible for consent, lawful basis, identification, opt-out language, platform terms, and applicable marketing law.

## Desktop interface

The Electron application is borderless and resizable. Back, forward, refresh, thin/wide navigation, minimize, maximize, and close controls live inside the application interface.

The workspace is organized into:

- **Discover** — search settings, plan, linked workflow, and live results.
- **History** — grouped runs with retained checkpoints and diagnostics.
- **Research library** — completed collections and collapsible intelligence sections.
- **Outreach** — Zoho connection, templates, drafts, campaigns, and outcomes.
- **Data sources** — built-in source cards, optional credentials, Google OAuth setup, updates, and repair.
- **Business registries** — reviewed official directories followed by offer-to-buyer planning.

## Install on Windows

### Installer

Download `Lead-Extractor-Setup-*.exe` from GitHub Releases.

The installer can enable Chrome integration. The app creates a separate persistent profile and never imports the normal Chrome profile. Saved research and browser state live in the Windows user-data directory, not the installation folder.

Requirements:

- Windows 10 or Windows 11
- Python 3.10 or newer on `PATH`
- Google Chrome for Maps and browser-assisted review
- Ollama only for optional local-AI features

### Run from source

```powershell
git clone https://github.com/ariyankhalid97-creator/lead-intelligence-workbench.git
cd lead-intelligence-workbench
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
npm install
npm start
```

Browser-only fallback:

```powershell
.venv\Scripts\python.exe dashboard.py --port 8788
```

Then open `http://127.0.0.1:8788`.

## Build the installer

```powershell
npm install
npm run build:windows
```

Electron Builder writes the NSIS installer and update metadata to `release/`. Public releases should be code-signed. Publish the installer and `latest.yml` together so installed builds can use the configured GitHub update channel.

## Local data and public repository boundary

The following paths are ignored and must never be committed:

- `data/` — databases, tokens, task state, local intelligence memory, and browser metadata
- `leads/` — CSV and JSON exports
- `logs/` — diagnostics and execution logs
- `release/`, `dist/`, `test-results/`, and browser reports
- `.env*`, private keys, certificates, local virtual environments, and `node_modules/`

Credentials are stored through Windows Credential Manager. The browser never receives secret values back from the connection API.

Reusable source code, niche packs, search-method packs, directory metadata, schemas, and tests are intentionally versioned.

## Privacy, security, and responsible use

- The backend binds only to `127.0.0.1`.
- Host and Origin checks protect browser requests.
- Electron uses renderer sandboxing, context isolation, and no renderer Node integration.
- Ollama and Chrome debugging connections are loopback-only.
- External links open outside the privileged application window.
- The app does not bypass logins, CAPTCHAs, paywalls, robots directives, security checkpoints, rate limits, or access controls.
- Collect only public professional information you have a legitimate reason to process.
- Do not use the project for credential harvesting, account abuse, sensitive-person profiling, indiscriminate messaging, or unlawful outreach.

This is a local desktop application, not a multi-user server. Never expose port `8788` to another machine. See [SECURITY.md](SECURITY.md).

## Testing and release checks

Backend tests:

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Browser workflow tests:

```powershell
npm run test:e2e
```

Desktop smoke test:

```powershell
npm run test:electron
```

Dependency and source checks:

```powershell
npm audit
.venv\Scripts\python.exe -m pip_audit -r requirements.txt
.venv\Scripts\python.exe -m bandit -r . -x .venv,node_modules,release
```

## Limitations

- A result limit is a ceiling, not a guaranteed count.
- Source coverage varies by niche, country, city, indexing, and provider availability.
- A location in a query does not prove that a company serves that location.
- Directory, social, hiring, review, and advertising claims can be stale and require human confirmation.
- A public company LinkedIn URL does not identify the correct decision-maker.
- Complex websites may expose no usable evidence even after rendering.
- Network providers can change policies, schemas, quotas, and access requirements.

## License

[MIT](LICENSE) © 2026 ariyankhalid97-creator
