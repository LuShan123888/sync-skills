"""sync_skills 回归测试"""

import shutil
import time
from pathlib import Path

import pytest

from sync_skills.cli import (
    ConflictResolution,
    SyncPlan,
    ask_base_selection,
    ask_conflict_resolution,
    check_duplicate_names,
    execute_bidirectional,
    execute_delete,
    execute_force,
    find_skill_in_source_by_name,
    find_skill_in_targets,
    find_skills_in_source,
    find_skills_in_target,
    main,
    preview_bidirectional,
    preview_force,
    show_overview,
    show_preview,
    skill_dir_hash,
    _build_skill_version,
    _resolve_conflicts,
)


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def env(tmp_path: Path):
    """创建测试环境：source + target_a + target_b"""
    source = tmp_path / "source"
    target_a = tmp_path / "target_a"
    target_b = tmp_path / "target_b"
    source.mkdir()
    target_a.mkdir()
    target_b.mkdir()
    return source, target_a, target_b


def create_skill(base: Path, name: str, content: str = "") -> Path:
    """在目录下创建一个平铺 skill"""
    skill_dir = base / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(content or f"# {name}")
    return skill_dir


def create_skill_in_category(source: Path, category: str, name: str, content: str = "") -> Path:
    """在源目录下按分类创建 skill"""
    skill_dir = source / category / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(content or f"# {name}")
    return skill_dir


def run_main(source: Path, targets: list[Path], force: bool = False):
    """运行 main 函数"""
    targets_str = ",".join(str(t) for t in targets)
    args = ["-y", "--source", str(source), "--targets", targets_str]
    if force:
        args.append("--force")
    main(args)


# ============================================================
# 扫描函数测试
# ============================================================


class TestScan:
    def test_find_skills_in_source(self, env):
        source, _, _ = env
        create_skill_in_category(source, "Code", "skill-a")
        create_skill_in_category(source, "Lark", "skill-b")

        skills = find_skills_in_source(source)
        names = {s.name for s in skills}
        assert names == {"skill-a", "skill-b"}

    def test_find_skills_in_source_empty(self, env):
        source, _, _ = env
        assert find_skills_in_source(source) == []

    def test_find_skills_in_source_nonexistent(self, tmp_path):
        assert find_skills_in_source(tmp_path / "nope") == []

    def test_find_skills_in_target(self, env):
        _, target_a, _ = env
        create_skill(target_a, "skill-a")
        create_skill(target_a, "skill-b")
        # 没有 SKILL.md 的目录不算
        (target_a / "not-a-skill").mkdir()

        names = find_skills_in_target(target_a)
        assert set(names) == {"skill-a", "skill-b"}

    def test_find_skill_in_source_by_name(self, env):
        source, _, _ = env
        create_skill_in_category(source, "Code", "my-skill")
        assert find_skill_in_source_by_name(source, "my-skill") == "Code/my-skill"
        assert find_skill_in_source_by_name(source, "nope") is None

    def test_check_duplicate_names(self):
        from sync_skills.cli import Skill
        skills = [
            Skill("dup", "Code/dup"),
            Skill("unique", "Lark/unique"),
            Skill("dup", "Other/dup"),
        ]
        dups = check_duplicate_names(skills)
        assert len(dups) == 1
        assert dups[0][0] == "dup"

    def test_check_no_duplicates(self):
        from sync_skills.cli import Skill
        skills = [Skill("a", "Code/a"), Skill("b", "Lark/b")]
        assert check_duplicate_names(skills) == []

    def test_skill_dir_hash_identical(self, env):
        """相同内容的目录产生相同哈希"""
        source, target_a, _ = env
        create_skill_in_category(source, "Code", "skill-a", "hello")
        create_skill(target_a, "skill-a", "hello")

        assert skill_dir_hash(source / "Code" / "skill-a") == skill_dir_hash(target_a / "skill-a")

    def test_skill_dir_hash_different(self, env):
        """不同内容的目录产生不同哈希"""
        source, target_a, _ = env
        create_skill_in_category(source, "Code", "skill-a", "hello")
        create_skill(target_a, "skill-a", "world")

        assert skill_dir_hash(source / "Code" / "skill-a") != skill_dir_hash(target_a / "skill-a")

    def test_skill_dir_hash_extra_file_detected(self, env):
        """目录中新增额外文件会导致哈希变化"""
        source, target_a, _ = env
        create_skill_in_category(source, "Code", "skill-a", "same")
        create_skill(target_a, "skill-a", "same")
        # 目标多一个文件
        (target_a / "skill-a" / "extra.txt").write_text("extra")

        assert skill_dir_hash(source / "Code" / "skill-a") != skill_dir_hash(target_a / "skill-a")

    def test_skill_dir_hash_order_independent(self, env):
        """文件创建顺序不影响哈希（因为按路径排序）"""
        _, target_a, _ = env
        create_skill(target_a, "skill-a", "content")
        (target_a / "skill-a" / "b.txt").write_text("b")
        (target_a / "skill-a" / "a.txt").write_text("a")

        hash1 = skill_dir_hash(target_a / "skill-a")
        # 重新创建，顺序相反
        shutil.rmtree(target_a / "skill-a")
        create_skill(target_a, "skill-a", "content")
        (target_a / "skill-a" / "a.txt").write_text("a")
        (target_a / "skill-a" / "b.txt").write_text("b")

        assert skill_dir_hash(target_a / "skill-a") == hash1


# ============================================================
# 双向同步测试
# ============================================================


class TestBidirectional:
    def test_no_changes(self, env):
        source, target_a, target_b = env
        create_skill_in_category(source, "Code", "skill-a", "content")
        create_skill(target_a, "skill-a", "content")
        create_skill(target_b, "skill-a", "content")

        plan = preview_bidirectional(source, [target_a, target_b])
        assert not plan.has_changes

    def test_new_skill_in_target_distributes(self, env):
        """目标目录新增 skill → 分发到源和其他目标"""
        source, target_a, target_b = env
        create_skill_in_category(source, "Code", "skill-a", "a")
        create_skill(target_a, "skill-a", "a")
        create_skill(target_a, "new-skill", "new")
        create_skill(target_b, "skill-a", "a")

        plan = preview_bidirectional(source, [target_a, target_b])
        ops = [op for op in plan.sync_ops if op.skill_name == "new-skill"]
        assert len(ops) == 2
        # target_a 是 origin
        assert all(op.origin_dir == target_a for op in ops)
        # 分发到 source 和 target_b
        dests = {op.dest_dir for op in ops}
        assert source in dests
        assert target_b in dests

    def test_target_update_distributes(self, env):
        """单个目标更新 skill → 从最新位置分发到源和其他目标"""
        source, target_a, target_b = env
        create_skill_in_category(source, "Code", "skill-a", "old")
        create_skill(target_a, "skill-a", "old")
        create_skill(target_b, "skill-a", "old")

        # 让 target_a 的版本更新
        time.sleep(0.1)
        (target_a / "skill-a" / "SKILL.md").write_text("updated")

        plan = preview_bidirectional(source, [target_a, target_b])
        ops = [op for op in plan.sync_ops if op.skill_name == "skill-a"]
        assert len(ops) == 2
        assert all(op.origin_dir == target_a for op in ops)
        dests = {op.dest_dir for op in ops}
        assert source in dests
        assert target_b in dests

    def test_source_new_skill_distributes(self, env):
        """源目录新增 skill → 分发到所有目标"""
        source, target_a, target_b = env
        create_skill_in_category(source, "Code", "skill-a", "a")
        create_skill_in_category(source, "Code", "skill-b", "b")
        create_skill(target_a, "skill-a", "a")
        create_skill(target_b, "skill-a", "a")

        plan = preview_bidirectional(source, [target_a, target_b])
        ops = [op for op in plan.sync_ops if op.skill_name == "skill-b"]
        assert len(ops) == 2
        dests = {op.dest_dir for op in ops}
        assert target_a in dests
        assert target_b in dests

    def test_orphan_skill_distributes(self, env):
        """目标多余 skill（源中不存在）→ 分发到源(Other/)和其他目标"""
        source, target_a, target_b = env
        create_skill_in_category(source, "Code", "skill-a", "a")
        create_skill(target_a, "skill-a", "a")
        create_skill(target_a, "orphan", "orphan")
        create_skill(target_b, "skill-a", "a")

        plan = preview_bidirectional(source, [target_a, target_b])
        ops = [op for op in plan.sync_ops if op.skill_name == "orphan"]
        assert len(ops) == 2
        assert any(op.dest_dir == source for op in ops)
        assert any(op.dest_dir == target_b for op in ops)

    def test_execute_distribute(self, env):
        source, target_a, target_b = env
        create_skill_in_category(source, "Code", "skill-a", "a")
        create_skill(target_a, "skill-a", "a")
        create_skill(target_a, "new-skill", "new-content")
        create_skill(target_b, "skill-a", "a")

        plan = preview_bidirectional(source, [target_a, target_b])
        execute_bidirectional(plan, source, [target_a, target_b])

        # new-skill 被分发到 Other/
        assert (source / "Other" / "new-skill" / "SKILL.md").read_text() == "new-content"
        # new-skill 被分发到 target_b
        assert (target_b / "new-skill" / "SKILL.md").is_file()

    def test_no_unnecessary_copy(self, env, capsys):
        source, target_a, target_b = env
        create_skill_in_category(source, "Code", "skill-a", "a")
        create_skill(target_a, "skill-a", "a")
        create_skill(target_b, "skill-a", "a")

        run_main(source, [target_a, target_b])
        captured = capsys.readouterr()
        assert "无需同步" in captured.err
        assert "同步到" not in captured.err

    def test_target_update_distributes_to_others(self, env):
        """单个目标修改 skill 后，从该目标分发到源和其他目标"""
        source, target_a, target_b = env
        create_skill_in_category(source, "Code", "skill-a", "old")
        create_skill(target_a, "skill-a", "new-version")
        create_skill(target_b, "skill-a", "old")

        plan = preview_bidirectional(source, [target_a, target_b])
        ops = [op for op in plan.sync_ops if op.skill_name == "skill-a"]
        assert len(ops) == 2
        # target_a 是最新版本所在位置
        assert all(op.origin_dir == target_a for op in ops)
        # 分发到 source 和 target_b
        dests = {op.dest_dir for op in ops}
        assert source in dests
        assert target_b in dests
        # 不应分发到 target_a（它已是最新）
        assert target_a not in dests

        # 执行
        execute_bidirectional(plan, source, [target_a, target_b])
        # 源应被更新
        assert (source / "Code" / "skill-a" / "SKILL.md").read_text() == "new-version"
        # target_b 应被更新
        assert (target_b / "skill-a" / "SKILL.md").read_text() == "new-version"


# ============================================================
# 强制同步测试
# ============================================================


