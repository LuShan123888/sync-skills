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

# ============================================================
# 数据结构
# ============================================================

DEFAULT_SOURCE = Path.home() / "Skills"
DEFAULT_TARGETS = [
    Path.home() / ".claude" / "skills",
    Path.home() / ".codex" / "skills",
    Path.home() / ".gemini" / "skills",
    Path.home() / ".openclaw" / "skills",
]


@dataclass
class Skill:
    name: str
    rel_path: str  # 相对于源目录的路径（含分类），如 "Code/my-skill"


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

    @property
    def has_changes(self) -> bool:
        return bool(self.collect_new or self.collect_update or self.creates or self.deletes or self.updates)

    @property
    def has_warnings(self) -> bool:
        return bool(self.warnings)


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
    # 源目录别名
    alias_map[source_dir] = "源"
    # 目标目录别名：取父目录名（如 ~/.claude/skills → "claude"）
    for target_dir in targets:
        alias_map[target_dir] = target_dir.parent.name
    return alias_map


def _alias_of(p: Path, alias_map: dict[Path, str]) -> str:
    """根据路径找到所属的根目录别名，找不到则返回短路径。"""
    for root, alias in alias_map.items():
        try:
            p.relative_to(root)
            return alias
        except ValueError:
            continue
    return _short_path(p)


def _fmt_time(mtime: float) -> str:
    """格式化 mtime 为可读时间"""
    return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")


def _build_version_warning(
    skill_name: str, source_dir: Path, source_rel: str, source_mtime: float,
    targets_info: list[tuple[Path, str, float]],
    alias_map: dict[Path, str],
    targets: list[Path],
) -> str:
    """为内容不一致的 skill 构建多行详细警告，按哈希分组展示所有版本。"""
    # 按 hash 分组所有位置（源 + 所有包含该 skill 的目标）
    versions: dict[str, list[tuple[Path, float, bool]]] = {}
    source_path = source_dir / source_rel
    source_hash = skill_dir_hash(source_path)
    versions.setdefault(source_hash, []).append((source_path, source_mtime, True))

    # 添加所有不一致的目标（已有记录）
    for target_dir, _, target_mtime in targets_info:
        versions.setdefault(skill_dir_hash(target_dir / skill_name), []).append(
            (target_dir / skill_name, target_mtime, False)
        )
    # 补充一致的目标（不在 targets_info 中但包含该 skill 且哈希匹配的）
    mismatch_dirs = {t for t, _, _ in targets_info}
    for target_dir in targets:
        if target_dir in mismatch_dirs or not target_dir.is_dir():
            continue
        skill_path = target_dir / skill_name
        if skill_path.is_dir() and (skill_path / "SKILL.md").is_file():
            target_hash = skill_dir_hash(skill_path)
            versions.setdefault(target_hash, []).append(
                (skill_path, (skill_path / "SKILL.md").stat().st_mtime, False)
            )

    # 按最新 mtime 降序排列
    sorted_versions = sorted(
        versions.items(),
        key=lambda kv: max(m for _, m, _ in kv[1]),
        reverse=True,
    )

    lines = [f"skill '{skill_name}' 内容不一致，请手动处理"]
    for i, (_, locations) in enumerate(sorted_versions):
        max_mtime = max(m for _, m, _ in locations)
        has_source = any(is_src for _, _, is_src in locations)
        loc_names = ", ".join(_alias_of(p, alias_map) for p, _, _ in locations)

        if i == 0:
            label = "★ 建议版本"
        else:
            label = f"版本{i + 1}"

        suffix = " (含源)" if has_source else ""
        lines.append(f"  {label}{suffix} — {len(locations)}处一致, 最新修改: {_fmt_time(max_mtime)}")
        lines.append(f"    {loc_names}")

    return "\n".join(lines)


