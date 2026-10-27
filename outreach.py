"""Durable, approval-gated one-to-one outreach through the official Zoho Mail API."""

from __future__ import annotations

import json
import os
import random
import re
import secrets
import threading
import time
import uuid
from collections import Counter
from dataclasses import fields
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import keyring

import engine
import leadfinder as lf
import local_ai
import intelligence
from contacts import now

LOCK = threading.RLock()
STOPS: dict[str, threading.Event] = {}
AI_JOBS: dict[str, threading.Event] = {}
MODEL_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,119}")
EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
VARIABLES = {"business_name", "niche", "city", "website", "ai_summary", "unsubscribe"}
DAILY_SEND_CAP = 50


def _recommended_email(row, address):
    try:
        quality = json.loads(row.get("email_quality") or "{}")
    except (ValueError, TypeError):
        return True
    recommended = quality.get("recommended")
    if not isinstance(recommended, list):
        return True
    return any(
        isinstance(item, dict)
        and str(item.get("email", "")).casefold() == address.casefold()
        and item.get("recommended") is True
        for item in recommended
    )
KEYRING_SERVICE = "LeadFinder-Zoho-OAuth"
KEYRING_USER = "local-dashboard"
OAUTH_STATES: dict[str, float] = {}
VALID_DCS = {"com", "eu", "in", "com.au", "jp", "ca", "sa"}


def _config():
    saved = {}
    try:
        raw = keyring.get_password(KEYRING_SERVICE, KEYRING_USER)
        saved = json.loads(raw) if raw else {}
    except Exception:
        saved = {}
    mapping = {
        "client_id": "ZOHO_CLIENT_ID", "client_secret": "ZOHO_CLIENT_SECRET",
        "refresh_token": "ZOHO_REFRESH_TOKEN", "account_id": "ZOHO_ACCOUNT_ID",
        "from_address": "ZOHO_FROM_ADDRESS", "dc": "ZOHO_DC",
    }
    for key, env in mapping.items():
        if os.getenv(env):
            saved[key] = os.environ[env]
    saved.setdefault("dc", "com")
    return saved


def _save_config(config):
    keyring.set_password(KEYRING_SERVICE, KEYRING_USER, json.dumps(config))


def save_zoho_client(data):
    client_id = str(data.get("client_id", "")).strip()
    client_secret = str(data.get("client_secret", "")).strip()
    dc = str(data.get("dc", "com")).strip().lower()
    if not (8 <= len(client_id) <= 200 and 8 <= len(client_secret) <= 300 and dc in VALID_DCS):
        raise ValueError("Enter the Zoho client ID, client secret and correct data center")
    current = _config()
    current.update(client_id=client_id, client_secret=client_secret, dc=dc)
    _save_config(current)


def oauth_authorize_url(callback):
    config = _config()
    if not config.get("client_id") or not config.get("client_secret"):
        raise ValueError("Save your Zoho client ID and client secret first")
    state = secrets.token_urlsafe(24)
    OAUTH_STATES[state] = time.time()
    query = urlencode({
        "scope": "ZohoMail.accounts.READ,ZohoMail.messages.CREATE",
        "client_id": config["client_id"], "response_type": "code",
        "access_type": "offline", "prompt": "consent", "redirect_uri": callback,
        "state": state,
    })
    return f"https://accounts.zoho.{config['dc']}/oauth/v2/auth?{query}"


def oauth_callback(code, state, callback):
    created = OAUTH_STATES.pop(state, None)
    if not created or time.time() - created > 600:
        raise ValueError("Zoho connection request expired; start again")
    config = _config()
    token_body = urlencode({"code": code, "client_id": config["client_id"], "client_secret": config["client_secret"], "redirect_uri": callback, "grant_type": "authorization_code"}).encode()
    with urlopen(Request(f"https://accounts.zoho.{config['dc']}/oauth/v2/token", data=token_body, method="POST"), timeout=25) as response:
        token_data = json.load(response)
    access = token_data.get("access_token")
    refresh = token_data.get("refresh_token") or config.get("refresh_token")
    if not access or not refresh:
        raise ValueError("Zoho did not return the required access and refresh tokens")
    request = Request(f"https://mail.zoho.{config['dc']}/api/accounts", headers={"Authorization": "Zoho-oauthtoken " + access, "Accept": "application/json"})
    with urlopen(request, timeout=25) as response:
        account_data = json.load(response)
    accounts = account_data.get("data") or []
    if isinstance(accounts, dict):
        accounts = [accounts]
    account = next((item for item in accounts if item.get("accountId")), None)
    if not account:
        raise ValueError("Zoho Mail account details were not returned")
    config.update(
        refresh_token=refresh,
        account_id=str(account.get("accountId")),
        from_address=account.get("primaryEmailAddress") or account.get("emailAddress") or account.get("mailId") or "",
    )
    if not EMAIL.fullmatch(config["from_address"]):
        raise ValueError("Zoho did not return a usable sender address")
    _save_config(config)
    return config["from_address"]