class TestForce:
    def test_distribute_new_skill(self, env):
        source, target_a, target_b = env
        create_skill_in_category(source, "Code", "skill-a", "a")
        create_skill_in_category(source, "Lark", "skill-b", "b")

        plan = preview_force(source, [target_a, target_b])
        execute_force(plan, source, [target_a, target_b])

        assert (target_a / "skill-a" / "SKILL.md").read_text() == "a"
        assert (target_a / "skill-b" / "SKILL.md").read_text() == "b"
        assert (target_b / "skill-a" / "SKILL.md").is_file()
        assert (target_b / "skill-b" / "SKILL.md").is_file()

    def test_delete_extra_skill(self, env):
        source, target_a, target_b = env
        create_skill_in_category(source, "Code", "skill-a", "a")
        create_skill(target_a, "skill-a", "a")
        create_skill(target_a, "extra", "extra")
        create_skill(target_b, "skill-a", "a")

        plan = preview_force(source, [target_a, target_b])
        execute_force(plan, source, [target_a, target_b])

        assert (target_a / "skill-a").is_dir()
        assert not (target_a / "extra").exists()

    def test_no_changes(self, env):
        source, target_a, target_b = env
        create_skill_in_category(source, "Code", "skill-a", "a")
        create_skill(target_a, "skill-a", "a")
        create_skill(target_b, "skill-a", "a")

        plan = preview_force(source, [target_a, target_b])
        assert not plan.has_changes

    def test_no_modify_source(self, env):
        source, target_a, target_b = env
        create_skill_in_category(source, "Code", "skill-a", "source-content")
        create_skill(target_a, "skill-a", "target-content")
        create_skill(target_a, "new-in-target", "new")
        create_skill(target_b, "skill-a", "source-content")

        plan = preview_force(source, [target_a, target_b])
        execute_force(plan, source, [target_a, target_b])

        # 源目录不应被修改
        assert (source / "Code" / "skill-a" / "SKILL.md").read_text() == "source-content"
        assert not (source / "Other" / "new-in-target").exists()
        # 目标多余的应被删除
        assert not (target_a / "new-in-target").exists()

    def test_flatten_categories(self, env):
        source, target_a, target_b = env
        create_skill_in_category(source, "Code", "skill-a", "a")
        create_skill_in_category(source, "Lark", "skill-b", "b")
        create_skill_in_category(source, "Other", "skill-c", "c")

        plan = preview_force(source, [target_a, target_b])
        execute_force(plan, source, [target_a, target_b])

        assert (target_a / "skill-a").is_dir()
        assert (target_a / "skill-b").is_dir()
        assert (target_a / "skill-c").is_dir()
        # 不应有分类子目录
        assert not (target_a / "Code").exists()
        assert not (target_a / "Lark").exists()

    def test_empty_source(self, env, capsys):
        source, target_a, target_b = env
        run_main(source, [target_a, target_b], force=True)
        captured = capsys.readouterr()
        assert "无需同步" in captured.err

    def test_force_overwrites_different_content(self, env):
        """force 模式下，同名但内容不同的 skill 被源目录覆盖"""
        source, target_a, target_b = env
        create_skill_in_category(source, "Code", "skill-a", "source-version")
        create_skill(target_a, "skill-a", "old-version")
        create_skill(target_b, "skill-a", "source-version")

        plan = preview_force(source, [target_a, target_b])
        ops_to_a = [op for op in plan.sync_ops if op.dest_dir == target_a]
        assert len(ops_to_a) == 1
        assert ops_to_a[0].skill_name == "skill-a"
        # target_b 内容一致，不产生操作
        assert not any(op.dest_dir == target_b for op in plan.sync_ops)

        execute_force(plan, source, [target_a, target_b])
        assert (target_a / "skill-a" / "SKILL.md").read_text() == "source-version"

    def test_force_overwrites_with_extra_files(self, env):
        """force 模式下，目标 skill 有额外文件时也完整覆盖"""
        source, target_a, _ = env
        create_skill_in_category(source, "Code", "skill-a", "src")
        create_skill(target_a, "skill-a", "tgt")
        (target_a / "skill-a" / "extra.txt").write_text("extra")

        plan = preview_force(source, [target_a])
        ops_to_a = [op for op in plan.sync_ops if op.dest_dir == target_a]
        assert len(ops_to_a) == 1
        execute_force(plan, source, [target_a])
        assert (target_a / "skill-a" / "SKILL.md").read_text() == "src"
        # 额外文件被清除（整个目录被替换）
        assert not (target_a / "skill-a" / "extra.txt").exists()


# ============================================================
# 错误处理测试
# ============================================================


class TestErrors:
    def test_duplicate_skill_names(self, env):
        source, target_a, target_b = env
        create_skill_in_category(source, "Code", "dup", "v1")
        create_skill_in_category(source, "Lark", "dup", "v2")

        with pytest.raises(SystemExit):
            run_main(source, [target_a, target_b], force=True)

    def test_nonexistent_source_force(self, tmp_path):
        source = tmp_path / "nonexistent"
        target = tmp_path / "target"
        target.mkdir()

        with pytest.raises(SystemExit):
            run_main(source, [target], force=True)


# ============================================================
# 预览展示测试
# ============================================================


class TestPreview:
    def test_preview_shows_actual_origin_for_target_update(self, env, capsys):
        """目标目录修改 skill 后，预览中其他目标应显示实际源头而非源目录"""
        source, target_a, target_b = env
        create_skill_in_category(source, "Code", "skill-a", "old")
        create_skill(target_a, "skill-a", "new-version")
        create_skill(target_b, "skill-a", "old")

        plan = preview_bidirectional(source, [target_a, target_b])
        show_preview(plan, source, [target_a, target_b], force=False)
        output = capsys.readouterr()
        combined = output.out + output.err
        # target_b 的更新应显示来自 target_a（实际源头），而非源目录
        assert str(target_a) in combined
        # 源目录部分显示 ← target_a
        assert "←" in combined

    def test_preview_shows_actual_origin_for_new_skill(self, env, capsys):
        """目标目录新增 skill 后，预览中其他目标应显示实际源头"""
        source, target_a, target_b = env
        create_skill(target_a, "new-skill", "new")
        create_skill(target_b, "new-skill", "new")

        plan = preview_bidirectional(source, [target_a, target_b])
        show_preview(plan, source, [target_a, target_b], force=False)
        output = capsys.readouterr()
        combined = output.out + output.err
        # 新 skill 的源头应显示来自 target_a
        assert "new-skill" in combined

    def test_preview_shows_per_directory(self, env, capsys):
        source, target_a, target_b = env
        create_skill_in_category(source, "Code", "skill-a", "a")
        create_skill_in_category(source, "Code", "skill-b", "b")
        create_skill(target_a, "skill-a", "a")
        # target_a 缺 skill-b，target_b 全缺

        run_main(source, [target_a, target_b])
        output = capsys.readouterr()
        combined = output.out + output.err
        assert str(target_a) in combined
        assert str(target_b) in combined
        assert "skill-b" in combined

    def test_force_preview_shows_delete(self, env, capsys):
        source, target_a, target_b = env
        create_skill_in_category(source, "Code", "skill-a", "a")
        create_skill(target_a, "skill-a", "a")
        create_skill(target_a, "to-delete", "del")
        create_skill(target_b, "skill-a", "a")

        run_main(source, [target_a, target_b], force=True)
        output = capsys.readouterr()
        combined = output.out + output.err
        assert "to-delete" in combined
        assert "-" in combined  # 删除标记

    def test_no_changes_no_confirm(self, env, capsys):
        source, target_a, target_b = env
        create_skill_in_category(source, "Code", "skill-a", "a")
        create_skill(target_a, "skill-a", "a")
        create_skill(target_b, "skill-a", "a")

        run_main(source, [target_a, target_b])
        output = capsys.readouterr()
        combined = output.out + output.err
        assert "无需同步" in combined
        assert "确认执行" not in combined


# ============================================================
# 多目标独立性测试
# ============================================================


class TestMultiTarget:
    def test_collect_from_multiple_targets(self, env):
        """S2: 多个目标各有不同的新 skill，都应分发到 Other/ 和其他目标"""
        source, target_a, target_b = env
        create_skill_in_category(source, "Code", "skill-a", "a")
        create_skill(target_a, "skill-a", "a")
        create_skill(target_a, "new-from-a", "from-a")
        create_skill(target_b, "skill-a", "a")
        create_skill(target_b, "new-from-b", "from-b")

        plan = preview_bidirectional(source, [target_a, target_b])
        execute_bidirectional(plan, source, [target_a, target_b])

        # 两个新 skill 都分发到 Other/
        assert (source / "Other" / "new-from-a" / "SKILL.md").read_text() == "from-a"
        assert (source / "Other" / "new-from-b" / "SKILL.md").read_text() == "from-b"
        # 交叉分发
        assert (target_a / "new-from-b" / "SKILL.md").is_file()
        assert (target_b / "new-from-a" / "SKILL.md").is_file()

    def test_targets_independent(self, env, capsys):
        source, target_a, target_b = env
        create_skill_in_category(source, "Code", "skill-a", "a")
        create_skill_in_category(source, "Code", "skill-b", "b")
        create_skill(target_a, "skill-a", "a")
        create_skill(target_a, "skill-b", "b")
        create_skill(target_b, "skill-a", "a")

        run_main(source, [target_a, target_b])
        output = capsys.readouterr()
        combined = output.out + output.err
        assert "同步完成" in combined
        assert (target_b / "skill-b" / "SKILL.md").is_file()

    def test_collect_from_target_b_only(self, env):
        """target_b 有新 skill，target_a 没有 → 从 target_b 分发到源和 target_a"""
        source, target_a, target_b = env
        create_skill_in_category(source, "Code", "skill-a", "a")
        create_skill(target_a, "skill-a", "a")
        create_skill(target_b, "skill-a", "a")
        create_skill(target_b, "only-in-b", "b-content")

        plan = preview_bidirectional(source, [target_a, target_b])
        execute_bidirectional(plan, source, [target_a, target_b])

        assert (source / "Other" / "only-in-b" / "SKILL.md").read_text() == "b-content"
        assert (target_a / "only-in-b" / "SKILL.md").is_file()

    def test_collect_from_multiple_targets_duplicate(self, env):
        """多个目标各有不同的新 skill，都应分发到 Other/ 并交叉分发（与第一个 test 等价但不同场景）"""
        source, target_a, target_b = env
        create_skill_in_category(source, "Code", "skill-a", "a")
        create_skill(target_a, "skill-a", "a")
        create_skill(target_a, "new-from-a", "from-a")
        create_skill(target_b, "skill-a", "a")
        create_skill(target_b, "new-from-b", "from-b")

        plan = preview_bidirectional(source, [target_a, target_b])
        execute_bidirectional(plan, source, [target_a, target_b])

        # 两个新 skill 都分发到 Other/
        assert (source / "Other" / "new-from-a" / "SKILL.md").read_text() == "from-a"
        assert (source / "Other" / "new-from-b" / "SKILL.md").read_text() == "from-b"
        # 交叉分发
        assert (target_a / "new-from-b" / "SKILL.md").is_file()
        assert (target_b / "new-from-a" / "SKILL.md").is_file()


# ============================================================
# 删除功能测试
# ============================================================


