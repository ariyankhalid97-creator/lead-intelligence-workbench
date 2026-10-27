"""Import user-owned historical research without touching live leads or outreach."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import reference_library


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", required=True, type=Path, help="Explicit path to the Tedt folder"
    )
    args = parser.parse_args()
    try:
        snapshot = reference_library.build(args.source)
    except (OSError, UnicodeError, ValueError) as exc:
        parser.exit(2, f"Import failed: {exc}\n")
    destination = reference_library.SNAPSHOT_PATH
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=destination.parent,
            prefix="tedt-",
            suffix=".json.tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            json.dump(snapshot, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        temporary.replace(destination)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()
    print(
        f"Imported {snapshot['source_row_count']} historical source rows as {snapshot['record_count']} reference businesses."
    )
    print(f"Snapshot: {destination}")
    print(
        "August 2026 data remains unverified. No live leads or outreach were changed."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
