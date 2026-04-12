# Feature Specification: Skill Distribution

**Feature Branch**: `004-skill-distribution`
**Created**: 2026-04-12
**Status**: Draft
**Input**: User description: "对于分发阶段。其实包含两个环节，一个是把本地的skill上传发布到云端。另外一个呢，就是从云端下载别人的skill。这里其实还会和迭代有关，也就是说我本地永远是最新版本，那历史版本我可以通过云端的这个，比如像GI的哈希一样去管理我的或者GI tag去管理我的历史版本。这样我本地就不需要去设计，比如说版本的维护啊，版本的预览之类的版本的储存这样。可以参考这个 https://github.com/vercel-labs/skills"

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Install Skill from Cloud (Priority: P1)

用户通过一条命令从云端安装他人的 skill 到本地，安装后 skill 立即在所有已配置的 Agent 中可用。

**Why this priority**: 从云端获取 skill 是分发功能的核心价值——没有安装能力，skill 生态就只是一个孤岛。

**Independent Test**: 执行安装命令指定一个云端 skill，验证 skill 出现在本地中央目录且通过同步机制对所有 Agent 可见。

**Acceptance Scenarios**:

1. **Given** 用户已初始化同步环境，**When** 用户执行 `sync-skills install <skill-identifier>`，**Then** 系统从云端下载 skill 内容到本地中央目录，并通过同步机制（spec `001-symlink-sync`）使 skill 在所有 Agent 中立即可用
2. **Given** 用户安装了一个 skill，**When** 安装完成，**Then** 系统输出安装结果（skill 名称、版本、安装路径），在 `--json` 模式下输出结构化 JSON
3. **Given** 目标中央目录下已存在同名 skill，**When** 用户执行安装，**Then** 系统提示冲突，建议使用更新命令而非安装命令
4. **Given** 用户提供了简写标识符（如 `owner/name`），**When** 系统解析标识符，**Then** 自动推断为默认分发平台的完整地址并完成安装

---

### User Story 2 — Publish Skill to Cloud (Priority: P1)

用户通过一条命令将本地 skill 发布到云端，发布后其他用户可以通过安装命令获取该 skill。

**Why this priority**: 发布是分发的另一半——用户需要能够分享自己的 skill 才能形成生态。

**Independent Test**: 对一个本地已有的 skill 执行发布命令，验证 skill 在云端可被其他用户安装。

**Acceptance Scenarios**:

1. **Given** 用户本地中央目录中存在一个 skill，**When** 用户执行 `sync-skills publish <skill-name>`，**Then** 系统将 skill 的当前内容上传到云端，输出发布结果（skill 名称、版本、云端地址）
2. **Given** 用户首次发布一个 skill，**When** 系统完成上传，**Then** 云端建立该 skill 的版本历史，初始版本标记为首个提交
3. **Given** 用户发布了 skill，**When** 其他用户通过标识符搜索或安装该 skill，**Then** 能成功找到并获取最新版本
4. **Given** 用户未指定目标平台，**When** 执行发布，**Then** 系统使用配置的默认分发平台

---

### User Story 3 — Update Skill from Cloud (Priority: P1)

当云端的 skill 有新版本时，用户可以拉取更新到本地，本地始终只保留最新版本。

**Why this priority**: 保持本地 skill 为最新是持续使用的基础——不更新就无法获得他人的改进。

**Independent Test**: 在云端更新一个 skill 后，在本地执行更新命令，验证本地 skill 内容与云端最新版本一致。

**Acceptance Scenarios**:

1. **Given** 本地已安装一个来自云端的 skill，**When** 云端发布了新版本且用户执行 `sync-skills update <skill-name>`，**Then** 系统下载最新版本替换本地内容，更新后的 skill 通过同步机制对所有 Agent 可见
2. **Given** 本地已安装的 skill 已是最新版本，**When** 用户执行更新命令，**Then** 系统提示"已是最新版本"，不执行任何写入操作
3. **Given** 本地 skill 已被用户本地迭代修改过，**When** 云端有新版本且用户执行更新，**Then** 系统提示本地有未发布的修改，建议用户先发布或确认覆盖
4. **Given** 用户执行 `sync-skills update --all`，**When** 系统检查所有已安装的云端 skill，**Then** 批量更新所有有新版本的 skill，输出更新摘要

---

### User Story 4 — Search and Discover Skills (Priority: P2)

用户可以通过关键词在云端搜索 skill，查看 skill 的基本信息（名称、描述、标签、作者），决定是否安装。

**Why this priority**: 发现能力让用户了解生态中有哪些可用 skill，但没有安装/发布能力就没有实际价值。

**Independent Test**: 执行搜索命令，验证返回的 skill 列表包含匹配的 skill 及其基本信息。

**Acceptance Scenarios**:

1. **Given** 用户执行 `sync-skills search <keyword>`，**When** 系统查询云端，**Then** 返回匹配的 skill 列表，每条结果包含名称、描述、标签和安装命令
2. **Given** 用户执行 `sync-skills search`，**When** 未提供关键词，**Then** 返回热门或推荐的 skill 列表
3. **Given** 搜索结果为空，**When** 系统完成查询，**Then** 输出"未找到匹配的 skill"并建议调整关键词
4. **Given** 用户执行 `sync-skills info <skill-identifier>`，**When** 系统查询云端，**Then** 返回该 skill 的详细信息（名称、描述、标签、作者、最新版本、安装次数）

---

### User Story 5 — View Skill Version History (Priority: P2)

用户可以查看云端管理的 skill 版本历史，了解 skill 的演进过程，按需获取特定历史版本。

**Why this priority**: 版本历史是协作的保障——用户需要知道 skill 发生了什么变化，但本地不需要存储这些历史。

**Independent Test**: 执行版本历史命令，验证返回的版本列表按时间倒序排列，包含版本号和变更摘要。

**Acceptance Scenarios**:

1. **Given** 用户执行 `sync-skills history <skill-name>`，**When** 系统查询云端，**Then** 返回该 skill 的版本历史列表，按时间倒序排列，每条包含版本号、时间戳和变更摘要
2. **Given** 用户想要获取特定历史版本，**When** 用户执行 `sync-skills install <skill-identifier>@<version>`，**Then** 系统下载指定版本到本地
3. **Given** 用户安装了特定历史版本，**When** 本地已有同名 skill，**Then** 系统提示版本降级警告，用户确认后替换本地内容

---

### User Story 6 — Use Pluggable Distribution Platforms (Priority: P2)

系统默认使用 GitHub 作为分发平台，用户可以通过配置切换到其他分发平台（如内部 Registry、npm 等），支持热插拔切换。

**Why this priority**: 可插拔性是架构原则的体现，但默认平台已能满足大多数需求。

**Independent Test**: 配置一个自定义分发平台，执行安装和发布操作，验证自定义平台被正确调用。

**Acceptance Scenarios**:

1. **Given** 用户未配置自定义分发平台，**When** 执行安装或发布操作，**Then** 系统使用 GitHub 作为默认分发平台
2. **Given** 用户在配置文件中指定了自定义分发平台，**When** 执行安装或发布操作，**Then** 系统调用自定义平台而非 GitHub
3. **Given** 用户修改配置文件切换分发平台，**When** 下一次执行分发操作，**Then** 系统使用新配置的平台（无需重启或重新初始化）
4. **Given** 用户为不同操作配置了不同平台（如发布到内部平台、安装从 GitHub），**When** 执行对应操作，**Then** 系统使用各自配置的平台

---

### User Story 7 — Uninstall Cloud-Installed Skill (Priority: P3)

用户可以卸载通过云端安装的 skill，系统从本地移除 skill 并清理同步关联。

**Why this priority**: 卸载是生命周期管理的完整性要求，但使用频率低于安装、发布和更新。

**Independent Test**: 对一个已安装的云端 skill 执行卸载命令，验证 skill 从本地所有位置移除。

**Acceptance Scenarios**:

1. **Given** 本地存在一个通过云端安装的 skill，**When** 用户执行 `sync-skills uninstall <skill-name>`，**Then** 系统从本地中央目录移除该 skill，并通过同步机制清理所有 Agent 目录中的对应内容
2. **Given** 用户对一个非云端安装的 skill 执行卸载，**When** 系统检测到该 skill 不是从云端安装的，**Then** 提示使用删除命令（`sync-skills --delete`）而非卸载命令
3. **Given** 用户执行卸载但未指定 skill 名称，**When** 系统无默认目标，**Then** 输出已安装的云端 skill 列表供用户选择

---

### Edge Cases