class TestDelete:
    """测试 delete 命令"""

    def test_delete_skill_from_all_locations(self, env):
        """skill 存在于源和所有目标 → 全部删除"""
        source, target_a, target_b = env
        create_skill_in_category(source, "Code", "to-delete", "del")
        create_skill(target_a, "to-delete", "del")
        create_skill(target_b, "to-delete", "del")

        # 执行删除
        execute_delete("to-delete", source, [target_a, target_b], auto_confirm=True)

        # 源和目标都应被删除
        assert not (source / "Code" / "to-delete").exists()
        assert not (target_a / "to-delete").exists()
        assert not (target_b / "to-delete").exists()

    def test_delete_skill_partial_exist(self, env):
        """skill 只存在于部分位置 → 删除存在的，忽略不存在的"""
        source, target_a, target_b = env
        create_skill_in_category(source, "Code", "partial-skill", "p")
        create_skill(target_a, "partial-skill", "p")
        # target_b 没有

        execute_delete("partial-skill", source, [target_a, target_b], auto_confirm=True)

        assert not (source / "Code" / "partial-skill").exists()
        assert not (target_a / "partial-skill").exists()
        # target_b 本来就没有，不报错

    def test_delete_nonexistent_skill(self, env):
        """skill 不存在 → 报错退出"""
        source, target_a, target_b = env

        with pytest.raises(SystemExit):
            execute_delete("nonexistent", source, [target_a, target_b], auto_confirm=True)

    def test_delete_only_in_targets(self, env):
        """skill 只在目标目录存在，源目录不存在 → 删除所有目标中的 skill"""
        source, target_a, target_b = env
        create_skill(target_a, "only-in-targets", "t")
        create_skill(target_b, "only-in-targets", "t")

        execute_delete("only-in-targets", source, [target_a, target_b], auto_confirm=True)

        assert not (target_a / "only-in-targets").exists()
        assert not (target_b / "only-in-targets").exists()

    def test_delete_with_other_skills_untouched(self, env):
        """删除一个 skill 不影响其他 skill"""
        source, target_a, target_b = env
        create_skill_in_category(source, "Code", "to-delete", "del")
        create_skill_in_category(source, "Code", "keep-me", "keep")
        create_skill(target_a, "to-delete", "del")
        create_skill(target_a, "keep-me", "keep")
        create_skill(target_b, "to-delete", "del")
        create_skill(target_b, "keep-me", "keep")

        execute_delete("to-delete", source, [target_a, target_b], auto_confirm=True)

        # to-delete 被删除
        assert not (source / "Code" / "to-delete").exists()
        assert not (target_a / "to-delete").exists()
        assert not (target_b / "to-delete").exists()
        # keep-me 保持不变
        assert (source / "Code" / "keep-me" / "SKILL.md").read_text() == "keep"
        assert (target_a / "keep-me" / "SKILL.md").read_text() == "keep"
        assert (target_b / "keep-me" / "SKILL.md").read_text() == "keep"

    def test_find_skill_in_targets(self, env):
        """测试辅助函数 find_skill_in_targets"""
        source, target_a, target_b = env
        create_skill(target_a, "skill-a")
        create_skill(target_b, "skill-b")

        # skill-a 只在 target_a
        assert find_skill_in_targets([target_a, target_b], "skill-a") == [target_a]
        # skill-b 只在 target_b
        assert find_skill_in_targets([target_a, target_b], "skill-b") == [target_b]
        # skill-c 不存在
        assert find_skill_in_targets([target_a, target_b], "skill-c") == []


# ============================================================
# 用户场景回归测试（对应 DESIGN.md 第3节）
# ============================================================


class TestUserScenarios:
    """覆盖 DESIGN.md 中定义的所有用户场景"""

    def test_s1_source_add_skill(self, env):
        """S1: 在源目录新增 skill → 分发到所有目标，已有 skill 不受影响"""
        source, target_a, target_b = env
        create_skill_in_category(source, "Code", "existing", "old")
        create_skill_in_category(source, "Code", "new-skill", "new")
        create_skill(target_a, "existing", "old")
        create_skill(target_b, "existing", "old")

        run_main(source, [target_a, target_b])

        # new-skill 被分发到两个目标
        assert (target_a / "new-skill" / "SKILL.md").read_text() == "new"
        assert (target_b / "new-skill" / "SKILL.md").read_text() == "new"
        # existing 保持不变
        assert (target_a / "existing" / "SKILL.md").read_text() == "old"
        assert (target_b / "existing" / "SKILL.md").read_text() == "old"

    def test_s1_source_add_nested(self, env):
        """S1: 在源目录嵌套分类中新增 skill → 平铺分发"""
        source, target_a, target_b = env
        create_skill_in_category(source, "Code", "skill-a", "a")
        create_skill_in_category(source, "Lark/SubCategory", "deep-skill", "deep")
        create_skill(target_a, "skill-a", "a")
        create_skill(target_b, "skill-a", "a")

        run_main(source, [target_a, target_b])

        # 嵌套分类下的 skill 也被平铺分发
        assert (target_a / "deep-skill" / "SKILL.md").read_text() == "deep"
        assert (target_b / "deep-skill" / "SKILL.md").read_text() == "deep"
        # 不应有分类目录
        assert not (target_a / "Lark").exists()

    def test_s2_target_add_skill(self, env):
        """S2: 在某个目标新增 skill → 分发到 Other/ 和其他目标"""
        source, target_a, target_b = env
        create_skill_in_category(source, "Code", "skill-a", "a")
        create_skill(target_a, "skill-a", "a")
        create_skill(target_a, "created-in-codex", "codex-new")
        create_skill(target_b, "skill-a", "a")

        run_main(source, [target_a, target_b])

        # 分发到源 Other/
        assert (source / "Other" / "created-in-codex" / "SKILL.md").read_text() == "codex-new"
        # 分发到 target_b
        assert (target_b / "created-in-codex" / "SKILL.md").read_text() == "codex-new"
        # target_a 中原始的保持不变
        assert (target_a / "created-in-codex" / "SKILL.md").is_file()

    def test_s3_target_update_skill(self, env):
        """S3: 在某个目标修改 skill → 更新回源 → 分发到其他目标"""
        source, target_a, target_b = env
        create_skill_in_category(source, "Code", "skill-a", "original")
        create_skill(target_a, "skill-a", "original")
        create_skill(target_b, "skill-a", "original")

        # 在 target_a 中修改
        time.sleep(0.1)
        (target_a / "skill-a" / "SKILL.md").write_text("updated-in-codex")

        run_main(source, [target_a, target_b])

        # 源被更新
        assert (source / "Code" / "skill-a" / "SKILL.md").read_text() == "updated-in-codex"

    def test_s5_source_duplicate_names(self, env):
        """S5: 源目录不同分类下重名 → 报错退出"""
        source, target_a, target_b = env
        create_skill_in_category(source, "Code", "dup-skill", "v1")
        create_skill_in_category(source, "Lark", "dup-skill", "v2")

        with pytest.raises(SystemExit):
            run_main(source, [target_a, target_b])

    def test_s4_source_updated_auto_distributes(self, env):
        """S4: 源目录修改 skill → 自动分发到所有目标（不再视为冲突）"""
        source, target_a, target_b = env
        create_skill_in_category(source, "Code", "skill-a", "old")
        create_skill(target_a, "skill-a", "old")
        create_skill(target_b, "skill-a", "old")

        # 源目录修改
        (source / "Code" / "skill-a" / "SKILL.md").write_text("updated-in-source")

        plan = preview_bidirectional(source, [target_a, target_b])
        # 不应有冲突
        assert not plan.has_conflicts
        # 源版本应自动分发到目标
        ops = [op for op in plan.sync_ops if op.skill_name == "skill-a"]
        assert len(ops) == 2
        assert all(op.origin_dir == source for op in ops)
        dests = {op.dest_dir for op in ops}
        assert target_a in dests
        assert target_b in dests

    def test_s6_multi_target_conflict(self, env):
        """S6: 多个目标同时修改同一 skill → 冲突"""
        source, target_a, target_b = env
        create_skill_in_category(source, "Code", "skill-a", "original")
        create_skill(target_a, "skill-a", "original")
        create_skill(target_b, "skill-a", "original")

        # 两个目标都修改了同一个 skill
        (target_a / "skill-a" / "SKILL.md").write_text("updated-by-a")
        (target_b / "skill-a" / "SKILL.md").write_text("updated-by-b")

        plan = preview_bidirectional(source, [target_a, target_b])
        # 应有冲突
        assert plan.has_conflicts
        conflict_names = [name for name, _ in plan.conflicts]
        assert "skill-a" in conflict_names

    def test_s6b_source_and_target_both_modified(self, env):
        """S6b: 源和目标都修改了同一 skill → 冲突"""
        source, target_a, target_b = env
        create_skill_in_category(source, "Code", "skill-a", "original")
        create_skill(target_a, "skill-a", "original")
        create_skill(target_b, "skill-a", "original")

        # 源先修改
        (source / "Code" / "skill-a" / "SKILL.md").write_text("updated-in-source")
        # 目标后修改
        (target_a / "skill-a" / "SKILL.md").write_text("updated-in-target")

        plan = preview_bidirectional(source, [target_a, target_b])
        # 应有冲突
        assert plan.has_conflicts
        conflict_names = [name for name, _ in plan.conflicts]
        assert "skill-a" in conflict_names

    def test_s7_delete_from_target_gets_restored(self, env):
        """S7: 从目标删除 skill → 双向同步会重新分发回来"""
        source, target_a, target_b = env
        create_skill_in_category(source, "Code", "skill-a", "a")
        create_skill_in_category(source, "Code", "skill-b", "b")
        create_skill(target_a, "skill-a", "a")
        create_skill(target_a, "skill-b", "b")
        create_skill(target_b, "skill-a", "a")
        create_skill(target_b, "skill-b", "b")

        # 从 target_a 删除 skill-b
        shutil.rmtree(target_a / "skill-b")
        assert not (target_a / "skill-b").exists()

        run_main(source, [target_a, target_b])

        # skill-b 被从源重新分发回 target_a
        assert (target_a / "skill-b" / "SKILL.md").read_text() == "b"

    def test_s8_delete_from_source_bidir_collects_back(self, env):
        """S8: 从源目录删除 skill → 双向同步会从目标收集回来"""
        source, target_a, target_b = env
        create_skill_in_category(source, "Code", "skill-a", "a")
        create_skill_in_category(source, "Code", "to-delete", "del")
        create_skill(target_a, "skill-a", "a")
        create_skill(target_a, "to-delete", "del")
        create_skill(target_b, "skill-a", "a")
        create_skill(target_b, "to-delete", "del")

        # 从源删除
        shutil.rmtree(source / "Code" / "to-delete")
        assert not (source / "Code" / "to-delete").exists()

        run_main(source, [target_a, target_b])

        # 双向模式下，to-delete 被从目标分发回 Other/
        assert (source / "Other" / "to-delete" / "SKILL.md").is_file()

    def test_s8_delete_from_source_force_removes_all(self, env):
        """S8: 从源目录删除 skill + force 模式 → 从所有目标也删除"""
        source, target_a, target_b = env
        create_skill_in_category(source, "Code", "skill-a", "a")
        create_skill_in_category(source, "Code", "to-delete", "del")
        create_skill(target_a, "skill-a", "a")
        create_skill(target_a, "to-delete", "del")
        create_skill(target_b, "skill-a", "a")
        create_skill(target_b, "to-delete", "del")

        # 从源删除
        shutil.rmtree(source / "Code" / "to-delete")

        run_main(source, [target_a, target_b], force=True)

        # force 模式下，目标中的 to-delete 被删除
        assert not (target_a / "to-delete").exists()
        assert not (target_b / "to-delete").exists()
        # 源中也没有被收集回来
        assert not (source / "Other" / "to-delete").exists()
        # skill-a 不受影响
        assert (target_a / "skill-a" / "SKILL.md").is_file()

    def test_s12_all_in_sync(self, env, capsys):
        """S12: 所有目录内容一致 → 无操作"""
        source, target_a, target_b = env
        create_skill_in_category(source, "Code", "skill-a", "same")
        create_skill_in_category(source, "Lark", "skill-b", "same")
        create_skill(target_a, "skill-a", "same")
        create_skill(target_a, "skill-b", "same")
        create_skill(target_b, "skill-a", "same")
        create_skill(target_b, "skill-b", "same")

        run_main(source, [target_a, target_b])
        output = capsys.readouterr()
        assert "无需同步" in output.err


