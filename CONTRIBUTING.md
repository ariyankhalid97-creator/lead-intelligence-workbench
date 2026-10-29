# Contributing to Lead Extractor

Thank you for helping improve Lead Extractor. Contributions are welcome when they preserve the project's local-first, evidence-backed and approval-gated design.

## Before you start

1. Search existing issues and Discussions before opening a duplicate.
2. Open an issue for significant behavior, architecture or provider changes before writing a large patch.
3. Never commit credentials, browser profiles, local databases, lead exports, logs, campaign content or screenshots containing real contacts.
4. Use official APIs or public, permitted pages. Do not add CAPTCHA bypasses, paywall bypasses, credential harvesting or access-control evasion.

## Development setup

```powershell
git clone https://github.com/ariyankhalid97-creator/lead-intelligence-workbench.git
cd lead-intelligence-workbench
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
npm install
npm start
```

## Required checks

Run the checks affected by your change before opening a pull request:

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
npm run test:e2e
npm run test:electron
npm audit --omit=dev --audit-level=high
```

New provider logic should include deterministic tests for normalization, provenance, failure diagnostics, continuation behavior and duplicate handling.

## Pull requests

- Keep each pull request focused on one outcome.
- Explain the user problem, implementation and verification performed.
- Include before/after screenshots for visible interface changes, using synthetic data only.
- Preserve existing local data and avoid unrelated formatting changes.
- Update README or CHANGELOG when behavior or setup changes.
- Mark assumptions as assumptions; never present inferred contact or company data as confirmed evidence.

By participating, you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).
