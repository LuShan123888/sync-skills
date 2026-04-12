# Feature Specification: Symlink-Based Skill Sync

**Feature Branch**: `001-symlink-sync`
**Created**: 2026-04-12
**Status**: Draft
**Last Revised**: 2026-04-12
**Input**: User description: "对于初始化阶段，我希望建立一个同步机制..." + 修订：架构重构为完全中心化——中央目录是唯一副本，所有 Agent 工具通过 config-redirect 直接读取中央目录，不存在 symlink 同步机制。

## Clarifications

### Session 2026-04-12

- Q: 同步触发机制（file watcher vs 手动 sync vs 混合模式）？ → A: 不存在同步机制。架构重构为完全中心化——中央目录是唯一副本，所有 Agent 工具通过 symlink 或 config-redirect 直接读取中央目录，所有修改（创建、迭代、删除）直接操作中央目录。无 sync 命令。
- Q: 不支持 config-redirect 的 Agent 工具如何处理？ → A: 默认统一使用 symlink。 symlink 通用、透明、不依赖工具配置。 config-redirect 仅作为 symlink 不可用时的 fallback（如 Windows 无管理员权限），不是首选策略。
- Q: 为什么要用 config-redirect 而不是 symlink？ → A: 去掉 config-redirect 概念，统一使用 symlink。Symlink 透明可读写，完美匹配"中央目录是唯一副本"的架构。symlink 不可用时（如 Windows 无管理员权限）报错并提示解决方案。
- Q: 规范定位——是否合并到 Init Configuration？ → A: 不合并。Symlink 关联是贯穿整个生命周期的能力（创建、下载、删除、新增 Agent 都涉及），不是一次性初始化。保留 001 作为独立规范，但需要重写。
- Q: Agent A 修改后 Agent B 是否立即可见？ → A: 即时可见（文件系统自然行为）。新会话自动读到最新内容，已加载的会话取决于工具自身缓存行为，sync-skills 不负责。
- Q: 系统是否需要自动清理断链？ → A: 需要。在 symlink 相关操作时（新建 Agent 关联、状态检查）顺带清理断链，避免 Agent 工具报错或显示异常 skill。

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Initialize Symlink Sync (Priority: P1)

用户首次运行初始化命令，系统自动检测已安装的 AI 编码工具，为每个工具选择最优的链接策略（软链接或配置重定向），并在中央目录和各工具目录之间建立关联。

**Why this priority**: 这是所有后续功能的基础——没有初始化就没有链接关系，其他场景都无法工作。

**Independent Test**: 运行初始化命令后，检查各工具的 skill 目录是否正确指向中央目录中的 skill 文件。

**Acceptance Scenarios**:

1. **Given** 用户已安装 Claude Code 和 Codex CLI，**When** 用户运行初始化命令，**Then** 系统检测到这两个工具，在各自 skill 目录下创建指向中央目录的软链接，并输出已建立链接的摘要
2. **Given** 用户已安装一个支持自定义 skill 目录的工具（如 OpenClaw），**When** 用户运行初始化命令，**Then** 系统识别该工具支持配置重定向，配置其指向中央目录，不创建软链接
3. **Given** 用户同时安装了支持配置重定向和不支持的工具，**When** 用户运行初始化命令，**Then** 系统对每个工具使用最优策略，摘要中明确标注每个工具使用的是"配置重定向"还是"软链接"
4. **Given** 中央目录中已有 10 个 skill，**When** 用户运行初始化命令，**Then** 所有 10 个 skill 在各工具中可用

---

### User Story 2 — Real-Time Sync on Edit (Priority: P1)

用户在任何一个 AI 编码工具中修改了 skill 的内容，修改立即对所有其他工具可见，无需手动执行同步命令。

**Why this priority**: 这是软链接方案的核心价值——零延迟同步。如果编辑后需要手动同步，则与复制方案无本质区别。

**Independent Test**: 在工具 A 中编辑 skill，切换到工具 B，确认看到的是编辑后的最新内容。

