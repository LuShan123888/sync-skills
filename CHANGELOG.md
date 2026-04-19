# 更新日志

本文档记录项目的重要变更。
格式遵循 [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)。

本仓库当前采用两套版本体系：
- 里程碑版本（如 `v1.0.0`、`v1.1.3`）
- 包版本（取自 `pyproject.toml`，如 `0.5.20260418.4`）

## [未发布]

### 变更
- 正式将项目历史独立到独立的 `CHANGELOG.md` 文件，并将发布历史从 `docs/DESIGN.md` 中迁移。
- 去除 `fix` / `sync` 兼容别名，不再将其映射到 `doctor`。
- 重写 `docs/DESIGN.md`，将其对齐到当前代码实现，并移除历史演进内容。

### 修复
- 将 `doctor --dry-run` 改为真正只读的预演模式，不再补登记状态、不再修复 symlink，也不再修改目录结构。
- 将 `status` 补齐为生命周期状态视图，显式报告 `managed`、`unknown`、`orphaned`、`broken link`、`real directory conflict` 和 `managed but not exposed`。

## [v1.1.3] - 2026-04-19
软件包版本行：`0.5.20260418.4`

### 新增
- 新增提交前的 Skill 版本自动管理。
- 新增 `skill_version.py` 模块，用于读取、提升并写回 `SKILL.md` 中的版本号。
- 为 commit/push 与 lifecycle 自动提交流程增加了版本回归测试。

### 变更
- `new` 命令默认创建 `version: 0.0.1` 的 Skill。
- 所有提交路径（`commit`、`push`、`new`、`link`、`unlink`、`remove`）共享同一套提交前版本处理逻辑。

## [v1.1.2] - 2026-04-19
软件包版本行：`0.5.20260418.2` - `0.5.20260418.3`

### 新增
- 为 `state.py`、`symlink.py`、`git_ops.py`、`cli.py` 与 v1 命令故事新增了模块级测试文件。
- 为“空源目录采集”和“目标独立性”补充了 Legacy 故事回归测试。

### 修复
- `doctor` 在非 `-y` 模式下不再默认改写状态，而会先请求用户确认。
- `doctor` 现在会在遇到真实目录冲突时询问处理方式，而不是默认跳过决策。

## [v1.1.1] - 2026-04-17
软件包版本行：`0.5.20260416.1`

### 新增
- 新增独立的 `sync-skills commit` 命令，用于仅本地提交不推送。
- 增强 Git 预览输出，展示受影响 Skill、分支信息与最近提交。
- 提升交互式初始化在默认参数路径下的安全性。

### 变更
- 默认提交信息生成逻辑在 `commit` 与 `push` 之间共享。

## [v1.1.1] - 2026-04-14
软件包版本行：`0.5.20260413.1`

### 新增
- `init` 流程增加每个 Skill 的 symlink 预览。
- `new`、`link`、`unlink`、`remove` 成功后自动执行 Git 提交。

### 变更
- 生命周期操作现在自动跳过空提交。

## [v1.1.0] - 2026-04-14
软件包版本行：`0.5.20260412.2`

### 变更
- 将架构从“两层软链”简化为“仓库到 Agent 目录”的直接软链方案。
- 将托管 Skill 的真实来源切换为 `skills.json` 状态文件。
- 重命名命令：`add -> new`，`fix -> doctor`，`uninstall -> unlink`。
- 将 `link` 改造为按名称纳管现有外部 Skill 的流程。

### 移除
- 移除了外部技能检测与锁文件驱动分类在 v1 主流程中的使用。
- 去除了两层软链架构。

## [v1.0.1] - 2026-04-12
软件包版本行：`0.5.20260412.1`

### 新增
- 增强对已有仓库的 push/pull 流程的异常处理。
- 新增卸载流程，用于将托管 Skill 恢复为普通目录。
- 在生命周期操作前后改进校验逻辑。

### 变更
- `sync` 重命名为 `fix`，并保留兼容别名。
- `push` 与 `pull` 在执行前都会预览完整 Git 命令。
- CLI 不再在未提供子命令时默认执行修复流程。

### 修复
- 增强了 non-fast-forward 推送、缺失跟踪分支与 rebase 冲突时的处理。
- 修复 `remove` / `uninstall` 流程中的清理问题。
- 修正外部技能可能被错误处理的隔离问题。

## [v1.0.0] - 2026-04-12
软件包版本行：`0.5.20260411.1`

