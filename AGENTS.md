# AGENTS.md

Primary working document for AI coding agents (Claude Code, Codex CLI, and any
other LLM-driven assistant) operating inside this repository. Read this first on
every session.

---

## 1. What StormFuse is

StormFuse is a Windows desktop app (PyQt6) that wraps `ffmpeg` / `ffprobe` to do
exactly two things: **combine** multiple MKV/MP4 files into one, and **compress**
a single video to fit under a size ceiling (MFC Share's 10 GB upload limit).
NVENC is preferred; `libx264` is the silent fallback. Process boundary is the
only coupling to ffmpeg — no native ffmpeg bindings.

**The full specification is in `docs/docs/DESIGN.md`.** Do not re-derive design decisions;
consult docs/docs/DESIGN.md and update it if scope shifts.

---

## 2. How the repo is organized

| Path | Purpose |
|------|---------|
| `docs/docs/DESIGN.md` | Authoritative spec. Read before implementation work. |
| `README.md` | End-user-facing docs. |
| `src/stormfuse/` | App source. Subpackages: `ffmpeg/`, `jobs/`, `ui/`. |
| `tests/unit/` | Linux-runnable, no real subprocesses. |
| `tests/functional/` | Windows-only; auto-skipped elsewhere. |
| `resources/` | Icons, license texts, bundled `ffmpeg/` binaries (gitignored). |
| `build/installer/` | NSIS script, ffmpeg SHA-256 pin. |
| `.github/workflows/` | `ci.yml` (lint + unit), `release.yml` (Windows installer). |
| `Makefile` | Entry point for all dev tasks — see §4. |

Layering rules (enforced by pylint + CI, not just convention):

- `stormfuse.ui` may import `stormfuse.jobs`.
- `stormfuse.jobs` may import `stormfuse.ffmpeg`.
- `stormfuse.ffmpeg` must not import either of the above.
- `subprocess` may only be imported inside `stormfuse.ffmpeg` (and
  `stormfuse.ui.menu_actions` for Explorer launch only). If you find yourself
  wanting subprocess elsewhere, you're in the wrong layer.
- Nothing outside `stormfuse.ui` may import PyQt6 widgets or GUI classes
  (`QtWidgets`, `QtGui`). `stormfuse.jobs` may import `PyQt6.QtCore` for
  signals and threading primitives (`QObject`, `pyqtSignal`, `QThread`).

---

## 3. Platform reality

- Development is usually done on **Linux** (or WSL) — the unit suite is designed
  to pass there.
- The app only *runs* on **Windows**. Functional tests, Explorer integration,
  `ffmpeg.exe`/NSIS builds all need Windows.
- Use `if sys.platform == "win32":` guards rather than `try/except ImportError`
  for platform-specific code paths. Windows-only tests carry
  `@pytest.mark.windows_only` and are skipped automatically via
  `tests/conftest.py`.

---

## 4. Dev workflow — always use the Makefile

| Command | What it does |
|---------|--------------|
| `make venv` | Creates `.venv/` with Python 3.12 |
| `make deps` | `pip install -r requirements-dev.txt` inside `.venv` |
| `make fetch-ffmpeg` | Downloads pinned gyan.dev ffmpeg, verifies SHA-256, extracts into `resources/ffmpeg/` |
| `make run` | Launches the app from source |
| `make lint` | ruff + mypy + pylint; must pass with zero warnings |
| `make lintfix` | `ruff format` + `ruff check --fix` — auto-fixes most ruff violations |
| `make format` | alias for `lintfix` (same operation) |
| `make test` | Unit only (default — runs on Linux) |
| `make test-functional` | Functional (Windows) |
| `make test-all` | Both |
| `make installer` | PyInstaller → NSIS → `dist/StormFuse-Setup-<ver>.exe` (Windows) |
| `make clean` | Delete `build/`, `dist/`, `.pytest_cache/`, `__pycache__/`, `.venv/` |

**Linting workflow**: always run `make lintfix` before `make lint`. `lintfix`
auto-fixes the majority of ruff violations in one pass; `lint` then confirms
zero remaining issues (including mypy and pylint). Do not invoke ruff, mypy, or
pylint directly — use these targets so auto-fixable errors are handled
efficiently without burning tokens on manual edits.

Never bypass these targets with ad-hoc `pip`/`pytest` invocations in long-lived
dev loops. If you need a new workflow, add a Makefile target and document it here.

---

## 5. What "done" means for a change

Before declaring any task complete, in order:

1. `make lintfix` then `make lint` passes.
2. `make test` passes.
3. If the change touches platform-specific or subprocess code, also
   `make test-functional` on a Windows machine (or note that it's deferred).
4. Any docs/DESIGN.md assumption you invalidated has been updated in docs/DESIGN.md.
5. New behavior has at least one unit test in `tests/unit/`, unless it's strictly
   UI wiring (then `pytest-qt` in `tests/unit/test_ui_*.py`).

---

## 6. Tooling you should be using

- **Serena MCP** is configured (`.serena/project.yml`). Prefer its semantic code
  tools (`find_symbol`, `get_symbols_overview`, `find_referencing_symbols`,
  `replace_symbol_body`, `insert_after_symbol`) over raw grep + full-file
  reads. Rationale: faster, cheaper, less context bloat. Raw reads are fine for
  small files or when you truly need full context.
- **ruff format** is the sole formatter. Do not introduce black, isort, or
  autopep8.
- **mypy --strict** on `src/stormfuse/`. New code should be fully typed; use
  `from __future__ import annotations` at the top of modules.
- **No `TYPE_CHECKING` circular-import tricks** unless genuinely needed —
  usually the right answer is to restructure the layer.

---

## 7. Logging is a feature, not plumbing

StormFuse logs in **JSON Lines + human mirror** format (docs/DESIGN.md §9). Contract
for new code:

- Log a structured event **before** any error bubbles up to the user. The UI
  dialog should be able to point at a `event` + `msg` already in the log.
- Use a stable `event` name (snake.dotted) so logs are grep-friendly for both
  humans and LLMs debugging later. Add new events to docs/DESIGN.md §9.3 when you
  introduce them.
- Never log raw user file paths truncated — full paths help postmortems.
- Never log command arguments through a shell-escaped string. Log the
  `list[str]` argv verbatim under `ctx.argv`.
- For ffmpeg errors, always include the last ~20 lines of stderr in `ctx.stderr_tail`.

---

## 8. ffmpeg invocation rules

- Always `subprocess.Popen` with a list of args. Never `shell=True`.
- Always `-hide_banner -y`. Always include `-progress <pipe> -nostats` for jobs
  that need progress reporting.
- Current implementation note: `runner.py` uses `tempfile.mkstemp()` and polls
  a temp file for `-progress` output instead of a named pipe. Windows named-pipe
  setup is more complex; temp-file polling is simpler and cross-platform.
- On Windows, use `creationflags=subprocess.CREATE_NO_WINDOW`.
- Pass filenames as positional args after `--` where the ffmpeg verb supports it.
- No network URLs as ffmpeg inputs. Local files only.
- No new encoders added without a pass through docs/DESIGN.md §7.4 and corresponding
  unit tests.

---

## 9. UI conventions

- Heavy work **never** on the UI thread. Use the `Job` abstraction in
  `stormfuse.jobs.base`.
- Widgets communicate with jobs over Qt signals/slots. Don't block on
  `QThread.wait()` in slot handlers.
- Dialogs are user-visible; their text is copy that a user reads — edit with care.
- Don't hardcode filename patterns for specific users/scenarios. v1 keeps
  defaults generic (see docs/DESIGN.md §5.1, §5.2).

---

## 10. Version management

**Single source of truth: `src/stormfuse/config.py:APP_VERSION`**

Never write a version string anywhere else. All consumers derive from this one
value automatically:

| Consumer | How it gets the version |
|----------|------------------------|
| Running app (`config.py`, `about_dialog.py`, status bar) | Reads `APP_VERSION` directly at import time |
| `stormfuse.__version__` | `from stormfuse.config import APP_VERSION as __version__` in `__init__.py` |
| `pyproject.toml` | `[tool.setuptools.dynamic] version = {attr = "stormfuse.config.APP_VERSION"}` |
| NSIS installer | `build/version.nsh` generated by `stormfuse.spec` at PyInstaller time; `!include`d by `stormfuse.nsi` |

**Rule: to bump the version, change exactly one line — `APP_VERSION` in
`src/stormfuse/config.py` — then update `CHANGELOG.md`.**

`build/version.nsh` is generated at build time and is gitignored.

## Release checklist

1. `make lintfix && make lint` — must pass with 10.00/10 and zero mypy errors.
2. `make test` — all 152+ unit tests must pass.
3. Bump `APP_VERSION` in `src/stormfuse/config.py`.
4. Add a new version entry at the top of `CHANGELOG.md` following Keep a Changelog format.
5. Commit with message: `Release vX.Y.Z` (subject line) plus a body summarising
   what changed (reference docs/DESIGN.md sections where relevant).
6. Tag: `git tag vX.Y.Z`.
7. Push branch and tag: `git push && git push --tags`.

## 11. Commit, branch, PR conventions

- `main` is the default branch and must always be buildable and test-green.
- Feature work lands on topic branches; PRs require lint + unit green.
- Commit messages: imperative mood, subject under 72 chars, optional body
  explaining *why*. Reference `docs/DESIGN.md` section numbers when a commit
  implements a specific spec clause.
- Do **not** commit `resources/ffmpeg/*.exe` — they come from `make fetch-ffmpeg`.
- Do **not** commit `.venv/`, `dist/`, `build/` artifacts beyond the NSIS script
  and `ffmpeg.sha256`.

---

## 12. When in doubt

1. Check docs/DESIGN.md for the spec.
2. Check `git log` / `git blame` for the *why* of current code.
3. Run `make lintfix && make lint && make test` before asserting a change is done.
4. If docs/DESIGN.md and the code disagree and you don't know which is right: ask
   the user, don't "fix" silently.

---

## 13. Tool-specific notes

### Claude Code
- `CLAUDE.md` is the short pointer file. This document is the substantive one.
- Use Serena MCP aggressively; it's configured and cheap to use.
- Follow the repo-wide logging and layering rules regardless of what a user
  request suggests — if a request conflicts with them, flag the conflict before
  acting.

### Codex CLI
- Codex reads `AGENTS.md` by convention — this file. The `.codex` marker at the
  repo root confirms Codex-awareness.
- Same layering and logging rules apply.
- Codex does not have Serena MCP; fall back to `rg` / `fd` / direct file reads.

Both assistants: when you finish a task, summarize what changed in terms that
map to docs/DESIGN.md sections ("implemented §7.5 bitrate math and §11.2 unit tests
for it"), so the next session can pick up context quickly.
