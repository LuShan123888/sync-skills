# Feature Specification: Pluggable Skill Iteration

**Feature Branch**: `003-pluggable-skill-iteration`
**Created**: 2026-04-12
**Status**: Draft
**Last Revised**: 2026-04-12
**Input**: User description: "对于迭代模式也是和创建比较类似...支持热插拔...默认使用skill creator...配置在初始化时让用户选择，保存为配置文件..." + 修订：默认按 vercel-labs/skills 行业规范实现，本地永远保存最新版本，历史版本通过 git commit/tag 在云端管理。sync-skills 作为统一聚合层，用户配置一次后无需在本地/GitHub/内部平台之间切换。

## Clarifications

### Session 2026-04-12

- Q: Git commit/tag 和版本管理由谁负责？ → A: Skill（skill-creator）负责全流程：修改内容 + 验证合规 + 版本递增 + git commit/tag，全部在 Skill 内完成。CLI 不需要 post-hook。
- Q: 迭代的 prepare 步骤返回什么给大模型？ → A: 返回一段自然语言指令文本，如"使用 skill-creator 迭代 skill"。CLI 读配置，返回对应的操作建议文本。
- Q: 规范中"系统"指谁？ → A: 明确区分角色——规范中将"系统"替换为具体执行者（Skill 负责 / CLI 负责 / AI 模型负责），避免实现时混淆。
- Q: FR-014 "sync mechanism"怎么改？ → A: 直接描述实际行为，不提及同步。修改通过 symlink 直达中央目录，其他 Agent 通过 symlink 自然读到最新内容。
- Q: US5（Configure Engines During Init）是否移到 008？ → A: 移到 008。引擎配置是 Init 的一部分，003 只引用"从配置读取迭代引擎"，不重复描述配置流程。

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Iterate Skill in Current Agent (Priority: P1)

用户在当前 Agent 中通过自然语言描述对某个已有 skill 的修改需求，工具调用迭代引擎完成修改。无论 skill 来自本地创建、GitHub 下载还是内部平台，迭代体验完全一致。

**Why this priority**: 迭代是 skill 生命周期中最频繁的操作——用户持续改进 skill 内容。这是迭代功能的核心价值。

**Independent Test**: 在 Claude Code 中描述对 `code-review` skill 的修改需求，验证修改后的内容在所有 Agent 中可见。

**Acceptance Scenarios**:

1. **Given** 用户正在使用 Claude Code 且 `code-review` skill 已存在，**When** 用户描述"给 code-review 添加性能检查维度"，**Then** 系统调用迭代引擎修改 `SKILL.md`，修改结果在所有 Agent 中立即可见（通过同步机制）
2. **Given** 用户正在使用 Codex CLI，**When** 用户描述修改需求，**Then** 系统在 Codex 环境中调用迭代引擎，修改通过同步机制同步到所有 Agent
3. **Given** 用户未指定要修改的 skill，**When** 用户描述修改需求，**Then** 系统根据描述内容推断目标 skill，或提示用户指定
4. **Given** 用户修改的是一个从 GitHub 下载的 skill，**When** 迭代完成，**Then** 修改在本地生效，系统标记该 skill 有未推送的变更（供发布阶段使用）

---

### User Story 2 — Version Bump on Iteration (Priority: P1)

每次迭代修改 skill 后，系统自动管理 skill 版本号，遵循语义化版本规范。版本管理通过 git commit/tag 实现，本地永远只保存最新版本，历史版本在 git 远程仓库中管理。

**Why this priority**: 版本管理是迭代的基本纪律——没有版本追踪就无法知道 skill 的演进历史。Git 是行业标准的版本管理方式。

**Independent Test**: 对一个 skill 执行修改，验证 git commit 被创建、版本号按规则更新。

**Acceptance Scenarios**:

1. **Given** skill 当前版本为 `1.0.0`，**When** 用户添加了新功能描述，**Then** 系统将版本号递增为 `1.1.0`（MINOR），并创建 git commit 和 tag
2. **Given** skill 当前版本为 `1.0.0`，**When** 用户修改了现有行为（如改变了审查标准），**Then** 系统将版本号递增为 `1.0.1`（PATCH），并创建 git commit 和 tag
3. **Given** skill 当前版本为 `1.0.0`，**When** 用户移除了某个功能或做了破坏性变更，**Then** 系统将版本号递增为 `2.0.0`（MAJOR），并创建 git commit 和 tag
4. **Given** 用户明确指定版本号，**When** 执行迭代，**Then** 系统使用用户指定的版本号而非自动推断
5. **Given** 迭代完成并创建了 git commit/tag，**When** 用户查看版本历史，**Then** 系统从 git 仓库中获取完整的版本历史列表（按需查询，不存储在本地）

---

### User Story 3 — Validate Skill Spec Compliance (Priority: P1)

迭代完成后，系统验证修改后的 skill 仍然符合 Agent Skills Open Standard 规范（frontmatter 完整性、结构正确性、name 字段与目录名匹配）。

**Why this priority**: 无验证的迭代可能破坏 skill 的可用性——不符合行业标准的 skill 无法被其他工具正确识别和使用。

**Independent Test**: 执行一次可能破坏 frontmatter 的修改，验证系统能检测到并提示修正。

**Acceptance Scenarios**:

1. **Given** 迭代引擎修改了 SKILL.md，**When** 系统执行合规验证，**Then** 检查 frontmatter 字段完整性（name 必填且与目录名匹配、description 必填等，遵循 Agent Skills Open Standard）
2. **Given** 迭代引擎删除了 frontmatter 中的 `description` 字段，**When** 系统执行验证，**Then** 输出警告并提示用户补充缺失字段
3. **Given** 迭代引擎修改后 frontmatter 格式错误（如语法错误），**When** 系统执行验证，**Then** 输出错误信息并拒绝写入，要求修正
4. **Given** 迭代引擎修改了 `name` 字段使其与目录名不一致，**When** 系统执行验证，**Then** 输出错误并提示 name 必须与目录名匹配（行业规范要求）

---

### User Story 4 — Use Default and Custom Iteration Engines (Priority: P2)

系统默认使用 `skill-creator` skill 作为迭代引擎（遵循 vercel-labs/skills 的默认行为），用户可以通过配置替换为自定义引擎，支持热插拔切换。

**Why this priority**: 可插拔性与创建阶段一致，是架构原则的体现，但默认引擎已能满足大多数需求。

**Independent Test**: 配置自定义迭代引擎，执行迭代操作，验证自定义引擎被正确调用。

**Acceptance Scenarios**:

1. **Given** 用户未配置自定义迭代引擎，**When** 执行迭代操作，**Then** 系统使用 `skill-creator` 作为默认迭代引擎
2. **Given** 用户在配置文件中指定了自定义迭代引擎，**When** 执行迭代操作，**Then** 系统调用自定义引擎而非默认引擎
3. **Given** 用户修改配置文件切换迭代引擎，**When** 下一次执行迭代操作，**Then** 系统使用新配置的引擎（无需重启或重新初始化）
4. **Given** 用户为不同 Agent 配置了不同迭代引擎，**When** 在对应 Agent 中执行迭代，**Then** 系统使用该 Agent 对应的引擎

---

### User Story 5 — Configure Engines During Init (Priority: P2)

初始化向导中让用户选择创建引擎和迭代引擎，配置保存到配置文件，可随时查看和修改。初始化同时配置 skill 来源（本地、GitHub、内部平台），实现统一管理。

**Why this priority**: 配置管理是创建和迭代两个功能的共享基础设施，但可以先用默认值再手动调整。

**Independent Test**: 运行初始化向导，验证创建引擎和迭代引擎的选择被正确保存到配置文件。

**Acceptance Scenarios**:

