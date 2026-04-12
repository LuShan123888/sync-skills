# Feature Specification: Skill Publishing

**Feature Branch**: `005-skill-publishing`
**Created**: 2026-04-12
**Status**: Draft
**Last Revised**: 2026-04-12
**Input**: User description: 生命周期重构——将"分发"拆分为独立的"发布"和"下载"阶段。

## Clarifications

### Session 2026-04-12

- Q: 发布时的平台选择体验？ → A: 预览时选择——展示所有已配置平台，用户勾选/取消勾选后确认发布。平台选择集成在预览步骤中，不增加额外步骤。
- Q: 不同 skill 的发布平台列表如何配置？ → A: 不需要 per-skill 持久化配置。每次发布时展示所有已配置平台，用户临时选择发布到哪些平台。选择不持久化。
- Q: 首次发布时远程仓库是否需要预先存在？ → A: 用户预先创建远程仓库，在初始化阶段（spec 008）配置远程仓库地址。CLI 不创建或管理远程仓库。
- Q: 发布到 GitHub 时 skill 在远程仓库中的组织方式？ → A: 单仓库多 skill——所有 skill 推送到同一个仓库，每个 skill 一个目录（如 `github.com/user/skills/tree/main/code-review/`），遵循 vercel-labs/skills 惯例。
- Q: 发布状态查看如何获取远程平台信息？ → A: 基于 git 查询——通过 `git ls-remote --tags` 等命令查询远程 tag，对比本地 tag 判断是否有更新待发布。无需额外 API，与迭代阶段的 git 模型一致。
**Input**: User description: 生命周期重构——将"分发"拆分为独立的"发布"和"下载"阶段。发布阶段负责将本地 skill 推送到一个或多个云端平台（GitHub 默认），支持同时发布到多个平台（内部+外部），通过门面模式实现平台可插拔。迭代阶段通过 git 管理版本后，发布阶段利用 git tag 推送到远程仓库，天然支持版本追踪。

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Publish Skill to Default Platform (Priority: P1)

用户通过一条命令将本地 skill 发布到默认平台（GitHub），发布后 skill 在平台上可被发现和安装。

**Why this priority**: 发布是 skill 从本地走向生态的核心一步——没有发布，skill 只存在于用户本地，无法被他人使用。

**Independent Test**: 对一个本地已有 skill 执行发布命令，验证 skill 出现在 GitHub 仓库中，其他用户可以通过标准方式安装。

**Acceptance Scenarios**:

1. **Given** 用户本地中央目录中存在一个 skill 且已通过迭代阶段完成 git 版本管理，**When** 用户执行发布命令，**Then** 系统将 skill 内容连同版本标签推送到默认平台（GitHub），输出发布结果（skill 名称、版本、平台地址）
2. **Given** 用户本地 skill 已有未推送的 git commit 或 tag，**When** 执行发布，**Then** 系统自动推送所有待推送的 commit 和 tag 到远程仓库
3. **Given** 用户首次发布一个 skill，**When** 系统完成发布，**Then** 远程仓库中建立该 skill 的完整目录结构和 SKILL.md，符合 Agent Skills Open Standard 格式要求
4. **Given** 用户未指定目标平台，**When** 执行发布，**Then** 系统使用配置的默认发布平台（GitHub）

---

### User Story 2 — Publish to Multiple Platforms Simultaneously (Priority: P1)

用户可以同时将 skill 发布到多个平台（如 GitHub + 内部 Registry），一次命令完成所有平台的发布。

**Why this priority**: 企业用户通常需要同时发布到外部开源平台和内部合规平台，这是实际使用中的刚需场景。

**Independent Test**: 配置两个发布平台，执行发布命令，验证 skill 同时出现在两个平台上。

**Acceptance Scenarios**:

1. **Given** 用户在配置文件中指定了多个发布平台，**When** 用户执行发布命令，**Then** 系统依次将 skill 推送到所有已配置的平台，输出每个平台的发布结果
2. **Given** 多平台发布中某个平台失败，**When** 系统继续执行，**Then** 已成功的平台保留发布结果，失败的平台输出错误信息和恢复建议，最终输出汇总报告（成功/失败/跳过）
3. **Given** 用户只想发布到指定平台而非全部，**When** 用户执行 `publish --platform <name>`，**Then** 系统仅发布到指定平台
4. **Given** 发布预览展示了所有已配置平台，**When** 用户取消勾选某些平台后确认，**Then** 系统仅发布到用户勾选的平台

---

### User Story 3 — Validate Before Publish (Priority: P1)

发布前系统验证 skill 内容符合规范（SKILL.md frontmatter 完整性、目录结构正确性），不符合规范的 skill 拒绝发布。