# ============================================================
# 基准目录选择测试
# ============================================================


class TestBaseSelection:
    """测试 force 模式下选择基准目录的功能"""

    def test_force_with_target_as_base(self, env):
        """以目标目录为基准同步到源和其他目标"""
        source, target_a, target_b = env
        # 源有旧版本
        create_skill_in_category(source, "Code", "skill-a", "old-source")
        # target_a 有新版本（作为基准）
        create_skill(target_a, "skill-a", "new-version")
        # target_b 有旧版本
        create_skill(target_b, "skill-a", "old-target")

        # 以 target_a 为基准，同步到 source 和 target_b
        plan = preview_force(target_a, [source, target_b], original_source_dir=source)
        execute_force(plan, target_a, [source, target_b], original_source_dir=source)

        # source 作为嵌套目录：skill-a 内容不同 → 更新到 Other/
        assert (source / "Other" / "skill-a" / "SKILL.md").read_text() == "new-version"
        # 旧版本 Code/skill-a 被删除
        assert not (source / "Code" / "skill-a").exists()
        # target_b 也被覆盖为新版本
        assert (target_b / "skill-a" / "SKILL.md").read_text() == "new-version"

    def test_force_base_syncs_to_source(self, env):
        """以目标为基准时，源目录的新增放到 Other/，删除在嵌套结构中定位"""
        source, target_a, _ = env
        create_skill_in_category(source, "Code", "skill-a", "v1")
        create_skill_in_category(source, "Code", "skill-b", "v1")
        # target_a 有 skill-a 的新版本 + skill-c（源中没有）
        create_skill(target_a, "skill-a", "v2")
        create_skill(target_a, "skill-c", "v1")

        plan = preview_force(target_a, [source], original_source_dir=source)
        execute_force(plan, target_a, [source], original_source_dir=source)

        # skill-a 内容不同 → 更新到 Other/
        assert (source / "Other" / "skill-a" / "SKILL.md").read_text() == "v2"
        assert not (source / "Code" / "skill-a").exists()
        # skill-b 基准没有 → 从源删除
        assert not (source / "Code" / "skill-b").exists()
        # skill-c 源没有 → 新增到 Other/
        assert (source / "Other" / "skill-c" / "SKILL.md").is_file()

    def test_force_y_still_defaults_to_source(self, env, capsys):
        """-y 模式下 force 仍默认以源为基准"""
        source, target_a, target_b = env
        create_skill_in_category(source, "Code", "skill-a", "source-ver")
        create_skill(target_a, "skill-a", "source-ver")
        create_skill(target_b, "skill-a", "source-ver")

        run_main(source, [target_a, target_b], force=True)
        captured = capsys.readouterr()
        # -y 模式不应出现选择基准目录的提示
        assert "请选择基准目录" not in captured.out
        assert "请选择基准目录" not in captured.err

    def test_show_overview_displays_mismatch(self, env, capsys):
        """概览应展示不一致数量"""
        source, target_a, _ = env
        create_skill_in_category(source, "Code", "skill-a", "same")
        create_skill_in_category(source, "Code", "skill-b", "diff")
        create_skill(target_a, "skill-a", "same")
        create_skill(target_a, "skill-b", "different")

        from sync_skills.cli import _build_alias_map
        alias_map = _build_alias_map(source, [target_a])
        show_overview(source, [target_a], alias_map)
        captured = capsys.readouterr()
        combined = captured.out + captured.err
        assert "不一致" in combined

    def test_ask_base_selection_valid(self, env, monkeypatch):
        """输入有效数字应返回对应目录"""
        source, target_a, target_b = env
        all_dirs = [(source, "源"), (target_a, "target_a"), (target_b, "target_b")]
        monkeypatch.setattr("builtins.input", lambda _: "1")
        result = ask_base_selection(all_dirs)
        assert result == target_a

    def test_ask_base_selection_cancel(self, env, monkeypatch):
        """输入 q 应返回 None"""
        source, target_a, _ = env
        all_dirs = [(source, "源"), (target_a, "target_a")]
        monkeypatch.setattr("builtins.input", lambda _: "q")
        result = ask_base_selection(all_dirs)
        assert result is None

    def test_ask_base_selection_invalid(self, env, monkeypatch, capsys):
        """输入无效值应返回 None"""
        source, target_a, _ = env
        all_dirs = [(source, "源"), (target_a, "target_a")]
        monkeypatch.setattr("builtins.input", lambda _: "abc")
        result = ask_base_selection(all_dirs)
        assert result is None


# ============================================================
# 冲突解决测试
# ============================================================


class TestConflictResolution:
    """测试纯哈希冲突检测和交互式冲突解决"""

    def test_safe_resolve_single_target_differs(self, env):
        """单个目标不同于源 → 自动解决（singleton 是最新）"""
        source, target_a, target_b = env
        create_skill_in_category(source, "Code", "skill-a", "same")
        create_skill(target_a, "skill-a", "modified")
        create_skill(target_b, "skill-a", "same")

        plan = preview_bidirectional(source, [target_a, target_b])
        assert not plan.has_conflicts
        ops = [op for op in plan.sync_ops if op.skill_name == "skill-a"]
        assert len(ops) == 2
        assert all(op.origin_dir == target_a for op in ops)

    def test_conflict_source_differs_from_all_targets(self, env):
        """源不同于所有目标（源是 singleton）→ 自动解决：以源版本分发"""
        source, target_a, target_b = env
        create_skill_in_category(source, "Code", "skill-a", "modified-source")
        create_skill(target_a, "skill-a", "same-target")
        create_skill(target_b, "skill-a", "same-target")

        plan = preview_bidirectional(source, [target_a, target_b])
        assert not plan.has_conflicts
        ops = [op for op in plan.sync_ops if op.skill_name == "skill-a"]
        assert len(ops) == 2
        assert all(op.origin_dir == source for op in ops)

    def test_conflict_two_targets_disagree(self, env):
        """两个目标不一致 → 冲突"""
        source, target_a, target_b = env
        create_skill_in_category(source, "Code", "skill-a", "original")
        create_skill(target_a, "skill-a", "version-a")
        create_skill(target_b, "skill-a", "version-b")

        plan = preview_bidirectional(source, [target_a, target_b])
        assert plan.has_conflicts
        conflict_names = [name for name, _ in plan.conflicts]
        assert "skill-a" in conflict_names

    def test_conflict_three_versions(self, env):
        """3 个不同版本 → 冲突"""
        source, target_a, target_b = env
        create_skill_in_category(source, "Code", "skill-a", "ver1")
        create_skill(target_a, "skill-a", "ver2")
        create_skill(target_b, "skill-a", "ver3")

        plan = preview_bidirectional(source, [target_a, target_b])
        assert plan.has_conflicts

    def test_new_skill_in_multiple_targets_same_content(self, env):
        """多个目标新增同一 skill 且内容一致 → 自动分发到源"""
        source, target_a, target_b = env
        create_skill(target_a, "skill-new", "same-content")
        create_skill(target_b, "skill-new", "same-content")

        plan = preview_bidirectional(source, [target_a, target_b])
        assert not plan.has_conflicts
        ops = [op for op in plan.sync_ops if op.skill_name == "skill-new"]
        assert len(ops) >= 1
        assert any(op.dest_dir == source for op in ops)

    def test_new_skill_in_multiple_targets_different_content(self, env):
        """多个目标新增同一 skill 但内容不同 → 冲突"""
        source, target_a, target_b = env
        create_skill(target_a, "skill-new", "version-a")
        create_skill(target_b, "skill-new", "version-b")

        plan = preview_bidirectional(source, [target_a, target_b])
        assert plan.has_conflicts

    def test_ask_conflict_resolution_valid(self, env, monkeypatch):
        """monkeypatch input 选版本"""
        source, target_a, _ = env
        create_skill_in_category(source, "Code", "skill-a", "source-ver")
        create_skill(target_a, "skill-a", "target-ver")

        versions = [
            _build_skill_version(source / "Code" / "skill-a", "source", is_source=True, source_rel="Code/skill-a"),
            _build_skill_version(target_a / "skill-a", "target"),
        ]

        monkeypatch.setattr("builtins.input", lambda _: "1")
        result = ask_conflict_resolution("skill-a", versions, auto_confirm=False)
        assert result is not None
        assert result.skill_name == "skill-a"

    def test_ask_conflict_resolution_skip(self, env, monkeypatch):
        """输入 s 跳过"""
        source, target_a, _ = env
        create_skill_in_category(source, "Code", "skill-a", "source-ver")
        create_skill(target_a, "skill-a", "target-ver")

        versions = [
            _build_skill_version(source / "Code" / "skill-a", "source", is_source=True, source_rel="Code/skill-a"),
            _build_skill_version(target_a / "skill-a", "target"),
        ]

        monkeypatch.setattr("builtins.input", lambda _: "s")
        result = ask_conflict_resolution("skill-a", versions, auto_confirm=False)
        assert result is None

    def test_ask_conflict_resolution_auto(self, env):
        """-y 模式返回 None"""
        source, target_a, _ = env
        versions = [
            _build_skill_version(source / "Code" / "skill-a", "source", is_source=True, source_rel="Code/skill-a"),
            _build_skill_version(target_a / "skill-a", "target"),
        ]

        result = ask_conflict_resolution("skill-a", versions, auto_confirm=True)
        assert result is None

    def test_auto_resolve_stale_target_singleton(self, env):
        """源+一个目标内容一致且更新，另一个目标是旧版 singleton → 应分发而非收集"""
        source, target_a, target_b = env
        create_skill(target_b, "skill-a", "old-ver")
        time.sleep(1.5)
        create_skill_in_category(source, "Code", "skill-a", "new-ver")
        create_skill(target_a, "skill-a", "new-ver")

        plan = preview_bidirectional(source, [target_a, target_b])
        assert not plan.has_conflicts
        ops = [op for op in plan.sync_ops if op.skill_name == "skill-a"]
        # 只需要更新 target_b（旧版 singleton）
        assert len(ops) == 1
        assert ops[0].dest_dir == target_b

    def test_auto_resolve_stale_source_singleton(self, env):
        """源是旧版 singleton，目标们内容一致且更新 → 应从目标分发到源"""
        source, target_a, target_b = env
        create_skill_in_category(source, "Code", "skill-a", "old-ver")
        time.sleep(1.5)
        create_skill(target_a, "skill-a", "new-ver")
        create_skill(target_b, "skill-a", "new-ver")

        plan = preview_bidirectional(source, [target_a, target_b])
        assert not plan.has_conflicts
        ops = [op for op in plan.sync_ops if op.skill_name == "skill-a"]
        # 只需要更新 source（旧版 singleton）
        assert len(ops) == 1
        assert ops[0].dest_dir == source
        assert ops[0].origin_dir in (target_a, target_b)

    def test_auto_resolve_source_singleton(self, env):
        """源不同于所有目标（源是 singleton）→ 自动解决"""
        source, target_a, target_b = env
        create_skill_in_category(source, "Code", "skill-a", "source-ver")
        create_skill(target_a, "skill-a", "target-ver")
        create_skill(target_b, "skill-a", "target-ver")

        plan = preview_bidirectional(source, [target_a, target_b])
        # 源是 singleton → 自动解决，不应有冲突
        assert not plan.has_conflicts
        ops = [op for op in plan.sync_ops if op.skill_name == "skill-a"]
        assert len(ops) == 2
        assert all(op.origin_dir == source for op in ops)

    def test_resolve_conflict_from_source(self, env, monkeypatch):
        """源不同于所有目标（2 hash groups, majority >= 2）→ 自动解决：以源版本分发"""
        source, target_a, target_b = env
        create_skill_in_category(source, "Code", "skill-a", "source-ver")
        create_skill(target_a, "skill-a", "target-ver")
        create_skill(target_b, "skill-a", "target-ver")

        plan = preview_bidirectional(source, [target_a, target_b])
        # 新模型中 source singleton + majority >= 2 自动解决，不再是冲突
        assert not plan.has_conflicts
        ops = [op for op in plan.sync_ops if op.skill_name == "skill-a"]
        assert len(ops) == 2
        assert all(op.origin_dir == source for op in ops)

    def test_resolve_conflict_from_target(self, env, monkeypatch):
        """目标 singleton + majority >= 2 → 自动解决：以目标版本分发"""
        source, target_a, target_b = env
        create_skill_in_category(source, "Code", "skill-a", "source-ver")
        create_skill(target_a, "skill-a", "target-ver")
        create_skill(target_b, "skill-a", "source-ver")

        plan = preview_bidirectional(source, [target_a, target_b])
        # 新模型中 target singleton + majority >= 2 自动解决
        assert not plan.has_conflicts
        ops = [op for op in plan.sync_ops if op.skill_name == "skill-a"]
        assert len(ops) >= 1
        # target_a 版本应分发到 source 和 target_b
        assert any(op.origin_dir == target_a for op in ops)

    def test_resolve_and_execute_end_to_end(self, env, monkeypatch, capsys):
        """端到端：解决冲突 → 执行 → 验证"""
        source, target_a, target_b = env
        # 先创建目标版本，再创建源版本（确保源 mtime 最新，排序后为 index 0）
        create_skill(target_a, "skill-a", "target-a-ver")
        create_skill(target_b, "skill-a", "target-b-ver")
        time.sleep(0.05)
        create_skill_in_category(source, "Code", "skill-a", "source-ver")

        plan = preview_bidirectional(source, [target_a, target_b])
        assert plan.has_conflicts

        # 模拟用户选源版本（版本 0，mtime 最新为建议版本）
        monkeypatch.setattr("builtins.input", lambda _: "0")
        _resolve_conflicts(plan, source, [target_a, target_b], auto_confirm=False)

        assert not plan.has_conflicts
        assert len(plan.resolutions) == 1

        # 执行
        execute_bidirectional(plan, source, [target_a, target_b])

        # 两个目标都应被更新为源版本
        assert (target_a / "skill-a" / "SKILL.md").read_text() == "source-ver"
        assert (target_b / "skill-a" / "SKILL.md").read_text() == "source-ver"


