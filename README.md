# sync-skills

自建 Skill 的全生命周期管理器。

它不是一个“下载别人 Skill 的工具”，也不是一个 Skill 商店。  
它解决的是另一类问题：你自己写出来的 Skill，怎么持续迭代、怎么给多个本地 Agent 使用、怎么放到 GitHub 做备份与分享、怎么在多台电脑之间同步。

## 一句话定位

`sync-skills` 是一个 `author-first`、`Git-first`、`repo-first` 的 Skill 管理工具。

- `author-first`：先服务“我自己写 Skill、我自己维护 Skill”这件事
- `Git-first`：版本管理、备份、协作、跨设备同步都建立在 Git 之上
- `repo-first`：当前分发粒度是“整个个人 Skill 仓库”，不是单个 Skill 包

## 它打通了什么

一条完整主线：

1. 创建一个新 Skill
2. 在本地持续修改和迭代
3. 让多个 Agent 同时可见
4. 把整个 Skill 仓库推到 GitHub
5. 在另一台电脑上继续拉取和使用
6. 在不再需要时解绑、删除或下线

## 核心能力

- 创建与纳管：创建新 Skill，或把已有 Skill 纳入统一管理
- 本地分发：通过符号链接把同一个 Skill 暴露给多个 Agent
- 版本管理：基于 Git 做提交、推送、拉取和回滚，并在失败时给出明确提示后安全退出
- 多机同步：通过远程仓库在多台设备之间保持一致
- 生命周期管理：支持 link、unlink、remove、doctor、status 等日常操作
- Agent 接管：项目自带 `skills/sync-skills/SKILL.md`，用于让 Agent 在创建、更新、删除 Skill 后自动衔接 `new`、`link`、`commit`、`push`、`remove`、`unlink`、`doctor`

## 工作模型

当前模型很明确：

- 你维护一个自己的 Skill 仓库
- 仓库里的 Skill 是事实源
- 各个 Agent 目录通过 symlink 使用这些 Skill
- GitHub 远程仓库用于备份、分享和跨设备同步

这意味着当前主线不是：

- 搜索别人发布的 Skill
- 像包管理器一样安装单个第三方 Skill
- 维护一个中心化 Skill registry

这些不是当前产品主线。

## 最小使用流程

```bash
sync-skills init
sync-skills new my-skill
sync-skills status
sync-skills commit
sync-skills push
```

如果你换了一台电脑，主线通常是：

```bash
sync-skills init
sync-skills pull
sync-skills doctor
```

## 当前命令

| 命令 | 作用 |
| --- | --- |
| `init` | 初始化或接入个人 Skill 仓库 |
| `new` | 创建新的 Skill |
| `link` | 将已有 Skill 纳入管理并分发到 Agent |
| `unlink` | 停止托管 Skill，并将内容还原为 Agent 目录中的真实文件 |
| `remove` | 从管理体系中删除 Skill |
| `status` | 查看当前 Skill、链接和状态 |
| `doctor` | 诊断并修复本地状态问题 |
| `commit` | 提交当前仓库改动 |
| `push` | 推送整个 Skill 仓库到远程，首次推送时自动建立 upstream |
| `pull` | 从远程拉取整个 Skill 仓库，并在成功后重建本地可见性 |

## Git 行为

- `commit` 在无改动时会直接跳过，不创建空提交
- `push` 会先预览将要执行的 Git 命令；首次推送会建立 `origin/<branch>` 追踪
- `push` 在本地落后远程或与远程已分叉时，会明确提示先执行 `sync-skills pull`
- `pull` 会先预览实际的 `git pull --rebase` 命令；成功后会继续执行 `doctor` 修复本地链接状态
- `commit` / `push` / `pull` 在 `git` 不可用、未配置远程、认证失败、detached HEAD、本地未提交改动、冲突或远程分支缺失等场景下，都会给出明确提示并安全退出

## 为什么现在不需要 `publish` / `import` / `install-from-git`

因为当前分发模型已经足够清晰：

- `init`：建立本地管理基线
- `push`：把整个仓库放到远程
- `pull`：在别的设备继续使用同一个仓库

只有当产品将来要支持“单个 Skill 的独立发布、独立安装、独立引用”时，`publish` / `import` / `install-from-git` 才会变成必要能力。  
在当前的 repo-first 模型下，它们不是主线需求。

## 文档

