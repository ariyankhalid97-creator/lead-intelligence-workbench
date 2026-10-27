# Apify Google Maps actor catalog: integration review

## Verdict

`cporter202/google-maps-scraping-apis` is a useful discovery catalog, not a scraper library that can be copied into the application. It indexes third-party Apify actors, examples and playbooks. Each actor remains an independently operated service with its own input schema, output shape, availability, terms and pricing.

Use the catalog to help users choose an Apify actor. Do not treat it as a free data source, automatically run every listed actor, or rely on its examples as a stable API contract.

The catalog's reusable search, qualification and review-monitoring concepts are now implemented locally in version 2.4.2. See [SEARCH_METHOD_PACKS.md](SEARCH_METHOD_PACKS.md). This does not enable actor execution.

## Important findings

- The repository currently presents 217 actor listings and groups them by capability.
- Its links include an affiliate parameter. The application should store canonical actor IDs and links without affiliate tracking.
- The repository's MIT licence covers its repository material. It does not relicense actor services or the data returned by them.
- The local review found that a playbook example for `compass/crawler-google-places` no longer matches the actor's current official example input or current event pricing. Actor metadata must therefore be fetched live from Apify before a run.
- The existing Apify credential connector is the right foundation. A token alone must never start a paid run.

## Safe integration design

### 1. Curated actor registry

Add a small, versioned registry rather than importing all listings. Store:

- canonical actor ID;
- supported jobs and countries;
- official actor URL;
- reviewed input/output adapter version;
- last metadata validation time;
- current pricing model and minimum charge, fetched from Apify;
- health, confidence and experimental/stable status.

The initial candidates can include `compass/crawler-google-places`, `thirdwatch/google-maps-scraper`, and `bovi/google-maps-scraper`. Usage counts and freshness should be shown as evidence, not as guarantees of quality.

### 2. Live preflight

Before every paid run:

1. fetch the actor's official metadata, current build, input schema and pricing;
2. reject an adapter whose expected schema no longer matches;
3. show actor, query limit, optional enrichments, estimated or bounded maximum cost and current minimum charge;
4. require explicit user confirmation;
5. create the run only after confirmation.

Never place an actor token in the browser page, export, diagnostics or logs.

### 3. One normalized output contract

Map each actor dataset into the existing lead schema:

- business name and normalized identity;
- address, city, region, country and coordinates;
- phone, website, category, rating and review count;
- published emails/social links only when returned with evidence;
- actor ID, run ID, dataset item ID, retrieval time and source URL.

Then pass records through the same entity-boundary checks, deduplication, contact-quality classification and research-library grouping as every other source. Paid actor output is discovery evidence, not automatically a verified lead.

### 4. Diagnostics and spend protection

Record safe operational metadata: actor ID, run status, build, dataset count, normalized/rejected counts, adapter version, billable event summary and redacted failure details. Add per-run and monthly spend ceilings, cancellation, retry rules and an audit trail. Do not log tokens or raw authenticated request headers.

## Recommended delivery sequence

1. Add actor-registry and live-metadata read-only views.
2. Implement one adapter against a saved fixture and contract tests.
3. Add preview, cost bounds and explicit confirmation.
4. Run the actor, poll completion and import the dataset.
5. Normalize, deduplicate and retain source provenance.
6. Add a second actor only after the first adapter remains stable.

This approach gains the catalog's breadth without silently introducing paid calls, stale schemas, affiliate links or inconsistent records.

## References

- Catalog: <https://github.com/cporter202/google-maps-scraping-apis>
- Local lead playbook: <https://github.com/cporter202/google-maps-scraping-apis/blob/main/playbooks/local-lead-pipeline.md>
- Repository licence: <https://github.com/cporter202/google-maps-scraping-apis/blob/main/LICENSE>
- Apify API: <https://docs.apify.com/api/v2>