# ============================================================
# TestSelectiveSync
# ============================================================


class TestSelectiveSync:
    """选择性同步：tools 和 exclude_tags 过滤

    注意：get_target_tool_name 提取 target_path.parent.name，
    所以测试需要使用 ~/.claude/skills 风格的路径结构。
    """

    @staticmethod
    def _make_targets(tmp_path: Path):
        """创建模拟真实路径结构的目标目录"""
        claude = tmp_path / ".claude" / "skills"
        codex = tmp_path / ".codex" / "skills"
        claude.mkdir(parents=True)
        codex.mkdir(parents=True)
        return claude, codex

    def test_tools_field_filters_sync_bidirectional(self, env):
        """tools: [claude] 的 skill 只同步到 .claude 目标"""
        source = env[0]
        claude, codex = self._make_targets(env[0].parent)
        create_skill_in_category(source, "Code", "skill-a", "---\ntools: [claude]\n---\n# skill-a\n")

        plan = preview_bidirectional(source, [claude, codex])
        ops_claude = [op.skill_name for op in plan.sync_ops if op.dest_dir == claude]
        ops_codex = [op.skill_name for op in plan.sync_ops if op.dest_dir == codex]
        assert "skill-a" in ops_claude
        assert "skill-a" not in ops_codex

    def test_tools_field_filters_sync_force(self, env):
        """tools: [claude] 的 skill 在 force 模式下只同步到 .claude 目标"""
        source = env[0]
        claude, codex = self._make_targets(env[0].parent)
        create_skill_in_category(source, "Code", "skill-a", "---\ntools: [claude]\n---\n# skill-a\n")

        plan = preview_force(source, [claude, codex])
        ops_claude = [op.skill_name for op in plan.sync_ops if op.dest_dir == claude]
        ops_codex = [op.skill_name for op in plan.sync_ops if op.dest_dir == codex]
        assert "skill-a" in ops_claude
        assert "skill-a" not in ops_codex

    def test_exclude_tags_skips_skill(self, env):
        """exclude_tags 中的标签阻止 skill 同步"""
        source, target_a, target_b = env
        create_skill_in_category(source, "Code", "skill-a", "---\ntags: [wip]\n---\n# skill-a\n")

        plan = preview_bidirectional(source, [target_a, target_b], exclude_tags=["wip"])
        assert len(plan.sync_ops) == 0

    def test_no_metadata_syncs_to_all(self, env):
        """无 frontmatter 的 skill 同步到所有目标"""
        source, target_a, target_b = env
        create_skill_in_category(source, "Code", "skill-a", "# skill-a\n")

        plan = preview_bidirectional(source, [target_a, target_b])
        ops_a = [op.skill_name for op in plan.sync_ops if op.dest_dir == target_a]
        ops_b = [op.skill_name for op in plan.sync_ops if op.dest_dir == target_b]
        assert "skill-a" in ops_a
        assert "skill-a" in ops_b

    def test_empty_tools_syncs_to_all(self, env):
        """tools: [] 的 skill 同步到所有目标"""
        source, target_a, target_b = env
        create_skill_in_category(source, "Code", "skill-a", "---\ntools: []\n---\n# skill-a\n")

        plan = preview_bidirectional(source, [target_a, target_b])
        ops_a = [op.skill_name for op in plan.sync_ops if op.dest_dir == target_a]
        ops_b = [op.skill_name for op in plan.sync_ops if op.dest_dir == target_b]
        assert "skill-a" in ops_a
        assert "skill-a" in ops_b

    def test_selective_sync_deletes_from_excluded_target(self, env):
        """双向同步：已在不应同步的目标中存在的 skill 应被删除"""
        source = env[0]
        claude, codex = self._make_targets(env[0].parent)
        create_skill_in_category(source, "Code", "skill-a", "---\ntools: [claude]\n---\n# skill-a\n")
        # skill-a 已在 codex 中（之前同步的）
        create_skill(codex, "skill-a", "---\ntools: [claude]\n---\n# skill-a\n")

        plan = preview_bidirectional(source, [claude, codex])
        deletes_codex = [n for n, d in plan.deletes if d == codex]
        assert "skill-a" in deletes_codex

    def test_force_deletes_from_excluded_target(self, env):
        """强制同步：已在不应同步的目标中存在的 skill 应被删除"""
        source = env[0]
        claude, codex = self._make_targets(env[0].parent)
        create_skill_in_category(source, "Code", "skill-a", "---\ntools: [claude]\n---\n# skill-a\n")
        create_skill(codex, "skill-a", "---\ntools: [claude]\n---\n# skill-a\n")

        plan = preview_force(source, [claude, codex])
        deletes_codex = [n for n, d in plan.deletes if d == codex]
        assert "skill-a" in deletes_codex

    def test_unknown_tool_warns(self, env):
        """引用未知工具的 skill 产生警告"""
        from sync_skills.metadata import warn_unknown_tools

        source, target_a, _ = env
        create_skill_in_category(source, "Code", "skill-a", "---\ntools: [nonexistent]\n---\n# skill-a\n")

        warnings = warn_unknown_tools(source, [target_a])
        assert len(warnings) == 1
        assert "nonexistent" in warnings[0]

    def test_end_to_end_force_selective(self, env):
        """端到端：force 模式下选择性同步正确执行"""
        source = env[0]
        claude, codex = self._make_targets(env[0].parent)
        create_skill_in_category(source, "Code", "skill-a", "---\ntools: [claude]\n---\n# skill-a\n")

        plan = preview_force(source, [claude, codex])
        execute_force(plan, source, [claude, codex])

        # skill-a 应只在 claude
        assert (claude / "skill-a" / "SKILL.md").is_file()
        assert not (codex / "skill-a").exists()

    def test_target_skill_respects_tools(self, env):
        """目标中的新 skill 根据 tools 字段选择性分发"""
        source = env[0]
        claude, codex = self._make_targets(env[0].parent)
        # codex 中有一个 skill 指定了只同步到 claude
        create_skill(codex, "skill-x", "---\ntools: [claude]\n---\n# skill-x\n")

        plan = preview_bidirectional(source, [claude, codex])
        ops = [op for op in plan.sync_ops if op.skill_name == "skill-x"]
        # skill-x 应分发到源和 claude，但不分发到 codex（codex 已有）
        assert any(op.dest_dir == source for op in ops)
        assert any(op.dest_dir == claude for op in ops)
        assert not any(op.dest_dir == codex for op in ops)


# ============================================================
# TestListCommand
# ============================================================


