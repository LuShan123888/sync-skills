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



def preview_bidirectional(source_dir: Path, targets: list[Path]) -> SyncPlan:
    """生成双向同步计划。基于纯哈希分组检测冲突，不依赖 mtime 归因。"""
    plan = SyncPlan()

    # 收集所有 skill 的版本信息（源 + 各目标）
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

        # 源存在 + 多版本 → 分析是否可自动解决
        if len(hash_groups) == 2:
            # 按 group 大小排序，找到 singleton（只有 1 个位置的组）
            group_sizes = sorted(hash_groups.values(), key=len)
            singleton_group = group_sizes[0]
            if len(singleton_group) == 1 and not singleton_group[0].is_source:
                # 单个目标不同于其他（含源）→ 安全收集更新
                source_rel = source_versions[0].source_rel
                plan.collect_update.append((skill_name, source_rel, singleton_group[0].path.parent))
                continue

        # 无法自动解决 → 冲突
        plan.conflicts.append((skill_name, versions))

    # 阶段2：计算分发变更
    source_skills = find_skills_in_source(source_dir)
    all_source_names = {s.name for s in source_skills}
    all_source_names.update(name for name, _ in plan.collect_new)

    for target_dir in targets:
        target_names = set(find_skills_in_target(target_dir))
        for name in target_names - all_source_names:
            plan.deletes.append((name, target_dir))
        for name in all_source_names - target_names:
            plan.creates.append((name, target_dir))

    return plan


def preview_force(source_dir: Path, targets: list[Path],
                  original_source_dir: Path | None = None) -> SyncPlan:
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

        for name in target_names - source_names:
            plan.deletes.append((name, target_dir))
        for name in source_names - target_names:
            plan.creates.append((name, target_dir))
        # 同名但内容不同 → 覆盖
        for name in source_names & target_names:
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


