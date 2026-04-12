# Feature Specification: Init Configuration

**Feature Branch**: `008-init-configuration`
**Created**: 2026-04-12
**Status**: Draft
**Input**: User description: 初始化配置作为独立阶段，覆盖一次性设置流程：中央目录选择、Agent 检测、创建/迭代引擎选择、Skill 来源平台配置（GitHub、内部平台）、平台认证。配置保存后所有生命周期阶段自动读取。

## User Scenarios & Testing *(mandatory)*

### User Story 1 — First-Time Init Wizard (Priority: P1)

用户首次运行初始化向导，系统引导完成所有一次性配置：中央目录选择、已安装 Agent 检测与选择、创建/迭代引擎选择。配置保存到配置文件，后续所有生命周期阶段自动读取。

**Why this priority**: 初始化是整个工具的入口——没有配置，用户无法使用任何生命周期功能。一次配置、全局生效是核心体验。

**Independent Test**: 运行初始化向导，验证所有配置项被正确保存，后续命令自动读取。

**Acceptance Scenarios**:

1. **Given** 用户首次运行初始化向导，**When** 进入中央目录配置步骤，**Then** 系统建议默认目录（`~/Skills/`），用户可以接受或自定义
2. **Given** 用户已安装 Claude Code 和 Codex CLI，**When** 系统检测已安装的 Agent，**Then** 向导展示检测结果，用户选择要关联的 Agent
3. **Given** 用户在向导中配置引擎，**When** 进入引擎选择步骤，**Then** 展示可选的创建引擎和迭代引擎列表，默认选中 `skill-creator`
4. **Given** 用户接受所有默认配置，**When** 向导完成，**Then** 配置保存到配置文件，输出配置摘要
5. **Given** 用户直接编辑配置文件修改了引擎或 Agent 配置，**When** 下一次执行任何生命周期命令，**Then** 系统读取最新配置并使用新设置

---

### User Story 2 — Configure Source Platforms (Priority: P1)

用户在初始化向导中配置 skill 来源平台（GitHub、内部平台），配置完成后安装和发布命令可以跨平台操作。

**Why this priority**: 来源平台是安装和发布功能的基础——没有平台配置，用户无法下载或发布 skill。

**Independent Test**: 在向导中配置 GitHub 和一个内部平台，验证后续安装命令可以搜索和安装来自两个平台的 skill。

**Acceptance Scenarios**:

1. **Given** 用户在向导中添加 GitHub 作为来源平台，**When** 向导完成，**Then** GitHub 被注册为默认来源平台，安装和发布命令自动可用
2. **Given** 用户在向导中添加内部平台（提供平台地址），**When** 向导完成，**Then** 内部平台被注册为可用来源，搜索和安装命令可以访问该平台
3. **Given** 用户配置了多个来源平台，**When** 执行搜索或安装命令，**Then** 系统在所有已配置的平台中操作
4. **Given** 用户跳过平台配置步骤，**When** 向导完成，**Then** 系统使用默认配置（仅 GitHub），用户后续可通过编辑配置文件添加平台

---

### User Story 3 — Platform Authentication (Priority: P2)

初始化向导引导用户完成各来源平台的认证配置（GitHub token、内部平台凭证），认证信息安全存储，后续操作自动使用。

**Why this priority**: 认证是使用发布和下载功能的前提，但可以在首次使用具体功能时再配置（延迟认证）。

**Independent Test**: 在初始化向导中完成 GitHub 认证，验证后续发布和安装命令可以正常访问 GitHub。

**Acceptance Scenarios**:

1. **Given** 用户在向导中进入 GitHub 认证步骤，**When** 系统引导用户配置访问凭证，**Then** 凭证安全存储，后续发布和安装命令自动使用
2. **Given** 用户配置了多个平台的认证信息，**When** 系统执行跨平台操作，**Then** 自动使用各平台的对应凭证
3. **Given** 某个平台的认证信息过期，**When** 执行涉及该平台的操作，**Then** 系统输出认证过期提示并引导用户重新认证
4. **Given** 用户在向导中跳过认证步骤，**When** 后续执行需要认证的操作，**Then** 系统在运行时提示用户完成认证