### 新增
- 基于 Git + symlink 的自定义 Skill 生命周期管理器。
- 新增 v1 版本命令，覆盖初始化、生命周期管理、状态查询与 Git 流程。
- 通过 `sync_legacy.py` 与 `--copy` 路由保留旧版复制同步方式。

### 变更
- 将项目从纯目录复制同步重构为托管式自定义 Skill 生命周期管理。
- 按功能拆分到生命周期、软链、分类、Git 与 legacy 模块。

## [v0.6.0] - 2026-04-11
软件包版本行：`0.5.20260411.1`

### 变更
- 用统一 `SyncOp` 架构替换“收集 -> 分发”双阶段同步模型。
- 将源目录视为“特殊目标”而非单一权威目录。
- 使各目标间的预览输出保持一致。

### 修复
- 通过收紧冲突处理规则，减少误自动解析。

## [v0.5.0] - 2026-04-05
软件包版本行：`0.5.20260405.3`

### 新增
- 为双向同步、强制同步与删除动作新增 `--dry-run`。
- 新增 `skills/sync-skills/SKILL.md`，使项目本身可被 AI Agent 安全调用。

### 变更
- 改进 CLI 帮助文本格式和示例，便于 Agent 使用。

## [v0.4.0] - 2026-04-05
软件包版本行：`0.3.20260405.2`

### 新增
- 新增 `SKILL.md` frontmatter 解析，支持 `tags`、`description`、`tools`。
- 新增 `list`、`search`、`info` 命令用于 Skill 发现。
- 支持基于 `tools` 与 `exclude_tags` 的选择性同步。
- 新增独立的元数据解析与过滤模块。

## [v0.3.x] - 2026-04-03
软件包版本行：`0.3.20260403.1` - `0.3.20260404.2`

### 新增
- 增加目录级 MD5 哈希用于全技能级比较。
- 引入基于哈希分组的交互式冲突选择机制。
- 增强基于源目录路径的强制基底选择。
- 建立 `src/` 包结构、配置加载与 `init` 向导。
- 新增 GitHub Actions 发布流程。

### 变更
- 从单文件脚本迁移到 `src/sync_skills/` 包结构。
- 将校验从数量统计升级为内容哈希校验。

### 修复
- 修复当源目录同时作为目标目录时的嵌套结构问题。
- 修复隐藏目录扫描问题。
- 修复从目标采集改动后未更新分发输出的问题。

## [v0.2] - 2026-03-28
软件包版本行：pre-automated package bump era

### 新增
- 新增 `--delete/-d` 一次性跨源与目标删除 Skill。
- 新增删除预览与确认流程。

## [v0.1] - 2026-03-21
软件包版本行：initial development snapshot

### 新增
- 完成单文件版本的初始实现。
- 增加了 README、设计文档与回归测试。
- 以用户场景为驱动设计同步流程，覆盖早期冲突处理与多目标行为。

### 变更
- 建立项目最初的 source + targets 同步模型。

---

# Changelog

This file documents all notable changes to this project.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

This repository currently uses two version tracks:
- Milestone versions such as `v1.0.0`, `v1.1.3`
- Package versions from `pyproject.toml` such as `0.5.20260418.4`

## [Unreleased]

### Changed
- Formalized project history into a standalone `CHANGELOG.md` and moved release history out of `docs/DESIGN.md`.
- Removed the `fix` / `sync` compatibility aliases instead of mapping them to `doctor`.
- Rewrote `docs/DESIGN.md` to match the current code behavior and removed historical evolution content from the design doc.

## [v1.1.3] - 2026-04-19
Package version line: `0.5.20260418.4`

### Added
- Added automatic Skill version management before commit.
- A new `skill_version.py` module for reading, bumping, and writing back `SKILL.md` versions.
- Version regression tests for commit/push and lifecycle auto-commit flows.

### Changed
- `new` now creates skills with `version: 0.0.1` by default.
- All commit paths (`commit`, `push`, `new`, `link`, `unlink`, `remove`) now share the same pre-commit version handling.

## [v1.1.2] - 2026-04-19
Package version line: `0.5.20260418.2` - `0.5.20260418.3`

### Added
- New module-level test files for `state.py`, `symlink.py`, `git_ops.py`, `cli.py`, and v1 command stories.
- Legacy story regression tests for empty-source collection and target independence.

### Fixed
- `doctor` now asks for confirmation before mutating state in non-`-y` mode.
- `doctor` now asks the user how to handle real-directory conflicts instead of silently skipping the decision.

## [v1.1.1] - 2026-04-17
Package version line: `0.5.20260416.1`

