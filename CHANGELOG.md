# Changelog

## 2.2.0 — 2026-10-27

First public Windows release.

### Included

- Linked discovery, verification, organization, intelligence, and outreach-preparation workflow.
- Google Maps dedicated Chrome profile, OpenStreetMap, public web discovery, Wikidata, NPI, public directories, startup/product sources, hiring signals, and advertising-transparency review paths.
- 200 curated niche packs.
- Automatic detection of compatible local Ollama chat models.
- Clear non-blocking behavior when local AI is unavailable.
- Approval-gated Zoho Mail campaigns with suppression and pacing controls.
- Borderless Electron desktop interface and an NSIS installer with an explicit Chrome-integration choice.

### Verification

- 134 backend tests passed.
- Browser workflow tests passed; the optional live-AI check is skipped when no configured model is available.
- Electron desktop smoke test passed.
- npm audit and pip-audit found no known dependency vulnerabilities.
- Project-owned Python code had no high-severity Bandit finding.

The Windows installer is unsigned, so Windows SmartScreen may display an unknown-publisher warning.