def _apply_resolutions(plan: SyncPlan, source_dir: Path, targets: list[Path]) -> None:
    """将用户的冲突选择转换为 collect/creates/updates。"""
    for r in plan.resolutions:
        chosen_skill_dir = r.chosen_path.parent
        if r.chosen_source_rel:
            # 选了源版本 → 分发到所有目标
            for target_dir in targets:
                if not target_dir.is_dir():
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
            # 分发到其他目标
            for target_dir in targets:
                if not target_dir.is_dir():
                    continue
                if target_dir == chosen_skill_dir:
                    continue  # 跳过来源目标
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

    # 计算基准目录的 skill 数量和别名
    base_alias = alias_map.get(source_dir, _short_path(source_dir))
    base_skills = find_skills_in_source(source_dir) if source_dir == DEFAULT_SOURCE else [
        Skill(name=n, rel_path=n) for n in find_skills_in_target(source_dir)]
    base_count = len(base_skills)
    source_map = {s.name: s.rel_path for s in base_skills}

    mode = "强制同步" if force else "双向同步"
    print(f"\n{Color.BOLD}========================================{Color.NC}")
    print(f"{Color.BOLD}  变更预览（{mode}）{Color.NC}")
    print(f"{Color.BOLD}========================================{Color.NC}\n")

    if force:
        print(f"{Color.YELLOW}模式: 以 {base_alias} 为准，强制覆盖所有目标目录{Color.NC}")
        print(f"基准目录 skills 数量: {Color.CYAN}{base_count}{Color.NC}\n")
    else:
        total_after = base_count + len(plan.collect_new)
        print(f"源目录当前 skills 数量: {Color.CYAN}{base_count}{Color.NC}, 同步后: {Color.CYAN}{total_after}{Color.NC}\n")

    if not plan.has_changes and not plan.has_warnings:
        label = f"所有目标目录已与 {base_alias} 一致，无需操作" if force else "没有任何变更需要执行"
        print(f"  {Color.GREEN}{label}{Color.NC}\n")
        return False

    # 警告信息（不阻塞同步，仅提示）
    if plan.warnings:
        print(f"{Color.BOLD}--- 注意 ---{Color.NC}\n")
        for warning in plan.warnings:
            for i, line in enumerate(warning.split("\n")):
                if i == 0:
                    print(f"  {Color.YELLOW}⚠ {line}{Color.NC}")
                else:
                    print(f"  {Color.YELLOW}  {line}{Color.NC}")
        print()

    # 冲突解决结果
    if plan.resolutions:
        print(f"{Color.BOLD}--- 冲突解决 ---{Color.NC}\n")
        for r in plan.resolutions:
            print(f"  {Color.GREEN}✓{Color.NC} {r.skill_name}: 保留 {r.chosen_alias} 的版本")
        print()

    if not plan.has_changes:
        print(f"  {Color.GREEN}除以上警告外，没有需要执行的变更{Color.NC}\n")
        return False

    # 阶段1：收集（仅双向模式）
    if plan.collect_new or plan.collect_update:
        print(f"{Color.BOLD}--- 阶段1：收集（目标 → 源）---{Color.NC}\n")
        if plan.collect_new:
            print(f"  {Color.GREEN}新增 (→ Other/):{Color.NC}")
            for name, from_dir in plan.collect_new:
                print(f"    {Color.GREEN}+{Color.NC} {name}  ← {from_dir}")
            print()
        if plan.collect_update:
            print(f"  {Color.YELLOW}更新:{Color.NC}")
            for name, source_rel, from_dir in plan.collect_update:
                print(f"    {Color.YELLOW}~{Color.NC} {source_rel}  ← {from_dir}")
            print()

    # 阶段2/分发：按目标目录分组
    if plan.creates or plan.deletes or plan.updates:
        if not force:
            print(f"{Color.BOLD}--- 阶段2：分发（源 → 目标）---{Color.NC}\n")
            for target_dir in targets:
                dir_creates = [n for n, d in plan.creates if d == target_dir]
                dir_deletes = [n for n, d in plan.deletes if d == target_dir]
                dir_updates = [(n, r) for n, r, d in plan.updates if d == target_dir]

                if not dir_creates and not dir_deletes and not dir_updates:
                    dir_alias = alias_map.get(target_dir, _short_path(target_dir))
                    print(f"  {Color.BOLD}{dir_alias}{Color.NC}  {Color.GREEN}✓ 无变更{Color.NC}")
                    continue

                dir_alias = alias_map.get(target_dir, _short_path(target_dir))
                print(f"  {Color.BOLD}{dir_alias}{Color.NC}")
                if dir_creates:
                    print(f"    {Color.GREEN}新增 ({len(dir_creates)}):{Color.NC}")
                    for name in dir_creates:
                        print(f"      {Color.GREEN}+{Color.NC} {name}")
                if dir_updates:
                    print(f"    {Color.YELLOW}覆盖 ({len(dir_updates)}):{Color.NC}")
                    for name, source_rel in dir_updates:
                        print(f"      {Color.YELLOW}~{Color.NC} {source_rel}")
                if dir_deletes:
                    print(f"    {Color.RED}删除 ({len(dir_deletes)}):{Color.NC}")
                    for name in dir_deletes:
                        print(f"      {Color.RED}-{Color.NC} {name}")
                print()
        else:
            # Force 模式：每个目标目录单独列出变更
            print(f"{Color.BOLD}--- 同步计划 ---{Color.NC}\n")

            for target_dir in targets:
                dir_creates = [n for n, d in plan.creates if d == target_dir]
                dir_deletes = [n for n, d in plan.deletes if d == target_dir]
                dir_updates = [(n, r) for n, r, d in plan.updates if d == target_dir]

                # 统计内容一致（跳过）的 skill
                is_nested = target_dir in nested_targets
                if is_nested:
                    existing = {s.name for s in find_skills_in_source(target_dir)}
                else:
                    existing = set(find_skills_in_target(target_dir))
                update_names = {n for n, _, d in plan.updates if d == target_dir}
                same_skills = sorted(set(source_map.keys()) & existing - update_names)
                same_count = len(same_skills)

                c, u, d = len(dir_creates), len(dir_updates), len(dir_deletes)
                dir_alias = alias_map.get(target_dir, _short_path(target_dir))

                # 摘要行
                parts = []
                if c:
                    parts.append(f"{Color.GREEN}新增 {c}{Color.NC}")
                if u:
                    parts.append(f"{Color.YELLOW}覆盖 {u}{Color.NC}")
                if d:
                    parts.append(f"{Color.RED}删除 {d}{Color.NC}")
                if same_count:
                    parts.append(f"{Color.CYAN}跳过 {same_count}{Color.NC}")
                summary = "  ".join(parts) if parts else f"{Color.GREEN}无变更{Color.NC}"
                print(f"  {Color.BOLD}{dir_alias}{Color.NC}  {summary}")

                # 按类型逐行列出 skill（相对路径）
                if c:
                    print(f"    {Color.GREEN}新增:{Color.NC}")
                    for name in sorted(dir_creates):
                        src_rel = source_map.get(name, name)
                        print(f"      {Color.GREEN}+{Color.NC} {name}  ← {base_alias}/{src_rel}")
                if u:
                    print(f"    {Color.YELLOW}覆盖:{Color.NC}")
                    for name, src_rel in sorted(dir_updates):
                        print(f"      {Color.YELLOW}~{Color.NC} {name}  ← {base_alias}/{src_rel}")
                if d:
                    print(f"    {Color.RED}删除:{Color.NC}")
                    for name in sorted(dir_deletes):
                        if is_nested:
                            rel = find_skill_in_source_by_name(target_dir, name)
                            path = f"{dir_alias}/{rel}" if rel else name
                        else:
                            path = f"{dir_alias}/{name}"
                        print(f"      {Color.RED}-{Color.NC} {path}")
                if same_skills:
                    print(f"    {Color.CYAN}跳过: {same_count} 个（内容一致）{Color.NC}")
                print()

    return True


