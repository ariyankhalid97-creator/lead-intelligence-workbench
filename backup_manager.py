"""Portable, validated backup and restore for Lead Extractor user data."""

from __future__ import annotations

import argparse
import base64
import ctypes
import hashlib
import json
import shutil
import sqlite3
import tempfile
import zipfile
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from ctypes import wintypes

import keyring

FORMAT = "lead-extractor-backup-v1"
MAX_FILES = 100_000
MAX_BYTES = 5_000_000_000
FILES = {
    "data/workbench.db",
    "data/leads.db",
    "data/ai_feedback.jsonl",
    "data/ai_benchmarks.json",
    "data/browser-session.json",
    "data/geocodes.json",
    "installer-preferences.json",
}
PREFIXES = ("data/reference/", "leads/")
PERSONAL_PREFIXES = ("data/chrome-profile/",)
PRIVATE_CREDENTIAL = "private/credentials.dpapi"
KEYRING_ITEMS = [
    ("LeadExtractor-Optional-Connections-v1", provider)
    for provider in ("google_sheets", "google_places", "apollo", "apify", "outscraper")
] + [("LeadFinder-Zoho-OAuth", "local-dashboard")]


def _allowed(name, personal=False):
    value = PurePosixPath(name).as_posix().lstrip("/")
    path = PurePosixPath(value)
    return (
        value in FILES
        or any(value.startswith(prefix) for prefix in PREFIXES)
        or (personal and value == PRIVATE_CREDENTIAL)
        or (personal and any(value.startswith(prefix) for prefix in PERSONAL_PREFIXES))
    ) and ".." not in path.parts and not path.is_absolute()


def _hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sqlite_copy(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(source)) as current, closing(
        sqlite3.connect(target)
    ) as backup:
        current.backup(backup)


class _Blob(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_char))]


def _protect(value):
    raw = value.encode("utf-8")
    source = _Blob(len(raw), ctypes.cast(ctypes.create_string_buffer(raw), ctypes.POINTER(ctypes.c_char)))
    output = _Blob()
    if not ctypes.windll.crypt32.CryptProtectData(ctypes.byref(source), "Lead Extractor backup", None, None, None, 0, ctypes.byref(output)):
        raise OSError("Windows could not protect the personal credential backup")
    try:
        return base64.b64encode(ctypes.string_at(output.data, output.size))
    finally:
        ctypes.windll.kernel32.LocalFree(output.data)


def _unprotect(value):
    raw = base64.b64decode(value)
    source = _Blob(len(raw), ctypes.cast(ctypes.create_string_buffer(raw), ctypes.POINTER(ctypes.c_char)))
    output = _Blob()
    if not ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(source), None, None, None, None, 0, ctypes.byref(output)):
        raise OSError("Personal credentials can only be restored by the Windows user that created this backup")
    try:
        return ctypes.string_at(output.data, output.size).decode("utf-8")
    finally:
        ctypes.windll.kernel32.LocalFree(output.data)


def _export_credentials(target):
    values = []
    for service, username in KEYRING_ITEMS:
        value = keyring.get_password(service, username)
        if value:
            values.append({"service": service, "username": username, "value": value})
    if values:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(_protect(json.dumps(values, ensure_ascii=False)))


def _restore_credentials(source):
    values = json.loads(_unprotect(source.read_bytes()))
    for item in values if isinstance(values, list) else []:
        if (item.get("service"), item.get("username")) in KEYRING_ITEMS and isinstance(item.get("value"), str):
            keyring.set_password(item["service"], item["username"], item["value"])