class TestListCommand:
    def test_list_all_skills(self, env, capsys):
        source, _, _ = env
        create_skill_in_category(source, "Code", "skill-a", "---\ntags: [code]\n---\n# skill-a\n")
        create_skill_in_category(source, "Lark", "skill-b", "---\ntags: [lark]\n---\n# skill-b\n")

        config_file = env[0].parent / "config.toml"
        config_file.write_text(f'source = "{source}"\n')
        main(["list", "--config", str(config_file)])
        captured = capsys.readouterr()
        assert "Code/" in captured.out
        assert "Lark/" in captured.out
        assert "skill-a" in captured.out
        assert "skill-b" in captured.out
        assert "共 2 个" in captured.out

    def test_list_filter_by_tags(self, env, capsys):
        source, _, _ = env
        create_skill_in_category(source, "Code", "skill-a", "---\ntags: [code, git]\n---\n# skill-a\n")
        create_skill_in_category(source, "Lark", "skill-b", "---\ntags: [lark]\n---\n# skill-b\n")

        config_file = env[0].parent / "config.toml"
        config_file.write_text(f'source = "{source}"\n')
        main(["list", "--tags", "code", "--config", str(config_file)])
        captured = capsys.readouterr()
        assert "skill-a" in captured.out
        assert "skill-b" not in captured.out

    def test_list_empty_source(self, env, capsys):
        source, _, _ = env
        config_file = env[0].parent / "config.toml"
        config_file.write_text(f'source = "{source}"\n')
        main(["list", "--config", str(config_file)])
        captured = capsys.readouterr()
        assert "没有找到" in captured.out

    def test_list_with_custom_source(self, env, capsys):
        source, _, _ = env
        create_skill_in_category(source, "Code", "skill-a", "# skill-a\n")
        main(["list", "--source", str(source)])
        captured = capsys.readouterr()
        assert "skill-a" in captured.out


# ============================================================
# TestSearchCommand
# ============================================================


class TestSearchCommand:
    def test_search_finds_match(self, env, capsys):
        source, _, _ = env
        create_skill_in_category(source, "Code", "git-commit",
                                 '---\ndescription: "代码提交工具"\n---\n# git-commit\n')
        main(["search", "代码提交", "--source", str(source)])
        captured = capsys.readouterr()
        assert "git-commit" in captured.out
        assert "找到 1 个" in captured.out

    def test_search_no_match(self, env, capsys):
        source, _, _ = env
        create_skill_in_category(source, "Code", "skill-a", "# skill-a\n")
        main(["search", "nonexistent", "--source", str(source)])
        captured = capsys.readouterr()
        assert "没有找到" in captured.out

    def test_search_with_custom_source(self, env, capsys):
        source, _, _ = env
        create_skill_in_category(source, "Code", "skill-a", "---\ntags: [code]\n---\n# skill-a\n")
        main(["search", "code", "--source", str(source)])
        captured = capsys.readouterr()
        assert "skill-a" in captured.out


# ============================================================
# TestInfoCommand
# ============================================================


class TestInfoCommand:
    def test_info_existing_skill(self, env, capsys):
        source, _, _ = env
        create_skill_in_category(source, "Code", "skill-a",
                                 '---\ntags: [code]\ndescription: "测试 skill"\nversion: "1.0"\n---\n# skill-a\n')
        main(["info", "skill-a", "--source", str(source)])
        captured = capsys.readouterr()
        assert "skill-a" in captured.out
        assert "code" in captured.out
        assert "测试 skill" in captured.out
        assert "1.0" in captured.out

    def test_info_nonexistent_skill(self, env):
        source, _, _ = env
        with pytest.raises(SystemExit):
            main(["info", "nonexistent", "--source", str(source)])

    def test_info_with_custom_source(self, env, capsys):
        source, _, _ = env
        create_skill_in_category(source, "Code", "skill-a", "# skill-a\n")
        main(["info", "skill-a", "--source", str(source)])
        captured = capsys.readouterr()
        assert "skill-a" in captured.out
        assert "所有目标" in captured.out


# ============================================================
# TestDryRun
# ============================================================


class TestDryRun:
    """测试 --dry-run 参数"""

    def test_dry_run_flag_in_args(self):
        from sync_skills.cli import parse_args
        args = parse_args(["--dry-run"])
        assert args.dry_run is True

    def test_dry_run_bidirectional_with_changes(self, env, capsys):
        """有新 skill 时，dry-run 应显示预览但不执行复制"""
        source, target_a, target_b = env
        create_skill_in_category(source, "Code", "skill-a", "a")
        create_skill(target_a, "skill-a", "a")
        create_skill(target_a, "new-skill", "new")
        create_skill(target_b, "skill-a", "a")

        main(["--dry-run", "-y", "--source", str(source),
              "--targets", f"{target_a},{target_b}"])
        captured = capsys.readouterr()

        # 应显示预览信息
        assert "new-skill" in captured.out or "new-skill" in captured.err
        # dry-run 提示
        assert "dry-run" in captured.err
        # 新 skill 不应被复制到 target_b
        assert not (target_b / "new-skill").exists()
        # 新 skill 不应被分发到源目录
        assert not (source / "Other" / "new-skill").exists()

    def test_dry_run_force_mode(self, env, capsys):
        """force + dry-run 应预览但不执行"""
        source, target_a, target_b = env
        create_skill_in_category(source, "Code", "skill-a", "a")
        create_skill_in_category(source, "Code", "skill-b", "b")
        # target_a 只有 skill-a，缺少 skill-b
        create_skill(target_a, "skill-a", "a")
        create_skill(target_b, "skill-a", "a")

        main(["--force", "--dry-run", "-y", "--source", str(source),
              "--targets", f"{target_a},{target_b}"])
        captured = capsys.readouterr()

        assert "dry-run" in captured.err
        # skill-b 不应被复制到 target_a
        assert not (target_a / "skill-b").exists()

    def test_dry_run_delete(self, env, capsys):
        """delete + dry-run 应显示预览但不删除"""
        source, target_a, target_b = env
        create_skill_in_category(source, "Code", "to-delete", "del")
        create_skill(target_a, "to-delete", "del")
        create_skill(target_b, "to-delete", "del")

        main(["--delete", "to-delete", "--dry-run", "-y",
              "--source", str(source), "--targets", f"{target_a},{target_b}"])
        captured = capsys.readouterr()

        assert "dry-run" in captured.err
        # skill 不应被删除
        assert (source / "Code" / "to-delete").exists()
        assert (target_a / "to-delete").exists()
        assert (target_b / "to-delete").exists()

    def test_dry_run_delete_nonexistent(self, env):
        """delete + dry-run 对不存在的 skill 仍应报错"""
        source, target_a, target_b = env
        with pytest.raises(SystemExit):
            main(["--delete", "nonexistent", "--dry-run", "-y",
                  "--source", str(source), "--targets", f"{target_a},{target_b}"])

    def test_dry_run_bidirectional_no_changes(self, env, capsys):
        """已同步状态，dry-run 不应执行任何操作"""
        source, target_a, target_b = env
        create_skill_in_category(source, "Code", "skill-a", "a")
        create_skill(target_a, "skill-a", "a")
        create_skill(target_b, "skill-a", "a")

        main(["--dry-run", "-y", "--source", str(source),
              "--targets", f"{target_a},{target_b}"])
        captured = capsys.readouterr()

        assert "无需同步" in captured.out or "无需同步" in captured.err

    def test_dry_run_force_no_changes(self, env, capsys):
        """force + dry-run 无变更时不应执行任何操作"""
        source, target_a, target_b = env
        create_skill_in_category(source, "Code", "skill-a", "a")
        create_skill(target_a, "skill-a", "a")
        create_skill(target_b, "skill-a", "a")

        main(["--force", "--dry-run", "-y", "--source", str(source),
              "--targets", f"{target_a},{target_b}"])
        captured = capsys.readouterr()

        assert "无需同步" in captured.out or "无需同步" in captured.err

    def test_dry_run_bidirectional_with_conflict(self, env, capsys):
        """双向同步 + dry-run + 冲突：源和两个目标各不相同（3 个哈希组）→ 冲突"""
        source, target_a, target_b = env
        create_skill_in_category(source, "Code", "skill-a", "source-ver")
        create_skill(target_a, "skill-a", "target-a-ver")
        create_skill(target_b, "skill-a", "target-b-ver")

        main(["--dry-run", "-y", "--source", str(source),
              "--targets", f"{target_a},{target_b}"])
        captured = capsys.readouterr()

        # 3 个哈希组 → 冲突，-y 模式下转为 warning
        assert "内容不一致" in captured.out
        # 不应修改任何文件
        assert (source / "Code" / "skill-a" / "SKILL.md").read_text() == "source-ver"
        assert (target_a / "skill-a" / "SKILL.md").read_text() == "target-a-ver"
        assert (target_b / "skill-a" / "SKILL.md").read_text() == "target-b-ver"


# ============================================================
# v1.0 新命令测试：add / remove / uninstall / push / pull / init
# ============================================================


def _create_v1_env(tmp_path: Path):
    """创建 v1.0 测试环境：repo + agents_dir + agent_dirs + config"""
    import json
    from sync_skills.config import Config, ExternalConfig

    repo = tmp_path / "Skills"
    repo_skills = repo / "skills"
    agents_dir = tmp_path / ".agents" / "skills"
    agent_dirs = [tmp_path / ".claude" / "skills", tmp_path / ".codex" / "skills"]
    state_file = tmp_path / "state" / "skills.json"

    for d in [repo_skills, agents_dir, state_file.parent] + agent_dirs:
        d.mkdir(parents=True)

    # 外部 skill lock 文件
    global_lock = tmp_path / ".agents" / ".skill-lock.json"
    local_lock = tmp_path / "skills-lock.json"
    global_lock.write_text('{"skills": {"external-skill": {"source": "npm"}}}')
    local_lock.write_text('{}')

    # 空状态文件
    state_file.write_text('{"skills": {}}')

    config = Config(
        repo=repo,
        agents_dir=agents_dir,
        agent_dirs=agent_dirs,
        external=ExternalConfig(global_lock=global_lock, local_lock=local_lock),
        state_file=state_file,
    )
    return repo, repo_skills, agents_dir, agent_dirs, config


class TestAddCommand:
    """测试 sync-skills add 命令"""

    def test_add_creates_skill_in_repo(self, tmp_path):
        """add 应在 repo 中创建真实文件"""
        repo, repo_skills, agents_dir, agent_dirs, config = _create_v1_env(tmp_path)
        from sync_skills.lifecycle import add_skill

        result = add_skill("my-skill", config, description="test skill")
        assert result is True
        assert (repo_skills / "my-skill" / "SKILL.md").is_file()

    def test_add_creates_agents_symlink(self, tmp_path):
        """add 应创建统一 Skill 目录 symlink"""
        repo, repo_skills, agents_dir, agent_dirs, config = _create_v1_env(tmp_path)
        from sync_skills.lifecycle import add_skill

        add_skill("my-skill", config)
        link = agents_dir / "my-skill"
        assert link.is_symlink()
        assert link.resolve() == (repo_skills / "my-skill").resolve()

    def test_add_creates_agent_symlinks(self, tmp_path):
        """add 应创建 Agent Skill 目录 symlink"""
        repo, repo_skills, agents_dir, agent_dirs, config = _create_v1_env(tmp_path)
        from sync_skills.lifecycle import add_skill

        add_skill("my-skill", config)
        for ad in agent_dirs:
            link = ad / "my-skill"
            assert link.is_symlink()

    def test_add_rejects_duplicate_in_repo(self, tmp_path):
        """add 应拒绝已存在于 repo 的 skill"""
        repo, repo_skills, agents_dir, agent_dirs, config = _create_v1_env(tmp_path)
        from sync_skills.lifecycle import add_skill

        add_skill("my-skill", config)
        result = add_skill("my-skill", config)
        assert result is False

    def test_add_rejects_duplicate_in_agents(self, tmp_path):
        """add 应拒绝已存在于 agents_dir 的 skill"""
        repo, repo_skills, agents_dir, agent_dirs, config = _create_v1_env(tmp_path)
        from sync_skills.lifecycle import add_skill

        # 在 agents_dir 创建外部 skill（真实目录）
        ext_dir = agents_dir / "ext-skill"
        ext_dir.mkdir()
        (ext_dir / "SKILL.md").write_text("---\nname: ext\n---\n")

        result = add_skill("ext-skill", config)
        assert result is False

    def test_add_rejects_external_skill(self, tmp_path):
        """add 应拒绝 lock 文件中的外部 skill"""
        repo, repo_skills, agents_dir, agent_dirs, config = _create_v1_env(tmp_path)
        from sync_skills.lifecycle import add_skill

        result = add_skill("external-skill", config)
        assert result is False

    def test_add_with_tags(self, tmp_path):
        """add 应支持 tags 参数"""
        repo, repo_skills, agents_dir, agent_dirs, config = _create_v1_env(tmp_path)
        from sync_skills.lifecycle import add_skill

        add_skill("my-skill", config, tags=["code", "review"])
        content = (repo_skills / "my-skill" / "SKILL.md").read_text()
        assert "code" in content
        assert "review" in content


