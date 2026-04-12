---
name: sync-skills
description: "Manage custom AI coding agent skills via git + symlink. Use when the user wants to add/remove/list/search custom skills, check git status, push/pull skill changes, or verify symlinks. TRIGGER on: 'sync-skills', 'add skill', 'remove skill', 'skill management', 'list skills', 'custom skill'."
tools: [Bash]
---

# sync-skills

Custom skill lifecycle manager for AI coding agents. Manages user-created skills via git + symlink, separate from external skills managed by `npx skills`.

## Prerequisites

The `sync-skills` CLI must be installed:

```bash
uv tool install sync-skills
```

## Important: Always Use `-y`

AI agents **cannot interact with stdin**. Always append `-y` to skip confirmation prompts.

## Commands Reference

| User intent | Command |
|---|---|
| Initialize ~/Skills/ repo | `sync-skills init` |
| Link a wild skill | `sync-skills link skill-name -y` |
| List wild skills | `sync-skills link` |
| Create new custom skill | `sync-skills add skill-name -d "description" -y` |
| Verify/repair symlinks | `sync-skills fix -y` |
| List custom skills | `sync-skills list` |
| Show git status | `sync-skills status` |
| Commit and push | `sync-skills push -m "update" -y` |
| Pull and rebuild | `sync-skills pull -y` |
| Search skills | `sync-skills search "query"` |
| Show skill details | `sync-skills info skill-name` |
| Remove custom skill | `sync-skills remove skill-name -y` |
| Uninstall custom skill | `sync-skills uninstall skill-name -y` |
| Uninstall all custom skills | `sync-skills uninstall -y` |
| Legacy copy sync | `sync-skills --copy -y` |

## Common Workflows

### 1. Create a new custom skill

```bash
sync-skills add my-skill -d "My custom skill description" -t "tag1,tag2" -y
```

Creates `~/Skills/skills/my-skill/SKILL.md` with skeleton and symlinks to all agent directories.

### 2. Edit a skill (via agent)

The agent edits `~/.claude/skills/my-skill/SKILL.md` normally. Changes flow through symlinks to `~/Skills/skills/my-skill/SKILL.md` automatically.

### 3. Push changes to GitHub

```bash
sync-skills status       # check what changed
sync-skills push -m "update my-skill" -y
```

Shows full git commands (`git add -A`, `git commit -m "..."`, `git push -u origin <branch>`) before confirming.

### 4. Pull changes from another machine

```bash
sync-skills pull -y      # git pull + rebuild symlinks
```

Shows full git command (`git pull --rebase`) before confirming. Automatically repairs symlinks after pull.

### 5. Check skill classification

```bash
sync-skills info my-skill
```

Shows whether a skill is "custom" (managed by sync-skills) or "external" (managed by npx skills).

### 6. Verify and repair symlinks

```bash
sync-skills fix -y
```

Checks all custom skill symlinks, repairs broken links, detects missing links and orphan skills.

## Flags

| Flag | Purpose |
|---|---|
| `-y`, `--yes` | Skip confirmation |
| `--dry-run` | Preview without executing |
| `--copy` | Use legacy copy-based sync |
| `--config PATH` | Use custom config file |
| `--message`, `-m` | Commit message (push command) |
| `--description`, `-d` | Skill description (add command) |
| `--tags`, `-t` | Comma-separated tags (add command) |

## Architecture

- **Custom skills**: stored in `~/Skills/` git repo, symlinked to `~/.agents/skills/`
- **External skills**: managed by `npx skills`, stored as real files in `~/.agents/skills/`
- **Detection**: external skills identified via lock files (`~/.agents/.skill-lock.json`, `~/skills-lock.json`)

## Config File

Location: `~/.config/sync-skills/config.toml`

```toml
repo = "~/Skills"
agents_dir = "~/.agents/skills"

[external]
global_lock = "~/.agents/.skill-lock.json"
local_lock = "~/skills-lock.json"
```