def preview_bidirectional(source_dir: Path, targets: list[Path]) -> SyncPlan:
    plan = SyncPlan()
    alias_map = _build_alias_map(source_dir, targets)

    # 阶段1：收集新增/修改的 skills
    target_updated: dict[str, list[Path]] = {}     # skill_name -> [target mtime > source mtime 的目标]
    source_also_changed: set[str] = set()           # 源 mtime >= target mtime 的 skill 名称
    # 记录不一致 skill 的版本详情，用于生成详细警告
    skill_versions: dict[str, tuple[str, float, list[tuple[Path, str, float]]]] = {}
    # skill_name -> (source_rel, source_mtime, [(target_dir, target_hash, target_mtime), ...])

    for target_dir in targets:
        if not target_dir.is_dir():
            continue
        for skill_name in find_skills_in_target(target_dir):
            source_rel = find_skill_in_source_by_name(source_dir, skill_name)
            if source_rel is None:
                plan.collect_new.append((skill_name, target_dir))
                continue

            # 比较目录哈希，判断内容是否一致
            source_hash = skill_dir_hash(source_dir / source_rel)
            target_hash = skill_dir_hash(target_dir / skill_name)
            if source_hash == target_hash:
                continue

            # 记录版本详情
            if skill_name not in skill_versions:
                source_skill = source_dir / source_rel / "SKILL.md"
                skill_versions[skill_name] = (source_rel, source_skill.stat().st_mtime, [])
            skill_versions[skill_name][2].append(
                (target_dir, target_hash, (target_dir / skill_name / "SKILL.md").stat().st_mtime)
            )

            # 基于 SKILL.md mtime 判断修改来源
            source_mtime = skill_versions[skill_name][1]
            target_mtime = skill_versions[skill_name][2][-1][2]
            if target_mtime > source_mtime:
                target_updated.setdefault(skill_name, []).append(target_dir)
            else:
                source_also_changed.add(skill_name)

    # 分析冲突：遍历所有有变更的 skill，决定动作
    all_changed_skills = set(target_updated.keys()) | source_also_changed
    for skill_name in sorted(all_changed_skills):
        source_rel, source_mtime, targets_info = skill_versions[skill_name]
        modified_targets = target_updated.get(skill_name, [])
        source_changed = skill_name in source_also_changed

        # 情况1: 多个目标都修改了 → 冲突
        if len(modified_targets) > 1:
            plan.warnings.append(
                _build_version_warning(skill_name, source_dir, source_rel, source_mtime, targets_info, alias_map, targets)
            )
        # 情况2: 源和目标都修改了 → 冲突
        elif modified_targets and source_changed:
            plan.warnings.append(
                _build_version_warning(skill_name, source_dir, source_rel, source_mtime, targets_info, alias_map, targets)
            )
        # 情况3: 仅目标修改了 → 安全收集
        elif modified_targets:
            plan.collect_update.append((skill_name, source_rel, modified_targets[0]))
        # 情况4: 仅源修改了 → 提示用 --force
        else:
            plan.warnings.append(
                _build_version_warning(skill_name, source_dir, source_rel, source_mtime, targets_info, alias_map, targets)
            )

    # 阶段2：计算分发变更
    source_skills = find_skills_in_source(source_dir)
    all_source_names = {s.name for s in source_skills}
    all_source_names.update(name for name, _ in plan.collect_new)

    for target_dir in targets:
        target_names = set(find_skills_in_target(target_dir))
        # 多余的要删除
        for name in target_names - all_source_names:
            plan.deletes.append((name, target_dir))
        # 缺少的要新增
        for name in all_source_names - target_names:
            plan.creates.append((name, target_dir))

    return plan


def preview_force(source_dir: Path, targets: list[Path]) -> SyncPlan:
    plan = SyncPlan()
    source_skills = find_skills_in_source(source_dir)
    source_map = {s.name: s.rel_path for s in source_skills}
    source_names = set(source_map.keys())

    for target_dir in targets:
        target_dir.mkdir(parents=True, exist_ok=True)
        target_names = set(find_skills_in_target(target_dir))

        for name in target_names - source_names:
            plan.deletes.append((name, target_dir))
        for name in source_names - target_names:
            plan.creates.append((name, target_dir))
        # 同名但内容不同 → 覆盖
        for name in source_names & target_names:
            source_hash = skill_dir_hash(source_dir / source_map[name])
            target_hash = skill_dir_hash(target_dir / name)
            if source_hash != target_hash:
                plan.updates.append((name, source_map[name], target_dir))

    return plan


# ============================================================
# 展示预览
# ============================================================

def show_preview(plan: SyncPlan, source_dir: Path, targets: list[Path], force: bool) -> bool:
    """展示变更预览，返回是否有变更"""
    source_skills = find_skills_in_source(source_dir)
    source_count = len(source_skills)

    mode = "强制同步" if force else "双向同步"
    print(f"\n{Color.BOLD}========================================{Color.NC}")
    print(f"{Color.BOLD}  变更预览（{mode}）{Color.NC}")
    print(f"{Color.BOLD}========================================{Color.NC}\n")

    if force:
        print(f"{Color.YELLOW}模式: 以源目录为准，强制覆盖所有目标目录{Color.NC}")
        print(f"源目录 skills 数量: {Color.CYAN}{source_count}{Color.NC}\n")
    else:
        total_after = source_count + len(plan.collect_new)
        print(f"源目录当前 skills 数量: {Color.CYAN}{source_count}{Color.NC}, 同步后: {Color.CYAN}{total_after}{Color.NC}\n")

    if not plan.has_changes and not plan.has_warnings:
        label = "所有目标目录已与源目录一致，无需操作" if force else "没有任何变更需要执行"
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
                print(f"  {Color.BOLD}{target_dir}{Color.NC}  {Color.GREEN}✓ 无变更{Color.NC}")
                continue

            print(f"  {Color.BOLD}{target_dir}{Color.NC}")
            if dir_creates:
                print(f"    {Color.GREEN}新增 ({len(dir_creates)}):{Color.NC}")
                for name in dir_creates:
                    print(f"      {Color.GREEN}+{Color.NC} {name}")
            if dir_updates:
                print(f"    {Color.YELLOW}覆盖 ({len(dir_updates)}):{Color.NC}")
                for name, source_rel in dir_updates:
                    print(f"      {Color.YELLOW}~{Color.NC} {name}  ← {source_rel}")
            if dir_deletes:
                print(f"    {Color.RED}删除 ({len(dir_deletes)}):{Color.NC}")
                for name in dir_deletes:
                    print(f"      {Color.RED}-{Color.NC} {name}")
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

        if not dir_creates and not dir_deletes:
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

        log_success(f"  ✓ 完成: 新增 {len(dir_creates)} 个, 删除 {len(dir_deletes)} 个")
        total_ops += len(dir_creates) + len(dir_deletes)
        print(file=sys.stderr)

    return {"collected": collected, "updated": updated, "distributed": total_ops}


