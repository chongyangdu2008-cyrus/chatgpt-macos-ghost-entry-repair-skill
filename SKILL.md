---
name: chatgpt-macos-ghost-entry-repair
description: Diagnose and repair a stale cloud ChatGPT conversation that was deleted on another device but remains as an undeletable ghost entry in the macOS ChatGPT Desktop Recents sidebar. Do not use for normal deletions, local Codex tasks, projects, duplicate app icons, or conversations that still exist in the cloud.
---

# ChatGPT macOS Ghost Entry Repair

Use this skill only for the narrow symptom where an ordinary cloud ChatGPT conversation was deleted from another client, is absent from the authoritative cloud list, but remains in **Recents** on macOS and cannot be removed through the normal sidebar controls.

The current desktop app may use the `com.openai.codex` bundle identifier and a Codex-named local catalog. That does not make a remote ChatGPT conversation a local Codex task.

## Safety invariants

- Diagnose read-only before proposing a mutation.
- Prefer normal sidebar deletion, refresh, and relisting when they can still address the item.
- Never clear cookies, authentication state, all application data, `~/.codex`, or the full local catalog for this symptom.
- Never modify a local Codex task or a row whose `source_kind` or catalog host is not `chatgpt`.
- Require exactly one candidate, `missing_candidate = 0`, no matching `thread_timeline_ledger` records, and a healthy database.
- Require explicit user authorization immediately before the local database mutation. Explain that a local backup will be created.
- Stop on a schema mismatch, zero or multiple candidates, a database lock that persists, backup failure, integrity failure, or any failed safety invariant.
- Treat the schema as internal and version-dependent. Do not improvise a broad workaround when it changes.

## Workflow

1. Confirm the user reports all of the following:
   - the cloud conversation was already deleted on another device or client;
   - it no longer appears in the authoritative conversation list;
   - it remains only in macOS Desktop Recents;
   - the normal removal control cannot remove it because the backing conversation is gone.
2. Identify the visible title locally. Do not repeat it in public reports, GitHub content, or logs intended for sharing.
3. From this skill directory, inspect without mutation:

   ```bash
   python3 scripts/catalog_repair.py inspect --title "VISIBLE TITLE"
   ```

   If the desktop adds a visible suffix and exact matching returns no candidate, retry once with `--title-prefix` instead of `--title`.
4. Continue only when the JSON result reports:
   - `integrity_check` is `ok`;
   - `candidate_count` is `1`;
   - the candidate is `eligible`;
   - `source_kind` and `host_kind` are both `chatgpt`;
   - `missing_candidate` and `timeline_record_count` are both `0`.
5. Show the user the sanitized findings and request explicit authorization if the request did not already clearly authorize this targeted deletion.
6. Run the repair with the returned opaque selection token:

   ```bash
   python3 scripts/catalog_repair.py repair --title "VISIBLE TITLE" \
     --selection-token "OPAQUE TOKEN" --confirm-cloud-deleted --apply
   ```

   Use `--title-prefix` consistently if inspection used prefix matching.
7. The helper creates a SQLite-consistent backup, opens an immediate transaction, rechecks every invariant, deletes only the confirmed composite-key row, increments `local_thread_catalog_metadata.catalog_revision`, commits, and verifies zero remaining rows plus `PRAGMA integrity_check`.
8. Refresh the sidebar. A full app restart or sign-out is normally unnecessary; if refresh is insufficient, restart the app without signing out. If the item reappears, stop and report a reconciliation defect instead of repeating deletions.

If the database is locked, ask the user to quit ChatGPT normally before retrying. Do not force-quit it without authorization.

## Privacy

Raw titles, account or user identifiers, host identifiers, conversation or thread identifiers, tokens, cookies, absolute user paths, database copies, screenshots, and logs are confidential. Keep them local. Public write-ups may contain only generic schema names, sanitized counts, opaque example placeholders, and the product-level behavior.
