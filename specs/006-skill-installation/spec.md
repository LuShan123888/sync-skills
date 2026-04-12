# Feature Specification: Skill Installation

**Feature Branch**: `006-skill-installation`
**Created**: 2026-04-12
**Status**: Draft
**Input**: User description: 下载阶段默认按 vercel-labs/skills 行业规范（Agent Skills Open Standard）实现，确保发布到 GitHub 的 skill 可被任何工具安装（不依赖 sync-skills）。同时框架层面支持可插拔的下载源——公司内部自建的 skill 平台若提供自己的 CLI 命令，可以通过适配器接入。

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Install Skill from GitHub (Priority: P1)

用户通过一条命令从 GitHub 安装 skill，安装后 skill 立即在所有已配置的 Agent 中可用。安装方式遵循 vercel-labs/skills 的行业约定。

**Why this priority**: 从 GitHub 安装是下载功能的核心价值——大多数公开 skill 托管在 GitHub，这是用户获取 skill 的主要途径。

**Independent Test**: 执行安装命令指定一个 GitHub 上的 skill，验证 skill 出现在本地中央目录且通过同步机制对所有 Agent 可见。

**Acceptance Scenarios**:

1. **Given** 用户已初始化同步环境，**When** 用户执行 `sync-skills install <owner/repo>`，**Then** 系统从 GitHub 下载 skill 到本地中央目录，通过同步机制（spec `001-symlink-sync`）使 skill 在所有 Agent 中立即可用
2. **Given** GitHub 仓库包含多个 skill，**When** 用户执行安装，**Then** 系统按行业约定扫描标准目录（仓库根目录、`skills/`、`skills/.curated/` 等），发现并安装所有符合条件的 skill
3. **Given** 用户指定了特定版本（如 `@v1.2.0`），**When** 系统解析版本标识符，**Then** 下载指定版本的 skill 而非最新版本
4. **Given** 安装完成，**Then** 系统输出安装结果（skill 名称、版本、来源仓库、安装路径），在 `--json` 模式下输出结构化数据

---

### User Story 2 — Update Installed Skill (Priority: P1)

当 GitHub 上的 skill 有新版本时，用户可以拉取更新到本地，本地始终只保留最新版本。

**Why this priority**: 保持本地 skill 为最新是持续使用的基础——不更新就无法获得他人的改进和安全修复。

**Independent Test**: 在 GitHub 上更新一个 skill 后，在本地执行更新命令，验证本地 skill 内容与最新版本一致。

**Acceptance Scenarios**:

1. **Given** 本地已安装一个来自 GitHub 的 skill，**When** GitHub 上发布了新版本且用户执行更新命令，**Then** 系统下载最新版本替换本地内容，更新后的 skill 通过同步机制对所有 Agent 可见
2. **Given** 本地已安装的 skill 已是最新版本，**When** 用户执行更新命令，**Then** 系统提示"已是最新版本"，不执行任何写入操作
3. **Given** 本地 skill 已被用户本地迭代修改过，**When** GitHub 有新版本且用户执行更新，**Then** 系统提示本地有未发布的修改，建议用户先发布或确认覆盖
4. **Given** 用户执行批量更新命令，**When** 系统检查所有已安装的 skill，**Then** 逐个检查更新，输出更新摘要（已更新/已最新/失败）

---

### User Story 3 — Search and Discover Skills (Priority: P2)

用户可以通过关键词搜索 GitHub 上的 skill，查看 skill 的基本信息（名称、描述、标签），决定是否安装。

**Why this priority**: 发现能力让用户了解生态中有哪些可用 skill，但没有安装能力就没有实际价值。

**Independent Test**: 执行搜索命令，验证返回的 skill 列表包含匹配的 skill 及其基本信息。

**Acceptance Scenarios**:

1. **Given** 用户执行搜索命令并提供关键词，**When** 系统查询 GitHub，**Then** 返回匹配的 skill 列表，每条结果包含名称、描述、标签和安装命令
2. **Given** 用户执行搜索命令未提供关键词，**When** 系统查询，**Then** 返回推荐的 skill 列表（如 skills.sh 目录上的热门 skill）
3. **Given** 搜索结果为空，**When** 系统完成查询，**Then** 输出"未找到匹配的 skill"并建议调整关键词
4. **Given** 用户执行详情查看命令，**When** 系统查询，**Then** 返回该 skill 的详细信息（名称、描述、标签、作者、最新版本、来源地址）

---

### User Story 4 — Install from Custom Platform (Priority: P2)

