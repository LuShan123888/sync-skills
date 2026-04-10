#!/usr/bin/env python3
"""Skills 同步工具

默认模式（双向同步）：
  1. 从目标目录收集新增/修改的 skills 到源目录
  2. 从源目录分发到所有目标目录
--force 模式（单向强制同步）：
  以源目录为唯一真实来源，强制覆盖所有目标目录
"""

import argparse
import hashlib
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .config import Config, Target, detect_installed_tools, load_config, save_config
from .constants import CONFIG_FILE, DEFAULT_SOURCE, DEFAULT_TARGETS

# ============================================================
# 数据结构
# ============================================================

@dataclass
class Skill:
    name: str
    rel_path: str  # 相对于源目录的路径（含分类），如 "Code/my-skill"


@dataclass
class SkillVersion:
    """冲突中某个版本的描述信息"""
    path: Path
    alias: str
    hash_prefix: str
    mtime: float
    content_preview: str
    is_source: bool
    source_rel: str | None = None


@dataclass
class ConflictResolution:
    """用户对冲突的选择"""
    skill_name: str
    chosen_path: Path
    chosen_alias: str
    chosen_source_rel: str | None  # 源中的相对路径；目标版本为 None


@dataclass
class SyncPlan:
    """同步计划，预览阶段生成，执行阶段消费"""
    # 收集阶段（双向模式）
    collect_new: list[tuple[str, Path]] = field(default_factory=list)     # (skill_name, from_target_dir)
    collect_update: list[tuple[str, str, Path]] = field(default_factory=list)  # (skill_name, source_rel, from_target_dir)
    # 分发阶段
    creates: list[tuple[str, Path]] = field(default_factory=list)    # (skill_name, target_dir)
    deletes: list[tuple[str, Path]] = field(default_factory=list)    # (skill_name, target_dir)
    updates: list[tuple[str, str, Path]] = field(default_factory=list)  # (skill_name, source_rel, target_dir)
    # 警告（不阻塞同步，仅提示用户）
    warnings: list[str] = field(default_factory=list)
    # 冲突（交互式解决）
    conflicts: list[tuple[str, list[SkillVersion]]] = field(default_factory=list)
    resolutions: list[ConflictResolution] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return bool(self.collect_new or self.collect_update or self.creates or self.deletes or self.updates)

    @property
    def has_warnings(self) -> bool:
        return bool(self.warnings)

    @property
    def has_conflicts(self) -> bool:
        return bool(self.conflicts)


# ============================================================
# 颜色输出
# ============================================================

class Color:
    RED = "\033[0;31m"
    GREEN = "\033[0;32m"
    YELLOW = "\033[1;33m"
    BLUE = "\033[0;34m"
    CYAN = "\033[0;36m"
    BOLD = "\033[1m"
    NC = "\033[0m"


def log_info(msg: str):
    print(f"{Color.BLUE}[INFO]{Color.NC} {msg}", file=sys.stderr)


def log_success(msg: str):
    print(f"{Color.GREEN}[SUCCESS]{Color.NC} {msg}", file=sys.stderr)


def log_warning(msg: str):
    print(f"{Color.YELLOW}[WARNING]{Color.NC} {msg}", file=sys.stderr)


def log_error(msg: str):
    print(f"{Color.RED}[ERROR]{Color.NC} {msg}", file=sys.stderr)


# ============================================================
# 扫描与哈希
# ============================================================

def skill_dir_hash(skill_path: Path) -> str:
    """计算 skill 目录所有文件的 MD5 哈希值，用于判断内容是否一致。忽略隐藏文件（如 .DS_Store）。"""
    h = hashlib.md5()
    for file_path in sorted(skill_path.rglob("*")):
        if file_path.is_file() and not file_path.name.startswith("."):
            rel = file_path.relative_to(skill_path)
            h.update(str(rel).encode())
            h.update(file_path.read_bytes())
    return h.hexdigest()


def find_skills_in_source(source_dir: Path) -> list[Skill]:
    """扫描源目录，返回所有 skill（支持嵌套分类，跳过隐藏目录）"""
    skills = []
    if not source_dir.is_dir():
        return skills
    for skill_md in source_dir.rglob("SKILL.md"):
        # 跳过隐藏目录（如 .system/）
        if any(part.startswith(".") for part in skill_md.relative_to(source_dir).parent.parts):
            continue
        skill_dir = skill_md.parent
        rel_path = str(skill_dir.relative_to(source_dir))
        skills.append(Skill(name=skill_dir.name, rel_path=rel_path))
    return skills


def find_skills_in_target(target_dir: Path) -> list[str]:
    """扫描目标目录，返回所有 skill 名称（扁平扫描，跳过隐藏目录）"""
    if not target_dir.is_dir():
        return []
    return [
        d.name for d in target_dir.iterdir()
        if d.is_dir() and not d.name.startswith(".") and (d / "SKILL.md").is_file()
    ]


def find_skill_path(target_dir: Path, name: str) -> Path | None:
    """在目标目录中查找 skill 的实际路径（扁平扫描，跳过隐藏目录），返回 skill 目录或 None"""
    if not target_dir.is_dir():
        return None
    skill_dir = target_dir / name
    if skill_dir.is_dir() and (skill_dir / "SKILL.md").is_file():
        return skill_dir
    return None


def find_skill_in_source_by_name(source_dir: Path, name: str) -> str | None:
    """在源目录中查找指定名称的 skill，返回相对路径（跳过隐藏目录）"""
    for skill_md in source_dir.rglob("SKILL.md"):
        if any(part.startswith(".") for part in skill_md.relative_to(source_dir).parent.parts):
            continue
        if skill_md.parent.name == name:
            return str(skill_md.parent.relative_to(source_dir))
    return None


def find_skill_in_targets(targets: list[Path], name: str) -> list[Path]:
    """在所有目标目录中查找指定名称的 skill，返回包含该 skill 的目标目录列表"""
    result = []
    for target_dir in targets:
        if target_dir.is_dir():
            path = find_skill_path(target_dir, name)
            if path:
                result.append(target_dir)
    return result


def _build_skill_version(skill_path: Path, alias: str, is_source: bool = False,
                         source_rel: str | None = None) -> SkillVersion:
    """构建 SkillVersion，用于冲突展示"""
    h = skill_dir_hash(skill_path)
    skill_md = skill_path / "SKILL.md"
    mtime = 0.0
    preview_lines = []
    if skill_md.is_file():
        mtime = skill_md.stat().st_mtime
        try:
            content = skill_md.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = skill_md.read_text(encoding="utf-8", errors="replace")
        for line in content.splitlines()[:3]:
            preview_lines.append(line)
    return SkillVersion(
        path=skill_path,
        alias=alias,
        hash_prefix=h[:8],
        mtime=mtime,
        content_preview="\n".join(preview_lines),
        is_source=is_source,
        source_rel=source_rel,
    )


