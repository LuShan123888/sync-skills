"""SKILL.md frontmatter 解析、元数据管理和搜索"""

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .cli import log_warning

# frontmatter 正则：匹配 ---\n...\n---\n
FRONTMATTER_PATTERN = re.compile(
    r"^---\s*\n(.*?)\n---\s*\n",
    re.DOTALL,
)

# 已知但不由 sync-skills 使用的 frontmatter 字段（属于 skill 自身运行时配置）
_KNOWN_UNUSED_KEYS = {
    "name", "version", "metadata", "argument-hint",
    "user-invocable", "allowed-tools", "author",
}


# ============================================================
# 数据结构
# ============================================================

@dataclass
class SkillMetadata:
    """从 SKILL.md YAML frontmatter 解析的元数据。所有字段可选。"""
    tags: list[str] = field(default_factory=list)
    description: str = ""
    tools: list[str] = field(default_factory=list)
    # 以下字段仅展示用，不影响同步逻辑
    name: str | None = None
    version: str | None = None
    # 未识别字段，用于向前兼容
    raw: dict = field(default_factory=dict)


# ============================================================
# frontmatter 解析
# ============================================================

def parse_frontmatter(skill_md_path: Path) -> SkillMetadata:
    """解析 SKILL.md 的 YAML frontmatter。

    - 文件不存在或无 frontmatter → 返回空 SkillMetadata
    - YAML 格式错误 → log_warning 并返回空 SkillMetadata
    """
    try:
        content = skill_md_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return SkillMetadata()

    return _parse_frontmatter_content(content)


def parse_frontmatter_content(content: str) -> tuple[SkillMetadata, str]:
    """从 SKILL.md 内容字符串解析 frontmatter。

    返回 (metadata, body)，body 是 --- 之后的正文内容。
    用于 search 的全文搜索。
    """
    metadata = _parse_frontmatter_content(content)
    match = FRONTMATTER_PATTERN.match(content)
    if match:
        body = content[match.end():]
    else:
        body = content
    return metadata, body


def _parse_frontmatter_content(content: str) -> SkillMetadata:
    """内部函数：从内容字符串解析 frontmatter 为 SkillMetadata。"""
    match = FRONTMATTER_PATTERN.match(content)
    if not match:
        return SkillMetadata()

    yaml_str = match.group(1)
    try:
        data = yaml.safe_load(yaml_str)
    except yaml.YAMLError:
        log_warning("YAML frontmatter 格式错误，跳过元数据解析")
        return SkillMetadata()

    if not isinstance(data, dict):
        return SkillMetadata()

    # tags
    tags = data.get("tags", [])
    if not isinstance(tags, list):
        tags = []
    tags = [str(t) for t in tags]

    # description
    description = data.get("description", "")
    if not isinstance(description, str):
        description = str(description) if description else ""
    description = description.strip()

    # tools（统一转小写）
    tools = data.get("tools", [])
    if not isinstance(tools, list):
        tools = []
    tools = [str(t).lower().lstrip(".") for t in tools]

    # raw：未识别字段
    raw = {k: v for k, v in data.items() if k not in _KNOWN_UNUSED_KEYS and k not in ("tags", "description", "tools")}

    return SkillMetadata(
        tags=tags,
        description=description,
        tools=tools,
        name=data.get("name"),
        version=data.get("version"),
        raw=raw,
    )


# ============================================================
# 工具标识映射
# ============================================================

def get_target_tool_name(target_path: Path) -> str:
    """从目标路径提取工具标识符。

    ~/.claude/skills → "claude"
    ~/.codex/skills → "codex"
    ~/.custom-tool/skills → "custom-tool"
    """
    name = target_path.parent.name
    return name.lstrip(".")


# ============================================================
# 选择性同步过滤
# ============================================================

def should_sync_to_target(
    metadata: SkillMetadata,
    target_path: Path,
    exclude_tags: list[str],
) -> bool:
    """判断 skill 是否应该同步到指定目标。

    返回 False 条件：
    - skill 的 tags 与 exclude_tags 有交集
    - metadata.tools 非空且不包含目标工具标识
    """
    # exclude_tags 过滤
    if exclude_tags and metadata.tags:
        if any(t in exclude_tags for t in metadata.tags):
            return False

    # tools 过滤
    if metadata.tools:
        tool_name = get_target_tool_name(target_path).lower()
        if tool_name not in metadata.tools:
            return False

    return True


def get_eligible_targets(
    metadata: SkillMetadata,
    targets: list[Path],
    exclude_tags: list[str],
) -> list[Path]:
    """返回 skill 应该同步到的目标列表。"""
    return [t for t in targets if should_sync_to_target(metadata, t, exclude_tags)]


# ============================================================
# 批量收集与搜索
# ============================================================

def collect_all_metadata(source_dir: Path) -> list[tuple["Skill", SkillMetadata]]:
    """扫描源目录，返回所有 skill 及其元数据。用于 list/search 命令。"""
    from .cli import find_skills_in_source

    result = []
    for skill in find_skills_in_source(source_dir):
        skill_md_path = source_dir / skill.rel_path / "SKILL.md"
        meta = parse_frontmatter(skill_md_path)
        result.append((skill, meta))
    return result


def search_skills(
    source_dir: Path,
    query: str,
) -> list[tuple["Skill", SkillMetadata]]:
    """全文搜索 skills。搜索范围：skill 名、tags、description、SKILL.md body。

    大小写不敏感的子串匹配。
    """
    from .cli import find_skills_in_source

    query_lower = query.lower()
    results = []

    for skill in find_skills_in_source(source_dir):
        skill_md_path = source_dir / skill.rel_path / "SKILL.md"
        meta, body = parse_frontmatter_content(skill_md_path.read_text(encoding="utf-8")) if skill_md_path.is_file() else (SkillMetadata(), "")

        # 搜索 skill 名
        if query_lower in skill.name.lower():
            results.append((skill, meta))
            continue

        # 搜索 tags
        if any(query_lower in t.lower() for t in meta.tags):
            results.append((skill, meta))
            continue

        # 搜索 description
        if query_lower in meta.description.lower():
            results.append((skill, meta))
            continue

        # 搜索 body
        if query_lower in body.lower():
            results.append((skill, meta))
            continue

    return results


def warn_unknown_tools(
    source_dir: Path,
    targets: list[Path],
) -> list[str]:
    """扫描所有 skills，检查引用了不存在的 tool，返回警告列表。"""
    from .cli import find_skills_in_source

    valid_tools = {get_target_tool_name(t).lower() for t in targets}
    warnings = []

    for skill in find_skills_in_source(source_dir):
        skill_md_path = source_dir / skill.rel_path / "SKILL.md"
        meta = parse_frontmatter(skill_md_path)
        if not meta.tools:
            continue
        unknown = [t for t in meta.tools if t not in valid_tools]
        if unknown:
            warnings.append(f"skill '{skill.name}' 引用了未知工具: {', '.join(unknown)}")

    return warnings
