---
name: sync-skills
description: "Manage self-authored AI coding agent skills with sync-skills. MUST trigger when the user wants to create a new managed skill, adopt an already-created skill, update an existing skill and save/sync it, diagnose broken skill visibility, or remove/unlink a skill. ALSO trigger when another workflow has just created, edited, or deleted a user skill directory or SKILL.md and lifecycle management must take over. Trigger on: 'sync-skills', 'create skill', 'new skill', 'make a skill', 'link skill', 'adopt skill', 'update skill', 'edit skill', 'commit skill', 'push skill', 'pull skill', 'remove skill', 'delete skill', 'unlink skill', 'repair skill links', 'manage skill lifecycle'."
tools: [Bash]
---

# sync-skills

Repo-first lifecycle manager for self-authored AI coding agent skills.

Use this skill for:

- create a managed skill
- adopt an existing skill into management
- save or sync skill updates through Git
- inspect or repair lifecycle state
- unlink or remove managed skills

Do not use this skill for:

- searching public skills
- installing third-party skills one by one
- `publish`, `import`, or `install-from-git`

## Preflight checks

Check `sync-skills` first:

```bash
command -v sync-skills >/dev/null 2>&1 && sync-skills --version
```

If missing, install with:

```bash
uv tool install sync-skills
```

Development install:

```bash
uv tool install --editable /path/to/sync-skills
```

Check Git:

```bash
command -v git >/dev/null 2>&1
```

If repo-level operations are about to run and setup is unclear:

```bash
sync-skills init --dry-run
sync-skills init -y
```

## Execution policy

For mutating commands, always use:

1. `--dry-run`
2. show preview
3. after confirmation, re-run with `-y`

Mutating commands:

- `init`
- `new`
- `link`
- `unlink`
- `remove`
- `doctor`
- `commit`
- `push`
- `pull`

Read-only commands:

- `list`
- `status`

## Current behavior to rely on

- `doctor --dry-run` is truly read-only
- `status` reports lifecycle states including `managed`, `unknown`, `orphaned`, `broken link`, `real directory conflict`, and `managed but not exposed`
- `doctor` cleans orphaned state entries during real execution
- `push` / `pull` provide explicit hints for missing remote, auth failure, detached HEAD, local changes, and missing remote branch

## Decision table

| Situation | Detection rule | Command path |
|---|---|---|
| Brand-new managed skill | No real skill exists yet | `new` |
| Skill files already exist before lifecycle handling | Agent or user already created `SKILL.md` or the skill directory | `link` |
| Managed skill content changed and user wants to save locally | Update without remote sync request | `status` -> `commit` |
| Managed skill content changed and user wants backup / GitHub / another machine sync | Update with remote sync intent | `status` -> `push` |
| Another machine needs latest state | Recovery / another computer / pull latest | `pull` -> `doctor` if needed |
| User wants to inspect lifecycle health | Managed / broken / orphaned / visible / what changed | `status` |
| User wants repair | Broken link / missing visibility / orphaned / repair | `doctor` |
| User wants to stop managing but keep content | Retire from management, not full deletion | `unlink` |
| User wants full removal | Clear deletion intent | `remove` |

## Routing priority

1. If real skill files already exist, prefer `link` over `new`
2. If the user wants local save only, prefer `commit`
3. If the user wants GitHub / backup / another machine sync, prefer `push`
4. If the user wants inspection first, prefer `status`
5. If the user wants repair, prefer `doctor`
6. If deletion intent is unclear, distinguish `unlink` vs `remove`

## Takeover rules

If another workflow touches a skill first, this skill should take over immediately:

- created new skill content first -> continue into `new` or `link`
- edited managed skill -> continue into `status` then `commit` or `push`
- edited unmanaged existing skill -> continue into `link`
- deleted files manually -> continue into `remove` or `unlink`
- hit visibility or sync problems -> continue into `status` then `doctor`

## Agent examples

| User says | Agent should do |
|---|---|
| “帮我创建一个新的 skill，名字叫 `foo`” | `sync-skills new foo --dry-run` -> `sync-skills new foo -y` |
| “帮我写一个新的 `SKILL.md`，然后纳入管理” | create files first -> `sync-skills link <name> --dry-run` -> `sync-skills link <name> -y` |
| “这个 skill 我已经写好了，帮我接入 sync-skills” | `sync-skills link <name> --dry-run` -> `sync-skills link <name> -y` |
| “我刚更新了 `foo`，帮我保存一下” | `sync-skills status` -> `sync-skills commit -m "update foo" --dry-run` -> `sync-skills commit -m "update foo" -y` |
| “我更新了 `foo`，顺便同步到 GitHub” | `sync-skills status` -> `sync-skills push -m "update foo" --dry-run` -> `sync-skills push -m "update foo" -y` |
| “我换电脑了，把最新 skill 拉下来” | `sync-skills pull --dry-run` -> `sync-skills pull -y` -> `sync-skills doctor --dry-run` / `sync-skills doctor -y` if needed |
| “看看我现在哪些 skill 有问题” | `sync-skills status` |
| “这些 skill 链接坏了，帮我修一下” | `sync-skills doctor --dry-run` -> `sync-skills doctor -y` |
| “把 `foo` 删掉” | `sync-skills remove foo --dry-run` -> `sync-skills remove foo -y` |
| “先别托管 `foo` 了，但内容保留” | `sync-skills unlink foo --dry-run` -> `sync-skills unlink foo -y` |

## Notes

- Prefer `status` before `commit`, `push`, and `pull`
- Prefer `link` over `new` when the skill already exists
- Prefer `remove` or `unlink` over manual directory deletion
- Do not use removed aliases `fix` or `sync`
- Treat `--copy` as legacy mode only

## Paths

- repo root: `~/Skills`
- managed skills: `~/Skills/skills/<name>/`
- state file: `~/.config/sync-skills/skills.json`
- common agent directories:
  - `~/.agents/skills`
  - `~/.claude/skills`
  - `~/.codex/skills`
  - `~/.gemini/skills`
  - `~/.openclaw/skills`