用户可以配置自定义的 skill 来源平台（如公司内部 Registry），通过相同的安装命令从自定义平台下载 skill。

**Why this priority**: 企业用户需要从内部平台获取 skill，这是实际使用中的合规需求。框架层面的可插拔支持确保架构的扩展性。

**Independent Test**: 配置一个自定义下载源平台，执行安装命令，验证自定义平台被正确调用。

**Acceptance Scenarios**:

1. **Given** 用户在配置文件中指定了自定义下载源平台，**When** 用户从该平台安装 skill，**Then** 系统调用自定义平台适配器完成下载
2. **Given** 自定义平台提供了自己的 CLI 命令用于下载，**When** 系统调用该平台适配器，**Then** 适配器桥接自定义 CLI 命令，用户无需直接操作自定义 CLI
3. **Given** 用户修改配置文件切换默认下载源，**When** 下一次执行安装操作，**Then** 系统使用新配置的下载源（无需重启）
4. **Given** 用户同时配置了 GitHub 和自定义平台，**When** 搜索 skill，**Then** 系统在所有已配置的源中搜索并汇总结果，标注来源平台

---

### User Story 5 — View Version History (Priority: P2)

用户可以查看 skill 在 GitHub 上的版本历史，了解 skill 的演进过程，按需获取特定历史版本。

**Why this priority**: 版本历史是协作的保障——用户需要知道 skill 发生了什么变化。本地不存储版本历史，所有历史信息从 GitHub 按需获取。

**Independent Test**: 执行版本历史命令，验证返回的版本列表按时间倒序排列，包含版本号和变更摘要。

**Acceptance Scenarios**:

1. **Given** 用户执行版本历史命令，**When** 系统查询 GitHub，**Then** 返回该 skill 的版本历史列表，按时间倒序排列，每条包含版本标识（tag）和变更摘要
2. **Given** 用户想要回退到特定历史版本，**When** 用户执行安装命令并指定版本，**Then** 系统下载指定版本到本地
3. **Given** 用户安装了特定历史版本，**When** 本地已有同名 skill 且版本更新，**Then** 系统提示版本降级警告，用户确认后替换本地内容

---

### Edge Cases

- GitHub 不可用（网络故障、仓库不存在）— 系统应输出明确的错误信息，提示检查网络或仓库地址，已有的本地 skill 不受影响
- 安装的 skill 与本地已有 skill 同名 — 系统应提示冲突，建议使用更新命令而非安装命令
- 安装的 skill 的 SKILL.md 格式不符合规范（frontmatter 解析失败）— 系统应拒绝安装，保留本地状态不变，输出具体格式错误
- 自定义平台适配器执行失败或返回异常 — 系统应输出平台名称和错误信息，建议检查平台配置或认证
- 批量更新时部分失败 — 系统应输出每个 skill 的更新结果（成功/失败/跳过），成功的保留，失败的输出错误原因
- 自定义平台认证过期 — 系统应输出认证指引，提示用户重新认证
- 用户在离线状态下执行安装或更新 — 系统应检测离线状态并提示，不执行网络请求
- 安装的 skill 依赖其他 skill — 系统应提示缺失的依赖 skill，但不自动安装（由用户决定）

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST support installing skills from GitHub via a single command, following the vercel-labs/skills discovery conventions (scan standard directories: root, `skills/`, `skills/.curated/`, agent-specific subdirectories)
- **FR-002**: System MUST support shorthand GitHub identifiers (e.g., `owner/repo`) that resolve to full repository URLs
- **FR-003**: System MUST support installing a specific version of a skill via version specifier (e.g., `@v1.2.0` or `@<commit-hash>`)
- **FR-004**: System MUST make installed skills immediately usable in all configured Agents via the sync mechanism (spec `001-symlink-sync`)
- **FR-005**: System MUST support updating locally installed skills to their latest version from the source platform
- **FR-006**: System MUST detect and warn when a locally modified skill has a newer version available during update
- **FR-007**: System MUST support batch updating all installed skills via a single command
- **FR-008**: System MUST delegate all download operations to configured source platform adapters via a facade interface — the core system handles orchestration only (resolve identifier → invoke adapter → validate → write → sync)
- **FR-009**: System MUST support pluggable download source platforms — users MUST be able to configure custom platforms (e.g., internal registries) via config file
- **FR-010**: System MUST support custom platform adapters that bridge to external CLI tools provided by the platform
- **FR-011**: System MUST support searching skills across all configured source platforms by keyword
- **FR-012**: System MUST support viewing detailed information of a skill from its source platform
- **FR-013**: System MUST support viewing version history of a skill from its source platform (tags, commits, changelog)
- **FR-014**: System MUST warn when installing a historical version that is older than the locally installed version
- **FR-015**: System MUST detect and reject installation when a skill with the same name already exists locally
- **FR-016**: System MUST validate downloaded skill for basic compliance (SKILL.md exists, frontmatter parseable) before writing to local
- **FR-017**: System MUST distinguish between downloaded skills and locally-created skills for proper update detection
- **FR-018**: System MUST support `--dry-run` mode for install and update operations
- **FR-019**: System MUST support `-y` mode for non-interactive execution (Agent integration)
- **FR-020**: System MUST output structured error messages with recovery hints when operations fail
- **FR-021**: System MUST NOT store version history locally — all version information is retrieved on-demand from the source platform
- **FR-022**: System MUST align with the Agent Skills Open Standard so that skills published to GitHub are installable by other tools without requiring sync-skills
- **FR-023**: System MUST share platform configuration with the publish phase (spec `005`) — both phases read from the same config file

