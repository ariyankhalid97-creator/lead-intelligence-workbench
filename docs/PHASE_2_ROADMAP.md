# Phase 2: country directories, geography, Sheets and LinkedIn-assisted research

## Implemented foundation in 2.4

- secure optional-provider vault and connection health checks;
- Google Sheets desktop OAuth and organized-library synchronization;
- explicitly enabled Google Places provider in the all-sources waterfall;
- persistent source catalog seeded for US, Singapore, Malaysia and Australia;
- country context selector with unrestricted manual location fallback.

The remaining country registry adapters, exact cross-directory comparison, and approved LinkedIn automation are staged below.

The optional Apify actor path has been reviewed separately in [APIFY_ACTOR_CATALOG_REVIEW.md](APIFY_ACTOR_CATALOG_REVIEW.md). It uses the external repository as a discovery catalog only; live official schemas, pricing, explicit spend confirmation and per-actor normalization are mandatory before any paid run.

This phase should extend the evidence waterfall without turning every directory page into a trusted lead. Google Maps remains a discovery seed. Registry and directory results are comparison evidence until an exact domain, phone, registration identifier, or name-and-address match connects them to the same entity.

## 1. Source registry and saved directory memory

Add a versioned `source_catalog` table and connector manifest with:

- country and covered subdivisions;
- source name, base domain, connector type and licence;
- supported niches and query template;
- public/API/authenticated/paid access classification;
- rate and pagination limits;
- parser version and last successful check;
- evidence authority and freshness weights;
- enabled, degraded and manual-review states.

When research discovers a useful directory, save it as a candidate source for that niche and country. Do not automatically crawl it on every run. A connector becomes active only after its profile-page pattern, access terms, robots policy, field mapping and test fixture have been reviewed.

The comparison stage should resolve records in this order:

1. official registration identifier;
2. normalized website domain;
3. normalized phone plus compatible branch address;
4. normalized name plus compatible street/city;
5. otherwise retain a possible-match flag instead of merging.

## 2. Initial country adapters

### United States

Keep Maps, OpenStreetMap, NPI and existing public-directory profiles. Add niche/state licensing adapters individually because state schemas and permissions differ. Chambers and commercial directories remain third-party corroboration.

### Singapore

Use the free ACRA open datasets published through data.gov.sg as registry evidence. The dataset is updated monthly and exposes entity identifiers, status, type and registered location. Keep the paid/restricted ACRA API Marketplace as an optional connector, not a free default.

Sources: [ACRA open-data initiative](https://www.acra.gov.sg/resources/open-data-initiative/), [data.gov.sg ACRA dataset](https://data.gov.sg/datasets/d_3f960c10fed6145404ca7b821f263b87/view).

### Australia

Use ABN Lookup for legal-entity validation. Its web services are free but require registration for an authentication GUID. Store the GUID in the operating-system credential store and never in an export or repository.

Source: [ABN Lookup web services](https://abr.business.gov.au/Tools/WebServices).

### Malaysia

Treat Malaysia's official open-data API as a source only when a relevant dataset is actually available. SSM business/company profiles are sold through official service-provider portals, so the application must not imply that paid SSM records are a free scrape or bypass their access controls.

Sources: [Malaysia Open API](https://developer.data.gov.my/quickstart), [SSM business information](https://www.ssm.com.my/Pages/Product/Business-Information.aspx).

## 3. Geography UX

Add a country selector with United States, Singapore, Malaysia and Australia first. After country selection, show only applicable state/region and city helpers. Keep the existing free-text location field as an always-available fallback for any country.

Store canonical fields separately from the user's query:

- ISO country code;
- state/region code where one exists;
- canonical city;
- original location text;
- geocoder evidence and coordinates.

The UI must label a country as supported only when at least one configured source can search it. Manual website/URL and web-discovery searches should remain available elsewhere.

## 4. Google Sheets export

Do not use an embedded API key for private spreadsheet writes. Sheets creation and updates require OAuth authorization. Use the narrow `drive.file` scope so the app can access only files the user creates or opens through this integration.

Flow:

1. Connect Google from the desktop settings panel.
2. Complete OAuth in the system browser.
3. Store the refresh token in Windows Credential Manager.
4. Choose an existing spreadsheet opened through the app or create a new one.
5. Map stable columns from the compiled research schema.
6. Append new companies and upsert existing rows by canonical company ID.
7. Save the spreadsheet ID, sheet name and last-sync cursor locally.
8. Show a preview and require confirmation before the first write or any destructive column remap.

Google recommends the per-file scope for the narrowest access: [Sheets API scopes](https://developers.google.com/workspace/sheets/api/scopes).

## 5. LinkedIn-assisted contacts

Keep LinkedIn as a manual, browser-assisted verification checkpoint. The ordinary LinkedIn developer permissions expose the authenticated member's own profile; broader member/profile and Sales Navigator access requires approved products or partner access. The application should not automate logins, defeat checkpoints, reuse saved passwords programmatically, or scrape authenticated employee pages with an unofficial GitHub bot.

Supported workflow:

1. Open an exact company or person query in the dedicated browser profile.
2. Let the user review the signed-in page.
3. Capture only user-confirmed public professional fields and their URL/time.
4. Compare a confirmed employee to the canonical company and preserve uncertainty.
5. Prefer an approved LinkedIn API or licensed export if automated employee coverage is required.

Source: [LinkedIn API access and permissions](https://learn.microsoft.com/en-gb/linkedin/shared/authentication/getting-access).

## 6. Delivery order

1. Source-catalog schema and connector contract.
2. Country/region/city canonicalization and UI.
3. Singapore ACRA open-data adapter and Australia ABN adapter.
4. Directory candidate memory and exact-entity comparison.
5. Google OAuth and Sheets upsert/export.
6. LinkedIn manual checkpoint improvements.
7. Per-country fixtures, licence notes, rate-limit diagnostics and end-to-end tests.

This order makes the entity model and geography stable before adding more records or export destinations.
