"""metadata 模块测试"""

from pathlib import Path

import pytest

from sync_skills.metadata import (
    SkillMetadata,
    collect_all_metadata,
    get_target_tool_name,
    parse_frontmatter,
    parse_frontmatter_content,
    search_skills,
    should_sync_to_target,
    warn_unknown_tools,
)


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def env(tmp_path: Path):
    """创建测试环境：source 目录"""
    source = tmp_path / "source"
    source.mkdir()
    return source


def create_skill(base: Path, name: str, content: str = "") -> Path:
    """创建 skill 目录"""
    skill_dir = base / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(content or f"# {name}")
    return skill_dir


def create_skill_in_category(source: Path, category: str, name: str, content: str = "") -> Path:
    """按分类创建 skill"""
    skill_dir = source / category / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(content or f"# {name}")
    return skill_dir


# ============================================================
# TestParseFrontmatter
# ============================================================


class TestParseFrontmatter:
    def test_parse_with_tags(self, tmp_path: Path):
        skill_dir = create_skill(tmp_path, "test-skill", "---\ntags: [code, review]\n---\n\n# test\n")
        meta = parse_frontmatter(skill_dir / "SKILL.md")
        assert meta.tags == ["code", "review"]

    def test_parse_with_description(self, tmp_path: Path):
        skill_dir = create_skill(tmp_path, "test-skill",
                                 '---\ndescription: "代码审查工具"\n---\n\n# test\n')
        meta = parse_frontmatter(skill_dir / "SKILL.md")
        assert meta.description == "代码审查工具"

    def test_parse_with_tools(self, tmp_path: Path):
        skill_dir = create_skill(tmp_path, "test-skill", "---\ntools: [claude, codex]\n---\n\n# test\n")
        meta = parse_frontmatter(skill_dir / "SKILL.md")
        assert meta.tools == ["claude", "codex"]

    def test_parse_with_all_fields(self, tmp_path: Path):
        content = """---
name: my-skill
version: 1.0.0
description: "A test skill"
tags: [code, test]
tools: [claude]
---
# my-skill
"""
        skill_dir = create_skill(tmp_path, "my-skill", content)
        meta = parse_frontmatter(skill_dir / "SKILL.md")
        assert meta.name == "my-skill"
        assert meta.version == "1.0.0"
        assert meta.description == "A test skill"
        assert meta.tags == ["code", "test"]
        assert meta.tools == ["claude"]

    def test_parse_legacy_attached_delimiter(self, tmp_path: Path):
        content = """---
name: my-skill
version: 1.0.0---
# my-skill
"""
        skill_dir = create_skill(tmp_path, "my-skill", content)
        meta = parse_frontmatter(skill_dir / "SKILL.md")
        assert meta.name == "my-skill"
        assert meta.version == "1.0.0"

    def test_parse_no_frontmatter(self, tmp_path: Path):
        skill_dir = create_skill(tmp_path, "test-skill", "# test skill\n\nSome content")
        meta = parse_frontmatter(skill_dir / "SKILL.md")
        assert meta.tags == []
        assert meta.description == ""
        assert meta.tools == []

    def test_parse_malformed_yaml(self, tmp_path: Path):
        skill_dir = create_skill(tmp_path, "test-skill", "---\ntags: [unclosed\n---\n\n# test\n")
        meta = parse_frontmatter(skill_dir / "SKILL.md")
        assert meta.tags == []

    def test_parse_empty_frontmatter(self, tmp_path: Path):
        skill_dir = create_skill(tmp_path, "test-skill", "---\n---\n\n# test\n")
        meta = parse_frontmatter(skill_dir / "SKILL.md")
        assert meta.tags == []
        assert meta.description == ""

    def test_parse_multiline_description(self, tmp_path: Path):
        content = """---
description: >-
  多行描述
  第二行
---
# test
"""
        skill_dir = create_skill(tmp_path, "test-skill", content)
        meta = parse_frontmatter(skill_dir / "SKILL.md")
        assert "多行描述" in meta.description
        assert "第二行" in meta.description

    def test_parse_preserves_raw(self, tmp_path: Path):
        content = """---
tags: [code]
custom_field: custom_value
---
# test
"""
        skill_dir = create_skill(tmp_path, "test-skill", content)
        meta = parse_frontmatter(skill_dir / "SKILL.md")
        assert "custom_field" in meta.raw
        assert meta.raw["custom_field"] == "custom_value"

    def test_parse_file_not_found(self, tmp_path: Path):
        meta = parse_frontmatter(tmp_path / "nonexistent" / "SKILL.md")
        assert meta.tags == []
        assert meta.description == ""

    def test_parse_tools_leading_dot_stripped(self, tmp_path: Path):
        skill_dir = create_skill(tmp_path, "test-skill", "---\ntools: [.claude, .codex]\n---\n\n# test\n")
        meta = parse_frontmatter(skill_dir / "SKILL.md")
        assert meta.tools == ["claude", "codex"]

    def test_parse_non_list_tags(self, tmp_path: Path):
        skill_dir = create_skill(tmp_path, "test-skill", "---\ntags: \"code\"\n---\n\n# test\n")
        meta = parse_frontmatter(skill_dir / "SKILL.md")
        assert meta.tags == []

    def test_parse_known_unused_fields_not_in_raw(self, tmp_path: Path):
        content = """---
name: test
version: "1.0"
argument-hint: "<arg>"
user-invocable: true
allowed-tools: Bash
---
# test
"""
        skill_dir = create_skill(tmp_path, "test-skill", content)
        meta = parse_frontmatter(skill_dir / "SKILL.md")
        assert meta.name == "test"
        assert meta.version == "1.0"
        assert "argument-hint" not in meta.raw
        assert "user-invocable" not in meta.raw