- 云端不可用（网络故障、服务宕机）— 系统应输出明确的错误信息，提示检查网络连接或稍后重试，已有的本地 skill 不受影响
- 发布时 skill 的 frontmatter 不完整（缺少必需字段）— 系统应在发布前验证，拒绝发布不符合规范的 skill 并提示修正
- 安装的 skill 与本地已有 skill 存在同名但内容不同 — 系统应提示冲突，建议用户确认覆盖或取消
- 安装时云端 skill 的内容格式异常（frontmatter 解析失败）— 系统应拒绝安装，保留本地状态不变
- 同时更新大量 skill（`--all`）时部分失败 — 系统应输出每个 skill 的更新结果（成功/失败/跳过），成功的更新保留，失败的输出错误原因
- 分发平台认证过期或无效 — 系统应输出认证指引，提示用户重新认证，错误信息中包含具体的认证步骤
- 用户在离线状态下执行分发操作 — 系统应检测离线状态并提示，不执行网络请求

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST support installing skills from a cloud distribution platform to the local central directory via a single command
- **FR-002**: System MUST support publishing local skills to a cloud distribution platform via a single command
- **FR-003**: System MUST support updating locally installed skills to their latest cloud version, with local always retaining only the latest version
- **FR-004**: System MUST detect and warn when a locally modified skill has a newer cloud version available during update
- **FR-005**: System MUST support batch updating all cloud-installed skills via `--all` flag
- **FR-006**: System MUST support searching skills on the cloud platform by keyword and returning structured results (name, description, tags)
- **FR-007**: System MUST support viewing detailed information of a cloud skill (name, description, tags, author, latest version)
- **FR-008**: System MUST support viewing version history of a cloud skill, managed by the cloud platform using commit-like or tag-like version identifiers
- **FR-009**: System MUST support installing a specific historical version of a skill via version specifier (e.g., `@<version>`)
- **FR-010**: System MUST warn when installing a historical version that is older than the locally installed version
- **FR-011**: System MUST use GitHub as the default distribution platform when no custom platform is configured
- **FR-012**: System MUST support pluggable distribution platforms — users MUST be able to configure custom platforms via config file
- **FR-013**: System MUST delegate all distribution operations to the configured platform via a facade interface — the core system handles orchestration only (resolve identifier → invoke platform → validate → write → sync)
- **FR-014**: System MUST validate skill spec compliance (frontmatter completeness, required fields) before publishing to cloud
- **FR-015**: System MUST detect and reject installation when a skill with the same name already exists locally
- **FR-016**: System MUST support uninstalling cloud-installed skills, removing them from local central directory and all synced Agent directories
- **FR-017**: System MUST support `--dry-run` mode for publish, install, and update operations
- **FR-018**: System MUST support `-y` mode for non-interactive execution (Agent integration)
- **FR-019**: System MUST output structured error messages with recovery hints when distribution operations fail (network errors, auth errors, validation errors)
- **FR-020**: Distribution changes MUST propagate to all Agents immediately via the sync mechanism (spec `001-symlink-sync`)
- **FR-021**: System MUST NOT store version history locally — all version management is delegated to the cloud platform
- **FR-022**: System MUST support shorthand identifiers (e.g., `owner/name`) that resolve to full platform-specific addresses

### Key Entities

- **Distribution Platform**: A pluggable adapter responsible for cloud-based skill storage and retrieval. Implements a standard interface: install (download), publish (upload), update, search, history, uninstall. Default: GitHub. The platform manages version history using its native versioning mechanism (commits, tags, releases).
- **Facade**: The sync-skills distribution commands that delegate to the configured distribution platform. Handles orchestration only: resolve identifier → invoke platform → validate output → write to local → trigger sync. Does not implement distribution logic itself.
- **Skill Identifier**: A unique reference to a skill on a distribution platform. Supports shorthand format (`owner/name`) and full URL format. The facade resolves identifiers to platform-specific addresses.
- **Cloud Version**: A version of a skill stored on the distribution platform, identified by the platform's native versioning mechanism (e.g., git commit hash, git tag, release version). Local system does not store or manage cloud versions.
- **Local State**: The local system tracks which skills were installed from the cloud (vs. created locally) to enable update detection and proper uninstall behavior. This is minimal metadata — no version history stored locally.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A skill published to the cloud is installable by another user within one sync cycle
- **SC-002**: Installing a skill from the cloud makes it immediately usable in all configured Agents (via sync mechanism)
- **SC-003**: Updating a skill from the cloud replaces local content and the change is visible in all Agents immediately
- **SC-004**: The default distribution platform (GitHub) successfully publishes and installs skills without any user platform configuration
- **SC-005**: Switching to a custom distribution platform requires only a configuration file change with no code modification
- **SC-006**: Invalid or incomplete skills are rejected before publishing — no broken skills reach the cloud
- **SC-007**: Network or authentication failures produce error messages with actionable recovery steps
- **SC-008**: Local system does not store any version history — all version information is retrieved on-demand from the cloud platform

## Assumptions

- The distribution platform interface is a pluggable adapter per Principle VII of the project constitution — it is one of the "Distribution platforms" that MUST be pluggable
- The facade pattern means sync-skills only handles orchestration: resolving identifiers, invoking the platform adapter, validating output, writing files locally, and triggering sync. All network operations and version management are delegated to the platform adapter
- Local always has the latest version — there is no local version storage, version preview, or version rollback. Users who need historical versions request them from the cloud on-demand
- The cloud platform manages version history using its native mechanism (git commits/tags for GitHub, equivalents for other platforms). sync-skills does not impose a version history format on the platform
- The sync mechanism after install/update/uninstall follows the strategy defined in spec `001-symlink-sync` — installed skills are placed in the central directory and synced to all Agents
- GitHub is the default distribution platform because it is the most widely accessible and requires no additional account setup for most developers
- Shorthand identifier format (`owner/name`) resolves to a GitHub repository URL by default. Other platforms define their own identifier resolution rules
- Distribution platform configuration is shared with other lifecycle phases via the same config file at `~/.config/sync-skills/config` — consistent with specs `002` and `003`
- The system distinguishes between cloud-installed skills and locally-created skills to enable proper update detection and uninstall behavior. This tracking is minimal (a metadata marker or registry file), not a full version database
- Authentication to distribution platforms is handled by the platform adapter. The core system passes through authentication requirements but does not implement auth logic
- The `--dry-run` mode for distribution operations shows what would be downloaded/uploaded without making network requests or writing files