def check_duplicate_names(skills: list[Skill]) -> list[tuple[str, str, str]]:
    """检查重名，返回 (name, path1, path2) 列表"""
    seen: dict[str, str] = {}
    duplicates = []
    for s in skills:
        if s.name in seen:
            duplicates.append((s.name, seen[s.name], s.rel_path))
        else:
            seen[s.name] = s.rel_path
    return duplicates


# ============================================================
# 选择性同步过滤
# ============================================================

def _get_skill_metadata(source_dir: Path, skill_name: str) -> "SkillMetadata":
    """获取源目录中指定 skill 的元数据。skill 不存在时返回空元数据。"""
    from .metadata import SkillMetadata, parse_frontmatter

    skill_rel = find_skill_in_source_by_name(source_dir, skill_name)
    if not skill_rel:
        return SkillMetadata()
    return parse_frontmatter(source_dir / skill_rel / "SKILL.md")


def _should_sync_to(skill_name: str, source_dir: Path, target_dir: Path,
                    exclude_tags: list[str]) -> bool:
    """判断 skill 是否应同步到指定目标。"""
    from .metadata import should_sync_to_target

    meta = _get_skill_metadata(source_dir, skill_name)
    return should_sync_to_target(meta, target_dir, exclude_tags)


def _should_delete_from_target(skill_name: str, source_dir: Path, target_dir: Path,
                               exclude_tags: list[str]) -> bool:
    """判断 skill 是否应从目标中删除。

    - skill 不在源中 → 应删除（多余 skill）
    - skill 在源中但不允许同步到此目标（tools/tags 过滤）→ 应删除
    """
    from .metadata import should_sync_to_target

    skill_rel = find_skill_in_source_by_name(source_dir, skill_name)
    if not skill_rel:
        return True  # 源中没有，多余 skill
    meta = _get_skill_metadata(source_dir, skill_name)
    return not should_sync_to_target(meta, target_dir, exclude_tags)


# ============================================================
# 预览阶段
# ============================================================

def _short_path(p: Path) -> str:
    """用 ~ 缩写 HOME 目录"""
    try:
        return f"~/{p.relative_to(Path.home())}"
    except ValueError:
        return str(p)


def _build_alias_map(source_dir: Path, targets: list[Path]) -> dict[Path, str]:
    """为源目录和目标目录构建别名映射。"""
    alias_map: dict[Path, str] = {}
    # 所有目录统一用 ~/ 缩写的相对路径
    alias_map[source_dir] = _short_path(source_dir)
    for target_dir in targets:
        alias_map[target_dir] = _short_path(target_dir)
    return alias_map


def _fmt_time(mtime: float) -> str:
    """格式化 mtime 为可读时间"""
    return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")



def preview_bidirectional(source_dir: Path, targets: list[Path],
                         exclude_tags: list[str] | None = None) -> SyncPlan:
    """生成双向同步计划。基于纯哈希分组检测冲突，不依赖 mtime 归因。"""
    plan = SyncPlan()

    # 阶段1 的分析：收集所有 skill 的版本信息
    # skill_name -> list[SkillVersion]
    skill_versions: dict[str, list[SkillVersion]] = {}

    # 源目录的 skill
    for skill in find_skills_in_source(source_dir):
        sv = _build_skill_version(
            source_dir / skill.rel_path, _short_path(source_dir),
            is_source=True, source_rel=skill.rel_path,
        )
        skill_versions[skill.name] = [sv]

    # 目标目录的 skill
    for target_dir in targets:
        if not target_dir.is_dir():
            continue
        alias = _short_path(target_dir)
        for skill_name in find_skills_in_target(target_dir):
            sv = _build_skill_version(target_dir / skill_name, alias)
            skill_versions.setdefault(skill_name, []).append(sv)

    # 分析每个 skill：按哈希分组，判断自动解决 or 冲突
    # auto_distribute: 源是 singleton（源修改了，其他没动）→ 阶段2 需要分发更新
    auto_distribute: set[str] = set()
    for skill_name, versions in skill_versions.items():
        # 按哈希分组
        hash_groups: dict[str, list[SkillVersion]] = {}
        for v in versions:
            hash_groups.setdefault(v.hash_prefix, []).append(v)

        source_versions = [v for v in versions if v.is_source]

        # 源目录有该 skill 且所有版本哈希一致 → 无变更
        if len(hash_groups) == 1 and source_versions:
            continue

        # 源目录没有 → 目标新增
        if not source_versions:
            if len(hash_groups) > 1:
                # 多个目标版本不一致 → 冲突
                plan.conflicts.append((skill_name, versions))
            else:
                # 所有目标版本一致 → 安全收集（从第一个目标）
                plan.collect_new.append((skill_name, versions[0].path.parent))
            continue

        # 源存在 + 2 个哈希组 → 分析是否可自动解决
        if len(hash_groups) == 2:
            # 按 group 大小排序，找到 singleton（只有 1 个位置的组）
            group_sizes = sorted(hash_groups.values(), key=len)
            singleton_group = group_sizes[0]
            majority_group = group_sizes[1]
            if len(singleton_group) == 1:
                # 一个位置与其他不一致 → 比较 mtime 决定方向
                singleton_sv = singleton_group[0]
                singleton_mtime = max(v.mtime for v in singleton_group)
                majority_mtime = max(v.mtime for v in majority_group)
                # mtime 差异 < 1s 视为同时修改，回退到以 singleton 为准（旧行为）
                if abs(singleton_mtime - majority_mtime) < 1.0 or singleton_mtime >= majority_mtime:
                    # singleton 更新或同时 → 以 singleton 版本为准
                    if singleton_sv.is_source:
                        auto_distribute.add(skill_name)
                    else:
                        source_rel = source_versions[0].source_rel
                        plan.collect_update.append((skill_name, source_rel, singleton_sv.path.parent))
                else:
                    # majority 明显更新 → 以 majority 版本为准
                    if not any(v.is_source for v in singleton_group):
                        # singleton 是目标且是旧版，majority（含源）是新版 → 分发
                        auto_distribute.add(skill_name)
                    else:
                        # singleton 是源且是旧版，majority（目标）是新版 → 收集
                        majority_sv = majority_group[0]
                        source_rel = source_versions[0].source_rel
                        plan.collect_update.append((skill_name, source_rel, majority_sv.path.parent))
                continue

        # 无法自动解决 → 冲突
        plan.conflicts.append((skill_name, versions))

    # 阶段2：计算分发变更（按 skill 粒度过滤目标）
    source_skills = find_skills_in_source(source_dir)
    source_map = {s.name: s.rel_path for s in source_skills}
    all_source_names = set(source_map.keys())
    all_source_names.update(name for name, _ in plan.collect_new)
    et = exclude_tags or []

    for target_dir in targets:
        target_names = set(find_skills_in_target(target_dir))
        for name in target_names - all_source_names:
            # 目标中多余（源中没有）：检查是否应排除
            if _should_delete_from_target(name, source_dir, target_dir, et):
                plan.deletes.append((name, target_dir))
        for name in all_source_names - target_names:
            # 源中有但目标缺少：检查是否应同步到此目标
            if _should_sync_to(name, source_dir, target_dir, et):
                plan.creates.append((name, target_dir))
        # 源和目标都有，但不应同步到此目标（tools/tags 过滤）→ 删除
        for name in all_source_names & target_names:
            if not _should_sync_to(name, source_dir, target_dir, et):
                plan.deletes.append((name, target_dir))
                continue
            # 源和目标都有，内容不同 → 更新（仅限自动解决的 singleton 源场景）
            if name in auto_distribute and name in source_map:
                source_rel = source_map[name]
                source_hash = skill_dir_hash(source_dir / source_rel)
                target_hash = skill_dir_hash(target_dir / name)
                if source_hash != target_hash:
                    plan.updates.append((name, source_rel, target_dir))

    # 收集更新后，将新版本分发到其他有旧版本的目标
    for skill_name, source_rel, from_target_dir in plan.collect_update:
        from_hash = skill_dir_hash(from_target_dir / skill_name)
        for target_dir in targets:
            if target_dir == from_target_dir:
                continue
            target_path = target_dir / skill_name
            if target_path.is_dir() and (target_path / "SKILL.md").is_file():
                if skill_dir_hash(target_path) != from_hash:
                    if _should_sync_to(skill_name, source_dir, target_dir, et):
                        plan.updates.append((skill_name, source_rel, target_dir))

    return plan


