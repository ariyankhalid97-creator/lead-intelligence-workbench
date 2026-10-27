# Lead Intelligence and Outreach Workflow

## Operating flow

1. **Niche pack and compiled terminology** — load editable synonyms, exclusions, decision-maker roles, source types, opportunity signals and enrichment order. Rule-vetted local-AI terms learned from compiled category evidence are saved to the pack and automatically included in later Maps searches.
2. **Discovery and immutable diagnostics** — search selected public sources within the query budget. Search History stores every provider start, query, result count, failure, exact pause/stop reason and merge event. A result or snippet remains discovery evidence until a stronger source corroborates it.
3. **Tiered website fetching** — respect `robots.txt` and per-domain crawl delay; attempt a bounded HTTP fetch first. Record status, redirects, response time, selected headers, cookie names and detected WAF signature. Escalate JavaScript shells or empty app roots to normal Playwright rendering. Never solve or evade CAPTCHA/WAF challenges: pause at `manual_browser_review` and use the dedicated browser profile.
4. **Evidence and decision-maker enrichment** — inspect structured data, visible pages, contact/about/team/leadership/press pages, mailto/tel links and public social links. Retain source URL, capture time, method, literal excerpt or selector. Match published people only to configured Niche pack roles. If a person has no published direct address, generate at most three review-only `inferred_permutation` candidates from an observed domain pattern; inferred candidates never become primary contacts without legitimate verification.
5. **Verification and technographics** — recheck the website, all retained email domains, public phones/social links, reviews and advertising signals. Audit response headers, cookie names, HTML/structured data, common JavaScript tags, SPF, DMARC, domain-verification TXT records, `robots.txt` and `sitemap.xml`. Passive pixels and landing parameters remain installation/traffic signals; active spend requires a retained public ad-library record.
6. **Three-stage contact safety** — (a) reject malformed, automated, abuse, legal, privacy, postmaster and support-only addresses; (b) record MX or standards-compatible address fallback plus SPF/DMARC without claiming mailbox validity; (c) ingest results only from a legitimate user-configured verification provider or real delivery outcome as `valid`, `invalid`, `catch_all`, `spam_trap` or `unknown`. Invalid/spam-trap addresses enter DNC immediately. Unknown is blocked when a provider explicitly returns it. Catch-all is blocked unless manually reviewed or corroborated by a prior direct reply.
7. **Organization, trust weighting and identity resolution** — consolidate only strongly supported duplicates. Each immutable `evidence_id` receives source authority and time-decay freshness weights (`official website > verified Maps > recent social > directory > snippet`). Stale or weak data cannot silently overwrite a retained stronger fact. Resolve a `ParentBrandID` from shared corporate identity and an `OperatingEntityID` from locality, Maps/place identity and local phone so branches remain separately actionable.
8. **Evidence-bound compilation** — deterministic compilation always produces contact readiness, opportunity signals, semantic change state and one next action. The optional local compiler receives only the immutable ledger and must return validated JSON. Every AI claim requires an existing `evidence_id` and literal excerpt; the entire AI result is rejected if a citation, excerpt, enum or queue state is invalid. Schemas: [`schemas/lead-intelligence.ts`](schemas/lead-intelligence.ts) and [`schemas/lead-intelligence.schema.json`](schemas/lead-intelligence.schema.json).
9. **Research Library and work queue** — publish the complete organized run without flattening evidence, diagnostics or timestamps. Lead Intelligence links parent brands, operating entities, locations, historical contacts, evidence, browser checkpoints, changes and outcomes. The queue exposes one next-best action.
10. **Compliance and campaign preparation** — apply email-, domain-, parent-brand- and operating-entity DNC scopes; previous outcomes; mailbox-provider states; duplicate-recipient detection; daily caps; and branch-scoped identity. Preserve one-to-one human approval. Templates must keep an unsubscribe path. Cold outreach is not automatically rotated to evade reputation controls; sender profiles must be explicitly configured and independently capped.
11. **Sequences and sending** — sequences contain one to five increasing-delay steps and enroll at operating-entity/contact scope. Only explicitly approved messages use Zoho’s official API. A reply, opt-out, hard bounce, wrong contact, meeting or customer outcome halts remaining steps immediately. Out-of-office pauses until a retained return date. Referral creates a reply event and routes the referred contact to discovery rather than silently treating it as verified.
12. **Outcome learning and monitoring** — accepted sends do not prove delivery. Record delivered, bounced, opened, replied, positive, referral, out-of-office, meeting, won, wrong-contact and unsubscribe outcomes. Update queue, DNC and sequence state deterministically. Website monitoring first sends conditional `If-None-Match`/`If-Modified-Since` requests, then strips timestamps, session IDs, rotating reviews, copyright years and ad nonces. Only material changes to contacts, leadership, service headings, locations or tech signals return a company to manual review.