1. **Given** 用户首次运行初始化向导，**When** 进入引擎配置步骤，**Then** 向导展示可选的创建引擎和迭代引擎列表，默认选中 `skill-creator`
2. **Given** 用户在向导中选择了自定义引擎，**When** 向导完成，**Then** 配置保存到配置文件中
3. **Given** 用户直接编辑配置文件修改引擎配置，**When** 下一次执行创建或迭代操作，**Then** 系统读取最新配置，使用新引擎
4. **Given** 用户运行查看配置命令，**When** 执行，**Then** 显示当前配置的创建引擎、迭代引擎和 skill 来源平台信息

---

### User Story 6 — Preview and Confirm Iteration (Priority: P2)

迭代完成后，系统展示修改前后的差异预览，用户确认后才写入文件系统并创建 git commit。

**Why this priority**: 与创建阶段一致的安全要求——修改已有内容比创建新内容风险更高。

**Independent Test**: 执行迭代，检查预览输出是否包含修改前后的差异对比。

**Acceptance Scenarios**:

1. **Given** 迭代引擎生成了修改后的内容，**When** 展示预览，**Then** 用户看到修改前后的差异（新增行、删除行、修改行）
2. **Given** 使用 `--dry-run` 模式，**When** 执行迭代，**Then** 系统仅展示差异预览和合规验证结果，不写入任何文件也不创建 git commit
3. **Given** 使用 `-y` 模式（Agent 集成），**When** 执行迭代，**Then** 系统跳过预览确认，直接写入、自动递增版本号并创建 git commit

---

### Edge Cases

- 迭代引擎执行失败或超时 — 系统应保留原始文件不变，不创建 git commit，输出错误信息和恢复建议
- 用户修改了中央目录中的 skill（非通过迭代引擎） — 同步机制已保证一致性，系统无需额外处理
- 迭代引擎输出了空内容或无效内容 — 系统应拒绝写入，保留原始文件，不创建 git commit
- 两个 Agent 同时迭代同一个 skill — 通过同步机制，后写入的覆盖先写入的；系统应提示冲突风险
- 迭代引擎不可用（未安装或路径错误） — 系统应输出明确的错误信息，提示安装或重新配置
- 迭代修改后的 skill 不符合 Agent Skills Open Standard — 系统应拒绝写入并输出具体的格式错误和修正建议
- Git 仓库状态异常（如存在未提交的修改）— 系统应检测并提示用户先处理 git 状态，避免版本管理混乱

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST delegate skill iteration to a pluggable iteration engine via a facade interface — the core system handles orchestration only (invoke engine → validate → version bump → git commit → sync)
- **FR-002**: System MUST use `skill-creator` as the default iteration engine when no custom engine is configured
- **FR-003**: System MUST support pluggable iteration engines — users MUST be able to configure custom engines in the config file
- **FR-004**: System MUST support per-Agent iteration engine configuration — different Agents can use different engines
- **FR-005**: System MUST automatically manage skill version numbers following semantic versioning (MAJOR.MINOR.PATCH) on each iteration
- **FR-006**: System MUST allow users to explicitly specify the version bump type (MAJOR, MINOR, PATCH) or exact version number
- **FR-007**: System MUST validate the modified SKILL.md for Agent Skills Open Standard compliance (name required and matches directory name, description required, frontmatter syntax) before writing
- **FR-008**: System MUST show a diff preview of changes before writing (modified content vs original content)
- **FR-009**: System MUST support `--dry-run` mode that shows the diff preview and validation results without writing files or creating git commits
- **FR-010**: System MUST support `-y` mode for non-interactive execution (Agent integration)
- **FR-011**: System MUST preserve the original file when iteration engine fails or produces invalid output — no git commit is created for failed iterations
- **FR-012**: System MUST share engine configuration with the creation phase — both phases read from the same config file
- **FR-013**: System MUST support viewing current engine configuration via a dedicated command
- **FR-014**: Iteration changes MUST propagate to all Agents immediately via the sync mechanism (spec `001-symlink-sync`)
- **FR-015**: System MUST create a git commit and version tag for each successful iteration, storing the version history in git rather than in local files
- **FR-016**: System MUST NOT store version history locally — all version information is managed by git and queryable on-demand from the git repository
- **FR-017**: System MUST work identically regardless of skill source (locally created, GitHub-installed, or internal platform-installed) — the iteration experience is unified
- **FR-018**: System MUST mark skills with unpushed changes after iteration, enabling the publish phase (spec `005`) to detect and push pending updates