# ============================================================
# 执行阶段
# ============================================================

def execute_bidirectional(plan: SyncPlan, source_dir: Path, targets: list[Path]):
    log_info("========== 阶段1：收集新增/修改的 skills ==========")
    print(file=sys.stderr)

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
        log_success(f"  + 已收集到 Other/{name}")

    updated = 0
    for name, source_rel, from_dir in plan.collect_update:
        dest = source_dir / source_rel
        shutil.rmtree(dest)
        shutil.copytree(from_dir / name, dest, copy_function=shutil.copy2)
        updated += 1
        log_success(f"  ~ 已更新: {source_rel}")

    if collected + updated == 0:
        log_info("没有发现新增或修改的 skills")
    else:
        log_success(f"收集完成: 新增 {collected} 个, 更新 {updated} 个")
    print(file=sys.stderr)

    log_info("========== 阶段2：分发 skills 到所有目标目录 ==========")
    print(file=sys.stderr)

    total_ops = 0
    for target_dir in targets:
        dir_creates = [(n, d) for n, d in plan.creates if d == target_dir]
        dir_deletes = [(n, d) for n, d in plan.deletes if d == target_dir]
        dir_updates = [(n, r, d) for n, r, d in plan.updates if d == target_dir]

        if not dir_creates and not dir_deletes and not dir_updates:
            log_info(f"跳过（无变更）: {target_dir}")
            continue

        log_info(f"同步到: {target_dir}")
        target_dir.mkdir(parents=True, exist_ok=True)

        for name, _ in dir_deletes:
            shutil.rmtree(target_dir / name)
            log_warning(f"  删除: {name}")

        for name, _ in dir_creates:
            source_rel = find_skill_in_source_by_name(source_dir, name)
            if source_rel:
                shutil.copytree(source_dir / source_rel, target_dir / name, copy_function=shutil.copy2)

        for name, source_rel, _ in dir_updates:
            skill_path = find_skill_path(target_dir, name)
            if skill_path:
                shutil.rmtree(skill_path)
            shutil.copytree(source_dir / source_rel, target_dir / name, copy_function=shutil.copy2)
            log_info(f"  覆盖: {name}")

        updated += len(dir_updates)
        log_success(f"  ✓ 完成: 新增 {len(dir_creates)} 个, 删除 {len(dir_deletes)} 个, 覆盖 {len(dir_updates)} 个")
        total_ops += len(dir_creates) + len(dir_deletes) + len(dir_updates)
        print(file=sys.stderr)

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

        target_display = _short_path(target_dir)

        if not dir_creates and not dir_deletes and not dir_updates:
            log_info(f"跳过（无变更）: {target_display}")
            continue

        is_nested = target_dir in nested_targets
        log_info(f"同步到: {target_display}" + ("（嵌套结构）" if is_nested else ""))
        target_dir.mkdir(parents=True, exist_ok=True)

        for name, _ in dir_deletes:
            if is_nested:
                rel = find_skill_in_source_by_name(target_dir, name)
                if rel:
                    shutil.rmtree(target_dir / rel)
                    log_warning(f"  删除: {rel}")
                    total_deleted += 1
            else:
                skill_path = find_skill_path(target_dir, name)
                if skill_path:
                    shutil.rmtree(skill_path)
                    log_warning(f"  删除: {name}")
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

        ops = f"新增 {len(dir_creates)} 个, 删除 {len(dir_deletes)} 个, 覆盖 {len(dir_updates)} 个"
        log_success(f"  ✓ 完成: {ops}")
        print(file=sys.stderr)

    return {"created": total_created, "deleted": total_deleted, "updated": total_updated}


# ============================================================
# 验证
# ============================================================

