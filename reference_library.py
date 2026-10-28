"""Portable, historical research imports; never a live lead or delivery check.

Only the two explicit CSV inputs are imported. The fictional demonstration jobs
and campaign message bodies are intentionally excluded from the reference data.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(os.environ.get("LEAD_EXTRACTOR_HOME", Path(__file__).resolve().parent)).expanduser().resolve()
SNAPSHOT_PATH = ROOT / "data" / "reference" / "tedt.json"
AS_OF = "2026-08"
CSV_FILES = (
    "research/02-lead-database.csv",
    "outreach/sheet-additions-waves5-7.csv",
)
NOTE_FILES = (
    "research/03-scoring-and-ranking.md",
    "outreach/followups-2026-08-24.md",
    "outreach/responses-log.md",
    "outreach/seventh-wave-queue.md",
)
GENERAL_WARNINGS = [
    "Historical August 2026 research: contacts, ownership and website claims have not been rechecked.",
    "Published or imported email does not establish mailbox validity, deliverability or permission to contact.",
    "Historical scores and workflow/software notes are prior research judgments, not independently verified facts.",
    "No software or portal visible on inspected pages does not prove the business has none.",
]


def _clean(value: object) -> str:
    value = str(value or "").strip()
    if not value or re.match(r"(?i)^unknown\b", value):
        return ""
    if value.casefold() in {"n/a", "na", "none", "null", "not known", "—", "-"}:
        return ""
    return value


def _url(value: object) -> str:
    value = _clean(value)
    if not value:
        return ""
    if "://" not in value:
        value = "https://" + value
    try:
        parts = urlsplit(value)
        host = (parts.hostname or "").lower().rstrip(".")
        if (
            parts.scheme.lower() not in {"http", "https"}
            or not host
            or "." not in host
            or re.search(r"\s", host)
        ):
            return ""
        port = parts.port
    except ValueError:
        return ""
    netloc = host + (f":{port}" if port else "")
    return urlunsplit((parts.scheme.lower(), netloc, parts.path, parts.query, ""))


def _host(value: str) -> str:
    return re.sub(r"^www\.", "", urlsplit(value).hostname or "")


def _comparable(field: str, value: object) -> str:
    value = str(value)
    if field in {"website", "source_url"}:
        return _host(value)
    if field == "phone":
        digits = re.sub(r"\D", "", value)
        return digits[1:] if len(digits) == 11 and digits.startswith("1") else digits
    return re.sub(r"\s+", " ", value).strip().casefold()


def _score(value: object) -> float | None:
    try:
        score = float(str(value).strip())
    except (ValueError, TypeError):
        return None
    return score if 0 <= score <= 10 else None


def _fields(row: dict[str, str], addition: bool) -> dict:
    website = _url(row.get("Website", ""))
    phone = _clean(row.get("Number" if addition else "Phone", ""))
    if re.match(r"(?i)^(verify|invalid|unverified)\b", phone):
        phone = ""
    email = _clean(row.get("Email", ""))
    if not re.fullmatch(r"[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+", email):
        email = ""
    note_fields = (
        "EvidenceOfManualWorkflow",
        "PainReason",
        "PersonalizationHook",
        "CompanySizeSignal",
        "RecurringService",
        "Services",
        "YearsInBusiness",
    )
    notes = "\n".join(
        f"{key}: {value}" for key in note_fields if (value := _clean(row.get(key)))
    )
    return {
        "name": _clean(row.get("Business" if addition else "Company")),
        "city": _clean(row.get("City")),
        "state": _clean(row.get("State")),
        "website": website,
        "phone": phone,
        "email": email,
        "decision_maker": _clean(row.get("Name" if addition else "DecisionMaker")),
        "role": _clean(row.get("Role")),
        "historical_score": _score(row.get("Score")),
        "workflow": _clean(row.get("ReportsPhotoWorkflow")),
        "software": _clean(row.get("ExistingSoftware")),
        "original_notes": notes,
        "original_status": _clean(row.get("Outreach Status")),
        "source_url": _url(row.get("SourceURL")) or website,
    }


def _empty(reason: str = "No research snapshot has been imported.") -> dict:
    return {
        "schema_version": 1,
        "name": "Tedt historical research",
        "available": False,
        "status": "not_imported",
        "as_of": AS_OF,
        "imported_at": "",
        "source_root": "",
        "record_count": 0,
        "source_row_count": 0,
        "claim_count": 0,
        "snapshot_hash": "",
        "source_files": [],
        "records": [],
        "collections": [],
        "compiled_record_count": 0,
        "warnings": [reason, *GENERAL_WARNINGS],
    }


def _compiled_collections() -> list[dict]:
    """Return completed, organized research runs without flattening their evidence.

    Import engine lazily because engine imports this module while starting up.
    A run enters the library only after the verification organizer has written its
    organization summary, so an unfinished discovery run never looks complete.
    """
    try:
        import engine

        with engine.connection() as conn:
            payloads = conn.execute(
                "SELECT payload,updated_at FROM jobs ORDER BY updated_at DESC LIMIT 100"
            ).fetchall()
    except Exception:
        return []

    collections = []
    for raw, updated_at in payloads:
        try:
            job = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            continue
        organization = job.get("organization")
        rows = job.get("rows")
        if not isinstance(organization, dict) or not isinstance(rows, list):
            continue
        rows = [row for row in rows if isinstance(row, dict)]
        params = job.get("params") if isinstance(job.get("params"), dict) else {}
        offer_title = str(params.get("offer_title") or "").strip()
        segment_title = str(params.get("offer_segment_label") or "").strip()
        sheet_title = (
            " - ".join(part for part in (offer_title, segment_title) if part)
            if offer_title
            else ""
        )
        collections.append(
            {
                "id": job.get("id", ""),
                "job_id": job.get("id", ""),
                "title": " · ".join(
                    part
                    for part in (
                        str(params.get("niche") or "Research"),
                        str(params.get("location") or "Anywhere"),
                    )
                    if part
                ),
                "niche": params.get("niche", "Research"),
                "sheet_title": sheet_title,
                "location": params.get("location", "Anywhere"),
                "created_at": job.get("created_at", ""),
                "updated_at": updated_at or "",
                "status": "compiled",
                "source_status": job.get("status", ""),
                "record_count": len(rows),
                "rows": rows,
                "organization": organization,
                "stats": job.get("stats", {}),
                "quality_report": job.get("quality_report", {}),
                "diagnosis": job.get("diagnosis", {}),
                "root_cause_analysis": job.get("root_cause_analysis", {}),
                "intelligence_summary": job.get("intelligence_summary", {}),
                "params": params,
            }
        )
    return collections


def _parse_row(headers: list[str], cells: list[str], relative: str, row_number: int):
    """Recover only identified unquoted commas; retain the original source cells."""
    raw_row = {
        key: cells[index] if index < len(cells) else None
        for index, key in enumerate(headers)
    }
    if len(cells) > len(headers):
        raw_row["__extra_columns"] = cells[len(headers) :]
    repair = ""
    parsed = list(cells)
    known = {
        "Clean Hoods Express": "EvidenceOfManualWorkflow",
        "WhaleyCo Kitchen & Cleaning Services": "EvidenceOfManualWorkflow",
        "DDAN Hood Services": "CompanySizeSignal",
    }
    if len(cells) != len(headers):
        field = known.get(raw_row.get("Company"))
        if (
            relative == CSV_FILES[0]
            and len(cells) == len(headers) + 1
            and field in headers
            and "Score" in headers
            and _score(cells[headers.index("Score") + 1]) is not None
            and _url(cells[-1])
        ):
            index = headers.index(field)
            parsed[index : index + 2] = [cells[index] + "," + cells[index + 1]]
            repair = f"Recovered one known unquoted comma in {field} at {relative}:{row_number}; original cells preserved."
        else:
            raise ValueError(
                f"Malformed CSV at {relative}:{row_number}; unexpected column count requires review."
            )
    return dict(zip(headers, parsed)), raw_row, list(cells), repair


def build(source: Path) -> dict:
    """Read the user's CSVs and caveat notes without writing to the source.

    Matching website hosts merge records. Every CSV row remains in provenance,
    including placeholders, conflicting contacts and the original score text.
    The first nonempty mapped value wins; later conflicts remain reviewable.
    """
    source = Path(source).resolve(strict=True)
    if not source.is_dir():
        raise ValueError("Choose the Tedt project folder, not a file.")
    source_files = []
    rows = []
    for index, relative in enumerate(CSV_FILES):
        raw = (source / relative).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        reader = csv.reader(io.StringIO(raw.decode("utf-8-sig")))
        headers = next(reader, [])
        required = {"Business" if index else "Company", "Website"}
        if not required.issubset(set(headers)):
            raise ValueError(
                f"Unexpected columns in {relative}; expected {sorted(required)}."
            )
        count = 0
        for row_number, cells in enumerate(reader, 2):
            if not any(value.strip() for value in cells):
                continue
            row, raw_row, raw_cells, repair = _parse_row(
                headers, cells, relative, row_number
            )
            rows.append(
                (
                    relative,
                    row_number,
                    row,
                    bool(index),
                    digest,
                    raw_row,
                    raw_cells,
                    repair,
                )
            )
            count += 1
        source_files.append({"path": relative, "sha256": digest, "rows": count})
    notes = {}
    for relative in NOTE_FILES:
        path = source / relative
        if path.is_file():
            raw = path.read_bytes()
            notes[relative] = raw.decode("utf-8-sig")
            source_files.append(
                {"path": relative, "sha256": hashlib.sha256(raw).hexdigest()}
            )

    records = {}
    for relative, row_number, row, addition, digest, raw_row, raw_cells, repair in rows:
        values = _fields(row, addition)
        host = _host(values["website"])
        fallback = "|".join(values[key].casefold() for key in ("name", "city", "state"))
        identity = "host:" + host if host else "name:" + fallback
        if not host and not values["name"]:
            identity = f"row:{relative}:{row_number}"
        if identity not in records:
            records[identity] = {
                "id": "tedt-" + hashlib.sha256(identity.encode()).hexdigest()[:16],
                **values,
                "as_of": AS_OF,
                "verified": False,
                "contact_status": "historical_unverified",
                "email_deliverability": "unknown",
                "provenance": [],
                "warnings": [],
            }
        record = records[identity]
        for field, value in values.items():
            existing = record[field]
            if existing in ("", None):
                record[field] = value
            elif value not in ("", None) and _comparable(
                field, existing
            ) != _comparable(field, value):
                warning = f"Conflicting historical {field} in {relative}:{row_number}; first nonempty value retained. Review provenance."
                if warning not in record["warnings"]:
                    record["warnings"].append(warning)
        record["provenance"].append(
            {
                "source_file": relative,
                "row_number": row_number,
                "as_of": AS_OF,
                "sha256": digest,
                "source_url": values["source_url"],
                "raw_row": raw_row,
                "raw_cells": raw_cells,
                "parsed_row": dict(row),
                "parse_repair": repair,
                "claim_status": "historical_unverified",
            }
        )
        if repair:
            record["warnings"].append(repair)
        original_phone = row.get("Number" if addition else "Phone", "") or ""
        if re.match(r"(?i)^(verify|invalid|unverified)\b", original_phone.strip()):
            record["warnings"].append(
                f"Source flagged the phone for verification; omitted from usable contacts. Original preserved in {relative}:{row_number}."
            )

    for record in records.values():
        _add_caveats(record, notes)
    snapshot = {
        "schema_version": 1,
        "name": "Tedt historical research",
        "available": True,
        "status": "imported",
        "as_of": AS_OF,
        "imported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_root": str(source),
        "record_count": len(records),
        "source_row_count": len(rows),
        "claim_count": len(rows),
        "source_files": source_files,
        "records": list(records.values()),
        "warnings": list(GENERAL_WARNINGS),
    }
    payload = {
        key: value
        for key, value in snapshot.items()
        if key not in {"imported_at", "source_root"}
    }
    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    snapshot["snapshot_hash"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return snapshot


def _add_caveats(record: dict, notes: dict[str, str]) -> None:
    name = record["name"].casefold()
    ranking = "research/03-scoring-and-ranking.md"
    followups = "outreach/followups-2026-08-24.md"
    responses = "outreach/responses-log.md"
    networks = "outreach/seventh-wave-queue.md"
    if "cima" in name:
        if "645-224-2817" in notes.get(ranking, ""):
            record["phone"] = ""
            record["warnings"].append(
                f"Historical source flagged 645-224-2817 as an invalid phone; do not dial without a fresh check ({ranking})."
            )
        if (
            "CIMA SKIPPED" in notes.get(followups, "")
            and "delivery delayed" in notes[followups]
        ):
            record["warnings"].append(
                f"Later August 2026 note reports CIMA email delivery delays and a skipped follow-up; not a current mailbox check ({followups})."
            )
    if "georgia vent works" in name and "search-result summary" in notes.get(
        ranking, ""
    ):
        record["warnings"].append(
            f"Historical phone came from a search-result summary, not the company's own page; confirm before use ({ranking})."
        )
    if "mr. hood clean" in name or "mr hood clean" in name:
        if "Address not found" in notes.get(responses, ""):
            record["warnings"].append(
                f"August 2026 response log reports an address-not-found bounce; imported email is not usable without a fresh check ({responses})."
            )
    if notes.get(networks) and (
        "hood cleaning pros" in name
        or _host(record["website"]) == "fortworthhoodcleaning.com"
    ):
        record["warnings"].append(
            f"Historical notes suspect a shared city-template or lead-generation network. Review ownership/duplicate contacts; not a verified exclusion ({networks})."
        )


def load() -> dict:
    """Load a saved reference snapshot; missing or damaged data is non-fatal."""
    collections = _compiled_collections()
    compiled = {
        "collections": collections,
        "compiled_record_count": sum(item["record_count"] for item in collections),
    }
    try:
        snapshot = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
        if not isinstance(snapshot, dict) or snapshot.get("schema_version") != 1:
            return {**_empty(
                "The saved research snapshot has an unsupported format; reimport the source CSVs."
            ), **compiled}
        records = snapshot.get("records")
        if not isinstance(records, list) or any(
            not isinstance(row, dict) for row in records
        ):
            return {**_empty(
                "The saved research snapshot is malformed; reimport the source CSVs."
            ), **compiled}
        ordered = sorted(
            records,
            key=lambda row: (
                str(row.get("state") or "").casefold(),
                str(row.get("city") or "").casefold(),
                str(row.get("name") or "").casefold(),
                str(row.get("id") or ""),
            ),
        )
        return {
            **_empty(),
            **snapshot,
            "records": ordered,
            "available": True,
            "record_count": len(ordered),
            "organization": "state_city_name",
            **compiled,
        }
    except FileNotFoundError:
        return {**_empty(), **compiled}
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {**_empty(
            "The saved research snapshot could not be read; reimport the source CSVs."
        ), **compiled}
