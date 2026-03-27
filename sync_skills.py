#!/usr/bin/env python3
"""Skills 同步工具

默认模式（双向同步）：
  1. 从目标目录收集新增/修改的 skills 到源目录
  2. 从源目录分发到所有目标目录
--force 模式（单向强制同步）：
  以源目录为唯一真实来源，强制覆盖所有目标目录
"""

import argparse
import shutil
import sys
from dataclasses import dataclass, field
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
    # 警告（不阻塞同步，仅提示用户）
    warnings: list[str] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return bool(self.collect_new or self.collect_update or self.creates or self.deletes)

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
# 扫描函数
# ============================================================

def find_skills_in_source(source_dir: Path) -> list[Skill]:
    """扫描源目录，返回所有 skill（支持嵌套分类）"""
    skills = []
    if not source_dir.is_dir():
        return skills
    for skill_md in source_dir.rglob("SKILL.md"):
        skill_dir = skill_md.parent
        rel_path = str(skill_dir.relative_to(source_dir))
        skills.append(Skill(name=skill_dir.name, rel_path=rel_path))
    return skills


def find_skills_in_target(target_dir: Path) -> list[str]:
    """扫描目标目录，返回所有 skill 名称（平铺结构）"""
    if not target_dir.is_dir():
        return []
    return [
        d.name for d in target_dir.iterdir()
        if d.is_dir() and (d / "SKILL.md").is_file()
    ]


def find_skill_in_source_by_name(source_dir: Path, name: str) -> str | None:
    """在源目录中查找指定名称的 skill，返回相对路径"""
    for skill_md in source_dir.rglob("SKILL.md"):
        if skill_md.parent.name == name:
            return str(skill_md.parent.relative_to(source_dir))
    return None


def find_skill_in_targets(targets: list[Path], name: str) -> list[Path]:
    """在所有目标目录中查找指定名称的 skill，返回包含该 skill 的目标目录列表"""
    result = []
    for target_dir in targets:
        if target_dir.is_dir() and (target_dir / name).is_dir() and (target_dir / name / "SKILL.md").is_file():
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

def preview_bidirectional(source_dir: Path, targets: list[Path]) -> SyncPlan:
    plan = SyncPlan()

    # 阶段1：收集新增/修改的 skills
    # 按 skill 分组记录：哪些目标有修改，源是否也有修改
    target_updated: dict[str, list[Path]] = {}     # skill_name -> [修改过的 target_dirs]
    source_also_changed: set[str] = set()           # 源也修改过的 skill 名称

    for target_dir in targets:
        if not target_dir.is_dir():
            continue
        for skill_name in find_skills_in_target(target_dir):
            source_rel = find_skill_in_source_by_name(source_dir, skill_name)
            if source_rel is None:
                plan.collect_new.append((skill_name, target_dir))
                continue

            source_skill = source_dir / source_rel / "SKILL.md"
            target_skill = target_dir / skill_name / "SKILL.md"
            if source_skill.read_bytes() == target_skill.read_bytes():
                continue

            # 内容不同，记录修改来源
            target_is_newer = target_skill.stat().st_mtime > source_skill.stat().st_mtime
            if target_is_newer:
                target_updated.setdefault(skill_name, []).append(target_dir)
            else:
                source_also_changed.add(skill_name)

    # 分析冲突：遍历所有有变更的 skill，决定动作
    all_changed_skills = set(target_updated.keys()) | source_also_changed
    for skill_name in sorted(all_changed_skills):
        source_rel = find_skill_in_source_by_name(source_dir, skill_name)
        modified_targets = target_updated.get(skill_name, [])
        source_changed = skill_name in source_also_changed

        # 情况1: 多个目标都修改了 → 冲突
        if len(modified_targets) > 1:
            dirs_str = ", ".join(str(d) for d in modified_targets)
            plan.warnings.append(
                f"skill '{skill_name}' 在多个目标目录中被修改 ({dirs_str})，已跳过自动合并，请手动处理"
            )
        # 情况2: 源和目标都修改了 → 冲突
        elif modified_targets and source_changed:
            plan.warnings.append(
                f"skill '{skill_name}' 在源目录和目标目录 ({modified_targets[0]}) 中都被修改，已跳过自动合并，请手动处理"
            )
        # 情况3: 仅目标修改了 → 安全收集
        elif modified_targets:
            plan.collect_update.append((skill_name, source_rel, modified_targets[0]))
        # 情况4: 仅源修改了 → 提示用 --force
        else:
            plan.warnings.append(
                f"skill '{skill_name}' 在源目录有更新，但双向模式不会自动覆盖目标，请使用 --force 同步"
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
    source_names = {s.name for s in source_skills}

    for target_dir in targets:
        target_dir.mkdir(parents=True, exist_ok=True)
        target_names = set(find_skills_in_target(target_dir))

        for name in target_names - source_names:
            plan.deletes.append((name, target_dir))
        for name in source_names - target_names:
            plan.creates.append((name, target_dir))

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
            print(f"  {Color.YELLOW}⚠ {warning}{Color.NC}")
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
    if plan.creates or plan.deletes:
        if not force:
            print(f"{Color.BOLD}--- 阶段2：分发（源 → 目标）---{Color.NC}\n")

        for target_dir in targets:
            dir_creates = [n for n, d in plan.creates if d == target_dir]
            dir_deletes = [n for n, d in plan.deletes if d == target_dir]

            if not dir_creates and not dir_deletes:
                print(f"  {Color.BOLD}{target_dir}{Color.NC}  {Color.GREEN}✓ 无变更{Color.NC}")
                continue

            print(f"  {Color.BOLD}{target_dir}{Color.NC}")
            if dir_creates:
                print(f"    {Color.GREEN}新增 ({len(dir_creates)}):{Color.NC}")
                for name in dir_creates:
                    print(f"      {Color.GREEN}+{Color.NC} {name}")
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
            total_deleted += 1

        for name, _ in dir_creates:
            rel_path = source_map.get(name)
            if rel_path:
                shutil.copytree(source_dir / rel_path, target_dir / name, copy_function=shutil.copy2)
                total_created += 1

        log_success(f"  ✓ 完成: 新增 {len(dir_creates)} 个, 删除 {len(dir_deletes)} 个")
        print(file=sys.stderr)

    return {"created": total_created, "deleted": total_deleted}


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
        if target_count == source_count:
            log_success(f"✓ {target_dir}: {target_count} 个 skills (一致)")
        else:
            log_error(f"✗ {target_dir}: {target_count} 个 skills (不一致!)")
            all_match = False

    print(file=sys.stderr)
    if all_match and not dups:
        log_success("所有目录同步成功，内容完全一致")
    else:
        log_error("同步存在问题，请检查")

    return all_match and not dups


# ============================================================
# 用户确认
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
    parser.add_argument("--force", "-f", action="store_true", help="强制同步模式（以源目录为准）")
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

    # 预览
    plan = preview_force(source_dir, targets) if force else preview_bidirectional(source_dir, targets)

    if not show_preview(plan, source_dir, targets, force):
        log_success("无需同步")
        return

    # 确认
    if not ask_confirmation(args.yes):
        return

    # 执行
    if force:
        stats = execute_force(plan, source_dir, targets)
        verify_sync(source_dir, targets)
        print("========================================")
        print("  同步完成")
        print("========================================")
        print(f"{Color.GREEN}新增: {stats['created']} 个{Color.NC}")
        print(f"{Color.YELLOW}删除: {stats['deleted']} 个{Color.NC}")
    else:
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