**Acceptance Scenarios**:

1. **Given** 初始化已完成，skill 通过软链接关联，**When** 用户在 Claude Code 中编辑了 `code-review` skill 的 SKILL.md，**Then** 在 Codex CLI 中立即看到修改后的内容，无需执行任何同步命令
2. **Given** 初始化已完成，skill 通过配置重定向关联，**When** 用户在支持配置重定向的工具中编辑了 skill，**Then** 在所有其他工具中立即看到修改后的内容
3. **Given** 用户在工具 A 中创建了一个新文件（如 skill 内的脚本），**When** 该新文件出现在中央目录中，**Then** 所有通过软链接关联的工具都能访问该文件

---

### User Story 3 — Add New Skill (Priority: P1)

用户在中央目录中创建了一个新的 skill，系统自动将该 skill 链接到所有已配置的 AI 编码工具。

**Why this priority**: 与编辑场景同等重要——新增 skill 也应零延迟对所有工具可见。

**Independent Test**: 在中央目录创建新 skill，检查所有工具目录是否出现对应的软链接。

**Acceptance Scenarios**:

1. **Given** 初始化已完成，**When** 用户在中央目录的 `Code/` 分类下创建了 `new-skill/SKILL.md`，**Then** 系统自动在各工具的 skill 目录下创建指向该 skill 的软链接
2. **Given** 初始化已完成，某个工具使用配置重定向策略，**When** 用户创建了新 skill，**Then** 该工具无需额外操作即可发现新 skill（因为它直接读取中央目录）
3. **Given** 新 skill 的 frontmatter 中 `tools` 字段指定了仅同步到特定工具，**When** 系统处理新 skill，**Then** 只在指定的工具目录中创建链接

---

### User Story 4 — Delete Skill (Priority: P2)

用户删除中央目录中的一个 skill，系统自动清理所有工具目录中的对应软链接，不留下断链。

**Why this priority**: 删除是日常操作的另一半，但不影响核心的编辑同步体验。

**Independent Test**: 删除中央目录中的 skill，验证所有工具目录中无断链残留。

**Acceptance Scenarios**:

1. **Given** 初始化已完成且 skill 已链接到 3 个工具，**When** 用户删除了中央目录中的 `code-review` skill，**Then** 3 个工具目录中的对应软链接全部被移除
2. **Given** 某个工具目录中的软链接被外部操作删除，**When** 系统执行同步检查，**Then** 系统识别到缺失的链接并重新创建
3. **Given** 用户误删了中央目录中的 skill，**When** 执行带 `--dry-run` 的删除同步，**Then** 系统显示将要清理的链接列表但不执行，用户确认后才真正清理

---

### User Story 5 — Install New Agent Tool (Priority: P2)

用户安装了一个新的 AI 编码工具，运行同步命令后系统自动为新工具建立链接关系。

**Why this priority**: 工具安装是低频事件，但自动化处理可以避免手动配置的遗漏。

**Independent Test**: 安装新工具后运行同步，验证新工具的 skill 目录正确建立链接。

**Acceptance Scenarios**:

1. **Given** 初始化已完成（关联了 2 个工具），用户新安装了 Gemini CLI，**When** 用户运行同步命令，**Then** 系统检测到新工具，为其创建所有 skill 的软链接
2. **Given** 新安装的工具支持配置重定向，**When** 用户运行同步命令，**Then** 系统配置该工具指向中央目录而非创建软链接

---

### User Story 6 — Handle Unsupported Tool (Priority: P3)

某个 AI 编码工具既不支持自定义 skill 目录，也不支持软链接（或系统无权限创建软链接），系统提供清晰的错误提示和替代方案。

**Why this priority**: 边界场景，影响少数用户，但需要有优雅的降级处理。

**Independent Test**: 模拟一个不支持软链接且无自定义目录支持的工具，验证系统给出明确的错误信息和替代建议。

**Acceptance Scenarios**:

1. **Given** 某个工具不支持配置重定向，**When** 系统尝试创建软链接但因权限不足失败，**Then** 系统输出明确的错误信息，说明权限要求和解决方法，其他工具的链接不受影响
2. **Given** 某个工具在平台上不支持符号链接（如 Windows 非管理员模式），**When** 系统检测到此限制，**Then** 系统建议用户以管理员身份运行或提供复制模式的替代方案

---

### Edge Cases

- 中央目录被移动或重命名后，所有软链接断裂——系统应能检测并提示用户重新初始化
- 用户在工具目录侧（而非中央目录）直接创建了一个 skill——系统应识别到这是一个非链接的本地 skill 并给出提示
- 中央目录中不同分类下存在同名 skill——系统应报错，因为平铺到工具目录时会冲突
- 软链接目标路径包含空格或特殊字符——系统应正确处理转义

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST support a central skill directory as the single source of truth for all skills
- **FR-002**: System MUST detect installed AI coding agent tools and determine each tool's linking strategy (symlink vs config redirect)
- **FR-003**: System MUST create symbolic links from agent tool skill directories to the central skill directory for tools that do not support custom skill paths
- **FR-004**: System MUST configure agent tools to read directly from the central directory for tools that support custom skill paths
- **FR-005**: System MUST automatically create links for new skills added to the central directory
- **FR-006**: System MUST automatically remove links when skills are deleted from the central directory
- **FR-007**: System MUST detect and repair broken symbolic links during sync operations
- **FR-008**: System MUST respect skill-level selective sync rules (e.g., `tools` field in frontmatter) when creating links
- **FR-009**: System MUST show a preview of all link operations before executing (supporting `--dry-run` mode)
- **FR-010**: System MUST support non-interactive execution mode (via `-y` flag) for AI agent integration
- **FR-011**: System MUST detect duplicate skill names across categories in the central directory and report them as errors
- **FR-012**: System MUST provide a status command that shows the linking state of all skills across all tools
- **FR-013**: System MUST handle the mixed strategy scenario where some tools use symlinks and others use config redirects transparently

### Key Entities

- **Central Directory**: The single source of truth directory containing all skills organized by category (e.g., `~/Skills/Code/code-review/`, `~/Skills/Lark/`).
- **Agent Tool**: An AI coding tool that consumes skills (e.g., Claude Code, Codex CLI, Gemini CLI). Each has a skill directory and a linking strategy.
- **Linking Strategy**: The method used to make central skills available to an agent tool — either "symlink" (create symbolic links) or "config-redirect" (configure tool to read from central directory).
- **Skill**: A directory containing a `SKILL.md` file, optionally with additional assets. Identified by its leaf directory name.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After initialization, all existing skills are accessible from all configured agent tools within 1 second (no copy latency)
- **SC-002**: An edit made to a skill in any agent tool is visible in all other agent tools immediately (same file system read)
- **SC-003**: Adding a new skill to the central directory makes it available in all agent tools without running a sync command (for symlink strategy) or within one sync cycle (for config-redirect strategy)
- **SC-004**: Deleting a skill from the central directory removes all associated links with zero broken links remaining
- **SC-005**: The `--dry-run` preview accurately reflects all link operations that would be performed
- **SC-006**: The status command reports the correct linking state (linked, missing, broken) for every skill across every tool

## Assumptions

- The central skill directory defaults to `~/Skills/` with nested category structure (e.g., `~/Skills/Code/code-review/`), consistent with the current project convention
- Agent tools follow the industry convention of storing skills in `~/.<tool-name>/skills/` (e.g., `~/.claude/skills/`, `~/.codex/skills/`)
- Most agent tools on macOS and Linux support symbolic links; Windows may require administrator privileges
- A tool's linking strategy (symlink vs config-redirect) is a property of the tool, not user-configurable — the system auto-detects and applies the appropriate strategy
- The linking strategy interface is pluggable per Principle VII of the project constitution — future strategies (e.g., file copy fallback) can be added as plugins
- Skills are identified by their leaf directory name — the category path is stripped when linking to flat agent tool directories