# ============================================================
# TestParseFrontmatterContent
# ============================================================


class TestParseFrontmatterContent:
    def test_returns_body_after_frontmatter(self):
        content = "---\ntags: [code]\n---\n\n# skill\n\nBody content"
        meta, body = parse_frontmatter_content(content)
        assert meta.tags == ["code"]
        assert "# skill\n\nBody content" in body

    def test_returns_full_content_when_no_frontmatter(self):
        content = "# skill\n\nBody content"
        meta, body = parse_frontmatter_content(content)
        assert meta.tags == []
        assert body == content

    def test_returns_body_for_legacy_attached_delimiter(self):
        content = "---\nname: demo\nversion: 1.0.0---\n# skill\n\nBody content"
        meta, body = parse_frontmatter_content(content)
        assert meta.name == "demo"
        assert meta.version == "1.0.0"
        assert body == "# skill\n\nBody content"

    def test_returns_body_for_legacy_attached_delimiter_with_body_rule(self):
        content = "---\nname: demo\nversion: 1.0.0---\n# skill\n\n---\nBody content"
        meta, body = parse_frontmatter_content(content)
        assert meta.name == "demo"
        assert meta.version == "1.0.0"
        assert body == "# skill\n\n---\nBody content"


# ============================================================
# TestTargetToolName
# ============================================================


class TestTargetToolName:
    def test_standard_path(self, tmp_path: Path):
        path = Path.home() / ".claude" / "skills"
        assert get_target_tool_name(path) == "claude"

    def test_non_standard_path(self, tmp_path: Path):
        path = Path.home() / ".my-tool" / "skills"
        assert get_target_tool_name(path) == "my-tool"

    def test_no_dot_prefix(self, tmp_path: Path):
        path = Path("/custom") / "my-tool" / "skills"
        assert get_target_tool_name(path) == "my-tool"


# ============================================================
# TestShouldSyncToTarget
# ============================================================


class TestShouldSyncToTarget:
    def test_no_restrictions(self):
        meta = SkillMetadata()
        target = Path.home() / ".claude" / "skills"
        assert should_sync_to_target(meta, target, []) is True

    def test_tools_filter_allows(self):
        meta = SkillMetadata(tools=["claude"])
        target = Path.home() / ".claude" / "skills"
        assert should_sync_to_target(meta, target, []) is True

    def test_tools_filter_blocks(self):
        meta = SkillMetadata(tools=["claude"])
        target = Path.home() / ".codex" / "skills"
        assert should_sync_to_target(meta, target, []) is False

    def test_exclude_tags_blocks(self):
        meta = SkillMetadata(tags=["wip"])
        target = Path.home() / ".claude" / "skills"
        assert should_sync_to_target(meta, target, ["wip"]) is False

    def test_exclude_tags_partial_match(self):
        meta = SkillMetadata(tags=["wip", "code"])
        target = Path.home() / ".claude" / "skills"
        assert should_sync_to_target(meta, target, ["wip"]) is False

    def test_exclude_tags_no_match(self):
        meta = SkillMetadata(tags=["code"])
        target = Path.home() / ".claude" / "skills"
        assert should_sync_to_target(meta, target, ["wip"]) is True

    def test_tools_and_exclude_tags_both(self):
        meta = SkillMetadata(tags=["code"], tools=["claude"])
        target = Path.home() / ".claude" / "skills"
        # tags 不匹配 exclude_tags，tools 匹配 → 允许
        assert should_sync_to_target(meta, target, ["wip"]) is True

    def test_tools_match_but_exclude_tags_blocks(self):
        meta = SkillMetadata(tags=["wip"], tools=["claude"])
        target = Path.home() / ".claude" / "skills"
        # tools 匹配但 exclude_tags 匹配 → 阻止
        assert should_sync_to_target(meta, target, ["wip"]) is False