def disconnect_zoho():
    try:
        keyring.delete_password(KEYRING_SERVICE, KEYRING_USER)
    except keyring.errors.PasswordDeleteError:
        pass


def init(recover=True):
    if not recover:
        return
    with engine.connection() as conn:
        rows = conn.execute(
            "SELECT id,payload FROM outreach_campaigns WHERE status IN ('running','drafting')"
        ).fetchall()
        for campaign_id, payload in rows:
            item = json.loads(payload)
            if item.get("status") == "drafting":
                item.update(
                    status="paused",
                    message="AI drafting paused after a dashboard restart. Continue it, or start a new campaign.",
                )
            else:
                item.update(status="paused", message="Paused safely after dashboard restart")
            conn.execute(
                "UPDATE outreach_campaigns SET status=?,updated_at=?,payload=? WHERE id=?",
                (item["status"], now(), json.dumps(item), campaign_id),
            )


def provider_status():
    config = _config()
    required = {
        "client_id": config.get("client_id", ""),
        "client_secret": config.get("client_secret", ""),
        "refresh_token": config.get("refresh_token", ""),
        "account_id": config.get("account_id", ""),
        "from_address": config.get("from_address", ""),
    }
    missing = [key for key, value in required.items() if not value]
    return {
        "connected": not missing,
        "from_address": required["from_address"],
        "missing": missing,
        "client_saved": bool(required["client_id"] and required["client_secret"]),
        "dc": config.get("dc", "com"),
        "message": "Zoho OAuth is connected through Windows Credential Manager." if not missing else "Zoho is not connected. Use Connect Zoho in this dashboard.",
    }


def _template_row(row):
    return dict(zip(("id", "name", "niche", "subject", "body", "created_at", "updated_at"), row))


def templates():
    with engine.connection() as conn:
        return [_template_row(row) for row in conn.execute("SELECT id,name,niche,subject,body,created_at,updated_at FROM outreach_templates ORDER BY niche,name")]


def save_template(data):
    if not isinstance(data, dict):
        raise ValueError("Enter a valid template")
    name = str(data.get("name", "")).strip()
    niche = str(data.get("niche", "")).strip()
    subject = str(data.get("subject", "")).strip()
    body = str(data.get("body", "")).strip()
    if not (2 <= len(name) <= 80 and 2 <= len(niche) <= 120 and 2 <= len(subject) <= 180 and 10 <= len(body) <= 5000):
        raise ValueError("Complete the template name, niche, subject and body within the shown limits")
    unknown = set(re.findall(r"{{\s*([a-z_]+)\s*}}", subject + body)) - VARIABLES
    if unknown:
        raise ValueError("Unknown template variable(s): " + ", ".join(sorted(unknown)))
    template_id = data.get("id") if re.fullmatch(r"[a-f0-9]{32}", str(data.get("id", ""))) else uuid.uuid4().hex
    stamp = now()
    with engine.connection() as conn:
        old = conn.execute("SELECT created_at FROM outreach_templates WHERE id=?", (template_id,)).fetchone()
        conn.execute(
            "INSERT INTO outreach_templates(id,name,niche,subject,body,created_at,updated_at) VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,niche=excluded.niche,subject=excluded.subject,body=excluded.body,updated_at=excluded.updated_at",
            (template_id, name, niche, subject, body, old[0] if old else stamp, stamp),
        )
    return template_id