def preview_force(source_dir: Path, targets: list[Path],
                  original_source_dir: Path | None = None,
                  exclude_tags: list[str] | None = None) -> SyncPlan:
    """生成强制同步计划。original_source_dir 标记原始源目录（嵌套结构），当它作为目标时需要特殊处理。"""
    plan = SyncPlan()
    source_skills = find_skills_in_source(source_dir)
    source_map = {s.name: s.rel_path for s in source_skills}
    source_names = set(source_map.keys())

    # 标记哪些目标目录是嵌套结构的（原始源目录）
    nested_targets = set()
    if original_source_dir and original_source_dir != source_dir and original_source_dir in targets:
        nested_targets.add(original_source_dir)

    for target_dir in targets:
        target_dir.mkdir(parents=True, exist_ok=True)
        # 嵌套目录（源目录）用递归扫描，平铺目录用扁平扫描
        is_nested = target_dir in nested_targets
        if is_nested:
            target_skills = find_skills_in_source(target_dir)
            target_map = {s.name: s.rel_path for s in target_skills}
            target_names = set(target_map.keys())
        else:
            target_names = set(find_skills_in_target(target_dir))

        et = exclude_tags or []
        for name in target_names - source_names:
            # 目标中多余（源中没有）：应删除
            plan.deletes.append((name, target_dir))
        for name in source_names - target_names:
            # 源中有但目标缺少：检查是否应同步到此目标
            if _should_sync_to(name, source_dir, target_dir, et):
                plan.creates.append((name, target_dir))
        # 同名但内容不同 → 覆盖（受选择性同步过滤）
        # 同名且不应同步到此目标 → 删除
        for name in source_names & target_names:
            if not _should_sync_to(name, source_dir, target_dir, et):
                plan.deletes.append((name, target_dir))
                continue
            source_hash = skill_dir_hash(source_dir / source_map[name])
            # 嵌套目录需要用实际路径计算哈希
            target_path = target_dir / target_map[name] if is_nested else target_dir / name
            target_hash = skill_dir_hash(target_path)
            if source_hash != target_hash:
                plan.updates.append((name, source_map[name], target_dir))

    return plan


# ============================================================
# 交互式冲突解决
# ============================================================

def ask_conflict_resolution(skill_name: str, versions: list[SkillVersion],
                            auto_confirm: bool) -> ConflictResolution | None:
    """让用户选择冲突 skill 的保留版本。返回选择结果，或 None（跳过/自动模式）。"""
    if auto_confirm:
        return None  # -y 模式跳过冲突，后续转为 warning

    # 按哈希分组，每组内按 mtime 降序
    hash_groups: dict[str, list[SkillVersion]] = {}
    for v in versions:
        hash_groups.setdefault(v.hash_prefix, []).append(v)
    sorted_groups = sorted(
        hash_groups.items(),
        key=lambda kv: max(m for m in (v.mtime for v in kv[1])) if kv[1] else 0,
        reverse=True,
    )

    # 展示冲突选择界面
    print(f"\n  {Color.RED}冲突: '{skill_name}' 存在 {len(sorted_groups)} 个不同版本{Color.NC}\n")
    for i, (_, group) in enumerate(sorted_groups):
        is_suggested = (i == 0)
        label = f"{Color.BOLD}[{i}]{Color.NC} {'★ 建议版本' if is_suggested else '版本'}"
        loc_count = len(group)
        has_source = any(v.is_source for v in group)
        suffix = f" (含源)" if has_source else ""

        loc_names = ", ".join(v.alias for v in group)
        latest_mtime = max(v.mtime for v in group)

        print(f"  {label} — {loc_count}处一致{suffix}")
        print(f"    哈希: {group[0].hash_prefix}  位置: {loc_names}")
        if latest_mtime > 0:
            print(f"    修改: {_fmt_time(latest_mtime)}")
        if group[0].content_preview:
            for line in group[0].content_preview.splitlines():
                print(f"    {line}")
        print()

    print(f"  {Color.CYAN}[s] 跳过此 skill{Color.NC}")
    print()

    try:
        answer = input(f"  {Color.YELLOW}选择要保留的版本 (输入编号, s 跳过): {Color.NC}")
    except (EOFError, KeyboardInterrupt):
        print()
        return None

    answer = answer.strip()
    if answer.lower() in ("s", "skip"):
        return None

    try:
        idx = int(answer)
        if 0 <= idx < len(sorted_groups):
            chosen_group = sorted_groups[idx][1]
            chosen = chosen_group[0]
            # 如果选的是源版本，取 source_rel；否则为 None
            chosen_source_rel = None
            for v in chosen_group:
                if v.is_source and v.source_rel:
                    chosen_source_rel = v.source_rel
                    break
            return ConflictResolution(
                skill_name=skill_name,
                chosen_path=chosen.path,
                chosen_alias=chosen.alias,
                chosen_source_rel=chosen_source_rel,
            )
    except ValueError:
        pass

    log_error(f"无效输入: {answer}")
    return None


