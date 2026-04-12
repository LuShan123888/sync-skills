# Feature Specification: Pluggable Skill Creation

**Feature Branch**: `002-pluggable-skill-creation`
**Created**: 2026-04-12
**Status**: Draft
**Last Revised**: 2026-04-12
**Input**: User description: "对于创建阶段，我希望用户是通过这个工具可以直接在当前Agent所引用的skill目录下去做创建..."

## Clarifications

### Session 2026-04-12

- Q: 创建目标位置（基于 001 clarify 的中心化架构）？ → A: 写入中央目录（如 `~/Skills/Code/new-skill/`），然后由 001 的 symlink 机制建立关联。不再有"同步"概念。
- Q: 创建引擎接口契约？ → A: CLI 不是独立的创建引擎。CLI + Skill 紧密耦合——CLI 负责硬编码工作流（读配置、返回指令、维护 symlink），Skill（如 skill-creator）负责与大模型协作的智能创建。流程：大模型调用 CLI 获取指令 → 大模型按指令调用 Skill 创建 → 大模型调用 CLI 建立 symlink。脱离 Skill，CLI 的创建功能非常有限。
- Q: CLI+Skill 协作模式是否适用于所有生命周期阶段？ → A: 统一适用。所有阶段（创建、迭代、发布、下载、删除、Init）都是 CLI（配置+symlink+平台操作）+ Skill（智能协作）模式。CLI/Skill 边界在所有阶段保持一致。
- Q: "当前 Agent"的概念是否还有意义？ → A: 有意义，但用途改变。对 Agent 屏蔽中央目录概念——Agent 只在自己的 skill 目录下操作（标准行为）。CLI 作为钩子：创建前 CLI 返回指令，创建后 Agent 通知 CLI，CLI 负责搬到中央目录+建立 symlink。Agent 体验：创建前问一下 CLI，创建后通知一下 CLI，其余全是 CLI 的事。
- Q: 双步钩子模式是否适用于所有阶段？ → A: 不是。只有创建需要双步钩子（prepare+done）。迭代仅需 prepare（返回迭代引擎建议），修改通过 symlink 直达中央目录。发布/下载/删除都是单次 CLI 调用，无需 AI 介入。各阶段交互模式不同，不要为了统一而增加不必要的调用次数和大模型负担。
**Input**: User description: "对于创建阶段，我希望用户是通过这个工具可以直接在当前Agent所引用的skill目录下去做创建...做成桥接、门面模式...skill creator这个skill可以作为默认的创建方式，用户也可以指定自己实现的skill creator..."

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Create Skill in Current Agent (Priority: P1)

用户在当前使用的 AI 编码工具中，通过自然语言描述想要创建的 skill，工具在当前 Agent 的 skill 目录下直接创建，创建完成后立即可用。

**Why this priority**: 这是创建功能的核心价值——在当前 Agent 中创建后立即可用，无需切换工具或手动移动文件。

**Independent Test**: 在 Claude Code 中触发创建命令，描述一个 skill 需求，验证 skill 出现在 `~/.claude/skills/` 下且可被 Claude Code 识别。

**Acceptance Scenarios**:

1. **Given** 用户正在使用 Claude Code 且已初始化同步，**When** 用户通过自然语言描述要创建一个"代码审查"skill，**Then** 系统在 `~/.claude/skills/code-review/` 下创建包含 `SKILL.md` 的 skill 目录，Claude Code 立即可以识别和使用该 skill
2. **Given** 用户正在使用 Codex CLI，**When** 用户描述要创建一个 skill，**Then** 系统在 Codex 的 skill 目录下创建，Codex 立即可用
3. **Given** 当前 Agent 的 skill 目录通过软链接与中央目录关联，**When** 用户创建了新 skill，**Then** 系统同时在中央目录中建立对应条目（或软链接），其他 Agent 可通过同步获取该 skill

---

### User Story 2 — Auto-Sync After Creation (Priority: P1)

skill 创建完成后，自动建立与中央目录的关联，使该 skill 对其他 AI 编码工具也可用。

**Why this priority**: 与 US1 同等重要——创建后不同步到中央目录就失去了跨 Agent 分发的能力。