### Key Entities

- **Download Source Adapter**: A pluggable component responsible for downloading skill content from a specific platform. Implements a standard interface: search, fetch metadata, download content, list versions. Default: GitHub adapter (following vercel-labs/skills discovery conventions). Custom adapters can bridge to internal platform CLIs or REST APIs.
- **Facade**: The sync-skills install/update/search commands that delegate to configured source adapters. Handles orchestration only: resolve identifier → invoke adapter → validate content → write to local → trigger sync. Does not implement download logic itself.
- **Skill Identifier**: A unique reference to a skill on a source platform. Default format: GitHub shorthand (`owner/repo`), resolvable to full URL. Custom platforms define their own identifier format. Supports version suffix (`@version`).
- **Install Registry**: Minimal local metadata tracking which skills were downloaded (vs. created locally), their source platform, and source identifier. Used for update detection and uninstall. Does NOT store version history.
- **Version Reference**: A pointer to a specific version of a skill on the source platform (e.g., git tag, commit hash, release version). Used for installing specific versions and version history display. Managed entirely by the source platform.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A skill published to GitHub (via spec `005`) is installable by another user with a single command, immediately usable in all configured Agents
- **SC-002**: A skill published to GitHub is installable by `npx skills add` (vercel-labs/skills) without requiring sync-skills — ecosystem interoperability
- **SC-003**: Updating a downloaded skill replaces local content and the change is visible in all Agents immediately
- **SC-004**: Configuring a custom download source platform requires only a config file change — no code modification needed
- **SC-005**: Invalid or corrupted downloads are detected before writing to local — original local state remains intact
- **SC-006**: Network or authentication failures produce error messages with actionable recovery steps
- **SC-007**: Local system does not store any version history — all version information is retrieved on-demand from the source platform
- **SC-008**: Batch update reports per-skill status (updated/already latest/failed) with specific error messages for failures

## Assumptions

- The default download source follows vercel-labs/skills discovery conventions: scan repository root, `skills/`, `skills/.curated/`, `skills/.experimental/`, and agent-specific subdirectories for SKILL.md files
- The Agent Skills Open Standard (maintained by `agentskills/agentskills` GitHub org) defines the canonical SKILL.md format. Downloaded skills are expected to comply with this standard
- The download source adapter interface is a pluggable adapter per Principle VII — custom platforms can implement their own adapter, including bridging to external CLI tools provided by the platform
- The facade pattern means sync-skills only handles orchestration: resolving identifiers, invoking source adapters, validating content, writing files locally, and triggering sync. All network operations are delegated to source adapters
- Local always has the latest version — no local version storage, version preview, or version rollback. Users who need historical versions request them from the source platform on-demand
- The sync mechanism after install/update/uninstall follows the strategy defined in spec `001-symlink-sync`
- GitHub is the default download source because it is the most widely used platform for open-source skill hosting and aligns with the vercel-labs/skills ecosystem
- Shorthand identifier format (`owner/repo`) resolves to a GitHub repository URL by default. Custom platforms define their own identifier resolution rules
- Platform configuration is shared with the publish phase via the same config file at `~/.config/sync-skills/config`
- The system distinguishes between downloaded skills and locally-created skills to enable proper update detection and uninstall behavior. This tracking is minimal (a metadata marker or registry), not a full database
- Authentication to download source platforms is handled by the source adapter. The core system passes through authentication requirements but does not implement auth logic
- Skills installed by sync-skills are stored in the local central directory using the same format as locally-created skills — no special marking in the skill content itself
- The `--dry-run` mode for download operations shows what would be downloaded without making network requests or writing files