def verify_sync(source_dir: Path, targets: list[Path],
                nested_targets: set[Path] | None = None) -> bool:
    log_info("========== 验证同步结果 ==========")
    print(file=sys.stderr)

    if nested_targets is None:
        nested_targets = set()

    # 基准目录的 skill 集合和哈希
    base_skills = find_skills_in_source(source_dir)
    base_map = {s.name: (s.rel_path, skill_dir_hash(source_dir / s.rel_path)) for s in base_skills}
    base_count = len(base_skills)
    log_info(f"基准目录 skills 数量: {base_count} ({_short_path(source_dir)})")

    all_match = True
    for target_dir in targets:
        if not target_dir.is_dir():
            continue

        is_nested = target_dir in nested_targets
        # 嵌套目录用递归扫描，平铺目录用扁平扫描
        if is_nested:
            target_skills = find_skills_in_source(target_dir)
            target_map = {s.name: (s.rel_path, skill_dir_hash(target_dir / s.rel_path)) for s in target_skills}
        else:
            target_map = {}
            for name in find_skills_in_target(target_dir):
                target_map[name] = (name, skill_dir_hash(target_dir / name))

        target_count = len(target_map)
        target_display = _short_path(target_dir)

        if target_count != base_count:
            log_error(f"✗ {target_display}: {target_count} 个 skills (数量不一致, 期望 {base_count})")
            all_match = False
            continue

        # 检查每个 skill 的内容哈希
        hash_mismatch = False
        for name, (base_rel, base_hash) in base_map.items():
            if name not in target_map:
                log_error(f"✗ {target_display}: 缺少 skill '{name}'")
                hash_mismatch = True
                all_match = False
                continue
            _, target_hash = target_map[name]
            if base_hash != target_hash:
                log_error(f"✗ {target_display}/{name}: 内容不一致")
                hash_mismatch = True
                all_match = False
        if not hash_mismatch:
            log_success(f"✓ {target_display}: {target_count} 个 skills (内容一致)")

    print(file=sys.stderr)
    if all_match:
        log_success("所有目录同步成功，内容完全一致")
    else:
        log_error("同步存在问题，请检查")

    return all_match


# ============================================================
# 用户确认与目录选择
# ============================================================

def ask_confirmation(auto_confirm: bool) -> bool:
    if auto_confirm:
        log_info("自动确认模式 (-y)")
        return True

    print(f"{Color.BOLD}========================================{Color.NC}")
    try:
        answer = input(f"{Color.YELLOW}确认执行以上操作? [y/N]: {Color.NC}")
    except (EOFError, KeyboardInterrupt):
        print()
        log_warning("用户取消操作")
        return False

    if answer.lower() in ("y", "yes"):
        print()
        return True
    log_warning("用户取消操作")
    return False


def show_overview(source_dir: Path, targets: list[Path], alias_map: dict[Path, str]):
    """展示所有目录的当前状态概览，帮助用户选择基准目录。"""
    print(f"{Color.BOLD}--- 目录概览 ---{Color.NC}\n")

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

    print()


def ask_base_selection(all_dirs: list[tuple[Path, str]]) -> Path | None:
    """让用户选择基准目录，返回选中的 Path 或 None（取消）。"""
    print(f"{Color.BOLD}========================================{Color.NC}")
    try:
        answer = input(f"{Color.YELLOW}请选择基准目录 (输入编号，q 取消): {Color.NC}")
    except (EOFError, KeyboardInterrupt):
        print()
        log_warning("用户取消操作")
        return None

    answer = answer.strip()
    if answer.lower() in ("q", "n", "quit", "exit"):
        log_warning("用户取消操作")
        return None

    try:
        idx = int(answer)
        if 0 <= idx < len(all_dirs):
            selected_path, alias = all_dirs[idx]
            print()
            log_info(f"已选择基准目录: {alias} ({_short_path(selected_path)})")
            return selected_path
    except ValueError:
        pass

    log_error(f"无效输入: {answer}，请输入 0-{len(all_dirs) - 1} 之间的数字")
    return None


# ============================================================
# 删除功能
# ============================================================