def _resolve_conflicts(plan: SyncPlan, auto_confirm: bool) -> None:
    """遍历所有冲突，交互式解决（非 -y 模式）。解决后转为 warning 或 resolution。"""
    unresolved = []
    for skill_name, versions in plan.conflicts:
        resolution = ask_conflict_resolution(skill_name, versions, auto_confirm)
        if resolution is None:
            # 跳过或 -y 模式 → 转为 warning
            plan.warnings.append(_build_version_warning_from_versions(skill_name, versions))
        else:
            plan.resolutions.append(resolution)
    plan.conflicts.clear()


def _build_version_warning_from_versions(skill_name: str, versions: list[SkillVersion]) -> str:
    """从 SkillVersion 列表构建警告文本（用于 -y 模式和跳过冲突）。"""
    hash_groups: dict[str, list[SkillVersion]] = {}
    for v in versions:
        hash_groups.setdefault(v.hash_prefix, []).append(v)

    sorted_groups = sorted(
        hash_groups.items(),
        key=lambda kv: max(v.mtime for v in kv[1]),
        reverse=True,
    )

    lines = [f"skill '{skill_name}' 内容不一致，请手动处理"]
    for i, (_, group) in enumerate(sorted_groups):
        has_source = any(v.is_source for v in group)
        loc_names = ", ".join(v.alias for v in group)
        max_mtime = max(v.mtime for v in group)
        label = "★ 建议版本" if i == 0 else f"版本{i + 1}"
        suffix = " (含源)" if has_source else ""
        lines.append(f"  {label}{suffix} — {len(group)}处一致, 最新修改: {_fmt_time(max_mtime)}")
        lines.append(f"    {loc_names}")

    return "\n".join(lines)


def _apply_resolutions(plan: SyncPlan, source_dir: Path, targets: list[Path],
                       exclude_tags: list[str] | None = None) -> None:
    """将用户的冲突选择转换为 collect/creates/updates。"""
    et = exclude_tags or []
    for r in plan.resolutions:
        chosen_skill_dir = r.chosen_path.parent
        if r.chosen_source_rel:
            # 选了源版本 → 分发到所有目标（受选择性同步过滤）
            for target_dir in targets:
                if not target_dir.is_dir():
                    continue
                if not _should_sync_to(r.skill_name, source_dir, target_dir, et):
                    continue
                target_path = target_dir / r.skill_name
                if target_path.is_dir() and (target_path / "SKILL.md").is_file():
                    target_hash = skill_dir_hash(target_path)
                    chosen_hash = skill_dir_hash(r.chosen_path)
                    if target_hash != chosen_hash:
                        plan.updates.append((r.skill_name, r.chosen_source_rel, target_dir))
                elif not target_path.is_dir():
                    plan.creates.append((r.skill_name, target_dir))
        else:
            # 选了目标版本 → 收集到源
            source_rel = find_skill_in_source_by_name(source_dir, r.skill_name)
            if source_rel:
                plan.collect_update.append((r.skill_name, source_rel, chosen_skill_dir))
            else:
                plan.collect_new.append((r.skill_name, chosen_skill_dir))
            # 分发到其他目标（受选择性同步过滤）
            for target_dir in targets:
                if not target_dir.is_dir():
                    continue
                if target_dir == chosen_skill_dir:
                    continue  # 跳过来源目标
                if not _should_sync_to(r.skill_name, source_dir, target_dir, et):
                    continue
                target_path = target_dir / r.skill_name
                if target_path.is_dir() and (target_path / "SKILL.md").is_file():
                    target_hash = skill_dir_hash(target_path)
                    chosen_hash = skill_dir_hash(r.chosen_path)
                    if target_hash != chosen_hash:
                        plan.updates.append((r.skill_name, r.skill_name, target_dir))
                elif not target_path.is_dir():
                    plan.creates.append((r.skill_name, target_dir))


# ============================================================
# 展示预览
# ============================================================

def show_preview(plan: SyncPlan, source_dir: Path, targets: list[Path], force: bool,
                 alias_map: dict[Path, str] | None = None,
                 nested_targets: set[Path] | None = None) -> bool:
    """展示变更预览，返回是否有变更"""
    if alias_map is None:
        alias_map = {}
    if nested_targets is None:
        nested_targets = set()

    base_alias = alias_map.get(source_dir, _short_path(source_dir))
    base_skills = find_skills_in_source(source_dir) if source_dir == DEFAULT_SOURCE else [
        Skill(name=n, rel_path=n) for n in find_skills_in_target(source_dir)]
    base_count = len(base_skills)
    source_map = {s.name: s.rel_path for s in base_skills}

    # 无变更
    if not plan.has_changes and not plan.has_warnings:
        label = f"所有目标目录已与 {base_alias} 一致" if force else "无需同步"
        print(f"\n  {Color.GREEN}{label}{Color.NC}")
        return False

    # skill 数量概要
    if not force:
        total_after = base_count + len(plan.collect_new)
        print(f"\n  {base_alias}: {Color.CYAN}{base_count}{Color.NC} 个 skills → {Color.CYAN}{total_after}{Color.NC} 个")

    # 警告
    if plan.warnings:
        for warning in plan.warnings:
            for i, line in enumerate(warning.split("\n")):
                if i == 0:
                    print(f"  {Color.YELLOW}⚠ {line}{Color.NC}")
                else:
                    print(f"    {Color.YELLOW}{line}{Color.NC}")

    # 冲突解决结果
    if plan.resolutions:
        for r in plan.resolutions:
            print(f"  {Color.GREEN}✓{Color.NC} {r.skill_name}: 保留 {r.chosen_alias} 的版本")

    if not plan.has_changes:
        print(f"  {Color.GREEN}除以上提示外，无需执行变更{Color.NC}")
        return False

    # 按目录分组展示变更
    if not force:
        src_creates = plan.collect_new
        src_updates = plan.collect_update
        if src_creates or src_updates:
            src_alias = alias_map.get(source_dir, _short_path(source_dir))
            print(f"\n  {Color.BOLD}{src_alias}{Color.NC}")
            if src_creates:
                for name, from_dir in src_creates:
                    print(f"    {Color.GREEN}+{Color.NC} Other/{name}  ← {_short_path(from_dir)}")
            if src_updates:
                for name, source_rel, from_dir in src_updates:
                    print(f"    {Color.YELLOW}~{Color.NC} {source_rel}  ← {_short_path(from_dir)}")

        for target_dir in targets:
            dir_creates = [n for n, d in plan.creates if d == target_dir]
            dir_deletes = [n for n, d in plan.deletes if d == target_dir]
            dir_updates = [(n, r) for n, r, d in plan.updates if d == target_dir]

            if not dir_creates and not dir_deletes and not dir_updates:
                dir_alias = alias_map.get(target_dir, _short_path(target_dir))
                print(f"  {dir_alias}  {Color.GREEN}✓{Color.NC}")
                continue

            dir_alias = alias_map.get(target_dir, _short_path(target_dir))
            print(f"\n  {Color.BOLD}{dir_alias}{Color.NC}")
            if dir_creates:
                for name in dir_creates:
                    src_rel = source_map.get(name, name)
                    print(f"    {Color.GREEN}+{Color.NC} {name}  ← {base_alias}/{src_rel}")
            if dir_updates:
                for name, src_rel in dir_updates:
                    print(f"    {Color.YELLOW}~{Color.NC} {name}  ← {base_alias}/{src_rel}")
            if dir_deletes:
                for name in dir_deletes:
                    print(f"    {Color.RED}-{Color.NC} {name}")
    else:
        # Force 模式：每个目标目录单独列出变更
        for target_dir in targets:
            dir_creates = [n for n, d in plan.creates if d == target_dir]
            dir_deletes = [n for n, d in plan.deletes if d == target_dir]
            dir_updates = [(n, r) for n, r, d in plan.updates if d == target_dir]

            is_nested = target_dir in nested_targets
            if is_nested:
                existing = {s.name for s in find_skills_in_source(target_dir)}
            else:
                existing = set(find_skills_in_target(target_dir))
            update_names = {n for n, _, d in plan.updates if d == target_dir}
            same_count = len(sorted(set(source_map.keys()) & existing - update_names))

            c, u, d = len(dir_creates), len(dir_updates), len(dir_deletes)
            dir_alias = alias_map.get(target_dir, _short_path(target_dir))

            parts = []
            if c: parts.append(f"{Color.GREEN}+{c}{Color.NC}")
            if u: parts.append(f"{Color.YELLOW}~{u}{Color.NC}")
            if d: parts.append(f"{Color.RED}-{d}{Color.NC}")
            if same_count: parts.append(f"✓{same_count}")

            if not parts:
                print(f"  {dir_alias}  {Color.GREEN}✓{Color.NC}")
                continue

            print(f"  {Color.BOLD}{dir_alias}{Color.NC}  {'  '.join(parts)}")
            for name in sorted(dir_creates):
                src_rel = source_map.get(name, name)
                print(f"    {Color.GREEN}+{Color.NC} {name}  ← {base_alias}/{src_rel}")
            for name, src_rel in sorted(dir_updates):
                print(f"    {Color.YELLOW}~{Color.NC} {name}  ← {base_alias}/{src_rel}")
            for name in sorted(dir_deletes):
                if is_nested:
                    rel = find_skill_in_source_by_name(target_dir, name)
                    path = f"{dir_alias}/{rel}" if rel else name
                else:
                    path = f"{dir_alias}/{name}"
                print(f"    {Color.RED}-{Color.NC} {path}")

    return True


