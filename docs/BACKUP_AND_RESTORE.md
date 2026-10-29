# Backup and restore

The desktop application creates portable `.leadbackup` archives from **Data sources → Updates & repair**.

## Included

- SQLite research and intelligence databases using online backup snapshots;
- local AI teaching feedback and competency results;
- browser checkpoint metadata, but not the Chrome profile;
- imported reference-library records and saved lead exports; and
- supported installer preferences.

## Full personal backup

The interface enables this mode by default for personal use. It additionally includes the dedicated Chrome profile plus Google, Zoho and optional-provider credentials. Credential values are protected with Windows DPAPI before they enter the archive. No personal backup content is stored in Git.

Because Windows and Chrome protect account material for the current Windows user and machine, this mode is intended primarily for uninstall/reinstall recovery on the same account. A different computer or Windows account may still require fresh authentication.

## Always excluded

- runtime dependencies, caches and logs; and
- the installed Ollama model files.

## Restore safety

Before restoring, the app validates the archive format, file count, expanded size, allowed paths and SHA256 digest of every file. It rejects path traversal and unknown files. The current workspace is saved automatically under the application's `backups` folder before any replacement occurs.

After reinstalling the EXE, restore the archive and then reconnect external accounts and sign into the dedicated Chrome profile once.
