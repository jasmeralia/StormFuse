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