# ============================================================
# 执行阶段
# ============================================================

def execute_bidirectional(plan: SyncPlan, source_dir: Path, targets: list[Path]):
    collected = 0
    collected_names = set()
    for name, from_dir in plan.collect_new:
        if name in collected_names:
            continue
        dest = source_dir / "Other" / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(from_dir / name, dest, copy_function=shutil.copy2)
        collected += 1
        collected_names.add(name)

    updated = 0
    for name, source_rel, from_dir in plan.collect_update:
        dest = source_dir / source_rel
        shutil.rmtree(dest)
        shutil.copytree(from_dir / name, dest, copy_function=shutil.copy2)
        updated += 1

    total_ops = 0
    for target_dir in targets:
        dir_creates = [(n, d) for n, d in plan.creates if d == target_dir]
        dir_deletes = [(n, d) for n, d in plan.deletes if d == target_dir]
        dir_updates = [(n, r, d) for n, r, d in plan.updates if d == target_dir]

        if not dir_creates and not dir_deletes and not dir_updates:
            continue

        target_dir.mkdir(parents=True, exist_ok=True)

        for name, _ in dir_deletes:
            shutil.rmtree(target_dir / name)

        for name, _ in dir_creates:
            source_rel = find_skill_in_source_by_name(source_dir, name)
            if source_rel:
                shutil.copytree(source_dir / source_rel, target_dir / name, copy_function=shutil.copy2)

        for name, source_rel, _ in dir_updates:
            skill_path = find_skill_path(target_dir, name)
            if skill_path:
                shutil.rmtree(skill_path)
            shutil.copytree(source_dir / source_rel, target_dir / name, copy_function=shutil.copy2)

        total_ops += len(dir_creates) + len(dir_deletes) + len(dir_updates)

    return {"collected": collected, "updated": updated, "distributed": total_ops}


def execute_force(plan: SyncPlan, source_dir: Path, targets: list[Path],
                  original_source_dir: Path | None = None):
    source_skills = find_skills_in_source(source_dir)
    source_map = {s.name: s.rel_path for s in source_skills}

    # 标记哪些目标目录是嵌套结构的（原始源目录）
    nested_targets = set()
    if original_source_dir and original_source_dir != source_dir and original_source_dir in targets:
        nested_targets.add(original_source_dir)

    total_created = 0
    total_deleted = 0
    total_updated = 0

    for target_dir in targets:
        dir_creates = [(n, d) for n, d in plan.creates if d == target_dir]
        dir_deletes = [(n, d) for n, d in plan.deletes if d == target_dir]
        dir_updates = [(n, r, d) for n, r, d in plan.updates if d == target_dir]

        if not dir_creates and not dir_deletes and not dir_updates:
            continue

        is_nested = target_dir in nested_targets
        target_dir.mkdir(parents=True, exist_ok=True)

        for name, _ in dir_deletes:
            if is_nested:
                rel = find_skill_in_source_by_name(target_dir, name)
                if rel:
                    shutil.rmtree(target_dir / rel)
                    total_deleted += 1
            else:
                skill_path = find_skill_path(target_dir, name)
                if skill_path:
                    shutil.rmtree(skill_path)
                    total_deleted += 1

        for name, _ in dir_creates:
            rel_path = source_map.get(name)
            if rel_path:
                if is_nested:
                    dest = target_dir / "Other" / name
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copytree(source_dir / rel_path, dest, copy_function=shutil.copy2)
                else:
                    shutil.copytree(source_dir / rel_path, target_dir / name, copy_function=shutil.copy2)
                total_created += 1

        for name, source_rel, _ in dir_updates:
            if is_nested:
                old_rel = find_skill_in_source_by_name(target_dir, name)
                if old_rel:
                    shutil.rmtree(target_dir / old_rel)
                dest = target_dir / "Other" / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(source_dir / source_rel, dest, copy_function=shutil.copy2)
            else:
                skill_path = find_skill_path(target_dir, name)
                if skill_path:
                    shutil.rmtree(skill_path)
                shutil.copytree(source_dir / source_rel, target_dir / name, copy_function=shutil.copy2)
            total_updated += 1

    return {"created": total_created, "deleted": total_deleted, "updated": total_updated}


