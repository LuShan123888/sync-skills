"""skill 分类判定

通过状态文件（~/.config/sync-skills/skills.json）识别哪些 skill 由 sync-skills 管理。
"""

import sys
from dataclasses import dataclass
from pathlib import Path


# ============================================================
# 数据结构
# ============================================================

@dataclass
class SkillClass:
    """skill 分类结果"""
    name: str
    skill_type: str  # "custom" | "unknown"
    # 自定义 skill 在 git 仓库中的路径
    custom_path: Path | None = None
    # skill 在 agent 目录中的路径（第一个找到的）
    agent_path: Path | None = None
    # 是否有至少一个指向 repo 的 symlink
    has_custom_link: bool = False
    # 是否在状态文件中（已纳入管理）
    managed: bool = False


# ============================================================
# 分类判定
# ============================================================

def classify_skill(
    name: str,
    managed_skills: set[str],
    repo_skills_dir: Path | None = None,
    agent_dirs: list[Path] | None = None,
) -> SkillClass:
    """判断单个 skill 的分类。

    判定逻辑（基于状态文件）：
    1. 在状态文件中（managed_skills）→ 自定义 skill（sync-skills 管理）
    2. 在 agent dir 或 repo 中但不在状态文件中 → unknown
    3. 都不在 → unknown
    """
    in_managed = name in managed_skills

    # 在 agent 目录中查找
    agent_path = None
    if agent_dirs:
        for ad in agent_dirs:
            if (ad / name).is_dir():
                agent_path = ad / name
                break

    # 在 repo 中查找
    in_repo = repo_skills_dir is not None and (repo_skills_dir / name).is_dir()

    if in_managed:
        # 检查是否有指向 repo 的 symlink
        has_link = False
        if repo_skills_dir is not None and agent_dirs:
            target = repo_skills_dir / name
            for ad in agent_dirs:
                link = ad / name
                if link.is_symlink():
                    try:
                        if link.resolve() == target.resolve():
                            has_link = True
                            break
                    except OSError:
                        pass
        return SkillClass(
            name=name,
            skill_type="custom",
            custom_path=(repo_skills_dir / name) if in_repo else None,
            agent_path=agent_path,
            has_custom_link=has_link,
            managed=True,
        )

    if agent_path:
        return SkillClass(
            name=name,
            skill_type="unknown",
            agent_path=agent_path,
        )

    return SkillClass(name=name, skill_type="unknown")


def classify_all_skills(
    managed_skills: set[str],
    repo_skills_dir: Path | None = None,
    agent_dirs: list[Path] | None = None,
) -> list[SkillClass]:
    """扫描所有目录，对每个 skill 进行分类。

    扫描来源：agent_dirs + repo_skills_dir（如果提供）。
    分类依据：状态文件。
    """
    all_names: set[str] = set()
    dirs = agent_dirs or []

    # 扫描所有 agent 目录
    for ad in dirs:
        if ad.is_dir():
            for d in ad.iterdir():
                if d.name.startswith(".") or not d.is_dir():
                    continue
                if (d / "SKILL.md").is_file():
                    all_names.add(d.name)

    # 扫描 ~/Skills/skills/
    if repo_skills_dir is not None and repo_skills_dir.is_dir():
        for d in repo_skills_dir.iterdir():
            if d.name.startswith(".") or not d.is_dir():
                continue
            if (d / "SKILL.md").is_file():
                all_names.add(d.name)

    # 也加入状态文件中的 skill（可能 symlink 全断了，文件系统中不存在）
    all_names.update(managed_skills)

    return sorted(
        [classify_skill(name, managed_skills, repo_skills_dir, agent_dirs) for name in all_names],
        key=lambda c: (c.skill_type, c.name),
    )


# ============================================================
# 辅助函数
# ============================================================

def log_warning(msg: str) -> None:
    """向 stderr 输出警告（避免循环导入 cli.log_warning）。"""
    print(f"[WARNING] {msg}", file=sys.stderr)