Work queue and outcome transitions:

| Current state | Evidence/event | Next state | Required effect |
|---|---|---|---|
| verification | Website/contact checks complete | contact discovery, decision-maker research or outreach | Retain report and evidence IDs |
| contact discovery | Supported public contact found | decision-maker research | Keep generic and inferred contacts distinct |
| decision-maker research | Published role/contact supported | outreach | Run deliverability and DNC gates |
| manual browser review | Login/WAF/manual evidence completed | verification | Save checkpoint; never infer success |
| outreach | Message accepted by provider | outreach / awaiting reply | Schedule only an approved next step |
| outreach | reply or positive reply | reply follow-up | Halt sequence immediately |
| outreach | out of office with return date | paused OOO | Resume no earlier than retained date |
| outreach | referral | contact discovery | Create a new unverified referred-contact record |
| outreach | unsubscribe, hard bounce, spam trap, wrong contact | suppression | Write scoped DNC immediately; halt sequence |
| reply follow-up | meeting booked | reply follow-up | Close prospecting sequence |
| reply follow-up | customer won | customer | Close queue item and preserve attribution |
| any active state | parent/branch identity conflict | manual browser review | Prevent cross-branch suppression or contact leakage |

## Evidence rules

- A search result or SERP snippet is discovery evidence, not proof; snippet-only claims are `unverified_snippet`.
- Every compiled fact, AI claim and opportunity signal must retain `evidence_id`, `source_url`, `captured_at` and a literal excerpt or selector.
- A published email is an observation, not proof the mailbox exists or accepts mail.
- MX or address fallback proves domain routing only. SPF/DMARC describe policy only. Neither proves an individual mailbox.
- Local AI may read retained public addresses for role classification, but syntax, source, DNC, provider and outcome gates retain final authority.
- Inferred permutations are visibly labeled and never eligible merely because the pattern looks plausible.
- A pixel, tag, cookie or network request proves installation/observation only, not active advertising spend.
- Missing text is `not_observed`, never `confirmed_absent`.
- Parent-brand similarity does not prove common ownership. Branch-level contact and suppression stay scoped unless explicit evidence supports a parent rollup.
- HTTP rendering may handle ordinary JavaScript pages but must not evade access controls, rotate residential identities, solve challenges or bypass a site’s stated restrictions.
- SMTP probing is not performed. Mailbox-level states come from a legitimate configured verification service, direct reply, or actual delivery/bounce evidence.
- AI output is advisory and is rejected—not partially accepted—when any required evidence pointer or literal excerpt is invalid.
- A send-provider acceptance is `sent`, not `delivered`; outcome performance is observed history, never predicted conversion.
- Regional compliance cannot be inferred from a city label alone. Unknown or higher-risk jurisdiction/consent questions remain a human pre-send review item.

## Durable links

```text
Niche pack + compiled terminology
  → search job + immutable provider/fetch diagnostics
    → raw candidates + field-level evidence
      → verification + technographics + contact states
        → source trust/freshness ledger
          → ParentBrandID
            → OperatingEntityID(s)
              → locations
              → contacts + verification history
              → immutable evidence IDs
              → deterministic + optional validated AI compilation
              → semantic/change snapshots
              → browser checkpoints
              → next-best-action queue
              → DNC/compliance gate
              → campaign variant + sequence state
              → Zoho provider outcomes + reply events
              → suppression / follow-up / customer learning loop
```

Search History remains the immutable run audit. Research Library remains the organized collection. Lead Intelligence remains cross-run memory. Parent-brand rollups never erase operating-entity scope. Outreach consumes only eligible compiled contacts and writes every operational outcome back into the same evidence-bound memory.