# ============================================================
# TestSearchSkills
# ============================================================


class TestSearchSkills:
    def test_search_by_name(self, env: Path):
        create_skill_in_category(env, "Code", "git-commit",
                                 "---\ntags: [code, git]\n---\n\n# git-commit\n")
        results = search_skills(env, "git-commit")
        assert len(results) == 1

    def test_search_by_tag(self, env: Path):
        create_skill_in_category(env, "Code", "git-commit",
                                 "---\ntags: [code, git]\n---\n\n# git-commit\n")
        results = search_skills(env, "code")
        assert len(results) == 1

    def test_search_by_description(self, env: Path):
        create_skill_in_category(env, "Code", "git-commit",
                                 '---\ndescription: "代码提交工具"\n---\n\n# git-commit\n')
        results = search_skills(env, "代码提交")
        assert len(results) == 1

    def test_search_by_body(self, env: Path):
        create_skill_in_category(env, "Code", "git-commit", "# git-commit\n\n生成 commit 消息的工具")
        results = search_skills(env, "commit 消息")
        assert len(results) == 1

    def test_search_no_results(self, env: Path):
        create_skill_in_category(env, "Code", "git-commit", "# git-commit\n")
        results = search_skills(env, "nonexistent")
        assert len(results) == 0

    def test_search_case_insensitive(self, env: Path):
        create_skill_in_category(env, "Code", "git-commit",
                                 "---\ntags: [Code, Git]\n---\n\n# git-commit\n")
        results = search_skills(env, "CODE")
        assert len(results) == 1


# ============================================================
# TestCollectAllMetadata
# ============================================================


class TestCollectAllMetadata:
    def test_collect_with_mixed_frontmatter(self, env: Path):
        create_skill_in_category(env, "Code", "skill-a", "---\ntags: [code]\n---\n\n# skill-a\n")
        create_skill_in_category(env, "Lark", "skill-b", "# skill-b\n")

        results = collect_all_metadata(env)
        assert len(results) == 2

        meta_a = next(m for s, m in results if s.name == "skill-a")
        assert meta_a.tags == ["code"]

        meta_b = next(m for s, m in results if s.name == "skill-b")
        assert meta_b.tags == []

    def test_collect_empty_source(self, env: Path):
        results = collect_all_metadata(env)
        assert len(results) == 0

    def test_collect_preserves_skill_structure(self, env: Path):
        create_skill_in_category(env, "Code", "my-skill", "# my-skill\n")
        results = collect_all_metadata(env)
        assert len(results) == 1
        skill, meta = results[0]
        assert skill.name == "my-skill"
        assert skill.rel_path == "Code/my-skill"


# ============================================================
# TestWarnUnknownTools
# ============================================================


class TestWarnUnknownTools:
    def test_warn_for_unknown_tool(self, env: Path):
        create_skill_in_category(env, "Code", "test-skill",
                                 "---\ntools: [claude, nonexistent]\n---\n\n# test\n")
        targets = [Path.home() / ".claude" / "skills"]
        warnings = warn_unknown_tools(env, targets)
        assert len(warnings) == 1
        assert "nonexistent" in warnings[0]

    def test_no_warn_for_known_tool(self, env: Path):
        create_skill_in_category(env, "Code", "test-skill",
                                 "---\ntools: [claude]\n---\n\n# test\n")
        targets = [Path.home() / ".claude" / "skills"]
        warnings = warn_unknown_tools(env, targets)
        assert len(warnings) == 0

    def test_no_warn_when_tools_empty(self, env: Path):
        create_skill_in_category(env, "Code", "test-skill", "# test\n")
        targets = [Path.home() / ".claude" / "skills"]
        warnings = warn_unknown_tools(env, targets)
        assert len(warnings) == 0