def execute_force(plan: SyncPlan, source_dir: Path, targets: list[Path]):
    source_skills = find_skills_in_source(source_dir)
    source_map = {s.name: s.rel_path for s in source_skills}

    total_created = 0
    total_deleted = 0
    total_updated = 0

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
            skill_path = find_skill_path(target_dir, name)
            if skill_path:
                shutil.rmtree(skill_path)
                log_warning(f"  删除: {name}")
                total_deleted += 1

        for name, _ in dir_creates:
            rel_path = source_map.get(name)
            if rel_path:
                shutil.copytree(source_dir / rel_path, target_dir / name, copy_function=shutil.copy2)
                total_created += 1

        for name, source_rel, _ in dir_updates:
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

def verify_sync(source_dir: Path, targets: list[Path]) -> bool:
    log_info("========== 验证同步结果 ==========")
    print(file=sys.stderr)

    source_skills = find_skills_in_source(source_dir)
    source_count = len(source_skills)
    log_info(f"源目录 skills 数量: {source_count}")

    # 检查重名
    dups = check_duplicate_names(source_skills)
    if dups:
        for name, p1, p2 in dups:
            log_error(f"发现重名 skill: {name} ({p1} vs {p2})")
        print(file=sys.stderr)

    all_match = True
    for target_dir in targets:
        if not target_dir.is_dir():
            continue
        target_count = len(find_skills_in_target(target_dir))
        if target_count != source_count:
            log_error(f"✗ {target_dir}: {target_count} 个 skills (数量不一致!)")
            all_match = False
            continue
        # 检查每个 skill 的内容哈希
        hash_mismatch = False
        for skill in source_skills:
            target_skill_path = target_dir / skill.name
            if target_skill_path.is_dir():
                source_hash = skill_dir_hash(source_dir / skill.rel_path)
                target_hash = skill_dir_hash(target_skill_path)
                if source_hash != target_hash:
                    log_error(f"✗ {target_dir}/{skill.name}: 内容不一致")
                    hash_mismatch = True
                    all_match = False
        if not hash_mismatch:
            log_success(f"✓ {target_dir}: {target_count} 个 skills (内容一致)")

    print(file=sys.stderr)
    if all_match and not dups:
        log_success("所有目录同步成功，内容完全一致")
    else:
        log_error("同步存在问题，请检查")

    return all_match and not dups


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
# CLI
# ============================================================

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Skills 同步工具")
    parser.add_argument("--force", "-f", action="store_true", help="强制同步模式（可选择任意目录为基准同步到其他目录）")
    parser.add_argument("--delete", "-d", type=str, metavar="SKILL_NAME", help="删除指定的 skill（从源目录和所有目标目录）")
    parser.add_argument("-y", "--yes", action="store_true", help="跳过确认")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE, help="源目录路径")
    parser.add_argument("--targets", type=str, default=None, help="目标目录路径，逗号分隔")
    args = parser.parse_args(argv)

    if args.targets:
        args.targets = [Path(t.strip()) for t in args.targets.split(",")]
    else:
        args.targets = list(DEFAULT_TARGETS)

    return args


def main(argv: list[str] | None = None):
    args = parse_args(argv)
    source_dir: Path = args.source
    targets: list[Path] = args.targets
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
        all_dirs_with_alias = [(source_dir, "源")] + [(t, t.parent.name) for t in targets]

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
        plan = preview_force(base_dir, other_dirs)

        if not show_preview(plan, base_dir, other_dirs, force=True):
            log_success("无需同步")
            return

        # 4. 确认
        if not ask_confirmation(args.yes):
            return

        # 5. 执行
        stats = execute_force(plan, base_dir, other_dirs)
        verify_sync(base_dir, other_dirs)
        print("========================================")
        print("  同步完成")
        print("========================================")
        print(f"{Color.GREEN}新增: {stats['created']} 个{Color.NC}")
        print(f"{Color.YELLOW}覆盖: {stats['updated']} 个{Color.NC}")
        print(f"{Color.RED}删除: {stats['deleted']} 个{Color.NC}")
    else:
        plan = preview_bidirectional(source_dir, targets)

        if not show_preview(plan, source_dir, targets, force=False):
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