**Independent Test**: 在 Agent A 中创建 skill，检查中央目录是否出现对应条目，检查其他 Agent 是否可以访问。

**Acceptance Scenarios**:

1. **Given** 使用软链接同步策略，**When** 在 Agent A 的目录下创建了新 skill，**Then** 中央目录中出现该 skill 的条目（或反向链接），下次同步后所有 Agent 可见
2. **Given** 使用配置重定向策略的 Agent B，**When** Agent A 中创建了新 skill 并同步到中央目录，**Then** Agent B 无需额外操作即可发现并使用该 skill
3. **Given** 新 skill 的 frontmatter 中指定了 `tools: [claude, codex]`，**When** 创建完成并同步，**Then** 只有 Claude Code 和 Codex 的目录中出现该 skill

---

### User Story 3 — Use Default Creator (Priority: P1)

系统默认使用 `skill-creator` skill 作为创建引擎，它能理解用户需求、读取上下文、并按照 skill 规范生成标准化的 SKILL.md。

**Why this priority**: 默认创建体验必须开箱即用，用户无需配置即可获得高质量的 skill 创建能力。

**Independent Test**: 不做任何创建器配置，直接描述一个 skill 需求，验证 `skill-creator` 被调用并生成符合规范的 SKILL.md。

**Acceptance Scenarios**:

1. **Given** 用户未配置自定义创建器，**When** 用户描述要创建一个 skill，**Then** 系统自动调用 `skill-creator` 作为创建引擎
2. **Given** `skill-creator` 已安装且可用，**When** 创建过程完成，**Then** 生成的 SKILL.md 包含完整的 frontmatter（tags、description、tools 字段）和结构化的 skill 内容
3. **Given** `skill-creator` 未安装，**When** 用户尝试创建 skill，**Then** 系统输出明确的错误信息，提示安装 `skill-creator` 或配置替代创建器

---

### User Story 4 — Use Custom Creator (Priority: P2)

用户可以配置自定义的 skill 创建器（如自己实现的创建工具或特定 Agent 的原生创建能力），系统通过门面模式统一调度。

**Why this priority**: 可扩展性是重要特性，但默认创建器已能满足大多数需求。

**Independent Test**: 配置一个自定义创建器，创建 skill 时验证自定义创建器被正确调用。

**Acceptance Scenarios**:

1. **Given** 用户在配置中指定了自定义创建器 `my-skill-creator`，**When** 用户创建 skill，**Then** 系统调用 `my-skill-creator` 而非默认的 `skill-creator`
2. **Given** 用户为不同的 Agent 配置了不同的创建器（Claude Code 用 A，Codex 用 B），**When** 在对应 Agent 中创建 skill，**Then** 系统使用该 Agent 对应的创建器
3. **Given** 用户配置了 Claude Code 的原生 `/skill` 命令作为创建器，**When** 在 Claude Code 中创建 skill，**Then** 系统委托给 Claude Code 的原生创建流程

---

### User Story 5 — Create with Context (Priority: P2)

创建器可以读取当前项目的上下文信息（如项目类型、技术栈、目录结构），生成更贴合项目需求的 skill。

**Why this priority**: 上下文感知提升创建质量，但基础创建不依赖此功能。

**Independent Test**: 在一个 Go 项目中创建 skill，验证生成的 SKILL.md 内容与 Go 项目相关。

**Acceptance Scenarios**:

1. **Given** 用户在 Go 项目目录下创建 skill，**When** 创建器读取上下文，**Then** 生成的 skill 内容包含 Go 相关的命令示例和约定
2. **Given** 用户在配置中指定了上下文文件（如 `CLAUDE.md`），**When** 创建器工作，**Then** 读取并遵循该上下文文件中的编码规范和约定
3. **Given** 用户未提供额外上下文，**When** 创建器工作，**Then** 生成通用的、符合基本 skill 规范的内容

---

### User Story 6 — Preview and Confirm Creation (Priority: P2)

创建完成后，系统展示生成的 skill 内容预览，用户确认后才写入文件系统。

**Why this priority**: 创建是不可逆的文件操作，预览机制符合安全原则。

**Independent Test**: 触发创建，检查预览输出是否包含 SKILL.md 的完整内容，确认后才写入。

**Acceptance Scenarios**:

1. **Given** 创建器生成了 skill 内容，**When** 展示预览，**Then** 用户看到完整的 SKILL.md 内容（包括 frontmatter 和正文），可以选择确认或取消
2. **Given** 使用 `--dry-run` 模式，**When** 创建 skill，**Then** 系统仅展示将要创建的内容和目标路径，不写入任何文件
3. **Given** 使用 `-y` 模式（Agent 集成），**When** 创建 skill，**Then** 系统跳过预览确认，直接写入文件

---

### Edge Cases

- 创建器执行失败或超时 — 系统应输出错误信息并建议用户检查创建器配置
- 目标目录已存在同名 skill — 系统应报错，提示用户先删除或使用不同名称
- 创建器生成了不符合规范的 SKILL.md（缺少必要字段） — 系统应验证并提示用户修正
- 用户在非 Agent 环境下（如纯终端）触发创建 — 系统应使用默认创建器，在中央目录中创建
- 创建器需要的上下文文件不存在 — 系统应使用可用上下文继续创建，输出警告而非报错

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST support creating skills directly in the current Agent's skill directory for immediate use
- **FR-002**: System MUST automatically establish association with the central skill directory after creation, enabling cross-agent sync
- **FR-003**: System MUST use `skill-creator` as the default creation engine when no custom creator is configured
- **FR-004**: System MUST support pluggable creation engines — users MUST be able to configure custom creators via configuration file
- **FR-005**: System MUST support per-Agent creator configuration — different Agents can use different creation engines
- **FR-006**: System MUST delegate to the creation engine via a facade interface — the core system invokes the creator but does not implement creation logic itself
- **FR-007**: System MUST validate the generated SKILL.md for basic compliance (contains frontmatter, has required fields) before writing
- **FR-008**: System MUST support `--dry-run` mode that previews the generated skill without writing files
- **FR-009**: System MUST support `-y` mode for non-interactive execution (Agent integration)
- **FR-010**: System MUST detect and reject creation when a skill with the same name already exists in the target directory
- **FR-011**: System MUST pass relevant context (project type, working directory, configuration files) to the creation engine
- **FR-012**: System MUST output structured error messages with recovery hints when creation fails (per Principle II)
- **FR-013**: System MUST respect skill-level `tools` field when syncing newly created skills to other Agents

### Key Entities

- **Creation Engine**: A pluggable component responsible for generating skill content. Implements a standard interface: receives user description + context, outputs SKILL.md content. Default: `skill-creator` skill.
- **Facade**: The sync-skills creation command that delegates to the configured creation engine. Does not implement creation logic itself — only orchestration (invoke creator → validate → write → sync).
- **Central Directory**: The single source of truth directory (e.g., `~/Skills/`) where skills are organized by category.
- **Agent Skill Directory**: The current Agent's skill directory (e.g., `~/.claude/skills/`) where the skill is created for immediate use.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A skill created in any Agent is immediately usable in that Agent without running a sync command
- **SC-002**: After creation, the skill becomes available in all configured Agents within one sync cycle
- **SC-003**: The default creation engine (`skill-creator`) generates a valid SKILL.md with frontmatter on first use, without any user configuration
- **SC-004**: Switching to a custom creation engine requires only a configuration change, no code modification
- **SC-005**: The `--dry-run` preview accurately reflects the skill content and target path that would be created
- **SC-006**: Creation failure produces an error message with actionable recovery steps (install creator, fix config, etc.)

## Assumptions

- The `skill-creator` skill is an existing, installable skill that understands natural language descriptions and generates SKILL.md content following the skill specification
- The creation engine interface is a pluggable adapter per Principle VII of the project constitution — it is one of the "Creation tools" that MUST be pluggable
- The facade pattern means sync-skills only handles orchestration: invoking the creator, validating output, writing files, and triggering sync. All creative work (understanding requirements, generating content) is delegated to the creation engine
- "Current Agent" is determined by the environment where sync-skills is invoked (e.g., when invoked from within Claude Code, the current Agent is Claude Code)
- Creation engines receive context via a standardized interface — the exact context fields (project type, config files, etc.) are defined by the interface, not by individual engines
- The sync mechanism after creation follows the symlink-based strategy defined in spec `001-symlink-sync`