def create(root, output, personal=False):
    root, output = Path(root).resolve(), Path(output).resolve()
    if output.suffix.casefold() != ".leadbackup":
        raise ValueError("Backup filename must end in .leadbackup")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="lead-extractor-backup-") as raw:
        stage = Path(raw)
        for name in sorted(FILES):
            source = root / Path(name)
            if not source.is_file():
                continue
            target = stage / Path(name)
            target.parent.mkdir(parents=True, exist_ok=True)
            if source.suffix.casefold() == ".db":
                _sqlite_copy(source, target)
            else:
                shutil.copy2(source, target)
        for prefix in (*PREFIXES, *(PERSONAL_PREFIXES if personal else ())):
            source_dir = root / Path(prefix)
            if not source_dir.is_dir():
                continue
            for source in source_dir.rglob("*"):
                if source.is_file() and not source.is_symlink():
                    relative = source.relative_to(root).as_posix()
                    if _allowed(relative, personal) and source.name not in {"LOCK", "lockfile"}:
                        target = stage / Path(relative)
                        target.parent.mkdir(parents=True, exist_ok=True)
                        try:
                            shutil.copy2(source, target)
                        except OSError:
                            continue
        if personal:
            _export_credentials(stage / PRIVATE_CREDENTIAL)
        files = []
        total = 0
        for path in sorted(item for item in stage.rglob("*") if item.is_file()):
            size = path.stat().st_size
            total += size
            files.append({"path": path.relative_to(stage).as_posix(), "bytes": size, "sha256": _hash(path)})
        manifest = {"format": FORMAT, "created_at": datetime.now(UTC).isoformat(), "files": files, "total_bytes": total, "personal": bool(personal), "privacy": "Full personal backup with browser data and Windows-user-protected credentials." if personal else "Portable research backup; browser login sessions and Credential Manager secrets are excluded."}
        temp_output = output.with_suffix(output.suffix + ".tmp")
        try:
            with zipfile.ZipFile(temp_output, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
                archive.writestr("manifest.json", json.dumps(manifest, indent=2))
                for item in files:
                    archive.write(stage / Path(item["path"]), item["path"])
            temp_output.replace(output)
        finally:
            temp_output.unlink(missing_ok=True)
    return manifest


def inspect(archive_path):
    archive_path = Path(archive_path).resolve()
    with zipfile.ZipFile(archive_path) as archive:
        infos = archive.infolist()
        if len(infos) > MAX_FILES + 1 or sum(info.file_size for info in infos) > MAX_BYTES:
            raise ValueError("Backup exceeds the safe restore limits")
        if "manifest.json" not in {info.filename for info in infos}:
            raise ValueError("Backup manifest is missing")
        manifest = json.loads(archive.read("manifest.json"))
        if manifest.get("format") != FORMAT or not isinstance(manifest.get("files"), list):
            raise ValueError("This is not a supported Lead Extractor backup")
        expected = {item.get("path"): item for item in manifest["files"] if isinstance(item, dict)}
        actual = {info.filename for info in infos if info.filename != "manifest.json" and not info.is_dir()}
        personal = manifest.get("personal") is True
        if actual != set(expected) or any(not _allowed(name, personal) for name in actual):
            raise ValueError("Backup contains unexpected or unsafe files")
        return manifest


def restore(root, archive_path):
    root, archive_path = Path(root).resolve(), Path(archive_path).resolve()
    manifest = inspect(archive_path)
    safety = root / "backups" / f"before-restore-{datetime.now().strftime('%Y%m%d-%H%M%S')}.leadbackup"
    create(root, safety, personal=manifest.get("personal") is True)
    with tempfile.TemporaryDirectory(prefix="lead-extractor-restore-") as raw:
        stage = Path(raw)
        with zipfile.ZipFile(archive_path) as archive:
            for item in manifest["files"]:
                name = item["path"]
                target = stage / Path(name)
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(name) as source, target.open("wb") as destination:
                    shutil.copyfileobj(source, destination)
                if target.stat().st_size != int(item["bytes"]) or _hash(target) != item["sha256"]:
                    raise ValueError(f"Backup integrity check failed for {name}")
        for item in manifest["files"]:
            name = item["path"]
            source, target = stage / Path(name), root / Path(name)
            target.parent.mkdir(parents=True, exist_ok=True)
            replacement = target.with_suffix(target.suffix + ".restore")
            shutil.copy2(source, replacement)
            replacement.replace(target)
        credential_file = stage / PRIVATE_CREDENTIAL
        if credential_file.is_file():
            _restore_credentials(credential_file)
    return {"restored_files": len(manifest["files"]), "safety_backup": str(safety), "created_at": manifest.get("created_at", "")}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("create", "inspect", "restore"))
    parser.add_argument("--root", required=True)
    parser.add_argument("--file", required=True)
    parser.add_argument("--personal", action="store_true")
    args = parser.parse_args()
    result = create(args.root, args.file, personal=args.personal) if args.action == "create" else inspect(args.file) if args.action == "inspect" else restore(args.root, args.file)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
