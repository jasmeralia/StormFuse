# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.14] - 2026-04-25

### Added

#### Log upload backend (§9)
- Added `infrastructure/` directory with CloudFormation template, Lambda function, and deploy script for the StormFuse log upload backend (`stormfuse.jasmer.tools`)
- Shell scripts in `infrastructure/` are now linted via `shellcheck` as part of `make lint` (non-Windows only)

### Changed

#### Menus (§5)
- Moved Settings from `File > Settings...` to a dedicated `Settings > Edit Settings...` top-level menu
- Renamed `Help > Send Logs...` to `Help > Send Logs to Jas`
- Combine tab Clear button now also clears the output filename field

#### Log upload (§9)
- Enabled log upload (`LOG_UPLOAD_ENABLED = True`); endpoint is `https://stormfuse.jasmer.tools/logs/upload`

## [1.0.13] - 2026-04-25

### Fixed

#### Compress progress tracking (§7.7)
- Progress reader now emits the *last* complete block from the ffmpeg `-progress` file instead of always replaying the first block; previously the rate-limiter caused `out_time_sec` and `frame` to freeze at the initial values for the entire job

#### UI — strategy preview readability (§5)
- Removed hardcoded `color: #334155` from the expanded strategy details label; text now inherits the system palette colour and is readable in both dark and light mode

#### Compress output filename (§5.2)
- Default output filename strips a trailing `-combined` suffix before appending `-compressed`, so `foo-combined.mkv` compresses to `foo-compressed.mp4` instead of `foo-combined-compressed.mp4`

## [1.0.12] - 2026-04-25

### Changed

#### Release pipeline (§16)
- Replaced `actions/download-artifact` with `gh run download` in the release job to eliminate the remaining Node deprecation warning emitted while collecting installer artifacts

## [1.0.11] - 2026-04-25

### Changed

#### Release pipeline (§16)
- Updated artifact upload/download actions to `v7` after GitHub still reported Node 20 deprecation warnings for `actions/download-artifact@v6`

## [1.0.10] - 2026-04-25

### Changed

#### Release pipeline (§16)
- Updated CI and release workflow actions to Node 24-compatible major versions to remove GitHub Actions Node 20 deprecation warnings

## [1.0.9] - 2026-04-25

### Fixed

#### Installer upgrade shutdown (§6.4, §12.2)
- The in-app updater now exits the StormFuse process completely after launching the installer so background Qt threads cannot keep the old executable locked
- The installer now runs `taskkill /IM StormFuse.exe /F /T` before writing application files, with the same guard before uninstall file removal

## [1.0.8] - 2026-04-25

### Fixed

#### Combine strategy and crash handling (§5.1, §6.1, §9)
- Mixed MP4/MKV combine inputs now force the normalize path instead of being treated as stream-copy compatible when their streams happen to match
- Normalize plans no longer keep original MP4 files on the copy path beside MKV intermediates
- The live log pane now receives log lines through a Qt signal, preventing ffmpeg stderr reader threads from mutating UI widgets directly
- Clear Log Files now truncates the active `fatal_errors.log` file held by `faulthandler` instead of trying to delete it
- Windows title-bar theming now skips child widgets, avoiding Qt warnings for docked panes

## [1.0.7] - 2026-04-25

### Added

#### Installer and settings (§6.4, §12.2)
- The installer finish page now offers to launch StormFuse after installation
- Added a Settings dialog for diagnostics and update preferences, including startup update checks and beta/prerelease update opt-in

#### Crash diagnostics (§9)
- Startup now detects fatal crash logs from the previous run, snapshots them, and shows a diagnostic dialog instead of leaving users with a silent disappearance
- Diagnostic bundles and log uploads now include fatal crash logs alongside `latest.log` and session logs

### Changed

#### Diagnostics and updates (§6.4, §9)
- Moved the debug ffmpeg logging preference out of the Help menu and into Settings
- Fatal crash logging now starts each session with metadata and keeps previous fatal logs separate

### Fixed

