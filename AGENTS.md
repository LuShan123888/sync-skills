# Project Memory

This file includes project-specific memory for `~/Code/sync-skills`.
Use it only for this repository. Rely on `~/.codex/AGENTS.md` for global user preferences.

## Project Overview

- `sync-skills` is a custom skill lifecycle manager for AI coding agents.
- It is a package-based CLI under `src/sync_skills/`.
- Python requirement is `>= 3.11`; it depends on `PyYAML`.
- Historical notes in older memory snapshots may lag behind the current repository state.

## Critical Commands

- Run tests with `uv run python -m pytest tests/ -v`.
- Do not switch this to `uv run pytest`; `pytest` is not registered as a script here.

## Read Before Changing Behavior

- Read `CHANGELOG.md` first to understand recent functional changes.
- Read `docs/DESIGN.md` when you need architecture or design context behind those changes.

## Documentation Responsibilities

- User-visible release history belongs in `CHANGELOG.md`.
- Architecture background and design rationale belong in `docs/DESIGN.md`.
- If history is missing, reconstruct it from Git before updating docs.
- Do not mix changelog entries and design records into one file again.

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
- `src/sync_skills/metadata.py`: frontmatter parsing and selective sync metadata.
- `CHANGELOG.md`: formal release and update history.
- `docs/DESIGN.md`: architecture background and design rationale.

## Notes

- Preserve the split: `CHANGELOG.md` for history, `docs/DESIGN.md` for design.
- When functionality changes, update both if user-visible behavior and architecture rationale both changed.
- If earlier iterations were missed, reconstruct them from Git history before documenting.