def _campaign(campaign_id):
    if not re.fullmatch(r"[a-f0-9]{32}", str(campaign_id)):
        return None
    with engine.connection() as conn:
        row = conn.execute("SELECT payload FROM outreach_campaigns WHERE id=?", (campaign_id,)).fetchone()
        if not row:
            return None
        campaign = json.loads(row[0])
        campaign["messages"] = [dict(zip(("id", "recipient", "lead_name", "status", "subject", "body", "attempts", "provider_id", "error", "sent_at"), item)) for item in conn.execute("SELECT id,recipient,lead_name,status,subject,body,attempts,provider_id,error,sent_at FROM outreach_messages WHERE campaign_id=? ORDER BY id", (campaign_id,))]
    counts = Counter(item["status"] for item in campaign["messages"])
    campaign.update(
        total=len(campaign["messages"]),
        sent=counts.get("sent", 0),
        ready=counts.get("draft", 0) + counts.get("queued", 0),
        drafting=counts.get("drafting", 0),
        draft_failed=counts.get("draft_failed", 0),
        failed=counts.get("failed", 0),
    )
    campaign["remaining"] = campaign["ready"] + campaign["drafting"]
    campaign["ai_drafted"] = campaign["ready"] + campaign["sent"] + campaign["failed"]
    campaign.setdefault("mode", "template")
    campaign.setdefault("ai_model", "")
    campaign.setdefault("ai_total", campaign["total"])
    campaign.setdefault("template_ids", [campaign.get("template_id")] if campaign.get("template_id") else [])
    campaign.setdefault("template_names", [campaign.get("template_name")] if campaign.get("template_name") else [])
    campaign.setdefault("message_sources", {})
    campaign["experiment_results"] = intelligence.experiment_results(campaign_id)
    return campaign



def campaigns():
    with engine.connection() as conn:
        ids = [row[0] for row in conn.execute("SELECT id FROM outreach_campaigns ORDER BY created_at DESC LIMIT 50")]
    return [_campaign(item) for item in ids]


def _render(text, row, niche, from_address):
    analysis = {}
    try:
        analysis = json.loads(row.get("ai_analysis") or "{}")
    except ValueError:
        pass
    values = {
        "business_name": row.get("name", "there"),
        "niche": niche,
        "city": row.get("city") or row.get("search_location", ""),
        "website": row.get("website", ""),
        "ai_summary": analysis.get("summary", "") if analysis.get("status") == "complete" else "",
        "unsubscribe": f"mailto:{from_address}?subject=Unsubscribe",
    }
    return re.sub(r"{{\s*([a-z_]+)\s*}}", lambda m: str(values.get(m.group(1), "")), text)


