# CLAUDE.md

**Primary agent documentation lives in [`AGENTS.md`](AGENTS.md). Read that first.**

This file exists as a short pointer plus Claude-Code-specific harness notes.
Anything that applies to all agents (layering, logging, Makefile workflow,
commit style, etc.) belongs in `AGENTS.md`, not here.

---

## Project

**StormFuse** — a Windows PyQt6 app that wraps `ffmpeg`/`ffprobe` to combine
videos and compress them under a size ceiling. Full specification in
[`docs/DESIGN.md`](docs/DESIGN.md).

## Claude-Code-specific notes

- **Serena MCP** is configured (`.serena/project.yml`). Prefer semantic code
  tools (`find_symbol`, `get_symbols_overview`, `find_referencing_symbols`,
  `replace_symbol_body`) over raw grep + full-file reads.
- On every session, the substantive contract is in `AGENTS.md` §§ 1–12. Do not
  duplicate it here.