---

### User Story 4 — View and Manage Configuration (Priority: P2)

用户可以查看当前完整配置状态，也可以通过重新运行向导或直接编辑配置文件来修改配置。

**Why this priority**: 配置管理是日常维护需求，但查看和修改频率较低。

**Independent Test**: 运行配置查看命令，验证输出包含所有配置项的当前状态。

**Acceptance Scenarios**:

1. **Given** 用户执行配置查看命令，**When** 系统查询，**Then** 输出当前完整配置：中央目录、已关联 Agent、创建/迭代引擎、已配置的来源平台及其认证状态
2. **Given** 用户重新运行初始化向导，**When** 系统检测到已有配置，**Then** 向导显示当前配置值作为默认选项，用户可以逐项修改
3. **Given** 配置文件损坏或格式错误，**When** 执行任何命令，**Then** 系统检测到配置异常并提示用户重新运行初始化

---

### Edge Cases

- 用户在初始化前已有本地 skill 和部分配置 — 初始化应保留现有 skill 和有效配置，仅补充缺失部分
- 多个平台认证同时过期 — 系统应逐个提示，不因一个平台失败而阻塞其他平台的配置
- 配置文件被手动删除 — 下次执行命令时系统应提示"未检测到配置，请运行初始化"
- 用户在非交互环境（CI/CD）中运行 — 系统应支持通过配置文件或环境变量完成初始化，无需交互

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide an interactive init wizard that guides users through one-time configuration: central directory, agent detection, engine selection, and source platform setup
- **FR-002**: System MUST detect installed AI coding agent tools and let users select which to associate
- **FR-003**: System MUST support configuring creation and iteration engines during init, with `skill-creator` as default
- **FR-004**: System MUST support configuring source platforms (GitHub, internal) during init
- **FR-005**: System MUST persist all configuration to a single config file shared across all lifecycle phases
- **FR-006**: System MUST support platform authentication configuration during init, with secure storage of credentials
- **FR-007**: System MUST provide a config view command that displays the current configuration state
- **FR-008**: System MUST allow direct config file editing as an alternative to the init wizard — changes take effect on next command execution
- **FR-009**: System MUST use sensible defaults: `skill-creator` engine, GitHub platform, `~/Skills/` central directory
- **FR-010**: System MUST detect and warn when the config file is corrupted or has invalid format
- **FR-011**: System MUST support re-running the init wizard to modify existing configuration (showing current values as defaults)

### Key Entities

- **Config File**: The persistent configuration stored at `~/.config/sync-skills/config` containing: central directory path, agent tool list, creation/iteration engine selections, source platform configurations (GitHub, internal), and platform credentials. Shared across all lifecycle phases.
- **Init Wizard**: The interactive configuration flow that guides users through first-time setup. Presents sensible defaults, validates inputs, and persists the final configuration.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After init, all lifecycle commands (create, iterate, publish, install, delete) read configuration automatically without requiring additional setup
- **SC-002**: The init wizard completes in under 2 minutes for a typical setup (2 agents, GitHub platform, default engines)
- **SC-003**: Configuring a new source platform requires only adding it to the config file — no code modification needed
- **SC-004**: The config view command accurately displays all configuration items and their current values

## Assumptions

- Init is a one-time setup process. After init, users can modify configuration by re-running the wizard or directly editing the config file
- The config file at `~/.config/sync-skills/config` is the single source of truth for all lifecycle phases
- Platform credentials are stored securely in the config file. The system delegates to platform-specific authentication mechanisms (e.g., GitHub personal access tokens, internal platform API keys)
- Sensible defaults lower the barrier: `skill-creator` as default engine, GitHub as default source platform, `~/Skills/` as default central directory. Advanced options are opt-in
- Users who skip authentication during init can complete it later when they first use a feature that requires it (lazy authentication)
- The init wizard is the primary configuration method for non-technical users. Direct config file editing is available for power users