class TestRemoveCommand:
    """测试 sync-skills remove 命令"""

    def test_remove_deletes_all_artifacts(self, tmp_path):
        """remove 应删除 repo 文件和所有 symlink"""
        repo, repo_skills, agents_dir, agent_dirs, config = _create_v1_env(tmp_path)
        from sync_skills.lifecycle import add_skill, remove_skill

        add_skill("my-skill", config)
        result = remove_skill("my-skill", config, auto_confirm=True)
        assert result is True
        assert not (repo_skills / "my-skill").exists()
        assert not (agents_dir / "my-skill").exists()
        for ad in agent_dirs:
            assert not (ad / "my-skill").exists()

    def test_remove_then_add_succeeds(self, tmp_path):
        """remove 后应该能重新 add 同名 skill（bad case: 之前 remove 不彻底导致 add 失败）"""
        repo, repo_skills, agents_dir, agent_dirs, config = _create_v1_env(tmp_path)
        from sync_skills.lifecycle import add_skill, remove_skill

        add_skill("my-skill", config)
        remove_skill("my-skill", config, auto_confirm=True)

        # 关键验证：remove 后 agents_dir 不应残留
        assert not (agents_dir / "my-skill").exists()

        # 应该能重新 add
        result = add_skill("my-skill", config)
        assert result is True

    def test_remove_rejects_external(self, tmp_path):
        """remove 应拒绝外部 skill"""
        repo, repo_skills, agents_dir, agent_dirs, config = _create_v1_env(tmp_path)
        from sync_skills.lifecycle import remove_skill

        result = remove_skill("external-skill", config, auto_confirm=True)
        assert result is False

    def test_remove_rejects_orphan(self, tmp_path):
        """remove 应拒绝未管理的 skill"""
        repo, repo_skills, agents_dir, agent_dirs, config = _create_v1_env(tmp_path)
        from sync_skills.lifecycle import remove_skill

        result = remove_skill("nonexistent", config, auto_confirm=True)
        assert result is False


class TestUnlinkCommand:
    """测试 sync-skills unlink 命令"""

    def test_unlink_restores_files(self, tmp_path):
        """unlink 应将文件还原到统一 Skill 目录"""
        repo, repo_skills, agents_dir, agent_dirs, config = _create_v1_env(tmp_path)
        from sync_skills.lifecycle import add_skill, unlink_skill

        add_skill("my-skill", config)
        result = unlink_skill(["my-skill"], config, auto_confirm=True)
        assert result is True

        # repo 中不应存在
        assert not (repo_skills / "my-skill").exists()
        # agents_dir 应有真实文件
        assert (agents_dir / "my-skill" / "SKILL.md").is_file()
        assert not (agents_dir / "my-skill").is_symlink()

    def test_unlink_preserves_agent_symlinks(self, tmp_path):
        """unlink 应保留 Agent Skill 目录 symlink"""
        repo, repo_skills, agents_dir, agent_dirs, config = _create_v1_env(tmp_path)
        from sync_skills.lifecycle import add_skill, unlink_skill

        add_skill("my-skill", config)
        unlink_skill(["my-skill"], config, auto_confirm=True)

        # Agent symlink 仍存在且有效
        for ad in agent_dirs:
            link = ad / "my-skill"
            assert link.is_symlink()
            assert link.resolve().exists()

    def test_unlink_all(self, tmp_path):
        """unlink --all 应移除所有已管理 skill"""
        repo, repo_skills, agents_dir, agent_dirs, config = _create_v1_env(tmp_path)
        from sync_skills.lifecycle import add_skill, unlink_skill

        add_skill("skill-a", config)
        add_skill("skill-b", config)
        add_skill("skill-c", config)

        result = unlink_skill(["--all"], config, auto_confirm=True)
        assert result is True

        # repo 应为空
        assert not any(repo_skills.iterdir())
        # agents_dir 应有 3 个真实目录
        assert (agents_dir / "skill-a" / "SKILL.md").is_file()
        assert (agents_dir / "skill-b" / "SKILL.md").is_file()
        assert (agents_dir / "skill-c" / "SKILL.md").is_file()

    def test_unlink_rejects_external(self, tmp_path):
        """unlink 应拒绝外部 skill"""
        repo, repo_skills, agents_dir, agent_dirs, config = _create_v1_env(tmp_path)
        from sync_skills.lifecycle import unlink_skill

        result = unlink_skill(["external-skill"], config, auto_confirm=True)
        assert result is False

    def test_unlink_no_managed_skills(self, tmp_path):
        """没有已管理 skill 时 unlink --all 应正常退出"""
        repo, repo_skills, agents_dir, agent_dirs, config = _create_v1_env(tmp_path)
        from sync_skills.lifecycle import unlink_skill

        result = unlink_skill(["--all"], config, auto_confirm=True)
        assert result is True


class TestSymlinkIsolation:
    """测试外部 skill 隔离（bad case: sync 误删外部 skill symlink）"""

    def test_sync_does_not_touch_external_skills(self, tmp_path):
        """sync 应跳过 lock 文件中的外部 skill，不创建 symlink"""
        repo, repo_skills, agents_dir, agent_dirs, config = _create_v1_env(tmp_path)
        from sync_skills.lifecycle import add_skill
        from sync_skills.symlink import sync_all_links
        from sync_skills.classification import get_external_skills
        from sync_skills.state import get_managed_skills

        # 添加自定义 skill
        add_skill("custom-skill", config)

        # 在 agents_dir 创建外部 skill（真实目录，模拟 npx skills 安装）
        ext_dir = agents_dir / "ext-from-npm"
        ext_dir.mkdir()
        (ext_dir / "SKILL.md").write_text("---\nname: ext-from-npm\n---\n")

        # 同步
        external = get_external_skills(config.external.global_lock, config.external.local_lock)
        managed = get_managed_skills(config.state_file)
        states = sync_all_links(
            config.agents_dir, config.repo_skills_dir,
            config.effective_agent_dirs, external_skills=external,
            managed_skills=managed,
        )

        # 只应管理 custom-skill，不包含 ext-from-npm
        names = [s.name for s in states]
        assert "custom-skill" in names
        assert "ext-from-npm" not in names

        # 外部 skill 应保持为真实目录
        assert ext_dir.is_dir()
        assert not ext_dir.is_symlink()

    def test_add_does_not_overwrite_external_skill(self, tmp_path):
        """add 不应覆盖 agents_dir 中已存在的外部 skill"""
        repo, repo_skills, agents_dir, agent_dirs, config = _create_v1_env(tmp_path)
        from sync_skills.lifecycle import add_skill

        # 在 agents_dir 创建外部 skill
        ext_dir = agents_dir / "ext-skill"
        ext_dir.mkdir()
        (ext_dir / "SKILL.md").write_text("---\nname: ext\n---\n")

        result = add_skill("ext-skill", config)
        assert result is False
        # 外部 skill 应保持为真实目录
        assert ext_dir.is_dir()
        assert not ext_dir.is_symlink()


