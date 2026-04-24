# StormFuse — Roadmap

Planned features and improvements not yet implemented. Items are roughly
priority-ordered within each section.

---

## Diagnostics

### Log submission to developer

**Goal:** Let users send a diagnostic bundle directly from the app when
something goes wrong, so bug reports arrive with structured logs and context
rather than a screenshot of an error message.

#### Backend

Copy and adapt `infrastructure/lambda_function.py` from GaleFling. The
function runs behind API Gateway and:

- Accepts a JSON POST body with log files (base64-encoded), system metadata,
  a user-written description, and an `app_version` field.
- Enforces a minimum supported version (HTTP 426 for outdated clients).
- Enforces a total attachment size cap (8 MB in GaleFling).
- Builds a MIME multipart email and sends it via AWS SES to
  `morgan@windsofstorm.net`.
- Returns `{"upload_id": "...", "success": true}` on success.

Changes needed from the GaleFling original:

| Area | GaleFling | StormFuse |
|------|-----------|-----------|
| Endpoint path | `/logs/upload` | `/logs/upload` (same pattern, different domain) |
| Domain | `galefling.jasmer.tools` | `stormfuse.jasmer.tools` |
| `app_version` minimum | `1.5.1` | `1.0.0` |
| Attachment types | `log_files`, `screenshots`, `wer_reports` | `log_files` only (no screenshots or WER reports in v1) |
| OAuth callback handler | Present (unrelated) | Remove entirely |

Deploy as a separate Lambda + API Gateway stack; do not share the GaleFling
deployment.

#### Client

Add two new modules following GaleFling's pattern:

**`src/stormfuse/core/log_uploader.py`** (or `src/stormfuse/log_uploader.py`
if not adding a `core/` sub-package):

- `LogUploader` class with a single `upload(user_notes: str) -> tuple[bool, str]` method.
- Collects all session log files from `config.LOG_DIR`, base64-encodes them.
- Includes system metadata: `app_version`, `hostname`, `username`,
  `os_version`, `os_platform`, and `encoder` (NVENC or libx264).
- POSTs to `LOG_UPLOAD_ENDPOINT` (constant in `config.py`) with a 30-second
  timeout.
- Handles HTTP 426 (outdated client) separately with a clear user message.
- Returns `(True, "Logs sent (ID: …)")` on success or `(False, reason)` on
  failure; never raises.

**`src/stormfuse/ui/log_submit_dialog.py`**:

- `LogSubmitDialog(QDialog)` with a multi-line text area for the user to
  describe the problem, a character counter, a Send / Cancel button pair, and
  a privacy notice listing exactly what is sent.
- Calls `LogUploader.upload()` on Send; shows a progress indicator while the
  request is in-flight (run on a `QThread` to avoid blocking the UI).
- Displays the returned success message or error reason.

#### Integration points

- **`DiagnosticErrorDialog`** (`src/stormfuse/ui/error_dialogs.py`): add a
  "Send to Developer" button alongside the existing "Copy diagnostic" button.
  Only enabled when the upload endpoint is reachable (or always enabled and
  let the uploader surface the error).
- **Help menu** (`src/stormfuse/ui/menu_actions.py`): add "Send Logs…" item
  so users can submit even when no error dialog is shown.

#### Payload shape

```json
{
  "app_version": "1.0.0",
  "user_notes": "<text from dialog>",
  "hostname": "DESKTOP-ABCDEF",
  "username": "morgan",
  "os_version": "Windows 10 22H2",
  "os_platform": "win32",
  "encoder": "libx264",
  "log_files": [
    {"filename": "2026-04-24T12-00-00.log", "content": "<base64>"},
    {"filename": "latest.log",              "content": "<base64>"}
  ]
}
```

#### Notes

- `LOG_UPLOAD_ENDPOINT = "https://stormfuse.jasmer.tools/logs/upload"` — add
  to `src/stormfuse/config.py` alongside `APP_VERSION`.
- The endpoint does not exist yet; stub it with a feature flag
  (`LOG_UPLOAD_ENABLED = False` in `config.py`) so the UI can be built and
  tested before the Lambda is deployed.
- Unit-test the uploader with a monkeypatched `requests.post`, covering the
  success, 426, timeout, and connection-error paths (same pattern as
  GaleFling's `tests/test_log_uploader.py`).
- Reference: `GaleFling/infrastructure/lambda_function.py`,
  `GaleFling/src/core/log_uploader.py`,
  `GaleFling/src/gui/log_submit_dialog.py`.

---

## Updates

### Auto-update workflow

**Goal:** Add application update support similar to GaleFling so StormFuse can
check GitHub releases, prompt the user when a newer installer exists, download
 it safely, and launch the installer after the app exits.

#### Backend / source of truth

Reuse GaleFling's update model:

- Query the GitHub Releases API for `jasmeralia/StormFuse`.
- Ignore draft releases.
- Default to stable-only updates, with an opt-in beta/prerelease channel.
- Select the first matching installer asset (`StormFuse-Setup-*.exe`) from the
  chosen release.

#### Core

Add a dedicated updater module following GaleFling's pattern:

**`src/stormfuse/core/update_checker.py`** (or `src/stormfuse/update_checker.py`
if not adding a `core/` package):

- `UpdateInfo` dataclass with:
  `current_version`, `latest_version`, `release_name`, `release_notes`,
  `download_url`, `download_size`, `browser_url`, `is_prerelease`.
- `check_for_updates(include_prerelease: bool = False) -> UpdateInfo | None`
  that:
  - calls the GitHub Releases API with a short timeout,
  - compares versions against `config.APP_VERSION`,
  - returns `None` when up to date or on soft failure,
  - logs success / no-update / error cases with stable event names.

#### UI / flow

- Add **Help → Check for Updates**.
- Add a startup update check gated by config, similar to GaleFling's
  `auto_check_updates` behavior.
- Add a modal update dialog showing:
  - current version,
  - available version,
  - stable vs beta label,
  - release notes,
  - a primary **Download and Install** action.
- Download the installer on a `QThread` with a progress dialog so the UI
  remains responsive.
- Save the installer to the user's Downloads directory.
- Validate the download before launch:
  - reject obviously invalid/too-small binaries,
  - verify file size against the GitHub release asset size when available.
- Launch the installer as a detached process, then exit StormFuse so the
  installer can replace the current installation cleanly.

#### Settings

Add update preferences similar to GaleFling:

- `auto_check_updates: bool = True`
- `allow_prerelease_updates: bool = False`

Expose them in a future settings surface or advanced preferences dialog.

#### Notes

- Reference implementation:
  - `GaleFling/src/core/update_checker.py`
  - `GaleFling/src/gui/update_dialog.py`
  - `GaleFling/src/gui/main_window.py`
  - `GaleFling/src/gui/settings_dialog.py`
- StormFuse currently has no settings dialog, so the first pass may need a
  simpler UX: Help-menu manual checks first, then startup checks/preferences in
  a follow-up.
- Unit tests should cover:
  - no update available,
  - stable update available,
  - prerelease gating,
  - malformed GitHub payloads,
  - network failures,
  - installer download validation and launch flow.