# ============================================================
# 验证
# ============================================================

def verify_sync(source_dir: Path, targets: list[Path],
                nested_targets: set[Path] | None = None) -> bool:
    if nested_targets is None:
        nested_targets = set()

    base_skills = find_skills_in_source(source_dir)
    base_map = {s.name: (s.rel_path, skill_dir_hash(source_dir / s.rel_path)) for s in base_skills}
    base_count = len(base_skills)

    all_match = True
    for target_dir in targets:
        if not target_dir.is_dir():
            continue

        is_nested = target_dir in nested_targets
        if is_nested:
            target_skills = find_skills_in_source(target_dir)
            target_map = {s.name: (s.rel_path, skill_dir_hash(target_dir / s.rel_path)) for s in target_skills}
        else:
            target_map = {}
            for name in find_skills_in_target(target_dir):
                target_map[name] = (name, skill_dir_hash(target_dir / name))

        target_display = _short_path(target_dir)

        if len(target_map) != base_count:
            print(f"  {Color.RED}✗ {target_display}: {len(target_map)} 个 (期望 {base_count}){Color.NC}")
            all_match = False
            continue

        hash_mismatch = False
        for name, (base_rel, base_hash) in base_map.items():
            if name not in target_map:
                print(f"  {Color.RED}✗ {target_display}: 缺少 '{name}'{Color.NC}")
                hash_mismatch = True
                all_match = False
                continue
            _, target_hash = target_map[name]
            if base_hash != target_hash:
                print(f"  {Color.RED}✗ {target_display}/{name}: 内容不一致{Color.NC}")
                hash_mismatch = True
                all_match = False
        if not hash_mismatch:
            print(f"  {Color.GREEN}✓ {target_display}: {len(target_map)} 个{Color.NC}")

    return all_match


# ============================================================
# 用户确认与目录选择
# ============================================================

def ask_confirmation(auto_confirm: bool) -> bool:
    if auto_confirm:
        return True

    try:
        answer = input(f"{Color.YELLOW}确认执行? [y/N]: {Color.NC}")
    except (EOFError, KeyboardInterrupt):
        print()
        return False

    if answer.lower() in ("y", "yes"):
        return True
    return False


def show_overview(source_dir: Path, targets: list[Path], alias_map: dict[Path, str]):
    """展示所有目录的当前状态概览，帮助用户选择基准目录。"""
    # 收集所有目录的 skill 集合和哈希
    all_dirs = [source_dir] + targets
    dir_skills: dict[Path, dict[str, str]] = {}  # dir -> {skill_name: hash}
    for d in all_dirs:
        if not d.is_dir():
            continue
        dir_skills[d] = {}
        if d == source_dir:
            for skill in find_skills_in_source(d):
                dir_skills[d][skill.name] = skill_dir_hash(d / skill.rel_path)
        else:
            for name in find_skills_in_target(d):
                dir_skills[d][name] = skill_dir_hash(d / name)

    # 展示每个目录
    for i, d in enumerate(all_dirs):
        alias = alias_map.get(d, _short_path(d))
        skills = dir_skills.get(d, {})
        count = len(skills)

        # 统计与源不一致的数量
        if d == source_dir:
            print(f"  {Color.CYAN}[{i}]{Color.NC} {alias:<20} {count} skills")
        else:
            source_hashes = dir_skills.get(source_dir, {})
            mismatch = sum(1 for name, h in skills.items()
                           if name in source_hashes and h != source_hashes[name])
            only_in_target = sum(1 for name in skills if name not in source_hashes)
            parts = []
            if mismatch:
                parts.append(f"{mismatch}个与源不一致")
            if only_in_target:
                parts.append(f"{only_in_target}个仅此目录有")
            detail = f" ({', '.join(parts)})" if parts else ""
            if mismatch or only_in_target:
                print(f"  {Color.CYAN}[{i}]{Color.NC} {alias:<20} {count} skills{Color.YELLOW}{detail}{Color.NC}")
            else:
                print(f"  {Color.CYAN}[{i}]{Color.NC} {alias:<20} {count} skills{Color.GREEN} ✓{Color.NC}")


def ask_base_selection(all_dirs: list[tuple[Path, str]]) -> Path | None:
    """让用户选择基准目录，返回选中的 Path 或 None（取消）。"""
    try:
        answer = input(f"{Color.YELLOW}选择基准目录 (编号, q 取消): {Color.NC}")
    except (EOFError, KeyboardInterrupt):
        print()
        return None

    answer = answer.strip()
    if answer.lower() in ("q", "n", "quit", "exit"):
        return None

    try:
        idx = int(answer)
        if 0 <= idx < len(all_dirs):
            return all_dirs[idx][0]
    except ValueError:
        pass

    log_error(f"无效输入: {answer}")
    return None


# ============================================================
# 删除功能
# ============================================================

def execute_delete(skill_name: str, source_dir: Path, targets: list[Path], auto_confirm: bool, dry_run: bool = False):
    """删除指定 skill（从源目录和所有目标目录）"""
    source_rel = find_skill_in_source_by_name(source_dir, skill_name)
    target_dirs_with_skill = find_skill_in_targets(targets, skill_name)

    if not source_rel and not target_dirs_with_skill:
        log_error(f"skill '{skill_name}' 不存在")
        sys.exit(1)

    print(f"  删除: {skill_name}")
    deleted_count = 0

    if source_rel:
        print(f"    {Color.RED}-{Color.NC} {_short_path(source_dir / source_rel)}")
        deleted_count += 1

    for target_dir in target_dirs_with_skill:
        print(f"    {Color.RED}-{Color.NC} {_short_path(target_dir / skill_name)}")
        deleted_count += 1

    if not ask_confirmation(auto_confirm):
        return

    if dry_run:
        log_info("dry-run mode: no changes made")
        return

    if source_rel:
        shutil.rmtree(source_dir / source_rel)
    for target_dir in target_dirs_with_skill:
        shutil.rmtree(target_dir / skill_name)

    print(f"  {Color.GREEN}✓ 已删除 {deleted_count} 处{Color.NC}")


# ============================================================
# init 向导
# ============================================================