def create_campaign(data):
    if not isinstance(data, dict):
        raise ValueError("Choose valid campaign settings")
    job_id = str(data.get("job_id", ""))
    mode = str(data.get("mode", "template"))
    if mode not in ("template", "ai"):
        raise ValueError("Choose a valid message source")
    requested = data.get("template_ids")
    if not isinstance(requested, list):
        requested = [data.get("template_id", "")]
    template_ids = []
    for value in requested:
        value = str(value).strip()
        if value and value not in template_ids:
            template_ids.append(value)
    if len(template_ids) > 20:
        raise ValueError("Choose at most 20 templates for one campaign")
    job = engine.get_job(job_id, events=False)
    if not job or job.get("status") in ("queued", "running", "waiting"):
        raise ValueError("Choose a finished search")
    with engine.connection() as conn:
        placeholders = ",".join("?" for _ in template_ids)
        rows = (
            conn.execute(
                f"SELECT id,name,niche,subject,body,created_at,updated_at FROM outreach_templates WHERE id IN ({placeholders})",
                template_ids,
            ).fetchall()
            if template_ids
            else []
        )
        suppressions = {row[0].casefold() for row in conn.execute("SELECT email FROM outreach_suppressions")}
    by_id = {row[0]: _template_row(row) for row in rows}
    templates = [by_id[item] for item in template_ids if item in by_id]
    ai_model = str(data.get("ai_model", "")).strip()
    ai_offer = str(data.get("offer", "")).strip()
    if mode == "template" and not templates:
        raise ValueError("Choose at least one saved template")
    if mode == "ai":
        if not MODEL_NAME.fullmatch(ai_model):
            raise ValueError("Choose an installed local model for AI drafting")
        if not 2 <= len(ai_offer) <= 800:
            raise ValueError("Describe your offer in 2 to 800 characters so the local model can draft")
    maximum = data.get("maximum", 20)
    if isinstance(maximum, bool) or not isinstance(maximum, int) or not 1 <= maximum <= 20:
        raise ValueError("A campaign can contain 1 to 20 designated recipients")
    scope = data.get("scope", "matches")
    if scope not in ("matches", "all"):
        raise ValueError("Choose a valid recipient scope")
    selected = []
    seen = set()
    preflight_excluded = []
    for index, row in enumerate(job.get("rows", [])):
        address = str(row.get("email", "")).strip().casefold()
        if not EMAIL.fullmatch(address) or not _recommended_email(row, address) or address in suppressions or address in seen:
            continue
        if scope == "matches" and row.get("match_status") == "candidate":
            continue
        gate = intelligence.preflight(row, address, job_id)
        if not gate["eligible"]:
            preflight_excluded.append({"name": row.get("name", ""), "email": address, "issues": gate["issues"]})
            continue
        seen.add(address)
        selected.append((row, address, index))
        if len(selected) >= maximum:
            break
    if not selected:
        raise ValueError("No eligible, unsuppressed email recipients were found in this search")
    campaign_id, stamp = uuid.uuid4().hex, now()
    niche = job.get("params", {}).get("niche", templates[0]["niche"] if templates else "")
    template_names = [item["name"] for item in templates]
    if mode == "ai":
        source_name = f"Local AI · {ai_model}"
    else:
        source_name = template_names[0] if len(template_names) == 1 else f"{len(template_names)} templates"
    status = "drafting" if mode == "ai" else "draft"
    campaign = {
        "id": campaign_id, "created_at": stamp, "updated_at": stamp,
        "status": status,
        "message": (
            f"Drafting {len(selected)} message{'s' if len(selected) != 1 else ''} with {ai_model}"
            if mode == "ai"
            else f"{len(selected)} message{'s' if len(selected) != 1 else ''} prepared from {len(templates)} template{'s' if len(templates) != 1 else ''}. Review each one, then approve."
        ),
        "job_id": job_id, "mode": mode,
        "template_id": template_ids[0] if len(template_ids) == 1 else "",
        "template_ids": template_ids,
        "template_names": template_names,
        "template_name": source_name,
        "message_sources": {}, "lead_entities": {}, "lead_identities": {},
        "preflight_excluded": preflight_excluded,
        "experiment": {"method": "stable_hash_assignment", "variants": len(templates) if mode == "template" else 1},
        "niche": niche,
        "ai_model": ai_model, "ai_offer": ai_offer,
        "ai_total": len(selected), "ai_drafted": 0,
        "ai_rows": {},
        "total": len(selected), "sent": 0, "failed": 0, "remaining": len(selected),
        "delay_min_seconds": 60, "delay_max_seconds": 120,
        "daily_send_cap": DAILY_SEND_CAP,
    }
    sender = provider_status().get("from_address", "")
    variant_positions = [
        intelligence.variant_index(row, campaign_id, len(templates), position)
        if mode == "template"
        else 0
        for position, (row, _address, _index) in enumerate(selected)
    ]
    with engine.connection() as conn:
        conn.execute("INSERT INTO outreach_campaigns(id,created_at,updated_at,status,payload) VALUES(?,?,?,?,?)", (campaign_id, stamp, stamp, status, json.dumps(campaign)))
        for position, (row, address, index) in enumerate(selected):
            if mode == "ai":
                subject, body, message_status = "", "", "drafting"
            else:
                template = templates[variant_positions[position]]
                subject = _render(template["subject"], row, niche, sender)
                body = _render(template["body"], row, niche, sender)
                message_status = "draft"
            cursor = conn.execute("INSERT INTO outreach_messages(campaign_id,recipient,lead_name,status,subject,body) VALUES(?,?,?,?,?,?)", (campaign_id, address, row.get("name", ""), message_status, subject, body))
            if mode == "ai":
                campaign["ai_rows"][str(cursor.lastrowid)] = index
            else:
                campaign["message_sources"][str(cursor.lastrowid)] = template["name"]
            campaign["lead_entities"][str(cursor.lastrowid)] = row.get("entity_id", "")
            campaign["lead_identities"][str(cursor.lastrowid)] = {key: row.get(key, "") for key in ("entity_id", "parent_brand_id", "operating_entity_id", "city", "address")}
        if mode == "ai" or campaign["message_sources"]:
            conn.execute("UPDATE outreach_campaigns SET payload=? WHERE id=?", (json.dumps(campaign), campaign_id))
    if mode == "ai":
        _start_drafting(campaign_id)
    return campaign_id


