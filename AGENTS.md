# Project Memory

This file includes project-specific memory migrated from Claude project memory on 2026-04-17.
Use it for `~/Code/sync-skills` only. Rely on `~/.codex/AGENTS.md` for global user preferences.

## Project Overview

- `sync-skills` is a custom skill lifecycle manager for AI coding agents.
- It is a package-based CLI under `src/sync_skills/`.
- Python requirement is `>= 3.11`; it depends on `PyYAML`.
- Known project state from migrated memory: v1.1.1, around 209 tests.

## Critical Commands

- Run tests with `uv run python -m pytest tests/ -v`.
- Do not switch this to `uv run pytest`; `pytest` is not registered as a script here.

## Read Before Changing Behavior

- Read `docs/DESIGN.md`, especially section 7 "变更日志", before making behavior changes in a new session.

## Commit Rules

- Do not add `Co-Authored-By: Claude`.
- Do not add `Generated with Claude Code`.

## Architecture Notes

- Managed skills are tracked by state file `~/.config/sync-skills/skills.json`.
- Repository skills live in `~/Skills/skills/`.
- The active design is direct single-layer symlink management from repo skills to agent skill directories.
- `~/.agents/skills/` should be treated like a normal agent directory.
- Skill classification is based on state, distinguishing managed vs unknown; do not revive old lock-file assumptions.

## Important Files

- `src/sync_skills/cli.py`: command routing, legacy auto-routing, re-exported old functions.
- `src/sync_skills/lifecycle.py`: add/remove/link/unlink/init and auto-commit behavior.
- `src/sync_skills/symlink.py`: symlink management.
- `src/sync_skills/state.py`: state file management.
- `src/sync_skills/classification.py`: skill classification.
- `src/sync_skills/git_ops.py`: git operations.
- `docs/DESIGN.md`: design notes and change log.

## Known Constraints And Pitfalls

- Preserve legacy CLI compatibility:
  - old flags like `--source`, `--force`, `--delete`, `-d`, `-f`
  - old subcommands like `init`, `list`, `search`, `info`
  should still auto-route to legacy handling where expected.
- `metadata.py` must not import `cli.py`; avoid circular dependencies.
- In TOML output, top-level keys must be written before `[section]` headers, or parsing breaks.
- Any file traversal or hashing logic must ignore hidden files such as `.DS_Store`.
- Any directory scan must ignore hidden directories such as `.system/`.

## Behavioral Principle

- Only unambiguous one-way changes should be auto-resolved.
- For true conflicts, stop and surface the choice to the user instead of forcing a resolution.