def _run_init_wizard(config_path: Path | None = None):
    """交互式初始化配置向导"""
    from .config import _expand_home, _unexpand_home

    config_file = config_path or CONFIG_FILE
    print("=== sync-skills 初始化配置 ===\n")

    # 1. 源目录
    default_source = "~/Skills"
    try:
        source_input = input(f"源目录路径 (默认 {default_source}): ")
    except (EOFError, KeyboardInterrupt):
        print()
        log_warning("用户取消")
        return
    source_str = source_input.strip() or default_source
    source_path = _expand_home(source_str)

    # 2. 检测已安装工具
    installed = detect_installed_tools()
    if installed:
        print(f"\n检测到已安装的工具:")
        for i, tool in enumerate(installed):
            print(f"  [{i}] {tool['name']}  {tool['path']}")
    else:
        print("\n未检测到已安装的工具，可以手动添加。")

    # 3. 选择目标目录
    try:
        select_input = input("\n选择要同步的目标目录 (编号，逗号分隔，直接回车全选): ")
    except (EOFError, KeyboardInterrupt):
        print()
        log_warning("用户取消")
        return

    if select_input.strip():
        indices = [int(x.strip()) for x in select_input.split(",") if x.strip().isdigit()]
        selected_tools = [installed[i] for i in indices if 0 <= i < len(installed)]
    else:
        selected_tools = installed

    # 4. 手动添加额外目标
    try:
        extra_input = input("添加额外的目标目录路径 (逗号分隔，直接回车跳过): ")
    except (EOFError, KeyboardInterrupt):
        print()
        extra_input = ""

    targets = []
    for tool in selected_tools:
        targets.append(Target(name=tool["name"], path=_expand_home(tool["path"])))
    if extra_input.strip():
        for extra in extra_input.split(","):
            extra = extra.strip()
            if extra:
                p = _expand_home(extra)
                targets.append(Target(name=p.name, path=p))

    if not targets:
        print("\n未选择任何目标目录，将使用内置默认值。")
        config = Config(source=source_path)
    else:
        config = Config(source=source_path, targets=targets)

    # 5. 保存配置
    save_config(config, config_path=config_file)
    print(f"\n配置已保存到: {config_file}")
    print(f"  源目录: {_unexpand_home(config.source)}")
    for t in config.targets:
        print(f"  目标: {t.name}  {_unexpand_home(t.path)}")


# ============================================================
# list/search/info 命令
# ============================================================

def _cmd_list(args: argparse.Namespace):
    """列出所有 skills，按分类分组。"""
    from .config import load_config
    from .metadata import collect_all_metadata

    config = load_config(args.config)
    source_dir = args.source if args.source else config.source
    filter_tags = args.tags or []

    skills_with_meta = collect_all_metadata(source_dir)

    # 按标签过滤
    if filter_tags:
        skills_with_meta = [
            (s, m) for s, m in skills_with_meta
            if any(t in m.tags for t in filter_tags)
        ]

    if not skills_with_meta:
        print("  没有找到匹配的 skills")
        return

    # 按分类分组（rel_path 的第一个组件）
    categories: dict[str, list[tuple[Skill, "SkillMetadata"]]] = {}
    for skill, meta in sorted(skills_with_meta, key=lambda x: x[0].rel_path):
        category = skill.rel_path.split("/")[0]
        categories.setdefault(category, []).append((skill, meta))

    total = 0
    for category, items in categories.items():
        print(f"\n  {Color.BOLD}{category}/{Color.NC}")
        for skill, meta in items:
            tags_str = ""
            if meta.tags:
                tags_str = f"  {Color.CYAN}[{', '.join(meta.tags)}]{Color.NC}"
            tools_str = ""
            if meta.tools:
                tools_str = f"  {Color.YELLOW}→ {', '.join(meta.tools)}{Color.NC}"
            desc_str = ""
            if meta.description:
                desc = meta.description.split("\n")[0][:60]
                if len(meta.description.split("\n")[0]) > 60:
                    desc += "..."
                desc_str = f"  {desc}"
            print(f"    {skill.name}{tags_str}{tools_str}{desc_str}")
            total += 1

    print(f"\n  共 {total} 个 skills")


def _cmd_search(args: argparse.Namespace):
    """全文搜索 skills。"""
    from .config import load_config
    from .metadata import search_skills

    config = load_config(args.config)
    source_dir = args.source if args.source else config.source

    if not args.query:
        log_error("请提供搜索关键词")
        return

    results = search_skills(source_dir, args.query)

    if not results:
        print(f"  没有找到匹配 '{args.query}' 的 skills")
        return

    print(f"  找到 {len(results)} 个匹配结果:\n")
    for skill, meta in results:
        print(f"  {Color.BOLD}{skill.name}{Color.NC}  ({skill.rel_path})")
        if meta.description:
            desc = meta.description.split("\n")[0][:80]
            if len(meta.description.split("\n")[0]) > 80:
                desc += "..."
            print(f"    {desc}")
        if meta.tags:
            print(f"    标签: {', '.join(meta.tags)}")
        if meta.tools:
            print(f"    工具: {', '.join(meta.tools)}")
        print()


def _cmd_info(args: argparse.Namespace):
    """查看 skill 详细信息。"""
    from .config import load_config
    from .metadata import parse_frontmatter

    config = load_config(args.config)
    source_dir = args.source if args.source else config.source

    if not args.query:
        log_error("请提供 skill 名称")
        return

    skill_name = args.query
    skill_rel = find_skill_in_source_by_name(source_dir, skill_name)
    if not skill_rel:
        log_error(f"skill '{skill_name}' 不存在")
        sys.exit(1)

    skill_path = source_dir / skill_rel
    meta = parse_frontmatter(skill_path / "SKILL.md")

    print(f"\n  {Color.BOLD}{skill_name}{Color.NC}")
    print(f"  路径: {_short_path(skill_path)}")

    if meta.description:
        print(f"\n  描述:")
        for line in meta.description.split("\n"):
            print(f"    {line}")

    if meta.tags:
        print(f"\n  标签: {', '.join(meta.tags)}")

    if meta.tools:
        print(f"  同步目标: {', '.join(meta.tools)}")
    else:
        print(f"  同步目标: 所有目标")

    if meta.version:
        print(f"  版本: {meta.version}")

    # 显示当前已同步到的目标
    targets = [t.path for t in config.targets]
    synced = [t for t in targets if t.is_dir() and find_skill_path(t, skill_name)]
    if synced:
        print(f"\n  已同步到:")
        for t in synced:
            print(f"    {_short_path(t)}")

    print()