def _update_message(message_id, status, subject=None, body=None, error=""):
    with engine.connection() as conn:
        if subject is None:
            conn.execute("UPDATE outreach_messages SET status=?,error=? WHERE id=?", (status, error[:500], message_id))
        else:
            conn.execute("UPDATE outreach_messages SET status=?,subject=?,body=?,error=? WHERE id=?", (status, subject, body, error[:500], message_id))


def _ai_message(row, model, offer):
    """Return (subject, body, error) for one designated recipient."""
    try:
        saved = json.loads(row.get("ai_draft") or "{}")
    except ValueError:
        saved = {}
    if (
        saved.get("status") == "ready_for_review"
        and saved.get("model") == model
        and saved.get("subject")
        and saved.get("body")
    ):
        return saved["subject"], saved["body"], ""
    allowed = {field.name for field in fields(lf.Lead)}
    lead = lf.Lead(**{key: value for key, value in row.items() if key in allowed})
    try:
        result = local_ai.review(lead, model, offer)
    except (ValueError, RuntimeError) as exc:
        return "", "", str(exc)
    draft = result.get("draft", {}) if isinstance(result, dict) else {}
    if draft.get("status") == "ready_for_review" and draft.get("subject") and draft.get("body"):
        return draft["subject"], draft["body"], ""
    reasons = {
        "insufficient_evidence": "No saved website evidence; recheck the website, then retry.",
        "invalid_output": "The model's draft was not usable; retry.",
        "needs_offer": "Describe your offer so the model can draft.",
        "error": result.get("analysis", {}).get("summary", "") if isinstance(result, dict) else "",
        "cancelled": "Drafting was cancelled.",
    }
    status = draft.get("status", "error")
    return "", "", str(reasons.get(status) or f"Local AI returned '{status}'; retry or edit the message manually.")[:400]


def _start_drafting(campaign_id):
    with LOCK:
        campaign = _campaign(campaign_id)
        if not campaign:
            raise ValueError("Campaign not found")
        if campaign.get("mode") != "ai":
            raise ValueError("Only local-AI campaigns need drafting")
        pending = [m for m in campaign["messages"] if m["status"] in ("drafting", "draft_failed")]
        if not pending:
            raise ValueError("Every message in this campaign already has a draft")
        if campaign_id in AI_JOBS:
            raise ValueError("Local AI is already drafting this campaign")
        event = threading.Event()
        AI_JOBS[campaign_id] = event
        campaign.update(
            status="drafting",
            message=f"Drafting {len(pending)} of {campaign['total']} messages with {campaign['ai_model']}",
        )
    _save_campaign(campaign)
    threading.Thread(target=_ai_worker, args=(campaign_id, event), daemon=True).start()


def resume_ai(campaign_id):
    campaign = _campaign(campaign_id)
    if not campaign or campaign.get("mode") != "ai":
        raise ValueError("Choose a local-AI campaign")
    if campaign["status"] not in ("draft", "paused", "drafting"):
        raise ValueError("This campaign is no longer drafting")
    return _start_drafting(campaign_id)


def _ai_worker(campaign_id, stop):
    model = ""
    try:
        campaign = _campaign(campaign_id)
        if not campaign:
            return
        model = campaign.get("ai_model", "")
        offer = campaign.get("ai_offer", "")
        job = engine.get_job(campaign.get("job_id", ""), events=False) or {}
        rows = job.get("rows", [])
        for message in campaign["messages"]:
            if stop.is_set():
                break
            if message["status"] not in ("drafting", "draft_failed"):
                continue
            index = campaign.get("ai_rows", {}).get(str(message["id"]))
            row = rows[index] if isinstance(index, int) and 0 <= index < len(rows) else None
            if not row or str(row.get("email", "")).strip().casefold() != message["recipient"].casefold():
                _update_message(message["id"], "draft_failed", error="The saved lead changed; recreate this campaign.")
            else:
                subject, body, error = _ai_message(row, model, offer)
                if subject and body:
                    _update_message(message["id"], "draft", subject=subject, body=body)
                else:
                    _update_message(message["id"], "draft_failed", error=error or "Drafting failed")
            campaign = _campaign(campaign_id)
            if not campaign:
                return
            campaign["status"] = "drafting"
            campaign["message"] = (
                f"Drafted {campaign['ai_drafted']} of {campaign['ai_total']} with {model}"
                + (f" · {campaign['draft_failed']} need attention" if campaign["draft_failed"] else "")
            )
            _save_campaign(campaign)
    except Exception as exc:  # keep partial drafts; never leave the campaign stuck
        campaign = _campaign(campaign_id)
        if campaign:
            campaign.update(status="paused", message=f"Local AI drafting stopped: {str(exc)[:200]}")
            _save_campaign(campaign)
        return
    finally:
        with LOCK:
            AI_JOBS.pop(campaign_id, None)
    campaign = _campaign(campaign_id)
    if not campaign:
        return
    if stop.is_set() and campaign["drafting"]:
        campaign.update(
            status="paused",
            message=f"AI drafting paused. {campaign['ai_drafted']} of {campaign['ai_total']} drafted; continue when ready.",
        )
    elif campaign["drafting"]:
        campaign.update(status="paused", message="AI drafting stopped early; continue when ready.")
    elif not campaign["ai_drafted"]:
        campaign.update(
            status="draft",
            message="No message could be drafted. Add saved website evidence, check the local model, then retry.",
        )
    else:
        note = f"{campaign['ai_drafted']} AI drafts ready for review with {model}."
        if campaign["draft_failed"]:
            note += f" {campaign['draft_failed']} message(s) need attention and will not be sent."
        campaign.update(status="draft", message=note)
    _save_campaign(campaign)



