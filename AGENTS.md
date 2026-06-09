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

**The full specification is in `docs/DESIGN.md`.** Do not re-derive design decisions;
consult docs/DESIGN.md and update it if scope shifts.

---

## 2. How the repo is organized

| Path | Purpose |
|------|---------|
| `docs/DESIGN.md` | Authoritative spec. Read before implementation work. |
| `README.md` | End-user-facing docs. |
| `src/stormfuse/` | App source. Subpackages: `core/`, `ffmpeg/`, `jobs/`, `ui/`. |
| `src/stormfuse/core/` | UI-agnostic app services shared by the UI layer. |
| `src/stormfuse/core/__init__.py` | Package marker for UI-agnostic core services. |
| `src/stormfuse/core/log_uploader.py` | Diagnostic log bundle upload client/service. |
| `src/stormfuse/core/update_checker.py` | GitHub Releases update checks and installer downloads. |
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
- `stormfuse.core` may import `stormfuse.ffmpeg`.
- `stormfuse.ui` may import `stormfuse.core`.
- `stormfuse.core` must not import `stormfuse.ui` or `stormfuse.jobs`.
- `stormfuse.ffmpeg` and `stormfuse.jobs` must not import `stormfuse.core`.
- `stormfuse.core` must not import `subprocess` or `PyQt6.QtWidgets` /
  `PyQt6.QtGui`.
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
| `make venv` | Creates `.venv/` with Python 3.14 |
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

- Global crash/install-time hooks live in `src/stormfuse/error_handling.py`.
  `run_app()` installs the sys/thread exception hooks, Qt message handler,
  signal hooks, and `faulthandler` there; keep new crash-surface work centralized.
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

- Use `stormfuse.ffmpeg._subprocess.run()` / `.popen()` as the canonical
  wrappers for ffmpeg/ffprobe subprocesses so Windows background launches always
  inherit `CREATE_NO_WINDOW`.
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

**Single source of truth: git tags (`vX.Y.Z`).**

The version is **not stored in source**. `src/stormfuse/_version.py` is generated
by `scripts/write_version.py` and is gitignored. All consumers read from it:

| Consumer | How it gets the version |
|----------|------------------------|
| Running app (`config.py`, `about_dialog.py`, status bar) | `from stormfuse._version import __version__ as APP_VERSION` in `config.py`, with a `0.0.0+dev` fallback |
| `stormfuse.__version__` | `from stormfuse.config import APP_VERSION as __version__` in `__init__.py` |
| `pyproject.toml` | `[tool.setuptools.dynamic] version = {attr = "stormfuse._version.__version__"}` |
| NSIS installer | `build/version.nsh` generated by `stormfuse.spec` from `_version.py` at PyInstaller time; `!include`d by `stormfuse.nsi` |

Who writes `_version.py`:

- **Local dev:** `make deps` (and `make installer`) depend on the `version-file`
  Make target, which runs `python scripts/write_version.py --root .`. It derives
  a dev version from `git describe` (e.g. `1.0.26+dev.3.gabc1234[.dirty]`) or
  falls back to `0.0.0+dev` when no tags are reachable.
- **CI release path:** the workflow runs `python scripts/write_version.py --tag vX.Y.Z`
  before `make installer`, embedding the exact release version.

`make version-file` is a file-target: it only writes `_version.py` when the
file is missing. Delete the file to refresh after new tags or dirty-state
changes. `make clean` removes it.

**Rule: never commit `src/stormfuse/_version.py` or `build/version.nsh`.**
Both are gitignored. If you find yourself wanting to hardcode a version string
anywhere, you're working around the contract — fix the contract instead.

## Release checklist

Releases are automated by the workflow on every push to `master`. The workflow
computes the next patch version from `git tag --sort=-v:refname`, tags it via
the GitHub API, builds the Windows installer, and publishes a GitHub release.

For a normal feature/fix PR:
1. `make lintfix && make lint` — must pass with 10.00/10 and zero mypy errors.
2. `make test` — all unit tests must pass.
3. **CHANGELOG housekeeping:** if `## [Unreleased]` at the top of `CHANGELOG.md`
   contains entries that have already shipped (i.e., a release tag was cut
   *after* those entries were added), promote it to a versioned section first:
   rename `## [Unreleased]` → `## [vX.Y.Z] - YYYY-MM-DD` using the most recent
   release tag and its date, then add a fresh empty `## [Unreleased]` above it.
   Then write your entries under the new `[Unreleased]`. The release workflow
   itself never modifies `CHANGELOG.md` — it's branch-protected against direct
   pushes, and the contributor is the right authority on what shipped.
4. Open a PR; CI must be green before merging.

Once merged to master, the workflow:
- Reads the latest `vX.Y.Z` tag, bumps the patch, and creates the new tag via
  the GitHub API pointing at the merge commit.
- Builds the Windows installer with the tag's version baked in.
- Publishes a GitHub release. Release notes come from the `[Unreleased]`
  section of `CHANGELOG.md` at the tagged commit (or the matching `[X.Y.Z]`
  section if step 3 was performed in the same PR that triggered the release).

**Manual override:** to rebuild or re-release a specific ref, use the Actions
"Run workflow" button on `release.yml`. Pick a branch or tag, and toggle
"release" to create a tag + publish. Selecting a non-master branch with
`release=true` is rejected by `scripts/release_info.py`.

There is no longer a "bump PR" or a workflow-change versioning rule.
PRs that only touch `.github/workflows/` flow through the standard path.

## 11. Commit, branch, PR conventions

- `master` is the default branch and must always be buildable and test-green.
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
