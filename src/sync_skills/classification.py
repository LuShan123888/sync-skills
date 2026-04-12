"""自定义 skill vs 外部 skill 分类判定

通过 lock 文件（~/.agents/.skill-lock.json 和 ~/skills-lock.json）
识别哪些 skill 由 npx skills 管理（外部），哪些是用户自创建的（自定义）。
"""

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path


# ============================================================
# 数据结构
# ============================================================

@dataclass
class SkillClass:
    """skill 分类结果"""
    name: str
    skill_type: str  # "custom" | "external" | "orphan"
    # 自定义 skill 在 git 仓库中的路径
    custom_path: Path | None = None
    # skill 在 ~/.agents/skills/ 中的路径
    agents_path: Path | None = None
    # 外部 skill 的来源（lock 文件中记录的 source）
    lock_source: str | None = None
    # 是否有 ~/.agents/skills/<name> → ~/Skills/skills/<name> 软链接
    has_custom_link: bool = False


# ============================================================
# Lock 文件解析
# ============================================================

def load_global_lock(path: Path) -> set[str]:
    """加载全局 lock 文件（~/.agents/.skill-lock.json），返回 skill 名集合。

    格式: { "skills": { "skill-name": { "source": "...", ... } } }
    """
    return _load_lock_file(path, key="skills")


def load_local_lock(path: Path) -> set[str]:
    """加载本地 lock 文件（~/skills-lock.json），返回 skill 名集合。

    格式: { "skills": { "skill-name": { "source": "...", ... } } }
    """
    return _load_lock_file(path, key="skills")


def _load_lock_file(path: Path, key: str) -> set[str]:
    """通用 lock 文件加载，返回指定 key 下的所有 skill 名。"""
    if not path.is_file():
        return set()
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return set()
        section = data.get(key, {})
        if not isinstance(section, dict):
            return set()
        return set(section.keys())
    except (json.JSONDecodeError, OSError) as e:
        log_warning(f"lock 文件读取失败 ({path}): {e}")
        return set()


def get_external_skills(
    global_lock_path: Path,
    local_lock_path: Path,
) -> set[str]:
    """合并两个 lock 文件，返回所有外部 skill 名集合。"""
    return load_global_lock(global_lock_path) | load_local_lock(local_lock_path)


def get_lock_source(name: str, global_lock_path: Path, local_lock_path: Path) -> str | None:
    """查询 skill 的 lock 来源（source 字段），优先查 global lock。"""
    source = _get_source_from_lock(name, global_lock_path)
    if source:
        return source
    return _get_source_from_lock(name, local_lock_path)


def _get_source_from_lock(name: str, path: Path) -> str | None:
    """从单个 lock 文件查询 skill 的 source。"""
    if not path.is_file():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        section = data.get("skills", {}).get(name, {})
        return section.get("source") if isinstance(section, dict) else None
    except (json.JSONDecodeError, OSError):
        return None


# ============================================================
# 分类判定
# ============================================================

def classify_skill(
    name: str,
    agents_dir: Path,
    repo_skills_dir: Path,
    external_skills: set[str],
) -> SkillClass:
    """判断单个 skill 的分类。

    判定逻辑：
    1. 在 lock 文件中 → 外部 skill（npx skills 管理）
    2. 不在 lock 中 + 在 repo_skills_dir → 自定义 skill
    3. 不在 lock 中 + 不在 repo_skills_dir + 在 agents_dir → 孤儿
    4. 都不在 → 不存在（返回 orphan）
    """
    in_external = name in external_skills
    in_agents = (agents_dir / name).is_dir()
    in_repo = (repo_skills_dir / name).is_dir()

    if in_external:
        return SkillClass(
            name=name,
            skill_type="external",
            agents_path=agents_dir / name if in_agents else None,
        )

    if in_repo and in_agents:
        agents_link = agents_dir / name
        has_link = agents_link.is_symlink() and _resolve_target(agents_link) == repo_skills_dir / name
        return SkillClass(
            name=name,
            skill_type="custom",
            custom_path=repo_skills_dir / name,
            agents_path=agents_dir / name,
            has_custom_link=has_link,
        )

    if in_repo and not in_agents:
        return SkillClass(
            name=name,
            skill_type="custom",
            custom_path=repo_skills_dir / name,
        )

    if in_agents and not in_repo:
        return SkillClass(
            name=name,
            skill_type="orphan",
            agents_path=agents_dir / name,
        )

    return SkillClass(name=name, skill_type="orphan")


def classify_all_skills(
    agents_dir: Path,
    repo_skills_dir: Path,
    external_skills: set[str],
) -> list[SkillClass]:
    """扫描所有目录，对每个 skill 进行分类。"""
    all_names: set[str] = set()

    # 扫描 ~/.agents/skills/
    if agents_dir.is_dir():
        for d in agents_dir.iterdir():
            if d.name.startswith(".") or not d.is_dir():
                continue
            if (d / "SKILL.md").is_file():
                all_names.add(d.name)

    # 扫描 ~/Skills/skills/
    if repo_skills_dir.is_dir():
        for d in repo_skills_dir.iterdir():
            if d.name.startswith(".") or not d.is_dir():
                continue
            if (d / "SKILL.md").is_file():
                all_names.add(d.name)

    return sorted(
        [classify_skill(name, agents_dir, repo_skills_dir, external_skills) for name in all_names],
        key=lambda c: (c.skill_type, c.name),
    )


# ============================================================
# 辅助函数
# ============================================================

def _resolve_target(link_path: Path) -> Path:
    """解析软链接的最终目标路径。"""
    try:
        return link_path.resolve()
    except OSError:
        return link_path


def log_warning(msg: str) -> None:
    """向 stderr 输出警告（避免循环导入 cli.log_warning）。"""
    print(f"[WARNING] {msg}", file=sys.stderr)