#### NVENC detection (§5.3)
- Fixed false libx264 fallback on NVIDIA systems that reject the old `64x64` test encode by probing with `256x256` and retrying `320x240` on minimum-dimension errors
- NVENC probing now logs the ffmpeg version, matching `h264_nvenc` encoder lines, exact test argv, test size, and stderr tail

#### Probe preview stability (§6.2, §6.3, §8)
- Probe jobs now deliver results through UI-owned slots with request context instead of worker-thread lambdas that could touch widgets after probing completes

## [1.0.6] - 2026-04-25

### Changed

#### Release pipeline (§16)
- `make test` now emits both `coverage.xml` and `junit.xml` so CI can publish coverage and test-result reports from the canonical Makefile target
- CI and release validation optionally upload coverage and JUnit results to Codecov when `CODECOV_TOKEN` is configured, without making Codecov availability a release blocker
- GitHub Releases now use changelog-derived release notes and are published as prereleases for updater-aware rollout

## [1.0.5] - 2026-04-24

### Added

#### Updates & diagnostics (§6.4, §6.6, §9)
- Help menu actions for checking GitHub Releases updates, sending logs to the developer, and enabling per-job ffmpeg/ffprobe debug reports
- `stormfuse.core.update_checker` with stable/prerelease filtering, installer-asset selection, download validation, and structured update lifecycle logging
- `stormfuse.core.log_uploader` plus a modal log-submission dialog that uploads the current log bundle and system metadata on a background thread
- Diagnostic error dialogs now include a "Send to Developer" action and mention generated ffmpeg/ffprobe report files when debug logging is enabled

### Changed

#### Appearance & preferences (§6.1, §6.4, §6.5, §6.6)
- Added a View menu with persisted System Default / Light Mode / Dark Mode theme selection, live palette updates, and Windows dark-title-bar integration where supported
- Added persisted settings for startup update checks, prerelease update preference, and ffmpeg debug-report generation
- Help > About and other modal dialogs now follow the active application theme

#### FFmpeg subprocess diagnostics (§7.2, §7.7, §9)
- ffmpeg/ffprobe launches now receive a per-job `FFREPORT` environment override when debug logging is enabled, without mutating the parent StormFuse process environment
- Clear Log Files and log uploads now include generated `ffmpeg-*.log` / `ffprobe-*.log` artifacts

### Fixed

- Updated the spec and roadmap to reflect that auto-update support, log submission, appearance controls, and ffmpeg debug-report workflows are now implemented

## [1.0.4] - 2026-04-24

### Added

#### Crash & error handling (§9)
- Centralized global crash hooks in `src/stormfuse/error_handling.py`: `sys.excepthook`, `threading.excepthook`, `qInstallMessageHandler`, SIGINT/SIGTERM signal handlers, and `faulthandler` writing to `LOG_DIR/fatal_errors.log`
- `ExceptionHookingApplication` overrides `QApplication.notify` to forward swallowed Qt slot/event exceptions through the same diagnostic pipeline
- `ffmpeg.runner` reader threads (stderr + progress) now log `ffmpeg.reader_crash` instead of dying silently on exception
- New logging events: `app.unhandled`, `app.thread_unhandled`, `app.qt_message`, `app.signal`, `app.fault`, `ffmpeg.reader_crash`

#### NVENC diagnostics (§5.3)
- `detect_encoder` now logs `ffmpeg -hwaccels` output, the `-encoders` stdout excerpt, and the test-encode stderr tail so fallbacks to libx264 are explainable from the log alone
- 10-second timeout on the NVENC test encode emits `nvenc.probe_timeout` instead of hanging app startup
- `STORMFUSE_FORCE_ENCODER=nvenc|libx264` env var skips detection entirely and emits `nvenc.probe_skipped`

#### UI persistence (§6.2, §6.3)
- `QSettings`-backed last-used directory persistence for "Add Files…" and "Browse…" (output folder) on the Combine tab and "Browse…" (input) and "Browse…" (output folder) on the Compress tab

### Changed

#### File list (§6.2)
- Reordering or removing files no longer re-probes everything: `FileListWidget` now caches probe results across reorder/remove and exposes a new `files_added` signal so only newly added paths are probed
- Removed the doubled-text rendering on filenames by dropping the redundant `QListWidgetItem.setText` call — the row widget is the sole renderer