class TestLinkCommand:
    """测试 sync-skills link 命令"""

    def test_link_wild_skill_from_agent_dir(self, tmp_path):
        """link 应将 Agent 目录中的野生 skill 纳入管理"""
        repo, repo_skills, agents_dir, agent_dirs, config = _create_v1_env(tmp_path)
        from sync_skills.lifecycle import link_skill

        # 在 claude skills 目录创建野生 skill
        claude_dir = agent_dirs[0]
        wild_skill = claude_dir / "wild-skill"
        wild_skill.mkdir()
        (wild_skill / "SKILL.md").write_text("# wild skill\n")

        result = link_skill("wild-skill", config, auto_confirm=True)
        assert result is True

        # 应复制到 repo
        assert (repo_skills / "wild-skill" / "SKILL.md").is_file()
        # 原 Agent 目录应为 symlink
        assert (claude_dir / "wild-skill").is_symlink()
        # 统一 Skill 目录应为 symlink
        assert (agents_dir / "wild-skill").is_symlink()

    def test_link_preserves_content(self, tmp_path):
        """link 应保留 skill 内容"""
        repo, repo_skills, agents_dir, agent_dirs, config = _create_v1_env(tmp_path)
        from sync_skills.lifecycle import link_skill

        content = "# my skill\n\nSome content here"
        claude_dir = agent_dirs[0]
        wild_skill = claude_dir / "my-skill"
        wild_skill.mkdir()
        (wild_skill / "SKILL.md").write_text(content)

        link_skill("my-skill", config, auto_confirm=True)
        assert (repo_skills / "my-skill" / "SKILL.md").read_text() == content

    def test_link_rejects_already_custom(self, tmp_path):
        """link 应拒绝已管理的自定义 skill"""
        repo, repo_skills, agents_dir, agent_dirs, config = _create_v1_env(tmp_path)
        from sync_skills.lifecycle import add_skill, link_skill

        add_skill("existing", config)
        result = link_skill("existing", config, auto_confirm=True)
        assert result is False

    def test_link_rejects_external(self, tmp_path):
        """link 应拒绝外部 skill"""
        repo, repo_skills, agents_dir, agent_dirs, config = _create_v1_env(tmp_path)
        from sync_skills.lifecycle import link_skill

        result = link_skill("external-skill", config, auto_confirm=True)
        assert result is False

    def test_link_rejects_nonexistent(self, tmp_path):
        """link 应拒绝不存在的 skill"""
        repo, repo_skills, agents_dir, agent_dirs, config = _create_v1_env(tmp_path)
        from sync_skills.lifecycle import link_skill

        result = link_skill("nonexistent", config, auto_confirm=True)
        assert result is False

    def test_detect_wild_skills(self, tmp_path):
        """detect_wild_skills 应列出所有野生 skill"""
        repo, repo_skills, agents_dir, agent_dirs, config = _create_v1_env(tmp_path)
        from sync_skills.lifecycle import detect_wild_skills

        # 在两个 Agent 目录各创建一个野生 skill
        (agent_dirs[0] / "skill-a").mkdir()
        (agent_dirs[0] / "skill-a" / "SKILL.md").write_text("# a\n")
        (agent_dirs[1] / "skill-b").mkdir()
        (agent_dirs[1] / "skill-b" / "SKILL.md").write_text("# b\n")

        wild = detect_wild_skills(config)
        names = {w["name"] for w in wild}
        assert "skill-a" in names
        assert "skill-b" in names

    def test_detect_wild_skills_ignores_managed(self, tmp_path):
        """detect_wild_skills 应忽略已管理的 skill"""
        repo, repo_skills, agents_dir, agent_dirs, config = _create_v1_env(tmp_path)
        from sync_skills.lifecycle import add_skill, detect_wild_skills

        add_skill("managed", config)
        wild = detect_wild_skills(config)
        names = {w["name"] for w in wild}
        assert "managed" not in names

    def test_detect_wild_skills_ignores_symlinks(self, tmp_path):
        """detect_wild_skills 应忽略 symlink（已管理的 skill）"""
        repo, repo_skills, agents_dir, agent_dirs, config = _create_v1_env(tmp_path)
        from sync_skills.lifecycle import add_skill, detect_wild_skills

        add_skill("linked", config)
        # agent dir 中的是 symlink，不算野生
        wild = detect_wild_skills(config)
        names = {w["name"] for w in wild}
        assert "linked" not in names

    def test_link_skill_in_multiple_agent_dirs(self, tmp_path):
        """link 应处理 skill 存在于多个 Agent 目录的情况"""
        repo, repo_skills, agents_dir, agent_dirs, config = _create_v1_env(tmp_path)
        from sync_skills.lifecycle import link_skill

        # 在两个 Agent 目录都创建同名野生 skill
        for ad in agent_dirs:
            skill = ad / "shared-skill"
            skill.mkdir()
            (skill / "SKILL.md").write_text("# shared\n")

        result = link_skill("shared-skill", config, auto_confirm=True)
        assert result is True

        # 应复制到 repo
        assert (repo_skills / "shared-skill" / "SKILL.md").is_file()
        # 两个 Agent 目录都应为 symlink
        for ad in agent_dirs:
            assert (ad / "shared-skill").is_symlink()
        # 统一 Skill 目录应为 symlink
        assert (agents_dir / "shared-skill").is_symlink()

    def test_link_skill_from_agents_dir(self, tmp_path):
        """link 应能从统一 Skill 目录收养野生 skill"""
        repo, repo_skills, agents_dir, agent_dirs, config = _create_v1_env(tmp_path)
        from sync_skills.lifecycle import link_skill

        # 在统一 Skill 目录创建野生 skill（不在 Agent 目录中）
        wild = agents_dir / "agents-dir-skill"
        wild.mkdir()
        (wild / "SKILL.md").write_text("# from agents dir\n")

        result = link_skill("agents-dir-skill", config, auto_confirm=True)
        assert result is True

        # 应复制到 repo
        assert (repo_skills / "agents-dir-skill" / "SKILL.md").is_file()
        # 原 agents_dir 中的应被替换为 symlink
        assert (agents_dir / "agents-dir-skill").is_symlink()
        # Agent 目录也应创建 symlink
        for ad in agent_dirs:
            assert (ad / "agents-dir-skill").is_symlink()


class TestPushCommand:
    """测试 sync-skills push 命令"""

    def test_push_commits_and_shows_branch_info(self, tmp_path, capsys, monkeypatch):
        """push 应 commit 并显示分支信息让用户确认"""
        repo, repo_skills, agents_dir, agent_dirs, config = _create_v1_env(tmp_path)
        from sync_skills.lifecycle import add_skill
        from sync_skills.git_ops import git_init
        from sync_skills.cli import cmd_push
        import argparse

        git_init(repo)
        add_skill("my-skill", config)

        # mock input 模拟用户取消推送
        monkeypatch.setattr("builtins.input", lambda _: "n")

        args = argparse.Namespace(message="test", config=None, dry_run=False, yes=False)
        cmd_push(args)
        captured = capsys.readouterr()

        # 应显示分支信息
        assert "分支" in captured.out
        # 用户取消
        assert "已取消" in captured.out


class TestStatusCommand:
    """测试 sync-skills status 命令"""

    def _make_args(self, config_path):
        import argparse
        return argparse.Namespace(config=config_path)

    def test_status_shows_skill_state(self, tmp_path, capsys):
        """status 应显示 skill 管理状态"""
        repo, repo_skills, agents_dir, agent_dirs, config = _create_v1_env(tmp_path)
        from sync_skills.cli import cmd_status
        from sync_skills.git_ops import git_init
        from sync_skills.lifecycle import add_skill
        from sync_skills.config import save_config

        git_init(repo)
        add_skill("test-skill", config)
        config_path = tmp_path / "config.toml"
        save_config(config, config_path)

        cmd_status(self._make_args(config_path))
        captured = capsys.readouterr()
        assert "test-skill" in captured.out

    def test_status_detects_orphan(self, tmp_path, capsys):
        """status 应检测孤儿 skill"""
        repo, repo_skills, agents_dir, agent_dirs, config = _create_v1_env(tmp_path)
        from sync_skills.cli import cmd_status
        from sync_skills.git_ops import git_init
        from sync_skills.config import save_config

        git_init(repo)

        # 创建孤儿 skill（在 agents_dir 中，不在 repo 中，不在 lock 中）
        orphan = agents_dir / "orphan-skill"
        orphan.mkdir()
        (orphan / "SKILL.md").write_text("# orphan\n")

        config_path = tmp_path / "config.toml"
        save_config(config, config_path)

        cmd_status(self._make_args(config_path))
        captured = capsys.readouterr()
        assert "孤儿" in captured.out


class TestFixCommand:
    """测试 sync-skills fix 命令"""

    def _make_args(self, config_path):
        import argparse
        return argparse.Namespace(config=config_path, dry_run=False, yes=False)

    def test_fix_detects_broken_links(self, tmp_path, capsys, monkeypatch):
        """fix 应检测断链 symlink（一级链路：agent dir → agents dir）"""
        repo, repo_skills, agents_dir, agent_dirs, config = _create_v1_env(tmp_path)
        from sync_skills.cli import cmd_fix
        from sync_skills.config import save_config

        config_path = tmp_path / "config.toml"
        save_config(config, config_path)

        # 直接在 Agent 目录创建指向 agents_dir 的断链（一级）
        import os
        os.symlink(agents_dir / "nonexistent-skill", agent_dirs[0] / "nonexistent-skill")

        monkeypatch.setattr("builtins.input", lambda _: "n")
        cmd_fix(self._make_args(config_path))
        captured = capsys.readouterr()
        assert "断链" in captured.out

    def test_fix_detects_missing_agents_links(self, tmp_path, capsys, monkeypatch):
        """fix 应检测缺失的统一 Skill 目录 symlink"""
        repo, repo_skills, agents_dir, agent_dirs, config = _create_v1_env(tmp_path)
        from sync_skills.cli import cmd_fix
        from sync_skills.lifecycle import add_skill
        from sync_skills.config import save_config

        add_skill("test-skill", config)
        config_path = tmp_path / "config.toml"
        save_config(config, config_path)

        # 手动删除统一 Skill 目录 symlink
        agents_link = agents_dir / "test-skill"
        if agents_link.is_symlink():
            agents_link.unlink()

        monkeypatch.setattr("builtins.input", lambda _: "y")
        cmd_fix(self._make_args(config_path))
        captured = capsys.readouterr()
        # 应检测到缺失并修复
        assert (agents_dir / "test-skill").is_symlink()

    def test_fix_detects_orphan_skills(self, tmp_path, capsys, monkeypatch):
        """fix 应检测孤儿 skill"""
        repo, repo_skills, agents_dir, agent_dirs, config = _create_v1_env(tmp_path)
        from sync_skills.cli import cmd_fix
        from sync_skills.config import save_config

        # 创建孤儿 skill
        orphan = agents_dir / "orphan-skill"
        orphan.mkdir()
        (orphan / "SKILL.md").write_text("# orphan\n")

        config_path = tmp_path / "config.toml"
        save_config(config, config_path)

        monkeypatch.setattr("builtins.input", lambda _: "n")
        cmd_fix(self._make_args(config_path))
        captured = capsys.readouterr()
        assert "未被管理" in captured.out

    def test_fix_adopts_orphan_skills(self, tmp_path, capsys, monkeypatch):
        """fix 应能收养孤儿 skill"""
        repo, repo_skills, agents_dir, agent_dirs, config = _create_v1_env(tmp_path)
        from sync_skills.cli import cmd_fix
        from sync_skills.config import save_config

        # 创建孤儿 skill
        orphan = agents_dir / "adopt-me"
        orphan.mkdir()
        (orphan / "SKILL.md").write_text("# adopt me\n")

        config_path = tmp_path / "config.toml"
        save_config(config, config_path)

        monkeypatch.setattr("builtins.input", lambda _: "y")
        cmd_fix(self._make_args(config_path))

        # 应已收养到 repo
        assert (repo_skills / "adopt-me" / "SKILL.md").is_file()
        # 原 agents_dir 应为 symlink
        assert (agents_dir / "adopt-me").is_symlink()


class TestPullCommand:
    """测试 sync-skills pull 命令"""

    def _make_args(self, config_path):
        import argparse
        return argparse.Namespace(config=config_path, dry_run=False, yes=False)

    def test_pull_shows_git_command(self, tmp_path, capsys, monkeypatch):
        """pull 应展示完整 git 命令"""
        repo, repo_skills, agents_dir, agent_dirs, config = _create_v1_env(tmp_path)
        from sync_skills.cli import cmd_pull
        from sync_skills.git_ops import git_init
        from sync_skills.config import save_config

        git_init(repo)
        config_path = tmp_path / "config.toml"
        save_config(config, config_path)

        monkeypatch.setattr("builtins.input", lambda _: "n")
        cmd_pull(self._make_args(config_path))
        captured = capsys.readouterr()
        assert "git" in captured.out.lower() or "已取消" in captured.out

    def test_pull_checks_state_before_pull(self, tmp_path, capsys, monkeypatch):
        """pull 应在执行前检查 skill 管理状态"""
        repo, repo_skills, agents_dir, agent_dirs, config = _create_v1_env(tmp_path)
        from sync_skills.cli import cmd_pull
        from sync_skills.git_ops import git_init
        from sync_skills.config import save_config

        git_init(repo)
        config_path = tmp_path / "config.toml"
        save_config(config, config_path)

        # 在 Agent 目录创建一级断链（指向 agents_dir 中不存在的目标）
        import os
        os.symlink(agents_dir / "broken-target", agent_dirs[0] / "broken-target")

        monkeypatch.setattr("builtins.input", lambda _: "y")
        cmd_pull(self._make_args(config_path))
        captured = capsys.readouterr()
        # 应检测到异常并提示
        assert "断链" in captured.out
