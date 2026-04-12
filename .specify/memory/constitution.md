<!--
Sync Impact Report
- Version change: 2.1.0 → 2.2.0
- Modified principles:
  - II. Agent-First Design → renamed to II. Agent-First Interface; materially expanded with JSON output, error recovery, stable command tree, context inference, and automation suitability requirements
- Added principles: None
- Removed principles: None
- Added sections: None
- Removed sections: None
- Templates requiring updates:
  - .specify/templates/plan-template.md: ✅ no changes needed (generic constitution check gate)
  - .specify/templates/spec-template.md: ✅ no changes needed (technology-agnostic)
  - .specify/templates/tasks-template.md: ✅ no changes needed (technology-agnostic)
- Follow-up TODOs (carried forward from 2.0.0):
  - ⚠ CLAUDE.md needs rewrite for TypeScript project structure, commands, and conventions
  - ⚠ README.md needs rewrite for TypeScript installation (npx) and development (npm)
  - ⚠ DESIGN.md §2 needs update for TypeScript architecture + pluggable design
  - ⚠ DESIGN.md §7 needs new changelog entry for this constitution change
  - ⚠ pyproject.toml → package.json migration (existing Python codebase)
  - ⚠ tests/ → rewrite in TypeScript with Vitest
-->

# sync-skills Constitution

sync-skills is a skill lifecycle management platform. It covers the full journey of AI coding agent skills — creation, iteration, and distribution — across multiple tools, lowering the barrier for users to leverage skills for productivity gains.

## Core Principles

### I. Full-Lifecycle Management

The project MUST address the complete skill lifecycle. No phase may be neglected or treated as secondary. Each phase MUST be independently pluggable (see Principle VII).

- **Creation**: Users MUST be able to create new skills with minimal friction (zero-config defaults, interactive init, SKILL.md-first workflow).
- **Iteration**: Skills MUST evolve in-place across any tool. Edits made in one location MUST propagate to all others (bidirectional sync, conflict resolution).
- **Distribution**: Skills MUST reach every configured target tool reliably and consistently (force sync, content hashing, post-sync verification).
- Feature proposals MUST articulate which lifecycle phase they serve. Cross-phase features (e.g., "edit in Claude, sync to Codex") MUST preserve lifecycle coherence.

**Rationale**: A sync-only tool leaves creation and iteration to manual processes, fragmenting the user experience. Covering the full lifecycle ensures users never need to leave the tool to manage their skills.

### II. Agent-First Interface

Every interface (CLI, Skill, MCP) MUST be designed for AI agent consumption as a primary use case, not an afterthought.

- **Structured output**: All commands MUST support `--json` output mode by default. JSON output MUST include all fields needed for programmatic consumption (exit codes, error types, affected paths, suggestion strings).
- **Error recovery**: Error messages MUST include actionable hints — suggested commands to fix the issue, authentication guidance when applicable, and references to relevant documentation. An agent encountering an error MUST be able to construct a recovery action from the error output alone.
- **Stable command tree**: The command structure MUST be consistent across CLI, Skill (SKILL.md), and MCP interfaces. Adding a command to one interface MUST be reflected in all others. Capability boundaries MUST be identical — if the CLI can do something, the Skill and MCP MUST expose the same capability.
- **Context inference**: The tool MUST support URL recognition and context-based parameter inference. When a user provides a URL, file path, or partial identifier, the tool MUST resolve it to the correct resource without requiring the agent to manually parse or transform the input.
- **Automation suitability**: Every command MUST be suitable for scripting and multi-step agent workflows. No command MAY rely on interactive prompts as the only mode — non-interactive flags (`-y`, `--json`) MUST be available for all operations.
- **Help text**: `--help` output MUST use English with structured examples. Runtime output (Chinese) and help text (English) serve different audiences; both MUST be maintained.

**Rationale**: AI agents are the primary operators. They consume CLI output, follow error hints, chain commands in multi-step workflows, and switch between interfaces (CLI ↔ Skill ↔ MCP). If the interface is designed for humans first and agents second, agents will fail on edge cases that humans handle intuitively. Agent-first means: structured, self-healing, consistent, and composable.

### III. Safety by Default

No destructive operation MAY execute without user awareness.

- All write operations MUST display a preview diff before execution.
- `--dry-run` MUST exist for every mutating command (sync, force, delete).
- Content-aware comparison (MD5 hashing) MUST skip identical files to avoid unnecessary overwrites.
- Delete operations MUST require explicit opt-in (`--delete` flag + confirmation or `-y`).
- Force mode MUST NOT silently overwrite; it MUST show what will be added, updated, and removed.

**Rationale**: Users manage skills across 4+ directories. A mistaken sync or delete is hard to undo. Preview-first design prevents data loss.

### IV. Content Integrity

Sync operations MUST guarantee content consistency across all directories.

- Directory-level MD5 hashing (excluding hidden files) is the authoritative content comparison method.
- Skill directories are atomic units: all files within a skill directory MUST be copied or replaced as a whole.
- Post-sync verification MUST confirm content hashes match across all synchronized directories.
- Hidden files (`.DS_Store`, etc.) MUST be excluded from hashing and filtered during scanning.

**Rationale**: Partial or inconsistent syncs defeat the purpose of the tool. Atomic operations and hash verification ensure reproducible, trustworthy state across all targets.

### V. Approachability

The tool MUST lower the barrier for users to benefit from skills. Complexity is a cost borne by the user.

