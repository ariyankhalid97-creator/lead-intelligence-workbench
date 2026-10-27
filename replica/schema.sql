CREATE TABLE IF NOT EXISTS jobs (
 id TEXT PRIMARY KEY,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('queued','running','waiting','complete','partial','failed','cancelled','interrupted')),
 payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_jobs_updated ON jobs(updated_at DESC);
CREATE TABLE IF NOT EXISTS events (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
 created_at TEXT NOT NULL,
 provider TEXT NOT NULL,
 level TEXT NOT NULL,
 message TEXT NOT NULL,
 details TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_job ON events(job_id,id);
CREATE TABLE IF NOT EXISTS ai_tasks (
 id TEXT PRIMARY KEY,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 status TEXT NOT NULL,
 payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ai_tasks_updated ON ai_tasks(updated_at);
CREATE TABLE IF NOT EXISTS verification_tasks (
 id TEXT PRIMARY KEY,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 status TEXT NOT NULL,
 payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_verification_tasks_updated ON verification_tasks(updated_at);

CREATE TABLE IF NOT EXISTS outreach_templates (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  niche TEXT NOT NULL,
  subject TEXT NOT NULL,
  body TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS outreach_campaigns (
  id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  status TEXT NOT NULL,
  payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS outreach_messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  campaign_id TEXT NOT NULL,
  recipient TEXT NOT NULL,
  lead_name TEXT NOT NULL,
  status TEXT NOT NULL,
  subject TEXT NOT NULL,
  body TEXT NOT NULL,
  attempts INTEGER NOT NULL DEFAULT 0,
  provider_id TEXT NOT NULL DEFAULT '',
  error TEXT NOT NULL DEFAULT '',
  sent_at TEXT NOT NULL DEFAULT '',
  UNIQUE(campaign_id, recipient),
  FOREIGN KEY(campaign_id) REFERENCES outreach_campaigns(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS outreach_suppressions (
  email TEXT PRIMARY KEY,
  reason TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS intelligence_companies (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  domain TEXT NOT NULL DEFAULT '',
  phone TEXT NOT NULL DEFAULT '',
  address TEXT NOT NULL DEFAULT '',
  city TEXT NOT NULL DEFAULT '',
  niche TEXT NOT NULL DEFAULT '',
  payload TEXT NOT NULL,
  first_seen TEXT NOT NULL,
  last_seen TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_intelligence_companies_domain ON intelligence_companies(domain);
CREATE INDEX IF NOT EXISTS idx_intelligence_companies_phone ON intelligence_companies(phone);
CREATE TABLE IF NOT EXISTS intelligence_locations (
  id TEXT PRIMARY KEY,
  company_id TEXT NOT NULL REFERENCES intelligence_companies(id) ON DELETE CASCADE,
  address TEXT NOT NULL DEFAULT '',
  city TEXT NOT NULL DEFAULT '',
  source_url TEXT NOT NULL DEFAULT '',
  first_seen TEXT NOT NULL,
  last_seen TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_intelligence_locations_company ON intelligence_locations(company_id);
CREATE TABLE IF NOT EXISTS intelligence_aliases (
  alias TEXT PRIMARY KEY,
  company_id TEXT NOT NULL REFERENCES intelligence_companies(id) ON DELETE CASCADE,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_intelligence_alias_company ON intelligence_aliases(company_id);
CREATE TABLE IF NOT EXISTS intelligence_contacts (
  id TEXT PRIMARY KEY,
  company_id TEXT NOT NULL REFERENCES intelligence_companies(id) ON DELETE CASCADE,
  email TEXT NOT NULL DEFAULT '',
  phone TEXT NOT NULL DEFAULT '',
  name TEXT NOT NULL DEFAULT '',
  role TEXT NOT NULL DEFAULT '',
  confidence INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'observed',
  payload TEXT NOT NULL,
  first_seen TEXT NOT NULL,
  last_seen TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_intelligence_contacts_company ON intelligence_contacts(company_id);
CREATE INDEX IF NOT EXISTS idx_intelligence_contacts_email ON intelligence_contacts(email);
CREATE TABLE IF NOT EXISTS intelligence_evidence (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  company_id TEXT NOT NULL REFERENCES intelligence_companies(id) ON DELETE CASCADE,
  job_id TEXT NOT NULL DEFAULT '',
  field TEXT NOT NULL,
  value TEXT NOT NULL,
  source_url TEXT NOT NULL DEFAULT '',
  basis TEXT NOT NULL DEFAULT '',
  observed_at TEXT NOT NULL,
  UNIQUE(company_id,field,value,source_url,basis)
);
CREATE INDEX IF NOT EXISTS idx_intelligence_evidence_company ON intelligence_evidence(company_id,id);
CREATE TABLE IF NOT EXISTS intelligence_outcomes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  company_id TEXT NOT NULL DEFAULT '',
  email TEXT NOT NULL DEFAULT '',
  campaign_id TEXT NOT NULL DEFAULT '',
  outcome TEXT NOT NULL,
  note TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_intelligence_outcomes_company ON intelligence_outcomes(company_id,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_intelligence_outcomes_email ON intelligence_outcomes(email,created_at DESC);
CREATE TABLE IF NOT EXISTS intelligence_queue (
  company_id TEXT PRIMARY KEY REFERENCES intelligence_companies(id) ON DELETE CASCADE,
  action TEXT NOT NULL,
  priority INTEGER NOT NULL,
  reason TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'open',
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_intelligence_queue_action ON intelligence_queue(status,priority DESC,updated_at DESC);
CREATE TABLE IF NOT EXISTS intelligence_niche_packs (
  slug TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  payload TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS intelligence_watch_snapshots (
  company_id TEXT PRIMARY KEY REFERENCES intelligence_companies(id) ON DELETE CASCADE,
  fingerprint TEXT NOT NULL,
  payload TEXT NOT NULL,
  observed_at TEXT NOT NULL,
  changed_at TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS intelligence_watch_schedule (
  company_id TEXT PRIMARY KEY REFERENCES intelligence_companies(id) ON DELETE CASCADE,
  url TEXT NOT NULL,
  interval_days INTEGER NOT NULL DEFAULT 30,
  enabled INTEGER NOT NULL DEFAULT 1,
  fingerprint TEXT NOT NULL DEFAULT '',
  last_run TEXT NOT NULL DEFAULT '',
  next_run TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'scheduled',
  last_error TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_intelligence_watch_due ON intelligence_watch_schedule(enabled,next_run);
CREATE TABLE IF NOT EXISTS intelligence_browser_checkpoints (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  company_id TEXT NOT NULL DEFAULT '',
  service TEXT NOT NULL,
  url TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL,
  detail TEXT NOT NULL DEFAULT '',
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_intelligence_browser_checkpoints ON intelligence_browser_checkpoints(company_id,updated_at DESC);
CREATE TABLE IF NOT EXISTS intelligence_experiments (
  campaign_id TEXT NOT NULL,
  company_id TEXT NOT NULL,
  variant TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY(campaign_id,company_id)
);

CREATE TABLE IF NOT EXISTS intelligence_parent_brands (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  domain TEXT NOT NULL DEFAULT '',
  payload TEXT NOT NULL,
  first_seen TEXT NOT NULL,
  last_seen TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_parent_brand_domain ON intelligence_parent_brands(domain);
CREATE TABLE IF NOT EXISTS intelligence_operating_entities (
  id TEXT PRIMARY KEY,
  parent_brand_id TEXT NOT NULL DEFAULT '' REFERENCES intelligence_parent_brands(id),
  company_id TEXT NOT NULL REFERENCES intelligence_companies(id) ON DELETE CASCADE,
  locality_key TEXT NOT NULL DEFAULT '',
  place_id TEXT NOT NULL DEFAULT '',
  ownership_scope TEXT NOT NULL DEFAULT 'unknown',
  payload TEXT NOT NULL,
  first_seen TEXT NOT NULL,
  last_seen TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_operating_parent ON intelligence_operating_entities(parent_brand_id,last_seen DESC);
CREATE INDEX IF NOT EXISTS idx_operating_company ON intelligence_operating_entities(company_id);
CREATE TABLE IF NOT EXISTS intelligence_evidence_claims (
  evidence_id TEXT PRIMARY KEY,
  company_id TEXT NOT NULL REFERENCES intelligence_companies(id) ON DELETE CASCADE,
  operating_entity_id TEXT NOT NULL DEFAULT '',
  job_id TEXT NOT NULL DEFAULT '',
  field TEXT NOT NULL,
  value TEXT NOT NULL,
  source_type TEXT NOT NULL,
  source_url TEXT NOT NULL DEFAULT '',
  captured_at TEXT NOT NULL,
  verbatim_excerpt TEXT NOT NULL,
  selector TEXT NOT NULL DEFAULT '',
  authority_weight REAL NOT NULL,
  freshness_weight REAL NOT NULL,
  trust_score REAL NOT NULL,
  payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_evidence_claim_company ON intelligence_evidence_claims(company_id,captured_at DESC);
CREATE TABLE IF NOT EXISTS fetch_diagnostics (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id TEXT NOT NULL DEFAULT '',
  company_id TEXT NOT NULL DEFAULT '',
  url TEXT NOT NULL,
  fetched_at TEXT NOT NULL,
  fetch_tier TEXT NOT NULL,
  status_code INTEGER NOT NULL DEFAULT 0,
  redirect_chain TEXT NOT NULL DEFAULT '[]',
  elapsed_ms INTEGER NOT NULL DEFAULT 0,
  render_ms INTEGER NOT NULL DEFAULT 0,
  waf_signature TEXT NOT NULL DEFAULT '',
  outcome TEXT NOT NULL,
  details TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_fetch_diagnostics_job ON fetch_diagnostics(job_id,id);
CREATE TABLE IF NOT EXISTS intelligence_watch_http (
  company_id TEXT PRIMARY KEY REFERENCES intelligence_companies(id) ON DELETE CASCADE,
  etag TEXT NOT NULL DEFAULT '',
  last_modified TEXT NOT NULL DEFAULT '',
  semantic_payload TEXT NOT NULL DEFAULT '{}',
  checked_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS outreach_dnc (
  scope TEXT NOT NULL CHECK(scope IN ('email','domain','parent_brand','operating_entity')),
  value TEXT NOT NULL,
  reason TEXT NOT NULL,
  source TEXT NOT NULL DEFAULT 'manual',
  created_at TEXT NOT NULL,
  PRIMARY KEY(scope,value)
);
CREATE TABLE IF NOT EXISTS email_verifications (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('valid','invalid','catch_all','spam_trap','unknown')),
  provider TEXT NOT NULL,
  checked_at TEXT NOT NULL,
  evidence TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_email_verification_latest ON email_verifications(email,checked_at DESC);
CREATE TABLE IF NOT EXISTS outreach_sequence_steps (
  sequence_id TEXT NOT NULL,
  step_number INTEGER NOT NULL,
  delay_days INTEGER NOT NULL DEFAULT 0,
  subject TEXT NOT NULL,
  body TEXT NOT NULL,
  condition TEXT NOT NULL DEFAULT 'no_reply',
  PRIMARY KEY(sequence_id,step_number)
);
CREATE TABLE IF NOT EXISTS outreach_sequence_states (
  id TEXT PRIMARY KEY,
  sequence_id TEXT NOT NULL,
  campaign_id TEXT NOT NULL DEFAULT '',
  company_id TEXT NOT NULL DEFAULT '',
  operating_entity_id TEXT NOT NULL DEFAULT '',
  email TEXT NOT NULL,
  current_step INTEGER NOT NULL DEFAULT 0,
  state TEXT NOT NULL,
  next_action_at TEXT NOT NULL DEFAULT '',
  pause_until TEXT NOT NULL DEFAULT '',
  last_outcome TEXT NOT NULL DEFAULT '',
  payload TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sequence_due ON outreach_sequence_states(state,next_action_at);
CREATE TABLE IF NOT EXISTS outreach_reply_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  sequence_state_id TEXT NOT NULL DEFAULT '',
  company_id TEXT NOT NULL DEFAULT '',
  email TEXT NOT NULL DEFAULT '',
  event_type TEXT NOT NULL,
  return_date TEXT NOT NULL DEFAULT '',
  referred_name TEXT NOT NULL DEFAULT '',
  referred_email TEXT NOT NULL DEFAULT '',
  source TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  payload TEXT NOT NULL DEFAULT '{}'
);
