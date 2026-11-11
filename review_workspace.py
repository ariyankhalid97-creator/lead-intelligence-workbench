"""Unified daily lead-review decisions, presets and evidence feedback."""

from __future__ import annotations

import json
import re
import uuid
from urllib.parse import urlparse

import engine
import intelligence
import organizer
from contacts import now

DECISIONS = {"confirmed", "rejected", "deferred", "pending"}


def _clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _json(value, default):
    if isinstance(value, type(default)):
        return value
    try:
        parsed = json.loads(value or "")
        return parsed if isinstance(parsed, type(default)) else default
    except (TypeError, ValueError):
        return default


def init():
    with engine.connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS search_presets (
              id TEXT PRIMARY KEY, name TEXT NOT NULL, offer TEXT NOT NULL DEFAULT '',
              target_role TEXT NOT NULL DEFAULT '', geography TEXT NOT NULL DEFAULT '',
              exclusions TEXT NOT NULL DEFAULT '[]', sources TEXT NOT NULL DEFAULT '[]',
              created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS lead_review_decisions (
              company_id TEXT NOT NULL, contact_key TEXT NOT NULL DEFAULT '',
              decision TEXT NOT NULL, permission_to_send INTEGER NOT NULL DEFAULT 0,
              note TEXT NOT NULL DEFAULT '', reviewer TEXT NOT NULL DEFAULT 'local_user',
              updated_at TEXT NOT NULL, PRIMARY KEY(company_id,contact_key)
            );
            CREATE TABLE IF NOT EXISTS linkedin_review_decisions (
              id TEXT PRIMARY KEY, company_id TEXT NOT NULL DEFAULT '',
              operating_entity_id TEXT NOT NULL DEFAULT '', candidate_url TEXT NOT NULL,
              person_name TEXT NOT NULL DEFAULT '', role TEXT NOT NULL DEFAULT '',
              current_company TEXT NOT NULL DEFAULT '', location TEXT NOT NULL DEFAULT '',
              decision TEXT NOT NULL, evidence_note TEXT NOT NULL DEFAULT '',
              updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS claim_feedback (
              evidence_id TEXT NOT NULL, company_id TEXT NOT NULL,
              decision TEXT NOT NULL, correction TEXT NOT NULL DEFAULT '',
              note TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL,
              PRIMARY KEY(evidence_id,company_id)
            );
            CREATE TABLE IF NOT EXISTS delivery_imports (
              content_hash TEXT PRIMARY KEY, imported_at TEXT NOT NULL,
              source_message_id TEXT NOT NULL DEFAULT '', result TEXT NOT NULL DEFAULT '{}'
            );
            CREATE TABLE IF NOT EXISTS delivery_events (
              id INTEGER PRIMARY KEY AUTOINCREMENT, content_hash TEXT NOT NULL,
              outreach_message_id INTEGER, campaign_id TEXT NOT NULL DEFAULT '',
              recipient TEXT NOT NULL DEFAULT '', action TEXT NOT NULL DEFAULT '',
              status_code TEXT NOT NULL DEFAULT '', diagnostic TEXT NOT NULL DEFAULT '',
              match_status TEXT NOT NULL, event_kind TEXT NOT NULL DEFAULT 'failure',
              created_at TEXT NOT NULL,
              UNIQUE(content_hash,recipient,status_code,action)
            );
            CREATE INDEX IF NOT EXISTS idx_delivery_event_review
              ON delivery_events(match_status,created_at DESC);
            CREATE TABLE IF NOT EXISTS manual_followup_tasks (
              id TEXT PRIMARY KEY, company_id TEXT NOT NULL DEFAULT '',
              title TEXT NOT NULL, due_date TEXT NOT NULL DEFAULT '',
              status TEXT NOT NULL DEFAULT 'open', note TEXT NOT NULL DEFAULT '',
              created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            """
        )


def _email_evidence(memory, email):
    email = email.casefold()
    rows = [
        item for item in memory.get("evidence", [])
        if item.get("field") == "email" and _clean(item.get("value")).casefold() == email
    ]
    strict = [
        item for item in memory.get("evidence_claims", [])
        if item.get("field") == "email" and _clean(item.get("value")).casefold() == email
    ]
    best = (strict or rows or [{}])[0]
    return {
        "published": bool(rows or strict),
        "source_url": best.get("source_url", ""),
        "excerpt": best.get("verbatim_excerpt", "") or best.get("basis", ""),
        "observed_at": best.get("captured_at", "") or best.get("observed_at", ""),
    }


def _review(conn, company_id, email):
    row = conn.execute(
        "SELECT decision,permission_to_send,note,updated_at FROM lead_review_decisions WHERE company_id=? AND contact_key=?",
        (company_id, email.casefold()),
    ).fetchone()
    return {
        "decision": row[0] if row else "pending",
        "permission_to_send": bool(row[1]) if row else False,
        "note": row[2] if row else "",
        "updated_at": row[3] if row else "",
    }


def _mailbox(conn, email):
    row = conn.execute(
        "SELECT status,provider,checked_at,evidence FROM email_verifications WHERE email=? ORDER BY checked_at DESC,id DESC LIMIT 1",
        (email.casefold(),),
    ).fetchone()
    return {
        "status": row[0] if row else "not_checked",
        "provider": row[1] if row else "",
        "checked_at": row[2] if row else "",
        "evidence": _json(row[3], {}) if row else {},
    }


def contact_decisions(company_id, memory=None):
    memory = memory or intelligence.entity(company_id)
    if not memory:
        return []
    lead = memory["company"]
    candidates = []
    seen = set()
    for contact in memory.get("contacts", []):
        email = _clean(contact.get("email")).casefold()
        if not email or email in seen:
            continue
        seen.add(email)
        candidates.append((email, contact))
    primary = _clean(lead.get("email")).casefold()
    if primary and primary not in seen:
        candidates.insert(0, (primary, {}))
    with engine.connection() as conn:
        rows = []
        for email, contact in candidates:
            evidence = _email_evidence(memory, email)
            review = _review(conn, company_id, email)
            mailbox = _mailbox(conn, email)
            gate = intelligence.preflight(lead, email)
            kind = organizer.classify_email(email)["type"]
            address_verified = evidence["published"] and mailbox["status"] not in {
                "invalid", "spam_trap"
            }
            reviewed_contact = review["decision"] == "confirmed"
            eligible = gate["eligible"] and address_verified and reviewed_contact and review["permission_to_send"]
            reasons = list(gate["issues"])
            if not evidence["published"]:
                reasons.append("address is not published on a retained business source")
            if review["decision"] != "confirmed":
                reasons.append("contact has not been confirmed in review")
            if not review["permission_to_send"]:
                reasons.append("permission to send has not been approved")
            rows.append({
                "email": email,
                "name": contact.get("name", ""),
                "role": contact.get("role", ""),
                "kind": kind,
                "confidence": contact.get("confidence", lead.get("contact_confidence", 0)),
                "address_verified": address_verified,
                "published": evidence["published"],
                "domain_accepts_mail": mailbox["status"] not in {"invalid", "spam_trap"},
                "mailbox_checked": mailbox["status"] != "not_checked",
                "mailbox": mailbox,
                "contact_review": review,
                "send_eligible": eligible,
                "block_reasons": list(dict.fromkeys(reasons)),
                "source_url": evidence["source_url"],
                "source_excerpt": evidence["excerpt"],
                "observed_at": evidence["observed_at"],
            })
    rows.sort(key=lambda item: (
        not item["send_eligible"],
        item["kind"] in {"support", "automated", "invalid"},
        not item["published"],
        -int(item.get("confidence") or 0),
    ))
    for index, item in enumerate(rows):
        item["selected"] = index == 0
        item["is_alternate"] = index > 0
    return rows


def list_leads(filters=None):
    filters = filters or {}
    search = _clean(filters.get("q")).casefold()
    action = _clean(filters.get("action")).casefold()
    decision = _clean(filters.get("decision")).casefold()
    output = []
    for item in intelligence.queue(limit=500):
        if search and search not in " ".join(
            str(item.get(key, "")) for key in ("name", "city", "niche", "action")
        ).casefold():
            continue
        if action and item.get("action", "").casefold() != action:
            continue
        contacts = contact_decisions(item["company_id"])
        selected = contacts[0] if contacts else None
        state = (selected or {}).get("contact_review", {}).get("decision", "pending")
        if decision and state != decision:
            continue
        output.append({
            **item,
            "contact_count": len(contacts),
            "selected_contact": selected,
            "readiness": {
                "verified_address": bool(selected and selected["address_verified"]),
                "reviewed_contact": bool(selected and selected["contact_review"]["decision"] == "confirmed"),
                "permission_to_send": bool(selected and selected["contact_review"]["permission_to_send"]),
                "send_eligible": bool(selected and selected["send_eligible"]),
            },
        })
    return output


def lead_detail(company_id):
    memory = intelligence.entity(company_id)
    if not memory:
        return None
    memory["contact_decisions"] = contact_decisions(company_id, memory)
    company_name = _clean(memory["company"].get("name")).casefold()
    company_site = _clean(memory["company"].get("website")).casefold().rstrip("/")
    with engine.connection() as conn:
        memory["review_decisions"] = [
            dict(zip(("contact_key", "decision", "permission_to_send", "note", "updated_at"), row))
            for row in conn.execute(
                "SELECT contact_key,decision,permission_to_send,note,updated_at FROM lead_review_decisions WHERE company_id=? ORDER BY updated_at DESC",
                (company_id,),
            )
        ]
        memory["linkedin_reviews"] = [
            dict(zip(("id", "candidate_url", "person_name", "role", "current_company", "location", "decision", "evidence_note", "updated_at"), row))
            for row in conn.execute(
                "SELECT id,candidate_url,person_name,role,current_company,location,decision,evidence_note,updated_at FROM linkedin_review_decisions WHERE company_id=? ORDER BY updated_at DESC",
                (company_id,),
            )
        ]
        job_payloads = conn.execute(
            "SELECT payload FROM jobs ORDER BY updated_at DESC LIMIT 100"
        ).fetchall()
    candidates = []
    seen = set()
    for (payload,) in job_payloads:
        job = _json(payload, {})
        for item in job.get("employees", []) if isinstance(job.get("employees"), list) else []:
            if not isinstance(item, dict):
                continue
            same_name = _clean(item.get("company_name")).casefold() == company_name
            same_site = company_site and _clean(item.get("company_website")).casefold().rstrip("/") == company_site
            url = _clean(item.get("employee_linkedin") or item.get("manual_search_url"))
            if not (url and (same_name or same_site)) or url in seen:
                continue
            seen.add(url)
            candidates.append(item)
    memory["linkedin_candidates"] = candidates[:100]
    return memory


def save_contact_review(data):
    company_id = _clean(data.get("company_id"))[:80]
    email = _clean(data.get("email")).casefold()[:320]
    decision = _clean(data.get("decision")).casefold()
    if not intelligence.entity(company_id):
        raise ValueError("Choose a saved business")
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise ValueError("Choose a valid saved email")
    if decision not in DECISIONS:
        raise ValueError("Choose confirm, reject, defer or pending")
    permission = bool(data.get("permission_to_send")) if decision == "confirmed" else False
    with engine.connection() as conn:
        conn.execute(
            "INSERT INTO lead_review_decisions(company_id,contact_key,decision,permission_to_send,note,reviewer,updated_at) VALUES(?,?,?,?,?,'local_user',?) ON CONFLICT(company_id,contact_key) DO UPDATE SET decision=excluded.decision,permission_to_send=excluded.permission_to_send,note=excluded.note,updated_at=excluded.updated_at",
            (company_id, email, decision, int(permission), _clean(data.get("note"))[:500], now()),
        )
    return {"saved": True, "company_id": company_id, "email": email, "decision": decision, "permission_to_send": permission}


def save_linkedin_review(data):
    decision = _clean(data.get("decision")).casefold()
    url = _clean(data.get("candidate_url"))[:1500]
    if decision not in DECISIONS:
        raise ValueError("Choose confirm, reject, defer or pending")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or "linkedin.com" not in (parsed.hostname or "").casefold():
        raise ValueError("Choose a LinkedIn candidate URL")
    item_id = _clean(data.get("id")) or "linkedin-" + uuid.uuid4().hex
    with engine.connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO linkedin_review_decisions(id,company_id,operating_entity_id,candidate_url,person_name,role,current_company,location,decision,evidence_note,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (item_id, _clean(data.get("company_id"))[:80], _clean(data.get("operating_entity_id"))[:80], url, _clean(data.get("person_name"))[:160], _clean(data.get("role"))[:160], _clean(data.get("current_company"))[:200], _clean(data.get("location"))[:200], decision, _clean(data.get("evidence_note"))[:1000], now()),
        )
    return {"saved": True, "id": item_id, "decision": decision}


def save_claim_feedback(data):
    decision = _clean(data.get("decision")).casefold()
    if decision not in {"approved", "corrected", "insufficient_evidence"}:
        raise ValueError("Choose approve, correct or insufficient evidence")
    evidence_id = _clean(data.get("evidence_id"))[:120]
    company_id = _clean(data.get("company_id"))[:80]
    if not evidence_id or not company_id:
        raise ValueError("Choose a saved evidence claim")
    with engine.connection() as conn:
        conn.execute(
            "INSERT INTO claim_feedback(evidence_id,company_id,decision,correction,note,updated_at) VALUES(?,?,?,?,?,?) ON CONFLICT(evidence_id,company_id) DO UPDATE SET decision=excluded.decision,correction=excluded.correction,note=excluded.note,updated_at=excluded.updated_at",
            (evidence_id, company_id, decision, _clean(data.get("correction"))[:1000], _clean(data.get("note"))[:1000], now()),
        )
    return {"saved": True, "evidence_id": evidence_id, "decision": decision}


def split_branch(data):
    """Split one operating branch from a mistaken company merge without losing sources."""
    company_id = _clean(data.get("company_id"))[:80]
    operating_id = _clean(data.get("operating_entity_id"))[:80]
    if not company_id or not operating_id:
        raise ValueError("Choose the operating branch to split")
    stamp = now()
    new_company_id = "company-" + uuid.uuid4().hex[:20]
    with engine.connection() as conn:
        company = conn.execute(
            "SELECT name,domain,phone,address,city,niche,payload,first_seen FROM intelligence_companies WHERE id=?",
            (company_id,),
        ).fetchone()
        branch = conn.execute(
            "SELECT parent_brand_id,locality_key,place_id,ownership_scope,payload,first_seen FROM intelligence_operating_entities WHERE id=? AND company_id=?",
            (operating_id, company_id),
        ).fetchone()
        count = conn.execute(
            "SELECT count(*) FROM intelligence_operating_entities WHERE company_id=?",
            (company_id,),
        ).fetchone()[0]
        if not company or not branch:
            raise ValueError("Saved operating branch was not found")
        if count < 2:
            raise ValueError("This business has only one operating branch; nothing can be split")
        lead = _json(company[6], {})
        branch_payload = _json(branch[4], {})
        lead.update(branch_payload if isinstance(branch_payload, dict) else {})
        lead.update(entity_id=new_company_id, operating_entity_id=operating_id, parent_brand_id=branch[0])
        conn.execute(
            "INSERT INTO intelligence_companies(id,name,domain,phone,address,city,niche,payload,first_seen,last_seen) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (new_company_id, company[0], company[1], company[2], lead.get("address", company[3]), lead.get("city", company[4]), company[5], json.dumps(lead, ensure_ascii=False), company[7], stamp),
        )
        conn.execute(
            "UPDATE intelligence_operating_entities SET company_id=?,last_seen=? WHERE id=?",
            (new_company_id, stamp, operating_id),
        )
        # Move a matching location when possible; otherwise duplicate the best
        # source-backed location so both records remain inspectable.
        locations = conn.execute(
            "SELECT id,address,city,source_url,first_seen,last_seen FROM intelligence_locations WHERE company_id=?",
            (company_id,),
        ).fetchall()
        matching = [row for row in locations if _clean(row[1]).casefold() == _clean(branch[1]).casefold() or _clean(row[2]).casefold() == _clean(branch[1]).casefold()]
        if matching:
            conn.execute("UPDATE intelligence_locations SET company_id=? WHERE id=?", (new_company_id, matching[0][0]))
        elif locations:
            row = locations[0]
            conn.execute(
                "INSERT INTO intelligence_locations(id,company_id,address,city,source_url,first_seen,last_seen) VALUES(?,?,?,?,?,?,?)",
                ("location-" + uuid.uuid4().hex[:20], new_company_id, row[1], row[2], row[3], row[4], row[5]),
            )
        conn.execute(
            "UPDATE intelligence_evidence_claims SET company_id=? WHERE company_id=? AND operating_entity_id=?",
            (new_company_id, company_id, operating_id),
        )
        for field, value, source_url, basis, observed_at, job_id in conn.execute(
            "SELECT field,value,source_url,basis,observed_at,job_id FROM intelligence_evidence WHERE company_id=?",
            (company_id,),
        ):
            conn.execute(
                "INSERT OR IGNORE INTO intelligence_evidence(company_id,job_id,field,value,source_url,basis,observed_at) VALUES(?,?,?,?,?,?,?)",
                (new_company_id, job_id, field, value, source_url, "preserved_from_manual_branch_split:" + basis, observed_at),
            )
        conn.execute(
            "INSERT INTO intelligence_queue(company_id,action,priority,reason,status,updated_at) VALUES(?,?,?,?,?,?)",
            (new_company_id, "verify_public_sources", 95, "Branch was split manually; confirm branch-specific contacts and evidence.", "open", stamp),
        )
    return {"split": True, "company_id": new_company_id, "operating_entity_id": operating_id}


def presets():
    with engine.connection() as conn:
        rows = conn.execute(
            "SELECT id,name,offer,target_role,geography,exclusions,sources,created_at,updated_at FROM search_presets ORDER BY updated_at DESC"
        ).fetchall()
    return [dict(zip(("id", "name", "offer", "target_role", "geography", "exclusions", "sources", "created_at", "updated_at"), row)) for row in rows]


def save_preset(data):
    name = _clean(data.get("name"))[:120]
    if not name:
        raise ValueError("Name this search preset")
    item_id = _clean(data.get("id")) or uuid.uuid4().hex
    stamp = now()
    with engine.connection() as conn:
        existing = conn.execute("SELECT created_at FROM search_presets WHERE id=?", (item_id,)).fetchone()
        conn.execute(
            "INSERT OR REPLACE INTO search_presets(id,name,offer,target_role,geography,exclusions,sources,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (item_id, name, _clean(data.get("offer"))[:500], _clean(data.get("target_role"))[:300], _clean(data.get("geography"))[:500], json.dumps(data.get("exclusions", []), ensure_ascii=False), json.dumps(data.get("sources", []), ensure_ascii=False), existing[0] if existing else stamp, stamp),
        )
    return {"saved": True, "id": item_id}


def followup_tasks():
    with engine.connection() as conn:
        rows = conn.execute(
            "SELECT id,company_id,title,due_date,status,note,created_at,updated_at FROM manual_followup_tasks ORDER BY CASE status WHEN 'open' THEN 0 WHEN 'deferred' THEN 1 ELSE 2 END,COALESCE(NULLIF(due_date,''),'9999-12-31'),updated_at DESC"
        ).fetchall()
    return [dict(zip(("id", "company_id", "title", "due_date", "status", "note", "created_at", "updated_at"), row)) for row in rows]


def save_followup_task(data):
    title = _clean(data.get("title"))[:240]
    status = _clean(data.get("status") or "open").casefold()
    due_date = _clean(data.get("due_date"))[:10]
    if not title:
        raise ValueError("Enter a follow-up task")
    if status not in {"open", "deferred", "done"}:
        raise ValueError("Choose open, deferred or done")
    if due_date and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", due_date):
        raise ValueError("Choose a valid due date")
    item_id = _clean(data.get("id")) or "task-" + uuid.uuid4().hex
    stamp = now()
    with engine.connection() as conn:
        existing = conn.execute("SELECT created_at FROM manual_followup_tasks WHERE id=?", (item_id,)).fetchone()
        conn.execute(
            "INSERT OR REPLACE INTO manual_followup_tasks(id,company_id,title,due_date,status,note,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
            (item_id, _clean(data.get("company_id"))[:80], title, due_date, status, _clean(data.get("note"))[:1000], existing[0] if existing else stamp, stamp),
        )
    return {"saved": True, "id": item_id}