**Why this priority**: 发布到公开平台意味着他人会使用该 skill，不符合规范的 skill 会损害体验和可信度。

**Independent Test**: 尝试发布一个 frontmatter 不完整的 skill，验证系统拒绝并提示修正。

**Acceptance Scenarios**:

1. **Given** skill 的 SKILL.md 缺少必填 frontmatter 字段（name、description），**When** 执行发布，**Then** 系统拒绝发布并输出具体的缺失字段列表和修正建议
2. **Given** skill 的 SKILL.md name 字段与目录名不一致，**When** 执行发布，**Then** 系统拒绝发布并提示 name 必须与目录名匹配（Agent Skills Open Standard 要求）
3. **Given** skill 内容完全符合规范，**When** 执行发布，**Then** 系统通过验证并继续发布流程
4. **Given** 使用 `--dry-run` 模式，**When** 执行发布，**Then** 系统仅执行验证和预览，不推送任何内容到远程平台

---

### User Story 4 — Use Pluggable Publish Platforms (Priority: P2)

系统默认使用 GitHub 作为发布平台，用户可以通过配置添加自定义发布平台（如内部 Registry、npm 等），支持热插拔切换。

**Why this priority**: 可插拔性是架构原则的体现，满足不同场景的合规和分发需求。

**Independent Test**: 配置一个自定义发布平台，执行发布操作，验证自定义平台被正确调用。

**Acceptance Scenarios**:

1. **Given** 用户未配置自定义发布平台，**When** 执行发布操作，**Then** 系统使用 GitHub 作为默认发布平台
2. **Given** 用户在配置文件中指定了自定义发布平台，**When** 执行发布操作，**Then** 系统调用自定义平台而非 GitHub
3. **Given** 用户修改配置文件切换发布平台，**When** 下一次执行发布操作，**Then** 系统使用新配置的平台（无需重启或重新初始化）
4. **Given** 自定义平台需要额外的认证信息，**When** 执行发布，**Then** 系统提示用户提供认证信息，错误信息中包含具体的认证步骤指引

---

### User Story 5 — Preview Publish Changes (Priority: P2)

发布前系统展示将发布的内容摘要（skill 名称、版本、目标平台、变更内容），用户确认后执行发布。

**Why this priority**: 与创建和迭代阶段一致的安全要求——发布是不可逆的公开操作，预览机制符合安全原则。

**Independent Test**: 执行发布命令，验证预览输出包含完整的发布信息。

**Acceptance Scenarios**:

1. **Given** 系统完成发布前验证，**When** 展示预览，**Then** 用户看到将发布的 skill 名称、当前版本、目标平台列表和变更摘要
2. **Given** 使用 `-y` 模式（Agent 集成），**When** 执行发布，**Then** 系统跳过预览确认，自动验证并发布
3. **Given** 使用 `--dry-run` 模式，**When** 执行发布，**Then** 系统展示完整的预览信息（验证结果 + 发布目标 + 变更摘要），不执行任何推送操作

---

### User Story 6 — View Publish Status (Priority: P3)

用户可以查看已发布 skill 的状态——哪些平台已发布、当前发布版本、上次发布时间。

**Why this priority**: 管理多个 skill 和多个平台时，用户需要了解发布状态以避免遗漏或重复发布。

**Independent Test**: 执行状态查看命令，验证输出包含每个 skill 在各平台的发布状态。

**Acceptance Scenarios**:

1. **Given** 用户执行发布状态查看命令，**When** 系统通过 git remote 查询远程 tag，**Then** 输出每个 skill 的发布状态：平台名称、已发布版本（远程 tag）、是否为最新版本（对比本地 tag）
2. **Given** 某个 skill 在某个平台上未发布，**When** 查看状态，**Then** 该平台显示为"未发布"状态
3. **Given** 本地 skill tag 高于远程 tag，**When** 查看状态，**Then** 该平台显示为"有更新待发布"提示

---

### Edge Cases

