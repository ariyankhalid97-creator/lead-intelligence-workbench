# Security policy

## Supported version

Security fixes are applied to the latest release on the default branch.

## Reporting a vulnerability

Please do not publish a working exploit, credential, private lead record, browser profile, or outreach data in a public issue. Open a minimal issue that asks the maintainer for a private reporting channel, without including sensitive details.

Include the affected version, operating system, reproduction conditions, impact, and any suggested mitigation. Remove business contacts, tokens, cookies, email bodies, and local file paths from screenshots and logs.

## Security design

- The dashboard binds only to the loopback interface (`127.0.0.1`).
- Requests validate the local Host and browser Origin.
- Electron uses context isolation, renderer sandboxing, and no Node.js integration.
- Zoho OAuth credentials are stored through the operating-system credential store.
- Local databases, Chrome profiles, exports, logs, and campaign content are excluded from Git.
- Local AI is restricted to the Ollama loopback endpoint and refuses redirects.
- Email sending remains approval-gated and uses the official Zoho Mail API.
- Desktop updates are accepted only through the configured public GitHub release channel. Release artifacts should be code-signed before broad distribution.
- Google Sheets write access, when implemented, must use user-approved OAuth with a narrow per-file scope; API keys and OAuth secrets must never be committed.

This is a local research tool, not a hardened multi-user server. Do not expose its dashboard port to a LAN or the public internet.