# ============================================================
# CLI
# ============================================================

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="sync-skills",
        description=(
            "sync-skills — Sync AI coding agent skills across multiple tools.\n"
            "AI 编码工具 skills 统一管理与同步工具。\n"
            "\n"
            "Maintain a single categorized skills repository (~/Skills/) and\n"
            "automatically distribute to Claude Code, Codex CLI, Gemini CLI, etc."
        ),
        epilog=(
            "examples:\n"
            "  sync-skills                          bidirectional sync (default)\n"
            "  sync-skills --dry-run                preview changes without executing\n"
            "  sync-skills --force -y               force sync, skip all prompts\n"
            "  sync-skills init                     interactive config wizard\n"
            "  sync-skills list                     list all skills grouped by category\n"
            "  sync-skills list --tags code,review  filter by tags\n"
            "  sync-skills search \"review\"          full-text search\n"
            "  sync-skills info skill-name          show skill details\n"
            "  sync-skills --delete skill-name -y   delete skill everywhere\n"
            "  sync-skills --source ~/my-skills     use custom source directory\n"
            "\n"
            "config: ~/.config/sync-skills/config.toml\n"
            "repo:   https://github.com/LuShan123888/sync-skills"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("command", nargs="?", default=None,
                        choices=["init", "list", "search", "info"],
                        help="sub-command: init (setup config), list (show skills), search (find skills), info (skill details)")
    parser.add_argument("query", nargs="?", default=None,
                        help="search query (for search command) or skill name (for info command)")
    parser.add_argument("--config", type=Path, default=None,
                        help="path to config file (default: ~/.config/sync-skills/config.toml)")
    parser.add_argument("--force", "-f", action="store_true",
                        help="force sync: use one directory as base, overwrite different content, remove extras")
    parser.add_argument("--dry-run", action="store_true",
                        help="preview changes without executing (show plan only)")
    parser.add_argument("--delete", "-d", type=str, metavar="SKILL_NAME",
                        help="delete a skill from source and all target directories")
    parser.add_argument("-y", "--yes", action="store_true",
                        help="skip all confirmation prompts (use in scripts and automation)")
    parser.add_argument("--source", type=Path, default=None,
                        help="source directory path (overrides config file)")
    parser.add_argument("--targets", type=str, default=None,
                        help="target directories, comma-separated (overrides config file)")
    parser.add_argument("--tags", type=str, default=None,
                        help="filter by tags, comma-separated (for list command only)")
    args = parser.parse_args(argv)

    if args.targets:
        args.targets = [Path(t.strip()) for t in args.targets.split(",")]
    if args.tags:
        args.tags = [t.strip() for t in args.tags.split(",")]

    return args


def main(argv: list[str] | None = None):
    args = parse_args(argv)

    # init 子命令
    if args.command == "init":
        _run_init_wizard(config_path=args.config)
        return

    # list/search/info 子命令（只需要配置中的 source，不需要完整同步流程）
    if args.command == "list":
        _cmd_list(args)
        return
    if args.command == "search":
        _cmd_search(args)
        return
    if args.command == "info":
        _cmd_info(args)
        return

    # 加载配置
    config = load_config(args.config)

    # CLI 参数覆盖配置文件
    source_dir: Path = args.source if args.source else config.source
    targets: list[Path] = args.targets if args.targets else [t.path for t in config.targets]
    force: bool = args.force

    # 删除模式
    if args.delete:
        execute_delete(args.delete, source_dir, targets, args.yes, dry_run=args.dry_run)
        return

    # 选择性同步：检查未知工具引用
    from .metadata import warn_unknown_tools
    unknown_warnings = warn_unknown_tools(source_dir, targets)
    for w in unknown_warnings:
        log_warning(w)

    exclude_tags = config.exclude_tags

    mode = "强制同步" if force else "双向同步"
    print(f"{'═' * 40}")
    print(f"  {mode} · Skills 同步")
    print(f"{'═' * 40}")

    # 检查源目录
    if not source_dir.is_dir():
        if force:
            log_error(f"源目录不存在: {source_dir}")
            sys.exit(1)
        log_info(f"正在创建源目录: {source_dir}")
        source_dir.mkdir(parents=True, exist_ok=True)

    # 检查重名
    source_skills = find_skills_in_source(source_dir)
    dups = check_duplicate_names(source_skills)
    if dups:
        log_error("源目录存在重名 skill，无法平铺同步到目标目录")
        for name, p1, p2 in dups:
            log_error(f"重名 skill: {name}")
            log_error(f"  路径1: {p1}")
            log_error(f"  路径2: {p2}")
        log_error("请先重命名重复的 skill，再重新执行同步")
        sys.exit(1)

    # 预览与执行
    if force:
        alias_map = _build_alias_map(source_dir, targets)
        all_dirs_with_alias = [(source_dir, _short_path(source_dir))] + [(t, _short_path(t)) for t in targets]

        # 1. 展示目录概览
        show_overview(source_dir, targets, alias_map)

        # 2. 选择基准目录
        if args.yes:
            base_dir = source_dir
        else:
            base_dir = ask_base_selection(all_dirs_with_alias)
            if base_dir is None:
                return

        # 3. 以基准为源，其他所有目录为目标
        other_dirs = [d for d in [source_dir] + targets if d != base_dir]
        # 当源目录作为目标时，需要保留其嵌套分类结构
        orig_source = source_dir if source_dir != base_dir else None
        nested = {orig_source} if orig_source else set()
        plan = preview_force(base_dir, other_dirs, original_source_dir=orig_source, exclude_tags=exclude_tags)

        if not show_preview(plan, base_dir, other_dirs, force=True,
                            alias_map=alias_map, nested_targets=nested):
            log_success("无需同步")
            return

        if args.dry_run:
            log_info("dry-run mode: no changes made")
            return

        # 4. 确认
        if not ask_confirmation(args.yes):
            return

        # 5. 执行
        stats = execute_force(plan, base_dir, other_dirs, original_source_dir=orig_source)
        verify_sync(base_dir, other_dirs, nested_targets=nested)
        c, u, d = stats['created'], stats['updated'], stats['deleted']
        parts = []
        if c: parts.append(f"{Color.GREEN}+{c}{Color.NC}")
        if u: parts.append(f"{Color.YELLOW}~{u}{Color.NC}")
        if d: parts.append(f"{Color.RED}-{d}{Color.NC}")
        print(f"  {Color.GREEN}✓ 同步完成{Color.NC}  {'  '.join(parts)}")
    else:
        bidir_alias_map = _build_alias_map(source_dir, targets)
        plan = preview_bidirectional(source_dir, targets, exclude_tags=exclude_tags)

        # 交互式冲突解决（非 -y 模式）
        if plan.has_conflicts:
            _resolve_conflicts(plan, args.yes)
            _apply_resolutions(plan, source_dir, targets, exclude_tags=exclude_tags)

        if not show_preview(plan, source_dir, targets, force=False, alias_map=bidir_alias_map):
            log_success("无需同步")
            return

        if args.dry_run:
            log_info("dry-run mode: no changes made")
            return

        if not ask_confirmation(args.yes):
            return

        stats = execute_bidirectional(plan, source_dir, targets)
        verify_sync(source_dir, targets)
        c, u = stats['collected'], stats['updated']
        print(f"  {Color.GREEN}✓ 同步完成{Color.NC}  收集 +{c} ~{u}  分发 {stats['distributed']} 次操作")

    print()


if __name__ == "__main__":
    main()
