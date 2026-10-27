"""Deterministic outreach-sequence state transitions and reply triage."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone

import engine
from contacts import now

TERMINAL = {"positive_reply", "meeting_booked", "customer_won", "unsubscribe", "unsubscribed", "hard_bounce", "bounced", "wrong_contact"}


def create(sequence_id, steps):
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,80}", sequence_id or ""):
        raise ValueError("Choose a valid sequence name")
    if not isinstance(steps, list) or not 1 <= len(steps) <= 5:
        raise ValueError("Choose between one and five sequence steps")
    with engine.connection() as conn:
        conn.execute("DELETE FROM outreach_sequence_steps WHERE sequence_id=?", (sequence_id,))
        previous = -1
        for index, step in enumerate(steps, 1):
            delay = int(step.get("delay_days", 0))
            if delay < previous or not 0 <= delay <= 60:
                raise ValueError("Sequence delays must increase and stay within 60 days")
            subject, body = str(step.get("subject", "")).strip(), str(step.get("body", "")).strip()
            if not subject or not body:
                raise ValueError("Every sequence step needs a subject and body")
            conn.execute("INSERT INTO outreach_sequence_steps VALUES(?,?,?,?,?,?)", (sequence_id, index, delay, subject[:300], body[:8000], "no_reply"))
            previous = delay
    return sequence_id


def enroll(sequence_id, campaign_id, company_id, operating_entity_id, email):
    state_id = "seq-" + hashlib.sha256(f"{sequence_id}:{company_id}:{email}".encode()).hexdigest()[:24]
    stamp = now()
    with engine.connection() as conn:
        first = conn.execute("SELECT delay_days FROM outreach_sequence_steps WHERE sequence_id=? ORDER BY step_number LIMIT 1", (sequence_id,)).fetchone()
        if not first:
            raise ValueError("Sequence has no steps")
        due = (datetime.now(timezone.utc) + timedelta(days=first[0])).isoformat()
        conn.execute("INSERT OR REPLACE INTO outreach_sequence_states VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (state_id, sequence_id, campaign_id, company_id, operating_entity_id, email.casefold(), 0, "scheduled", due, "", "", "{}", stamp, stamp))
    return state_id


def apply_outcome(company_id, email, outcome, payload=None):
    outcome = str(outcome or "").casefold()
    with engine.connection() as conn:
        rows = conn.execute("SELECT id,current_step FROM outreach_sequence_states WHERE (company_id=? OR email=?) AND state IN ('scheduled','active','paused_ooo')", (company_id, email.casefold())).fetchall()
        for state_id, step in rows:
            state = "halted" if outcome in TERMINAL or outcome in {"replied", "referral"} else "paused_ooo" if outcome == "out_of_office" else "active"
            pause_until = str((payload or {}).get("return_date", "")) if state == "paused_ooo" else ""
            conn.execute("UPDATE outreach_sequence_states SET state=?,last_outcome=?,pause_until=?,updated_at=? WHERE id=?", (state, outcome, pause_until, now(), state_id))
            conn.execute("INSERT INTO outreach_reply_events(sequence_state_id,company_id,email,event_type,return_date,referred_name,referred_email,source,created_at,payload) VALUES(?,?,?,?,?,?,?,?,?,?)", (state_id, company_id, email.casefold(), outcome, pause_until, str((payload or {}).get("referred_name", ""))[:160], str((payload or {}).get("referred_email", ""))[:320], str((payload or {}).get("source", "manual"))[:120], now(), json.dumps(payload or {}, ensure_ascii=False)))
    return len(rows)


def transition_table():
    return [
        {"from": "verification", "event": "verified contact", "to": "decision_maker_research or outreach"},
        {"from": "contact_discovery", "event": "supported contact found", "to": "decision_maker_research"},
        {"from": "decision_maker_research", "event": "eligible contact", "to": "outreach"},
        {"from": "manual_browser_review", "event": "evidence captured", "to": "verification"},
        {"from": "outreach", "event": "reply", "to": "reply_follow_up"},
        {"from": "outreach", "event": "unsubscribe/hard bounce", "to": "suppression"},
        {"from": "outreach", "event": "out of office", "to": "paused_ooo"},
        {"from": "reply_follow_up", "event": "meeting/customer", "to": "customer"},
    ]
