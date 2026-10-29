#!/usr/bin/env python3
"""Loopback-only web interface for the local lead research engine."""

from __future__ import annotations
import argparse
import html
import json
import mimetypes
import os
import threading
import webbrowser
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
import engine
from discovery import plan
from research import strategy
import reference_library
import registry_catalog
import local_ai
import ai_tasks
import verification
import outreach
import browser_session
import connections
import intelligence
import ai_brain
import sequence_engine
import workflow
import personal_offer
import employee_discovery

WEB = engine.SOURCE_ROOT / "dashboard"


class LocalHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = False

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


class Handler(BaseHTTPRequestHandler):
    server_version = "LeadFinder/2.0"

    def log_message(self, *args):
        pass

    def trusted(self):
        host = urlparse("http://" + self.headers.get("Host", "")).hostname
        origin = self.headers.get("Origin")
        return host in ("127.0.0.1", "localhost", "::1") and (
            not origin
            or origin
            in (
                f"http://127.0.0.1:{self.server.server_port}",
                f"http://localhost:{self.server.server_port}",
            )
        )

    def send(self, data, status=200, mime="application/json", filename=None):
        if not isinstance(data, bytes):
            data = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", mime + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'",
        )
        if filename:
            self.send_header(
                "Content-Disposition", f'attachment; filename="{filename}"'
            )
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if not self.trusted():
            self.send({"error": "Local app requests only"}, 403)
            return
        parsed = urlparse(self.path)
        path = parsed.path
        query_values = parse_qs(parsed.query)
        if path in {"/", "/api/connections/google/callback"} and (
            query_values.get("code")
            or query_values.get("state")
            or query_values.get("error")
        ):
            callback = f"http://127.0.0.1:{self.server.server_port}"
            try:
                if query_values.get("error"):
                    raise ValueError("Google access was not approved")
                connections.google_callback(
                    query_values.get("code", [""])[0],
                    query_values.get("state", [""])[0],
                    callback,
                )
                body = b"<!doctype html><meta charset='utf-8'><title>Google connected</title><h1>Google Sheets connected</h1><p>Return to Lead Extractor. This window can be closed.</p>"
                self.send(body, mime="text/html")
            except Exception as exc:
                body = f"<!doctype html><meta charset='utf-8'><title>Google connection failed</title><h1>Google connection failed</h1><p>{html.escape(str(exc))}</p>".encode()
                self.send(body, 400, "text/html")
            return
        if path == "/api/health":
            chrome_preference = (
                os.getenv("LEAD_EXTRACTOR_CHROME_INTEGRATION", "1") != "0"
            )
            self.send(
                {
                    "ok": True,
                    "version": "2.0",
                    "sources": engine.catalog(),
                    "preferences": {"chrome_integration": chrome_preference},
                }
            )
            return
        if path == "/api/ai/status":
            self.send(local_ai.status())
            return
        if path == "/api/browser/status":
            self.send(browser_session.status())
            return
        if path == "/api/connections":
            connection_status = connections.statuses()
            connection_status["google_redirect_uri"] = (
                f"http://127.0.0.1:{self.server.server_port}"
            )
            self.send(connection_status)
            return
        if path == "/api/connections/catalog":
            with engine.connection() as conn:
                rows = conn.execute(
                    "SELECT id,name,country,connector_type,niches,access_class,enabled,status,last_checked FROM source_catalog ORDER BY country,name"
                ).fetchall()
            fields = (
                "id",
                "name",
                "country",
                "connector_type",
                "niches",
                "access_class",
                "enabled",
                "status",
                "last_checked",
            )
            self.send({"sources": [dict(zip(fields, row)) for row in rows]})
            return
        if path == "/api/registries":
            values = parse_qs(parsed.query)
            country = values.get("country", [""])[0]
            niche = values.get("niche", [""])[0]
            query = values.get("query", [""])[0]
            payload = registry_catalog.metadata()
            payload["directories"] = registry_catalog.list_directories(
                country, niche, query
            )
            self.send(payload)
            return
        if path == "/api/personal/offer-plan":
            values = parse_qs(parsed.query)
            try:
                self.send(personal_offer.plan(
                    values.get("offer", [""])[0],
                    values.get("country", ["US"])[0],
                    values.get("segment", [""])[0],
                ))
            except ValueError as exc:
                self.send({"error": str(exc)}, 400)
            return
        if path == "/api/outreach/status":
            self.send(outreach.provider_status())
            return
        if path == "/api/intelligence/overview":
            self.send(intelligence.overview())
            return
        if path == "/api/intelligence/queue":
            self.send(intelligence.queue())
            return
        if path == "/api/intelligence/ai-teaching":
            niche = parse_qs(parsed.query).get("niche", [""])[0]
            try:
                self.send(intelligence.ai_teaching_view(niche))
            except ValueError as exc:
                self.send({"error": str(exc)}, 400)
            return
        if path == "/api/intelligence/brain":
            niche = parse_qs(parsed.query).get("niche", [""])[0]
            try:
                self.send(ai_brain.snapshot(niche))
            except ValueError as exc:
                self.send({"error": str(exc)}, 400)
            return
        if path == "/api/intelligence/niche-packs":
            self.send(intelligence.niche_packs())
            return
        if path == "/api/intelligence/dnc":
            self.send(intelligence.dnc_entries())
            return
        if path == "/api/intelligence/transitions":
            self.send(sequence_engine.transition_table())
            return
        if path.startswith("/api/intelligence/entities/"):
            item = intelligence.entity(path.split("/")[-1])
            self.send(
                item or {"error": "Company memory not found"}, 200 if item else 404
            )
            return
        if path == "/api/outreach/zoho/connect":
            callback = (
                f"http://127.0.0.1:{self.server.server_port}/api/outreach/zoho/callback"
            )
            try:
                destination = outreach.oauth_authorize_url(callback)
                self.send_response(302)
                self.send_header("Location", destination)
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
            except ValueError as exc:
                self.send({"error": str(exc)}, 400)
            return
        if path == "/api/connections/google/connect":
            callback = f"http://127.0.0.1:{self.server.server_port}"
            try:
                destination = connections.google_authorize_url(callback)
                self.send_response(302)
                self.send_header("Location", destination)
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
            except ValueError as exc:
                self.send({"error": str(exc)}, 400)
            return
        if path == "/api/outreach/zoho/callback":
            query = parse_qs(parsed.query)
            callback = (
                f"http://127.0.0.1:{self.server.server_port}/api/outreach/zoho/callback"
            )
            try:
                address = outreach.oauth_callback(
                    query.get("code", [""])[0], query.get("state", [""])[0], callback
                )
                body = f"<!doctype html><meta charset='utf-8'><title>Zoho connected</title><h1>Zoho connected</h1><p>{html.escape(address)} is now linked. Return to Lead Finder; this window can be closed.</p>".encode()
                self.send(body, mime="text/html")
            except Exception as exc:
                self.send(
                    f"<!doctype html><meta charset='utf-8'><title>Zoho connection failed</title><h1>Zoho connection failed</h1><p>{html.escape(str(exc))}</p>".encode(),
                    400,
                    "text/html",
                )
            return
        if path == "/api/outreach/templates":
            self.send(outreach.templates())
            return
        if path == "/api/outreach/campaigns":
            self.send(outreach.campaigns())
            return
        if path.startswith("/api/outreach/campaigns/"):
            campaign = outreach._campaign(path.split("/")[-1])
            self.send(
                campaign or {"error": "Campaign not found"}, 200 if campaign else 404
            )
            return
        if path.startswith("/api/ai/tasks/"):
            task = ai_tasks.get_task(path.split("/")[-1])
            self.send(task or {"error": "AI request not found"}, 200 if task else 404)
            return
        if path.startswith("/api/verification/tasks/"):
            task = verification.get_task(path.split("/")[-1])
            self.send(
                task or {"error": "Verification task not found"}, 200 if task else 404
            )
            return
        if path.startswith("/api/employee-discovery/"):
            job_id = path.split("/")[-1]
            try:
                self.send(employee_discovery.get(job_id))
            except ValueError as exc:
                self.send({"error": str(exc)}, 404)
            return
        if path == "/api/workflows/current":
            self.send(
                workflow.current(parse_qs(parsed.query).get("job_id", [""])[0]) or {}
            )
            return
        if path.startswith("/api/workflows/"):
            task = workflow.get_task(path.split("/")[-1])
            self.send(task or {"error": "Workflow not found"}, 200 if task else 404)
            return
        if path == "/api/plan":
            query = parse_qs(parsed.query)
            niche = query.get("niche", ["service"])[0] or "service"
            try:
                payload = {
                    key: query.get(key, [default])[0]
                    for key, default in [
                        ("niche", niche),
                        ("location", "Dallas, Texas"),
                        ("country", "US"),
                        ("source", "hybrid"),
                        ("target", "both"),
                        ("coverage", "exact"),
                        ("depth", "balanced"),
                        ("research_profile", "general"),
                    ]
                } | {
                    "query_budget": int(query.get("query_budget", [24])[0]),
                    "phrases": query.get("phrases", [""])[0],
                    "browser": query.get("browser", ["true"])[0] == "true",
                }
                raw_source = payload["source"]
                if raw_source == "websites":
                    payload["source"] = "hybrid"
                params = engine.validate(payload)
                params["source"] = raw_source
                base = plan(niche, params["phrases"])
                self.send({**base, "strategy": strategy(base, params)})
            except (ValueError, TypeError) as exc:
                self.send({"error": str(exc)}, 400)
            return
        if path == "/api/jobs":
            self.send(engine.history())
            return
        if path == "/api/library":
            self.send(reference_library.load())
            return
        if path.startswith("/api/jobs/"):
            job = engine.get_job(path.split("/")[-1])
            self.send(job or {"error": "Search not found"}, 200 if job else 404)
            return
        if path.startswith("/api/download/"):
            parts = path.strip("/").split("/")
            result = engine.download(parts[2], parts[3]) if len(parts) == 4 else None
            if not result:
                self.send({"error": "Download not found"}, 404)
                return
            body, mime, name = result
            self.send(body, mime=mime, filename=name)
            return
        static = {
            "/": "index.html",
            "/index.html": "index.html",
            "/app.js": "app.js",
            "/style.css": "style.css",
            "/tokens.css": "tokens.css",
            "/professional.css": "professional.css",
            "/logo.svg": "logo.svg",
        }
        if path in static:
            file = WEB / static[path]
            self.send(
                file.read_bytes(),
                mime=mimetypes.guess_type(file.name)[0] or "text/plain",
            )
            return
        self.send({"error": "Not found"}, 404)

    def do_POST(self):
        if not self.trusted():
            self.send({"error": "Local app requests only"}, 403)
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 25000:
                raise ValueError("Request too large or empty")
            params = json.loads(self.rfile.read(size))
            if self.path == "/api/ai/assist":
                self.send({"id": ai_tasks.start(params)}, 202)
                return
            if self.path == "/api/verification/start":
                self.send({"id": verification.start(params)}, 202)
                return
            if self.path == "/api/employee-discovery/start":
                self.send({"id": employee_discovery.start(params)}, 202)
                return
            if self.path.startswith("/api/employee-discovery/") and self.path.endswith(
                "/resume"
            ):
                self.send(
                    {"id": employee_discovery.resume(self.path.split("/")[-2])},
                    202,
                )
                return
            if self.path.startswith("/api/employee-discovery/") and self.path.endswith(
                "/cancel"
            ):
                self.send(
                    {
                        "cancel_requested": employee_discovery.cancel(
                            self.path.split("/")[-2]
                        )
                    }
                )
                return
            if self.path == "/api/workflows":
                self.send({"id": workflow.start(params)}, 202)
                return
            if self.path == "/api/browser/open":
                self.send(browser_session.open_service(params.get("service", "all")))
                return
            if self.path == "/api/connections/save":
                self.send(
                    connections.save(str(params.get("provider", "")), params), 201
                )
                return
            if self.path == "/api/connections/test":
                self.send(connections.test(str(params.get("provider", ""))))
                return
            if self.path == "/api/connections/enabled":
                self.send(
                    connections.set_enabled(
                        str(params.get("provider", "")),
                        params.get("enabled") is True,
                    )
                )
                return
            if self.path == "/api/connections/disconnect":
                self.send(connections.disconnect(str(params.get("provider", ""))))
                return
            if self.path == "/api/connections/google/sync":
                self.send(connections.sync_sheet(reference_library.load()))
                return
            if self.path == "/api/browser/open-url":
                self.send(
                    browser_session.open_url(
                        params.get("url", ""), params.get("company_id", "")
                    )
                )
                return
            if self.path == "/api/browser/preferences":
                self.send(browser_session.set_preferences(params))
                return
            if self.path == "/api/browser/clear-search-checkpoint":
                self.send(browser_session.clear_search_checkpoint())
                return
            if self.path == "/api/intelligence/outcomes":
                self.send(intelligence.record_outcome(params), 201)
                return
            if self.path == "/api/intelligence/ai-teaching":
                self.send(intelligence.save_ai_teaching(params), 201)
                return
            if self.path == "/api/intelligence/brain/refresh":
                self.send(ai_brain.refresh(params.get("niche", "")), 201)
                return
            if self.path == "/api/intelligence/ai-terms":
                self.send(
                    intelligence.approve_ai_terms(
                        params.get("niche"),
                        params.get("phrases"),
                        params.get("model", ""),
                        bool(params.get("accepted", True)),
                    ),
                    201,
                )
                return
            if self.path == "/api/intelligence/niche-packs":
                self.send({"slug": intelligence.save_niche_pack(params)}, 201)
                return
            if self.path == "/api/intelligence/browser-checkpoints":
                self.send({"id": intelligence.browser_checkpoint(params)}, 201)
                return
            if self.path == "/api/intelligence/dnc":
                self.send(
                    intelligence.add_dnc(
                        params.get("scope", "email"),
                        params.get("value", ""),
                        params.get("reason", "Manual do-not-contact"),
                    ),
                    201,
                )
                return
            if self.path == "/api/intelligence/email-verifications":
                self.send(intelligence.record_email_verification(params), 201)
                return
            if self.path == "/api/personal/offer-activate":
                self.send(personal_offer.activate(str(params.get("offer", ""))), 201)
                return
            if self.path == "/api/outreach/sequences":
                self.send(
                    {
                        "id": sequence_engine.create(
                            params.get("id", ""), params.get("steps", [])
                        )
                    },
                    201,
                )
                return
            if self.path == "/api/outreach/sequences/enroll":
                self.send(
                    {
                        "id": sequence_engine.enroll(
                            params.get("sequence_id", ""),
                            params.get("campaign_id", ""),
                            params.get("company_id", ""),
                            params.get("operating_entity_id", ""),
                            params.get("email", ""),
                        )
                    },
                    201,
                )
                return
            if self.path == "/api/outreach/templates":
                self.send({"id": outreach.save_template(params)}, 201)
                return
            if self.path == "/api/outreach/zoho/client":
                outreach.save_zoho_client(params)
                self.send({"saved": True})
                return
            if self.path == "/api/outreach/zoho/disconnect":
                outreach.disconnect_zoho()
                self.send({"disconnected": True})
                return
            if self.path == "/api/outreach/campaigns":
                self.send({"id": outreach.create_campaign(params)}, 201)
                return
            if self.path.startswith("/api/outreach/campaigns/") and self.path.endswith(
                "/draft"
            ):
                outreach.resume_ai(self.path.split("/")[-2])
                self.send({"drafting": True}, 202)
                return
            if self.path.startswith("/api/outreach/campaigns/") and self.path.endswith(
                "/start"
            ):
                outreach.start(
                    self.path.split("/")[-2], params.get("confirmation") is True
                )
                self.send({"started": True}, 202)
                return
            if self.path.startswith("/api/outreach/campaigns/") and self.path.endswith(
                "/pause"
            ):
                self.send({"pause_requested": outreach.pause(self.path.split("/")[-2])})
                return
            if self.path == "/api/outreach/suppressions":
                outreach.suppress(
                    params.get("email", ""), params.get("reason", "Manual suppression")
                )
                self.send({"suppressed": True}, 201)
                return
            if self.path.startswith("/api/verification/tasks/") and self.path.endswith(
                "/cancel"
            ):
                self.send(
                    {
                        "cancel_requested": verification.cancel_task(
                            self.path.split("/")[-2]
                        )
                    }
                )
                return
            if self.path.startswith("/api/ai/tasks/") and self.path.endswith("/cancel"):
                self.send(
                    {"cancel_requested": ai_tasks.cancel_task(self.path.split("/")[-2])}
                )
                return
            if self.path.startswith("/api/workflows/") and self.path.endswith(
                "/cancel"
            ):
                self.send(
                    {"cancel_requested": workflow.cancel(self.path.split("/")[-2])}
                )
                return
            if self.path == "/api/search":
                self.send({"id": engine.start(params)}, 202)
                return
            if self.path.startswith("/api/jobs/") and self.path.endswith("/cancel"):
                self.send(
                    {"cancel_requested": engine.cancel_job(self.path.split("/")[-2])}
                )
                return
            if self.path.startswith("/api/jobs/") and self.path.endswith("/pause"):
                self.send(
                    {"pause_requested": engine.pause_job(self.path.split("/")[-2])}
                )
                return
            if self.path.startswith("/api/jobs/") and self.path.endswith("/resume"):
                self.send(
                    {"resumed": engine.resume_job(self.path.split("/")[-2])}, 202
                )
                return
            self.send({"error": "Not found"}, 404)
        except (ValueError, TypeError) as exc:
            self.send({"error": str(exc)}, 400)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8788)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument(
        "--preserve-active",
        action="store_true",
        help="Do not recover jobs while another older local instance is still running",
    )
    args = parser.parse_args()
    try:
        server = LocalHTTPServer(("127.0.0.1", args.port), Handler)
    except OSError:
        # A second launcher must not mark the first instance's active jobs interrupted.
        from urllib.request import urlopen

        try:
            with urlopen(
                f"http://127.0.0.1:{args.port}/api/health", timeout=2
            ) as response:
                running = json.load(response)
            if running.get("version") == "2.0":
                if not args.no_browser:
                    webbrowser.open(f"http://127.0.0.1:{args.port}")
                print("Lead Finder is already running.", flush=True)
                return
        except Exception:
            pass
        raise
    engine.init(recover=not args.preserve_active)
    ai_tasks.init(recover=not args.preserve_active)
    verification.init(recover=not args.preserve_active)
    employee_discovery.init(recover=not args.preserve_active)
    outreach.init(recover=not args.preserve_active)
    intelligence.init()
    workflow.init(recover=not args.preserve_active)
    intelligence.start_watcher()
    print(f"Lead Finder workspace: http://127.0.0.1:{args.port}", flush=True)
    if not args.no_browser:
        threading.Timer(
            0.5, lambda: webbrowser.open(f"http://127.0.0.1:{args.port}")
        ).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