- 设计文档：[docs/DESIGN.md](docs/DESIGN.md)
- 用户故事：[docs/USER_STORIES.md](docs/USER_STORIES.md)
- 变更历史：[CHANGELOG.md](CHANGELOG.md)
- Agent Skill 定义：[skills/sync-skills/SKILL.md](skills/sync-skills/SKILL.md)

---

# sync-skills

The lifecycle manager for self-authored Skills.

This is not a tool for downloading other people's Skills, and it is not a Skill marketplace.  
It solves a different problem: once you create your own Skill, how do you iterate on it, expose it to multiple local agents, back it up or share it through GitHub, and keep it synced across multiple machines?

## Positioning

`sync-skills` is an `author-first`, `Git-first`, `repo-first` Skill manager.

- `author-first`: built for people who create and maintain their own Skills
- `Git-first`: versioning, backup, collaboration, and multi-device sync are all based on Git
- `repo-first`: the current distribution unit is the whole personal Skill repository, not an individual Skill package

## What it covers

One complete path:

1. Create a new Skill
2. Keep iterating on it locally
3. Make it visible to multiple agents
4. Push the whole Skill repository to GitHub
5. Pull and continue using it on another machine
6. Unlink, remove, or retire it when it is no longer needed

## Core capabilities

- Creation and adoption: create a new Skill or bring an existing one under management
- Local distribution: expose the same Skill to multiple agents through symlinks
- Version management: use Git for commit, push, pull, and history-based recovery, with explicit failure hints and safe exits
- Multi-device sync: keep the repository aligned across machines through a remote
- Lifecycle operations: manage daily operations through `link`, `unlink`, `remove`, `doctor`, and `status`
- Agent handoff: the repository ships `skills/sync-skills/SKILL.md` so an agent can continue into `new`, `link`, `commit`, `push`, `remove`, `unlink`, and `doctor` after creating, updating, or deleting a Skill

## Operating model

The current model is explicit:

- You maintain one personal Skill repository
- Skills inside that repository are the source of truth
- Agent directories consume those Skills through symlinks
- The GitHub remote is used for backup, sharing, and multi-device sync

This means the current product is not centered on:

- discovering Skills published by others
- installing a single third-party Skill like a package manager
- maintaining a centralized Skill registry

Those are not the mainline product goals today.

## Minimal workflow

```bash
sync-skills init
sync-skills new my-skill
sync-skills status
sync-skills commit
sync-skills push
```

On another machine, the mainline usually looks like:

```bash
sync-skills init
sync-skills pull
sync-skills doctor
```

## Current commands

| Command | Purpose |
| --- | --- |
| `init` | Initialize or attach to a personal Skill repository |
| `new` | Create a new Skill |
| `link` | Bring an existing Skill under management and expose it to agents |
| `unlink` | Stop managing a Skill and restore real directories into agent paths |
| `remove` | Remove a Skill from the managed lifecycle |
| `status` | Inspect current Skills, links, and state |
| `doctor` | Diagnose and repair local state problems |
| `commit` | Commit current repository changes |
| `push` | Push the whole Skill repository to the remote, establishing upstream on first push |
| `pull` | Pull the whole Skill repository from the remote and rebuild local visibility afterward |

## Git behavior

- `commit` skips clean worktrees instead of creating empty commits
- `push` previews the exact Git commands first; the first push establishes `origin/<branch>` tracking
- `push` explicitly tells you to run `sync-skills pull` when the local branch is behind the remote or has diverged
- `pull` previews the exact `git pull --rebase` command first; after success it runs `doctor` to restore local link visibility
- `commit`, `push`, and `pull` fail safely with explicit hints for missing `git`, missing remote, auth failure, detached HEAD, local uncommitted changes, conflicts, and missing remote branches

## Why `publish` / `import` / `install-from-git` are not required yet

Because the current distribution model is already coherent:

- `init`: establish local management
- `push`: send the whole repository to a remote
- `pull`: continue using the same repository on another device

`publish`, `import`, and `install-from-git` only become necessary if the product later moves to independent publishing, installation, or referencing at the single-Skill level.  
Under the current repo-first model, they are not mainline requirements.

## Documents

- Design: [docs/DESIGN.md](docs/DESIGN.md)
- User stories: [docs/USER_STORIES.md](docs/USER_STORIES.md)
- Changelog: [CHANGELOG.md](CHANGELOG.md)
- Agent skill definition: [skills/sync-skills/SKILL.md](skills/sync-skills/SKILL.md)