def suppress(email, reason="Manual suppression"):
    email = str(email).strip().casefold()
    if not EMAIL.fullmatch(email):
        raise ValueError("Enter a valid email address")
    with engine.connection() as conn:
        conn.execute("INSERT INTO outreach_suppressions(email,reason,created_at) VALUES(?,?,?) ON CONFLICT(email) DO UPDATE SET reason=excluded.reason", (email, str(reason)[:300], now()))
    intelligence.add_dnc("email", email, reason)


def _save_campaign(campaign):
    campaign["updated_at"] = now()
    payload = {key: value for key, value in campaign.items() if key != "messages"}
    with engine.connection() as conn:
        conn.execute("UPDATE outreach_campaigns SET status=?,updated_at=?,payload=? WHERE id=?", (campaign["status"], campaign["updated_at"], json.dumps(payload), campaign["id"]))


def _zoho_send(recipient, subject, body):
    status = provider_status()
    if not status["connected"]:
        raise RuntimeError(status["message"])
    config = _config()
    dc = config.get("dc", "com")
    accounts_host = "accounts.zoho." + dc
    mail_host = "mail.zoho." + dc
    token_body = urlencode({"refresh_token": config["refresh_token"], "client_id": config["client_id"], "client_secret": config["client_secret"], "grant_type": "refresh_token"}).encode()
    with urlopen(Request(f"https://{accounts_host}/oauth/v2/token", data=token_body, method="POST"), timeout=20) as response:
        token = json.load(response).get("access_token")
    if not token:
        raise RuntimeError("Zoho did not return an access token")
    payload = json.dumps({"fromAddress": config["from_address"], "toAddress": recipient, "subject": subject, "content": body, "mailFormat": "plaintext", "askReceipt": "no"}).encode()
    request = Request(f"https://{mail_host}/api/accounts/{config['account_id']}/messages", data=payload, method="POST", headers={"Authorization": "Zoho-oauthtoken " + token, "Accept": "application/json", "Content-Type": "application/json"})
    with urlopen(request, timeout=30) as response:
        result = json.load(response)
    return str(result.get("data", {}).get("messageId") or result.get("data", {}).get("mailId") or "accepted")