- Zero-install execution via `npx sync-skills` MUST be the primary distribution method — no pre-installation, no residue, always the latest version.
- Zero-configuration defaults MUST work out of the box (`sync-skills init` auto-detects tools).
- Natural language MUST be a first-class interaction method (via SKILL.md agent integration).
- CLI knowledge MUST NOT be required — users who prefer GUI or natural language MUST have an equally viable path.
- Configuration MUST use sensible defaults; advanced options MUST be opt-in, not opt-out.
- Error messages MUST suggest actionable next steps rather than dumping technical details.

**Rationale**: The project's mission is to make skills accessible. `npx` embodies this principle: users run `npx sync-skills` with zero setup, no global installation, and no cleanup needed. Every design decision should be evaluated by asking: "Does this make it easier for a non-technical user to manage their skills?"

### VI. User-Scenario Acceptance

User-facing test cases are the authoritative acceptance criteria. Tests MUST mirror what users do, not how code is structured.

- Each user scenario defined in DESIGN.md Section 3 MUST have corresponding test cases that verify the end-to-end outcome.
- Tests MUST assert on observable behavior (CLI output, file system state, exit codes), not on internal implementation details (private functions, intermediate data structures).
- Test suites MUST be organized by user scenario (e.g., `user-scenarios.test.ts`), not by code module. Scenario-level tests serve as living documentation of expected behavior.
- Edge cases and error scenarios from DESIGN.md Section 4 MUST have dedicated test coverage.
- New features MUST add user-scenario acceptance tests before or alongside implementation tests. A feature without scenario-level coverage is incomplete.

**Rationale**: Tests organized around user scenarios remain stable across refactors and clearly communicate expected behavior. They catch regressions where internal tests pass but the user experience breaks.

### VII. Pluggable Architecture

Every lifecycle phase MUST be implemented behind a replaceable interface. The core MUST NOT hardcode any single platform, tool, or strategy.

- Each lifecycle phase (creation, iteration, distribution) MUST define a TypeScript `interface`. Core logic MUST depend on the interface, never on concrete implementations.
- Built-in implementations (local filesystem sync, GitHub distribution, default skill templates) are defaults, not mandates. Users MUST be able to replace them via configuration without modifying core code.
- Distribution platforms MUST be pluggable adapters: GitHub for open-source teams, internal registries for compliance-bound enterprises, npm for community sharing — all loadable via config.
- Creation tools MUST be pluggable: different scenarios may require different skill scaffolding, template generators, or AI-assisted creation flows.
- Plugin loading MUST follow a convention-over-configuration approach: a well-known directory or config field (e.g., `plugins` in `config.toml`) for discovery, with a minimal registration API.
- New plugins MUST NOT require changes to the core package. Plugin authors MUST be able to distribute plugins independently (as separate npm packages or local paths).

**Rationale**: Users operate in diverse environments with different constraints. A startup distributes skills via GitHub; an enterprise uses an internal platform for compliance reasons; a power user customizes the creation workflow. Hardcoding any single platform or tool limits applicability. Pluggable architecture ensures sync-skills adapts to the user's environment, not the other way around.

## Technology Constraints

- **Language**: TypeScript (strict mode), targeting Node.js >= 18.
- **Distribution**: `npx sync-skills` as primary method (zero-install, no residue, always latest). Optional global install via `npm install -g sync-skills` for power users.
- **Build**: tsup for CLI binary bundling, published to npm registry via `package.json`.
- **Package manager**: npm for both development and user installation.
- **External dependencies**: gray-matter for YAML frontmatter parsing. File operations use Node.js built-in `fs`/`path` modules. New dependencies MUST be proposed with rationale and approved before addition.
- **Testing**: Vitest for all tests, organized by user scenario with describe blocks.
- **CI/CD**: GitHub Actions auto-build and publish to npm on push to main.
- **Runtime platform**: Cross-platform (macOS, Linux, Windows) — Node.js abstracts platform differences.

## Development Workflow

- All tests MUST pass before any commit. Run via `npm test`.
- New features MUST include user-scenario acceptance tests (Principle VI) covering happy path and edge cases.
- New lifecycle phase implementations (Principle VII) MUST include interface compliance tests.
- Commit messages MUST be in English, following Conventional Commits format.
- CLAUDE.md is the authoritative runtime guidance for AI agents working on this project.
- DESIGN.md Section 7 (changelog) MUST be updated for any architectural decision or significant code change.
- Version bumps follow SemVer: MAJOR for breaking changes, MINOR for new features, PATCH for fixes.

## Governance

This constitution defines the non-negotiable principles for sync-skills development. All code changes, feature proposals, and architectural decisions MUST comply with these principles.

- **Amendment procedure**: Changes to this constitution MUST be documented in DESIGN.md Section 7 with rationale. The constitution version MUST be bumped according to SemVer rules.
- **Versioning policy**: MAJOR for principle removals or redefinitions; MINOR for new principles or materially expanded guidance; PATCH for clarifications and wording fixes.
- **Compliance review**: Every pull request SHOULD be checked against these principles. Violations MUST be explicitly justified in the PR description.
- **Guidance file**: CLAUDE.md provides runtime development guidance and takes precedence for day-to-day coding decisions. This constitution governs architectural and design-level decisions.

**Version**: 2.2.0 | **Ratified**: 2026-04-12 | **Last Amended**: 2026-04-12