### Added
- Added a dedicated `sync-skills commit` command for local commits without push.
- Richer Git preview output showing affected skills, branch info, and recent commits.
- Safer init behavior when accepting defaults in interactive prompts.

### Changed
- Default commit message generation is shared between `commit` and `push`.

## [v1.1.1] - 2026-04-14
Package version line: `0.5.20260413.1`

### Added
- Added per-skill symlink preview during `init`.
- Automatic Git commits after successful `new`, `link`, `unlink`, and `remove` operations.

### Changed
- Lifecycle operations now skip empty commits automatically.

## [v1.1.0] - 2026-04-14
Package version line: `0.5.20260412.2`

### Changed
- Simplified the architecture from two-layer symlinks to direct repo-to-agent symlinks.
- Switched managed-skill truth to `skills.json` state file.
- Renamed commands: `add -> new`, `fix -> doctor`, `uninstall -> unlink`.
- Changed `link` into a by-name adoption workflow for existing wild skills.

### Removed
- Removed external skill detection and lock-file-driven classification from the main v1 path.
- Removed two-layer symlink architecture.

## [v1.0.1] - 2026-04-12
Package version line: `0.5.20260412.1`

### Added
- Safer Git push/pull handling for existing repositories.
- Uninstall workflow to restore managed skills back to regular directories.
- Better validation before and after lifecycle operations.

### Changed
- `sync` was renamed to `fix` while keeping compatibility aliases.
- Push and pull now preview the exact Git commands before execution.
- The CLI no longer runs a default repair command when no subcommand is provided.

### Fixed
- Handling of non-fast-forward pushes, missing tracking branches, and rebase conflicts.
- Cleanup issues in remove/uninstall flows.
- Isolation bugs where external skills could be touched incorrectly.

## [v1.0.0] - 2026-04-12
Package version line: `0.5.20260411.1`

### Added
- A Git + symlink based custom Skill lifecycle manager.
- New v1 commands for initialization, lifecycle management, status, and Git workflows.
- Legacy copy sync preservation through `sync_legacy.py` and `--copy` routing.

### Changed
- Reworked the project away from pure directory copy sync into managed custom skill lifecycle control.
- Split the codebase into dedicated modules for lifecycle, symlink, classification, git, and legacy logic.

## [v0.6.0] - 2026-04-11
Package version line: `0.5.20260411.1`

### Changed
- Replaced the two-phase collect→distribute sync model with a unified `SyncOp`-based decentralized architecture.
- Treated the source directory as a special target instead of absolute authority.
- Made preview output symmetric across all directories.

### Fixed
- Reduced false auto-resolve behavior by tightening conflict handling rules.

## [v0.5.0] - 2026-04-05
Package version line: `0.5.20260405.3`

### Added
- `--dry-run` support for bidirectional sync, force sync, and delete.
- `skills/sync-skills/SKILL.md` so the project itself can be invoked safely by AI agents.

### Changed
- Improved CLI help formatting and examples for agent-driven usage.

## [v0.4.0] - 2026-04-05
Package version line: `0.3.20260405.2`

### Added
- `SKILL.md` frontmatter parsing for `tags`, `description`, and `tools`.
- `list`, `search`, and `info` commands for skill discovery.
- Selective sync via `tools` and `exclude_tags`.
- Dedicated metadata parsing and filtering module.

## [v0.3.x] - 2026-04-03
Package version line: `0.3.20260403.1` - `0.3.20260404.2`

### Added
- Directory-level MD5 hashing for full-skill comparison.
- Interactive hash-group-based conflict resolution.
- Force mode base-directory selection.
- Upgraded to `src/` package layout, config loading, and `init` wizard.
- GitHub Actions publish workflow.

### Changed
- Moved from single-file script layout to `src/sync_skills/` package structure.
- Upgraded verification from count-based checks to content-hash validation.

### Fixed
- Nested structure handling when the source directory is also used as a target.
- Hidden-directory scanning issues.
- Update distribution after collecting changes from targets.

## [v0.2] - 2026-03-28
Package version line: pre-automated package bump era

### Added
- Added a `--delete/-d` command for one-shot skill removal across source and targets.
- Delete preview and confirmation flow.

## [v0.1] - 2026-03-21
Package version line: initial development snapshot

### Added
- Initial single-file implementation of sync-skills.
- Added README, design documentation, and regression tests.
- User-scenario-driven sync design, including early conflict handling and multi-target behavior coverage.

### Changed
- Established the project’s original source + targets sync model.