def start(campaign_id, confirmation=False):
    if confirmation is not True:
        raise ValueError("Review the campaign and explicitly confirm sending")
    if not provider_status()["connected"]:
        raise ValueError(provider_status()["message"])
    with LOCK:
        if len(STOPS) >= 5:
            raise ValueError("Five campaigns are already sending. Pause one before starting another.")
        campaign = _campaign(campaign_id)
        if not campaign or campaign["status"] not in ("draft", "paused"):
            raise ValueError("Choose a draft or paused campaign")
        if campaign["drafting"]:
            raise ValueError("Local AI is still drafting this campaign. Finish drafting before approving.")
        if not campaign["ready"]:
            raise ValueError("No reviewed messages are ready to send in this campaign")
        utc_day = now()[:10]
        with engine.connection() as conn:
            sent_today = conn.execute(
                "SELECT count(*) FROM outreach_messages WHERE status='sent' AND substr(sent_at,1,10)=?",
                (utc_day,),
            ).fetchone()[0]
        if campaign["ready"] > max(0, DAILY_SEND_CAP - sent_today):
            raise ValueError(
                f"Daily safety cap is {DAILY_SEND_CAP}. {sent_today} messages were already sent today; reduce or postpone this campaign."
            )
        blocked = []
        for message in campaign["messages"]:
            if message["status"] not in ("draft", "queued"):
                continue
            gate = intelligence.preflight(
                campaign.get("lead_identities", {}).get(str(message["id"]), {"entity_id": campaign.get("lead_entities", {}).get(str(message["id"]), "")}),
                message["recipient"],
                campaign.get("job_id", ""),
                campaign_id,
            )
            if not gate["eligible"]:
                blocked.append(f"{message['recipient']}: {', '.join(gate['issues'])}")
        if blocked:
            raise ValueError("Safety gate blocked this campaign: " + " | ".join(blocked[:5]))
        content = Counter(
            (message.get("subject", "").strip().casefold(), message.get("body", "").strip().casefold())
            for message in campaign["messages"]
            if message["status"] in ("draft", "queued")
        )
        campaign["safety_review"] = {
            "checked_at": now(),
            "sent_today": sent_today,
            "daily_cap": DAILY_SEND_CAP,
            "duplicate_message_groups": sum(count > 1 for count in content.values()),
            "approved_recipients": campaign["ready"],
        }
        if campaign_id in STOPS:
            raise ValueError("This campaign is already sending")
        stop = threading.Event()
        STOPS[campaign_id] = stop
    campaign.update(status="running", message=f"Sending {campaign['ready']} approved one-to-one messages")
    _save_campaign(campaign)
    # Return control to the UI before network sending begins. This also makes
    # two explicitly approved campaigns register atomically as active.
    worker = threading.Timer(0.01, _run, args=(campaign, stop))
    worker.daemon = True
    worker.start()


def pause(campaign_id):
    stopped = False
    with LOCK:
        for jobs in (STOPS, AI_JOBS):
            stop = jobs.get(campaign_id)
            if stop:
                stop.set()
                stopped = True
    return stopped


def _run(campaign, stop):
    try:
        while not stop.is_set():
            with engine.connection() as conn:
                row = conn.execute("SELECT id,recipient,subject,body FROM outreach_messages WHERE campaign_id=? AND status IN ('draft','queued') ORDER BY id LIMIT 1", (campaign["id"],)).fetchone()
            if not row:
                campaign.update(status="complete", message="Approved outreach campaign complete")
                break
            message_id, recipient, subject, body = row
            try:
                provider_id = _zoho_send(recipient, subject, body)
                with engine.connection() as conn:
                    conn.execute("UPDATE outreach_messages SET status='sent',attempts=attempts+1,provider_id=?,sent_at=?,error='' WHERE id=?", (provider_id, now(), message_id))
                intelligence.record_outcome({"company_id": campaign.get("lead_entities", {}).get(str(message_id), ""), "email": recipient, "campaign_id": campaign["id"], "outcome": "sent", "note": "Accepted by Zoho Mail API"})
            except (HTTPError, URLError, OSError, RuntimeError) as exc:
                with engine.connection() as conn:
                    conn.execute("UPDATE outreach_messages SET status='failed',attempts=attempts+1,error=? WHERE id=?", (str(exc)[:500], message_id))
                intelligence.record_outcome({"company_id": campaign.get("lead_entities", {}).get(str(message_id), ""), "email": recipient, "campaign_id": campaign["id"], "outcome": "failed", "note": str(exc)[:300]})
                campaign.update(status="paused", message="Paused after a Zoho/API error; inspect the failed message before resuming")
                break
            current = _campaign(campaign["id"])
            campaign["sent"] = sum(m["status"] == "sent" for m in current["messages"])
            campaign["failed"] = sum(m["status"] == "failed" for m in current["messages"])
            campaign["remaining"] = campaign["total"] - campaign["sent"] - campaign["failed"]
            campaign["message"] = f"Sent {campaign['sent']} of {campaign['total']} approved messages"
            _save_campaign(campaign)
            stop.wait(random.uniform(campaign["delay_min_seconds"], campaign["delay_max_seconds"]))
        if stop.is_set():
            campaign.update(status="paused", message="Paused; unsent messages remain queued")
    finally:
        _save_campaign(campaign)
        with LOCK:
            STOPS.pop(campaign["id"], None)
