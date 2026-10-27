"""Apply current directory exclusions to a saved run without losing raw records."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import engine
import leadfinder
from contacts import now
from discovery import is_directory

job = engine.get_job(sys.argv[1], events=False)
if not job or job["status"] in ("running", "queued", "waiting"):
    raise SystemExit("Choose a completed saved run")
excluded = [
    row
    for row in job["rows"]
    if is_directory(row.get("website", "")) and row.get("source") == "web"
]
job["quality_exclusions"] = job.get("quality_exclusions", []) + excluded
job["rows"] = [row for row in job["rows"] if row not in excluded]
job["count"] = len(job["rows"])
job["stats"] = {
    "phones": sum(bool(r.get("phone")) for r in job["rows"]),
    "emails": sum(bool(r.get("email")) for r in job["rows"]),
    "websites": sum(bool(r.get("website")) for r in job["rows"]),
    "matches": sum(r.get("match_status") != "candidate" for r in job["rows"]),
}
job["message"] = f"{job['count']} businesses collected"
job["diagnosis"] = (
    f"Quality review excluded {len(excluded)} directory page(s). Raw records remain in the diagnostic report and original export. Location/service-area coverage still needs checking."
)
job["warnings"] = [
    f"{name}: source unavailable; successful results retained. See Run diagnostics."
    for name, p in job["providers"].items()
    if p.get("failures", 0) or p.get("status") == "failed"
]
engine.save(job)
with engine.connection() as conn:
    conn.execute(
        "INSERT INTO events(job_id,created_at,provider,level,message,details) VALUES(?,?,?,?,?,?)",
        (
            job["id"],
            now(),
            "quality",
            "info",
            "Directory pages removed from business results",
            json.dumps({"excluded": len(excluded), "remaining": job["count"]}),
        ),
    )
rows = [leadfinder.Lead(**row) for row in job["rows"]]
leadfinder.export(
    rows, engine.ROOT / "leads" / f"{job['export_base']}-reviewed.csv", "csv"
)
print(
    json.dumps(
        {
            "id": job["id"],
            "count": job["count"],
            "excluded": len(excluded),
            "stats": job["stats"],
        }
    )
)
