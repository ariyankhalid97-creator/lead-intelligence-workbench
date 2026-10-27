# Search-method and vertical research packs

Version 2.4.2 adapts useful research concepts from the MIT-licensed [`cporter202/google-maps-scraping-apis`](https://github.com/cporter202/google-maps-scraping-apis) catalog and its lead/review playbooks. No actor code, credentials, affiliate links or automatic paid execution are included.

## Integrated methods

Every niche pack now contains editable methods for:

- category plus city/state discovery;
- nearby-radius coverage checks;
- listings that supplied no website or only a social profile;
- observed ratings below 4.0 with at least 20 listed reviews;
- review recency, low-rating replies and review-velocity checks;
- exact Place ID or Maps URL identity resolution;
- first-party website contact and published-email enrichment;
- domain, phone and address comparison across sources;
- rating and review-count snapshot comparison.

A missing website field is labeled only as a candidate for verification. It is never promoted to a claim that the company has no website.

## Vertical packs

The catalog's most reusable vertical concepts were converted into deterministic packs for childcare, construction, dental, fitness, funeral services, healthcare, hospitality, legal services, pet services, real estate, restaurants, and salons/spas.

Each applicable pack adds:

- provider terminology suitable for Maps and public-web discovery;
- software/platform names to verify in retained first-party evidence;
- standard review-monitoring signals;
- an editable method list shown in AI Lead Intelligence Memory.

Technology names are hypotheses, not facts. The application records a technology signal only when a saved evidence payload actually mentions it. Local AI receives these names as items to check, with an explicit instruction not to assume them.

## Execution boundary

These packs improve the existing free/local workflow. They do not run Apify actors. An Apify actor still requires the user's own token, current-schema validation, cost limits and explicit confirmation as described in [APIFY_ACTOR_CATALOG_REVIEW.md](APIFY_ACTOR_CATALOG_REVIEW.md).

## Attribution

Concept source: `cporter202/google-maps-scraping-apis`, copyright Chris Porter, MIT License. The application stores a source note in generated niche packs so the origin remains inspectable.
