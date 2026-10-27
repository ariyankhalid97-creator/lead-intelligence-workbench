"""Secure optional provider connections and Google Sheets synchronization."""

from __future__ import annotations

import json
import re
import secrets
import time
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

import keyring

KEYRING_SERVICE = "LeadExtractor-Optional-Connections-v1"
GOOGLE_SCOPE = "https://www.googleapis.com/auth/drive.file"
OAUTH_STATES: dict[str, float] = {}
PROVIDERS = {
    "google_sheets": {
        "name": "Google Sheets",
        "auth": "Google OAuth 2.0",
        "description": "Create and update only spreadsheets opened or created through Lead Extractor.",
        "automatic": False,
    },
    "google_places": {
        "name": "Google Places API",
        "auth": "Restricted API key",
        "description": "Optional billing-enabled Places Text Search source. Disabled until you enable it.",
        "automatic": True,
    },
    "apollo": {
        "name": "Apollo",
        "auth": "Personal API key",
        "description": "Optional company/contact provider. OAuth is reserved for approved Apollo partners.",
        "automatic": False,
    },
    "apify": {
        "name": "Apify",
        "auth": "Bearer API token",
        "description": "Connect an Apify account. Actor selection remains explicit to prevent accidental spend.",
        "automatic": False,
    },
    "outscraper": {
        "name": "Outscraper",
        "auth": "API key",
        "description": "Optional licensed data provider. Searches remain disabled until explicitly enabled.",
        "automatic": False,
    },
}
SOURCE_SEEDS = (
    ("us_npi", "US NPI Registry", "US", "official_api", "healthcare", "free"),
    ("sg_acra", "ACRA open data", "SG", "open_dataset", "general", "free"),
    ("au_abn", "ABN Lookup", "AU", "official_api", "general", "registration"),
    ("my_data_gov", "Malaysia Open API", "MY", "open_api", "dataset_specific", "free"),
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read(provider: str) -> dict:
    if provider not in PROVIDERS:
        raise ValueError("Choose a supported connection")
    try:
        raw = keyring.get_password(KEYRING_SERVICE, provider)
        value = json.loads(raw) if raw else {}
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _write(provider: str, value: dict) -> None:
    try:
        keyring.set_password(KEYRING_SERVICE, provider, json.dumps(value))
    except Exception as exc:
        raise ValueError(
            "Windows Credential Manager could not save this connection"
        ) from exc


def _hint(value: str) -> str:
    value = str(value or "")
    if len(value) < 8:
        return "saved" if value else ""
    return f"••••{value[-4:]}"


def init_source_catalog(conn) -> None:
    for source_id, name, country, connector, niches, access in SOURCE_SEEDS:
        conn.execute(
            """INSERT INTO source_catalog
               (id,name,country,connector_type,niches,access_class,enabled,status,parser_version,last_checked)
               VALUES(?,?,?,?,?,?,0,'planned','1','')
               ON CONFLICT(id) DO UPDATE SET name=excluded.name,country=excluded.country,
               connector_type=excluded.connector_type,niches=excluded.niches,access_class=excluded.access_class""",
            (source_id, name, country, connector, niches, access),
        )


def statuses() -> dict:
    items = []
    for provider, meta in PROVIDERS.items():
        config = _read(provider)
        if provider == "google_sheets":
            configured = bool(config.get("client_id") and config.get("client_secret"))
            connected = bool(configured and config.get("refresh_token"))
            secret_hint = _hint(config.get("client_id", ""))
        else:
            configured = bool(config.get("api_key"))
            connected = configured and bool(config.get("verified_at"))
            secret_hint = _hint(config.get("api_key", ""))
        items.append(
            {
                "id": provider,
                **meta,
                "configured": configured,
                "connected": connected,
                "enabled": bool(config.get("enabled", False)),
                "verified_at": config.get("verified_at", ""),
                "secret_hint": secret_hint,
                "message": config.get("message", ""),
                "spreadsheet_id": config.get("spreadsheet_id", "")
                if provider == "google_sheets"
                else "",
            }
        )
    return {"providers": items, "secrets_storage": "Windows Credential Manager"}


def save(provider: str, data: dict) -> dict:
    if provider not in PROVIDERS or not isinstance(data, dict):
        raise ValueError("Choose a supported connection")
    current = _read(provider)
    if provider == "google_sheets":
        client_id = str(data.get("client_id", "")).strip()
        client_secret = str(data.get("client_secret", "")).strip()
        if (
            not re.fullmatch(r"[A-Za-z0-9_.-]{20,220}", client_id)
            or not 6 <= len(client_secret) <= 300
        ):
            raise ValueError(
                "Enter the Google desktop OAuth client ID and client secret"
            )
        if current.get("client_id") != client_id:
            current.pop("refresh_token", None)
            current.pop("spreadsheet_id", None)
        current.update(client_id=client_id, client_secret=client_secret, enabled=True)
    else:
        api_key = str(data.get("api_key", "")).strip()
        if not 12 <= len(api_key) <= 500 or re.search(r"\s", api_key):
            raise ValueError("Enter a valid API key or token")
        if current.get("api_key") != api_key:
            current.pop("verified_at", None)
        current.update(
            api_key=api_key,
            enabled=bool(data.get("enabled", False) and current.get("verified_at")),
            message="Credential saved; test the connection before using it.",
        )
    _write(provider, current)
    return next(item for item in statuses()["providers"] if item["id"] == provider)


def set_enabled(provider: str, enabled: bool) -> dict:
    if provider not in PROVIDERS or provider == "google_sheets":
        raise ValueError("Choose an optional data provider")
    current = _read(provider)
    if not current.get("api_key"):
        raise ValueError("Save this provider's credential first")
    if enabled and not PROVIDERS[provider]["automatic"]:
        raise ValueError(
            "This provider's automatic search adapter is not available yet"
        )
    if enabled and not current.get("verified_at"):
        raise ValueError("Test this provider before enabling it")
    current["enabled"] = bool(enabled)
    _write(provider, current)
    return next(item for item in statuses()["providers"] if item["id"] == provider)


def disconnect(provider: str) -> dict:
    if provider not in PROVIDERS:
        raise ValueError("Choose a supported connection")
    current = _read(provider)
    if provider == "google_sheets" and current.get("refresh_token"):
        try:
            request = Request(
                "https://oauth2.googleapis.com/revoke?"
                + urlencode({"token": current["refresh_token"]}),
                data=b"",
                method="POST",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            with urlopen(request, timeout=12):
                pass
        except Exception:
            pass
    try:
        keyring.delete_password(KEYRING_SERVICE, provider)
    except keyring.errors.PasswordDeleteError:
        pass
    return next(item for item in statuses()["providers"] if item["id"] == provider)


def secret(provider: str) -> str:
    """Return a provider key only inside backend provider code."""
    config = _read(provider)
    if not (config.get("enabled") and config.get("verified_at")):
        return ""
    return str(config.get("api_key") or "")


def _json_request(
    url: str, *, headers=None, data=None, method=None, timeout=25
) -> dict:
    body = json.dumps(data).encode() if data is not None else None
    request = Request(
        url,
        data=body,
        method=method or ("POST" if body is not None else "GET"),
        headers={"Accept": "application/json", **(headers or {})},
    )
    if body is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.load(response)
            return payload if isinstance(payload, dict) else {"data": payload}
    except HTTPError as exc:
        try:
            payload = json.loads(exc.read(2000).decode("utf-8", errors="replace"))
            detail = payload.get("error") or payload.get("errorMessage") or payload
        except Exception:
            detail = exc.reason
        raise ValueError(
            f"Provider rejected the credential ({exc.code}): {str(detail)[:240]}"
        ) from exc
    except URLError as exc:
        raise ValueError(
            f"Provider could not be reached: {str(exc.reason)[:240]}"
        ) from exc


def test(provider: str) -> dict:
    if provider not in PROVIDERS or provider == "google_sheets":
        raise ValueError("Use Connect Google for Google Sheets")
    config = _read(provider)
    key = str(config.get("api_key") or "")
    if not key:
        raise ValueError("Save this provider's credential first")
    label = ""
    if provider == "apollo":
        payload = _json_request(
            "https://api.apollo.io/api/v1/auth/health",
            headers={"x-api-key": key, "Cache-Control": "no-cache"},
        )
        label = str(payload.get("message") or payload.get("status") or "Apollo account")
    elif provider == "apify":
        payload = _json_request(
            "https://api.apify.com/v2/users/me",
            headers={"Authorization": f"Bearer {key}"},
        )
        user = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        label = str(user.get("username") or user.get("email") or "Apify account")
    elif provider == "outscraper":
        payload = _json_request(
            "https://api.outscraper.cloud/profile/balance",
            headers={"X-API-KEY": key},
        )
        label = f"Outscraper account · balance {payload.get('balance', 'available')}"
    elif provider == "google_places":
        payload = _json_request(
            "https://places.googleapis.com/v1/places:searchText",
            headers={"X-Goog-Api-Key": key, "X-Goog-FieldMask": "places.id"},
            data={"textQuery": "coffee in New York", "maxResultCount": 1},
        )
        if not isinstance(payload.get("places", []), list):
            raise ValueError("Google Places returned an unexpected response")
        label = "Google Places API key verified"
    config.update(verified_at=_now(), message=label or "Connection verified")
    _write(provider, config)
    return next(item for item in statuses()["providers"] if item["id"] == provider)


def google_places_text(query: str, limit: int = 20) -> list[dict]:
    """Run one explicitly enabled Places Text Search with a bounded field mask."""
    key = secret("google_places")
    if not key:
        return []
    payload = _json_request(
        "https://places.googleapis.com/v1/places:searchText",
        headers={
            "X-Goog-Api-Key": key,
            "X-Goog-FieldMask": (
                "places.id,places.displayName,places.formattedAddress,"
                "places.nationalPhoneNumber,places.websiteUri,places.location,"
                "places.primaryType,places.rating,places.userRatingCount"
            ),
        },
        data={"textQuery": query, "maxResultCount": max(1, min(int(limit), 20))},
    )
    places = payload.get("places", [])
    return places if isinstance(places, list) else []


def google_authorize_url(callback: str) -> str:
    config = _read("google_sheets")
    if not config.get("client_id") or not config.get("client_secret"):
        raise ValueError("Save the Google desktop OAuth client first")
    state = secrets.token_urlsafe(24)
    OAUTH_STATES[state] = time.time()
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(
        {
            "client_id": config["client_id"],
            "redirect_uri": callback,
            "response_type": "code",
            "scope": GOOGLE_SCOPE,
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
            "state": state,
        }
    )


def google_callback(code: str, state: str, callback: str) -> None:
    created = OAUTH_STATES.pop(state, None)
    if not created or time.time() - created > 600:
        raise ValueError("Google connection request expired; start again")
    config = _read("google_sheets")
    token_body = urlencode(
        {
            "code": code,
            "client_id": config.get("client_id", ""),
            "client_secret": config.get("client_secret", ""),
            "redirect_uri": callback,
            "grant_type": "authorization_code",
        }
    ).encode()
    request = Request(
        "https://oauth2.googleapis.com/token",
        data=token_body,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urlopen(request, timeout=25) as response:
            token = json.load(response)
    except HTTPError as exc:
        detail = exc.read(2000).decode("utf-8", errors="replace")
        raise ValueError(
            f"Google OAuth exchange failed ({exc.code}): {detail[:240]}"
        ) from exc
    refresh = token.get("refresh_token") or config.get("refresh_token")
    granted = set(str(token.get("scope") or GOOGLE_SCOPE).split())
    if not refresh or GOOGLE_SCOPE not in granted:
        raise ValueError("Google did not grant the required per-file Drive permission")
    config.update(
        refresh_token=refresh,
        verified_at=_now(),
        enabled=True,
        message="Google Sheets connected with per-file access.",
    )
    _write("google_sheets", config)


def _google_access_token() -> str:
    config = _read("google_sheets")
    if not config.get("refresh_token"):
        raise ValueError("Connect Google Sheets first")
    body = urlencode(
        {
            "client_id": config.get("client_id", ""),
            "client_secret": config.get("client_secret", ""),
            "refresh_token": config["refresh_token"],
            "grant_type": "refresh_token",
        }
    ).encode()
    request = Request(
        "https://oauth2.googleapis.com/token",
        data=body,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urlopen(request, timeout=25) as response:
            token = json.load(response).get("access_token")
    except HTTPError as exc:
        raise ValueError(
            "Google authorization expired; disconnect and connect again"
        ) from exc
    if not token:
        raise ValueError("Google did not return an access token")
    return token


SHEET_COLUMNS = (
    "collection",
    "niche",
    "name",
    "category",
    "address",
    "city",
    "state",
    "phone",
    "email",
    "website",
    "linkedin",
    "facebook",
    "instagram",
    "source",
    "source_url",
    "match_status",
    "qualification",
    "lead_score",
    "updated_at",
)


def _sheet_rows(snapshot: dict) -> list[list[str]]:
    records = []
    for row in snapshot.get("records", []):
        if isinstance(row, dict):
            records.append({"collection": "Historical research", **row})
    for collection in snapshot.get("collections", []):
        if not isinstance(collection, dict):
            continue
        for row in collection.get("rows", []):
            if isinstance(row, dict):
                records.append(
                    {
                        "collection": collection.get("title", "Compiled research"),
                        "niche": collection.get("niche", ""),
                        "updated_at": collection.get("updated_at", ""),
                        **row,
                    }
                )
    values = [list(SHEET_COLUMNS)]
    seen = set()
    for row in records[:10000]:
        signature = (
            str(row.get("website", "")).casefold().rstrip("/"),
            str(row.get("name", "")).casefold(),
            str(row.get("city", "")).casefold(),
        )
        if signature in seen:
            continue
        seen.add(signature)
        values.append(
            [
                re.sub(r"[\r\n\t]+", " ", str(row.get(column, "") or ""))[:3000]
                for column in SHEET_COLUMNS
            ]
        )
    return values


def sync_sheet(snapshot: dict) -> dict:
    token = _google_access_token()
    config = _read("google_sheets")
    headers = {"Authorization": f"Bearer {token}"}
    spreadsheet_id = str(config.get("spreadsheet_id") or "")
    if not spreadsheet_id:
        created = _json_request(
            "https://sheets.googleapis.com/v4/spreadsheets",
            headers=headers,
            data={
                "properties": {"title": "Lead Extractor Research Library"},
                "sheets": [{"properties": {"title": "Leads"}}],
            },
        )
        spreadsheet_id = str(created.get("spreadsheetId") or "")
        if not spreadsheet_id:
            raise ValueError("Google Sheets did not return a spreadsheet ID")
        config["spreadsheet_id"] = spreadsheet_id
        _write("google_sheets", config)
    values = _sheet_rows(snapshot)
    encoded_range = quote("Leads!A1", safe="!")
    _json_request(
        f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/Leads!A:Z:clear",
        headers=headers,
        data={},
    )
    result = _json_request(
        f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/{encoded_range}?valueInputOption=RAW",
        headers=headers,
        data={"range": "Leads!A1", "majorDimension": "ROWS", "values": values},
        method="PUT",
    )
    return {
        "spreadsheet_id": spreadsheet_id,
        "url": f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit",
        "rows": max(0, len(values) - 1),
        "updated_cells": int(result.get("updatedCells", 0) or 0),
    }