def execute_delete(skill_name: str, source_dir: Path, targets: list[Path], auto_confirm: bool):
    """删除指定 skill（从源目录和所有目标目录）"""
    print(f"========================================")
    print(f"  删除 Skill: {skill_name}")
    print(f"========================================\n")

    # 检查 skill 是否存在
    source_rel = find_skill_in_source_by_name(source_dir, skill_name)
    target_dirs_with_skill = find_skill_in_targets(targets, skill_name)

    if not source_rel and not target_dirs_with_skill:
        log_error(f"skill '{skill_name}' 在源目录和所有目标目录中都不存在")
        sys.exit(1)

    # 预览删除
    print(f"{Color.BOLD}将要删除以下位置的 skill '{skill_name}':{Color.NC}\n")

    deleted_count = 0

    if source_rel:
        print(f"  {Color.RED}-{Color.NC} 源目录: {source_dir / source_rel}")
        deleted_count += 1

    for target_dir in target_dirs_with_skill:
        print(f"  {Color.RED}-{Color.NC} 目标目录: {target_dir / skill_name}")
        deleted_count += 1

    print()

    if deleted_count == 0:
        log_error(f"skill '{skill_name}' 不存在")
        sys.exit(1)

    # 确认
    if not ask_confirmation(auto_confirm):
        return

    # 执行删除
    log_info("========== 开始删除 ==========")
    print(file=sys.stderr)

    actual_deleted = 0

    if source_rel:
        shutil.rmtree(source_dir / source_rel)
        log_success(f"  已从源目录删除: {source_rel}")
        actual_deleted += 1

    for target_dir in target_dirs_with_skill:
        shutil.rmtree(target_dir / skill_name)
        log_success(f"  已从目标目录删除: {target_dir / skill_name}")
        actual_deleted += 1

    print(file=sys.stderr)
    log_success(f"删除完成: 共删除 {actual_deleted} 个位置")


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
# CLI
# ============================================================

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Skills 同步工具")
    parser.add_argument("command", nargs="?", default=None, help="子命令：init（初始化配置）")
    parser.add_argument("--config", type=Path, default=None, help="配置文件路径")
    parser.add_argument("--force", "-f", action="store_true", help="强制同步模式（可选择任意目录为基准同步到其他目录）")
    parser.add_argument("--delete", "-d", type=str, metavar="SKILL_NAME", help="删除指定的 skill（从源目录和所有目标目录）")
    parser.add_argument("-y", "--yes", action="store_true", help="跳过确认")
    parser.add_argument("--source", type=Path, default=None, help="源目录路径（覆盖配置文件）")
    parser.add_argument("--targets", type=str, default=None, help="目标目录路径，逗号分隔（覆盖配置文件）")
    args = parser.parse_args(argv)

    if args.targets:
        args.targets = [Path(t.strip()) for t in args.targets.split(",")]

    return args


def main(argv: list[str] | None = None):
    args = parse_args(argv)

    # init 子命令
    if args.command == "init":
        _run_init_wizard(config_path=args.config)
        return

    # 加载配置
    config = load_config(args.config)

    # CLI 参数覆盖配置文件
    source_dir: Path = args.source if args.source else config.source
    targets: list[Path] = args.targets if args.targets else [t.path for t in config.targets]
    force: bool = args.force

    # 删除模式
    if args.delete:
        execute_delete(args.delete, source_dir, targets, args.yes)
        return

    mode = "强制模式" if force else "双向模式"
    print(f"========================================")
    print(f"  Skills 同步脚本（{mode}）")
    print(f"========================================\n")

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
        plan = preview_force(base_dir, other_dirs, original_source_dir=orig_source)

        if not show_preview(plan, base_dir, other_dirs, force=True,
                            alias_map=alias_map, nested_targets=nested):
            log_success("无需同步")
            return

        # 4. 确认
        if not ask_confirmation(args.yes):
            return

        # 5. 执行
        stats = execute_force(plan, base_dir, other_dirs, original_source_dir=orig_source)
        verify_sync(base_dir, other_dirs, nested_targets=nested)
        print("========================================")
        print("  同步完成")
        print("========================================")
        print(f"{Color.GREEN}新增: {stats['created']} 个{Color.NC}")
        print(f"{Color.YELLOW}覆盖: {stats['updated']} 个{Color.NC}")
        print(f"{Color.RED}删除: {stats['deleted']} 个{Color.NC}")
    else:
        bidir_alias_map = _build_alias_map(source_dir, targets)
        plan = preview_bidirectional(source_dir, targets)

        # 交互式冲突解决（非 -y 模式）
        if plan.has_conflicts:
            _resolve_conflicts(plan, args.yes)
            _apply_resolutions(plan, source_dir, targets)

        if not show_preview(plan, source_dir, targets, force=False, alias_map=bidir_alias_map):
            log_success("无需同步")
            return

        if not ask_confirmation(args.yes):
            return

        stats = execute_bidirectional(plan, source_dir, targets)
        verify_sync(source_dir, targets)
        print("========================================")
        print("  同步完成")
        print("========================================")
        print(f"{Color.GREEN}收集: 新增 {stats['collected']} 个, 更新 {stats['updated']} 个{Color.NC}")
        print(f"{Color.GREEN}分发: 共 {stats['distributed']} 次操作{Color.NC}")

    print()


if __name__ == "__main__":
    main()