- 网络故障或平台不可用 — 系统应输出明确的错误信息，提示检查网络连接或稍后重试，本地 skill 不受影响
- 发布平台认证过期或无效 — 系统应输出认证指引和具体步骤，错误信息中包含可操作的恢复命令
- 远程仓库中同名 skill 内容冲突 — 系统应提示远程版本与本地版本不一致，建议用户先拉取远程变更或强制覆盖
- 发布过程中断（如用户取消或进程终止）— 系统应确保不会留下部分发布的不一致状态，已推送的内容保持完整
- skill 目录中包含不应发布的文件（如本地配置、临时文件）— 系统应支持发布排除规则，或提示用户清理
- 同时发布大量 skill 时部分失败 — 系统应输出每个 skill 的发布结果，成功的保留，失败的输出错误原因
- 发布平台返回格式异常的响应 — 系统应拒绝解析并输出原始错误信息

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST support publishing local skills to a default platform (GitHub) via a single command
- **FR-002**: System MUST support publishing to multiple platforms simultaneously via a single command
- **FR-003**: System MUST support publishing to a specific platform via `--platform` flag
- **FR-004**: System MUST delegate all publish operations to configured platform adapters via a facade interface — the core system handles orchestration only (validate → invoke platform adapters → report results)
- **FR-005**: System MUST validate skill spec compliance (SKILL.md frontmatter completeness, directory name match, required fields) before publishing
- **FR-006**: System MUST align published skill format with the Agent Skills Open Standard (name required, name matches directory name, metadata field for extensions)
- **FR-007**: System MUST support pluggable publish platforms — users MUST be able to configure custom platforms via config file
- **FR-008**: System MUST output structured error messages with recovery hints when publish operations fail (network errors, auth errors, validation errors, partial failures)
- **FR-009**: System MUST support `--dry-run` mode that validates and previews publish without pushing to any platform
- **FR-010**: System MUST support `-y` mode for non-interactive execution (Agent integration)
- **FR-011**: System MUST report per-platform publish results in multi-platform publish (success/failure/skipped per platform)
- **FR-012**: System MUST NOT modify local skill content during publish — publish is a read-and-push operation
- **FR-013**: System MUST support viewing publish status across all configured platforms via git remote queries (e.g., `git ls-remote --tags`), comparing local and remote tags to determine published version, pending updates, and unpublished skills
- **FR-014**: System MUST share platform configuration with the download phase — both phases read from the same config file

### Key Entities

- **Publish Platform Adapter**: A pluggable component responsible for pushing skill content to a specific platform. Implements a standard interface: receives skill content + version info + authentication, performs the push operation. Default: GitHub (git push). Custom adapters can target internal registries, npm, or other platforms.
- **Facade**: The sync-skills publish command that delegates to configured platform adapters. Handles orchestration only: validate skill → invoke adapters → aggregate results → report. Does not implement push logic itself.
- **Publish Manifest**: The metadata describing what will be published — skill name, version, target platforms, and validation status. Generated by the facade before invoking adapters.
- **Publish Report**: The result of a publish operation — per-platform status (success/failure/skipped), published version, platform-specific URLs, error messages for failures.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A skill published to GitHub is discoverable and installable by other users using standard tools (e.g., `npx skills add`) without requiring sync-skills
- **SC-002**: Publishing a skill to multiple platforms completes with a single command, reporting per-platform results
- **SC-003**: Skills that do not meet the Agent Skills Open Standard format requirements are rejected before publish with specific, actionable error messages
- **SC-004**: Switching to a custom publish platform requires only a configuration file change with no code modification
- **SC-005**: The `--dry-run` preview accurately reflects validation results and target platforms without pushing any content
- **SC-006**: Partial publish failures (multi-platform) do not affect successfully published platforms — each platform's result is independent

## Assumptions

- The publish phase follows the iteration phase in the lifecycle — by the time a skill is published, it has already been iterated and version-managed via git (spec `003-pluggable-skill-iteration`)
- The publish platform interface is a pluggable adapter per Principle VII of the project constitution — it is one of the "Distribution platforms" that MUST be pluggable
- The facade pattern means sync-skills only handles orchestration: validating the skill, invoking platform adapters, and aggregating results. All push operations and platform-specific logic are delegated to adapters
- GitHub is the default publish platform because: (a) it is the most widely accessible, (b) git-based version management from the iteration phase maps directly to GitHub's git push model, (c) it naturally supports version tags
- Skills are published to a single repository in a flat per-skill directory structure (e.g., `skills/code-review/SKILL.md`), following vercel-labs/skills conventions. The remote repository is pre-created by the user and configured during init (spec 008)
- The Agent Skills Open Standard (maintained by `agentskills/agentskills` GitHub org, adopted by Anthropic and Vercel) defines the canonical SKILL.md format. Published skills MUST comply with this standard to ensure interoperability
- Platform configuration is shared between publish and download phases via the same config file at `~/.config/sync-skills/config`
- Authentication to publish platforms is handled by the platform adapter. The core system passes through authentication requirements but does not implement auth logic
- Publishing is a read-and-push operation — the system reads local skill content and pushes to remote. It does not modify local files
- The system does NOT create or manage remote repositories — users must have pre-existing repository access. The system pushes skill content to configured repository paths
- The `--dry-run` mode for publish validates the skill and shows what would be pushed without making any network requests