#### Subprocess invocation (§7.7)
- New `stormfuse.ffmpeg._subprocess.run`/`popen` wrappers always inject `CREATE_NO_WINDOW` on Windows; `runner.py`, `probe.py`, and `encoders.py` route through them, suppressing the terminal-window flashes that previously occurred during NVENC detection at app startup

### Fixed

- "Help > About" and the troubleshooting links now point at `github.com/jasmeralia/stormfuse` (was `winds-of-storm`)

## [1.0.3] - 2026-04-24

### Fixed

#### Release pipeline (§16)
- Installed NSIS on the Windows release runner and added its install directory to `PATH` before `make installer`, so the `makensis` invocation inside the Makefile works on GitHub Actions
- Superseded the failed `v1.0.2` release attempt without rewriting its pushed tag

## [1.0.2] - 2026-04-24

### Fixed

#### Release pipeline (§16)
- Generated `THIRD-PARTY.md` in the Windows `build-installer` job before running unit tests so the installer-asset checks pass on the release runner
- Superseded the failed `v1.0.1` release attempt without rewriting its pushed tag

## [1.0.1] - 2026-04-24

### Fixed

#### Release pipeline (§16)
- Fixed `build/fetch_ffmpeg.py` so the pinned archive hash is matched against the configured ffmpeg asset name instead of GitHub's redirected CDN UUID path, unblocking the Windows release build for tagged releases
- Added a regression test covering GitHub release-asset redirects during `make fetch-ffmpeg`
- Restructured GitHub Actions to match GaleFling's CI/release layout more closely: named jobs, tag-ref checkout for releases, split lint/test and release stages, and artifact-based publishing via `softprops/action-gh-release`

## [1.0.0] - 2026-04-24

### Added

#### Combine workflow (§5.1)
- File list with locale-aware case-insensitive initial sort and drag reorder (Up/Down buttons)
- Timestamp-aware sort supporting OBS (`YYYYMMDD-HHMMSS`) and MFC (`M-D-YYYY HHMM am/pm`) filename formats
- Stream-copy eligibility check across 8 signature fields (codec, resolution, fps ±0.01, colour space, bit depth, pixel format, audio codec/rate); mismatches logged in `concat.decision` event
- Normalize-then-concat fallback: target profile is the largest pixel count (fps tiebreak); intermediates kept on failure, deleted on success
- Duration-weighted progress across all normalization phases plus the final concat
- Strategy preview panel (collapsible) with "Why?" tooltip explaining the stream-copy vs. normalize decision
- Default output path: `<first-stem>-combined.mkv` in the same directory as the first input

#### Compress workflow (§5.2)
- Target-size slider: 1.0–10.0 GB in 0.1 GB steps, default 9.5 GB
- Bitrate calculator: overhead and audio budget deducted, video bitrate/maxrate/bufsize derived; Run button disabled with tooltip when `video_bitrate_k ≤ 0`
- 2-pass encoding: NVENC uses `-multipass fullres`; libx264 uses a true two-pass with log files cleaned up on completion or cancellation
- Audio: AAC 192 k stereo 48 kHz; container: MP4 + `-movflags +faststart`
- Default output path: `<stem>-compressed.mp4`

#### NVENC detection (§5.3)
- Two-step probe: encoder list scan → 1-frame test encode; all four branches covered by unit tests
- Status bar badge shows `NVENC` or `libx264`; fallback reason logged at INFO under `nvenc.probe`
- Right-click context menu on status bar to re-run NVENC detection at any time

#### Cancellation (§5.4)
- Graceful shutdown sequence: `q\n` → 5 s wait → `terminate()` → 3 s wait → `kill()`
- Final output file deleted on cancel; normalize temp directory and 2-pass log files also cleaned up
- Cancellation step (`q` / `terminate` / `kill`) logged in `ffmpeg.cancel` event