### Key Entities

- **Iteration Engine**: A pluggable component responsible for modifying existing skill content. Implements a standard interface: receives skill name + modification description + current content, outputs modified SKILL.md content. Default: `skill-creator` skill. The default behavior follows vercel-labs/skills conventions for skill modification.
- **Facade**: The sync-skills iteration command that delegates to the configured iteration engine. Handles orchestration: invoke engine → validate output → bump version → create git commit/tag → write → sync. Does not implement modification logic itself.
- **Version Policy**: The rules governing version number increments. Default: semantic versioning with auto-detection of bump type based on change scope. Overridable by explicit user specification. Version history is stored in git commits/tags, not in local files.
- **Config File**: The persistent configuration containing engine selections for creation and iteration phases, skill source platforms (local, GitHub, internal), and platform credentials. Shared across all lifecycle phases.
- **Unified Skill Identity**: A skill is identified by its name regardless of source. After installation (from any source), iteration works identically. The system tracks the source for publish/update purposes but does not differentiate during iteration.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A modification made to a skill in any Agent is visible in all configured Agents immediately (via sync mechanism)
- **SC-002**: Every iteration automatically produces a valid version number increment following semantic versioning rules and a corresponding git commit/tag
- **SC-003**: The default iteration engine (`skill-creator`) successfully modifies an existing skill without any user configuration
- **SC-004**: Switching to a custom iteration engine requires only a configuration file change with no code modification
- **SC-005**: Invalid output from an iteration engine is detected before writing — the original file remains intact and no git commit is created
- **SC-006**: The `--dry-run` preview accurately shows the diff between original and modified content
- **SC-007**: Iteration works identically for skills from any source (local, GitHub, internal platform) — users do not need to know or switch between platforms
- **SC-008**: Modified SKILL.md always complies with Agent Skills Open Standard after successful iteration

## Assumptions

- The `skill-creator` skill supports both creation and iteration modes — it can generate new SKILL.md content and modify existing content based on natural language descriptions
- The iteration engine interface is a pluggable adapter per Principle VII of the project constitution — it is one of the "Creation tools" that MUST be pluggable, with iteration as a mode of creation
- The facade pattern means sync-skills only handles orchestration: invoking the engine, validating output, bumping version, creating git commits/tags, writing files, and triggering sync. All creative/modification work is delegated to the engine
- Version management follows git conventions: each successful iteration creates a git commit with a version tag. The local working directory always contains the latest version. Historical versions are accessible via git log and git tag
- Version auto-detection follows these rules: new capability → MINOR, behavior change → PATCH, removal/breaking change → MAJOR. Users can override with explicit specification
- The Agent Skills Open Standard (maintained by `agentskills/agentskills` GitHub org, adopted by Anthropic and Vercel) defines the canonical SKILL.md format. Iteration output MUST comply with this standard
- sync-skills is a unified aggregation layer — it manages skills across local storage, GitHub (industry standard via vercel-labs/skills), and internal platforms. Users configure once and operate seamlessly across all sources
- The config file is shared between creation and iteration phases — engine configuration is unified. Skill source platforms (GitHub, internal) are also configured here
- The sync mechanism relies on the strategy defined in spec `001-symlink-sync` — modifications to the central file are immediately visible everywhere
- Iteration engine selection during init is optional — users can skip and use defaults, then configure later by editing the config file
- After iteration, skills that originated from GitHub or internal platforms are marked with unpushed changes, enabling the publish phase to detect and push pending updates