#### User interface (§6)
- `QMainWindow` titled "StormFuse" with two-tab central widget (Combine / Compress)
- Menu bar: File → Exit; Help → About, Open Logs, Clear Log Files
- Status bar: encoder badge, job state label, elapsed time / ETA
- Bottom dockable log pane (collapsible) showing human-readable log mirror only — never raw JSON
- Combine tab: per-row badges for detected timestamp and stream-copy signature; separate filename and folder output fields
- Compress tab: input browse, size slider with live bitrate preview, 2-pass toggle, encoder badge, split filename/folder output fields
- About dialog: version, copyright, GPL v3, full dependency list, AI attribution; three buttons — View Licenses, GitHub, Close
- "Open Logs" opens `%LOCALAPPDATA%\StormFuse\logs\` in Explorer (Linux fallback: `xdg-open`)
- "Clear Log Files" truncates the held session file and unlinks older files, catching `PermissionError`

#### Logging (§9)
- JSON Lines format with `event`, `msg`, `ts`, `level`, `job_id`, and `ctx` fields on every record
- Human-readable mirror stream feeds the log pane and is never mixed with the JSON stream
- Per-session log files under `%LOCALAPPDATA%\StormFuse\logs\`; `latest.log` written in parallel by a second handler; retention capped at 20 session files
- Full structured event catalog: `app.start/exit/unhandled`, `nvenc.probe`, `probe.start/result/error`, `concat.decision`, `job.start/finish/cancel/fail`, `ffmpeg.start/progress/stderr/exit/cancel`, `logs.clear`
- `job_id` (time-sortable: ms timestamp + sequence counter + random suffix) stamped on every log line via `contextvars`
- `DiagnosticErrorDialog`: shows what/why/next-step guidance and a "Copy diagnostic" button that bundles the event, message, last 10 stderr lines, encoder, and platform into a single copyable string

#### ffmpeg subsystem (§7)
- `locator.py`: PyInstaller bundle → source tree resolution; no PATH fallback; raises `FfmpegNotFoundError` naming the specific missing item; startup error shown in `DiagnosticErrorDialog` with troubleshooting link
- `probe.py`: typed `FileProbe` dataclass, `--` before filename, no `shell=True`
- `signatures.py`: frozen dataclass with all 8 stream-copy eligibility fields
- `encoders.py`: arg builders return `list[str]`; `detect_encoder()` covers all four probe outcomes
- `bitrate.py`: pure functions, no side effects
- `concat.py`: `ConcatPlan` serializable to log via `to_log_ctx()`
- `runner.py`: `Popen` with list args, no `shell=True`; `CREATE_NO_WINDOW` on Windows; temp-file polling for `-progress` output (avoids Windows named-pipe complexity); stderr tail 200 lines; graceful cancel loop

#### Job layer (§8)
- `Job(QObject)` base with `progress`, `log`, `done`, `failed`, `finished` signals; `cancel()` idempotent
- `CombineJob` and `CompressJob` run on `QThread`; single-job model (new job rejected while one is running)
- `ProbeFilesJob` runs ffprobe on each input in parallel threads before the Combine job starts

#### Architecture and tooling
- Three-layer architecture (`ffmpeg/` → `jobs/` → `ui/`) enforced by a custom pylint checker (`_pylint_layering.py`); `subprocess` confined to `stormfuse.ffmpeg` and `stormfuse.ui.menu_actions`
- 152 unit tests (Linux-runnable, no real subprocesses); functional test suite (Windows-only, auto-skipped elsewhere)
- `mypy --strict` across all source; `ruff` formatting and linting; pylint 10.00/10
- PyInstaller onedir build with bundled gyan.dev ffmpeg 7.1.1 (SHA-256 pinned)
- NSIS installer: per-machine or per-user install, optional Desktop shortcut, Add/Remove Programs entry, "Remove application data" checkbox on uninstall
- GitHub Actions CI (`ci.yml`: lint + unit on every push) and release (`release.yml`: Windows installer on version tag)
- GPL v3/v2 license compliance: SPDX headers on all Python sources, `resources/licenses/` texts, `THIRD-PARTY.md` regenerated at build time by `build/generate_third_party.py`
- Single version source of truth: `src/stormfuse/config.py:APP_VERSION`; `pyproject.toml` and NSIS installer derive from it automatically
