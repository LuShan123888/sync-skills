"""sync_skills 回归测试"""

import shutil
import time
from pathlib import Path

import pytest

from sync_skills import (
    SyncPlan,
    check_duplicate_names,
    execute_bidirectional,
    execute_force,
    find_skill_in_source_by_name,
    find_skills_in_source,
    find_skills_in_target,
    main,
    preview_bidirectional,
    preview_force,
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
        from sync_skills import Skill
        skills = [
            Skill("dup", "Code/dup"),
            Skill("unique", "Lark/unique"),
            Skill("dup", "Other/dup"),
        ]
        dups = check_duplicate_names(skills)
        assert len(dups) == 1
        assert dups[0][0] == "dup"

    def test_check_no_duplicates(self):
        from sync_skills import Skill
        skills = [Skill("a", "Code/a"), Skill("b", "Lark/b")]
        assert check_duplicate_names(skills) == []


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

    def test_collect_new_skill(self, env):
        source, target_a, target_b = env
        create_skill_in_category(source, "Code", "skill-a", "a")
        create_skill(target_a, "skill-a", "a")
        create_skill(target_a, "new-skill", "new")
        create_skill(target_b, "skill-a", "a")

        plan = preview_bidirectional(source, [target_a, target_b])
        assert len(plan.collect_new) == 1
        assert plan.collect_new[0][0] == "new-skill"
        # new-skill 需要分发到 target_b
        create_names = {n for n, _ in plan.creates}
        assert "new-skill" in create_names

    def test_collect_updated_skill(self, env):
        source, target_a, target_b = env
        create_skill_in_category(source, "Code", "skill-a", "old")
        create_skill(target_a, "skill-a", "old")
        create_skill(target_b, "skill-a", "old")

        # 让 target_a 的版本更新
        time.sleep(0.1)
        (target_a / "skill-a" / "SKILL.md").write_text("updated")

        plan = preview_bidirectional(source, [target_a, target_b])
        assert len(plan.collect_update) == 1
        assert plan.collect_update[0][0] == "skill-a"

    def test_distribute_new_skill(self, env):
        source, target_a, target_b = env
        create_skill_in_category(source, "Code", "skill-a", "a")
        create_skill_in_category(source, "Code", "skill-b", "b")
        create_skill(target_a, "skill-a", "a")
        create_skill(target_b, "skill-a", "a")

        plan = preview_bidirectional(source, [target_a, target_b])
        create_entries = [(n, d) for n, d in plan.creates]
        assert ("skill-b", target_a) in create_entries
        assert ("skill-b", target_b) in create_entries

    def test_delete_extra_not_in_source(self, env):
        """双向模式下，目标多余 skill 会被收集到 Other/ 而非删除"""
        source, target_a, target_b = env
        create_skill_in_category(source, "Code", "skill-a", "a")
        create_skill(target_a, "skill-a", "a")
        create_skill(target_a, "orphan", "orphan")
        create_skill(target_b, "skill-a", "a")

        plan = preview_bidirectional(source, [target_a, target_b])
        # orphan 应被收集而非删除
        assert len(plan.collect_new) == 1
        assert plan.collect_new[0][0] == "orphan"

    def test_execute_collect_and_distribute(self, env):
        source, target_a, target_b = env
        create_skill_in_category(source, "Code", "skill-a", "a")
        create_skill(target_a, "skill-a", "a")
        create_skill(target_a, "new-skill", "new-content")
        create_skill(target_b, "skill-a", "a")

        plan = preview_bidirectional(source, [target_a, target_b])
        execute_bidirectional(plan, source, [target_a, target_b])

        # new-skill 被收集到 Other/
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
        assert "删除" in combined

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
        """S2: 多个目标各有不同的新 skill，都应收集到 Other/ 并交叉分发"""
        source, target_a, target_b = env
        create_skill_in_category(source, "Code", "skill-a", "a")
        create_skill(target_a, "skill-a", "a")
        create_skill(target_a, "new-from-a", "from-a")
        create_skill(target_b, "skill-a", "a")
        create_skill(target_b, "new-from-b", "from-b")

        plan = preview_bidirectional(source, [target_a, target_b])
        execute_bidirectional(plan, source, [target_a, target_b])

        # 两个新 skill 都收集到 Other/
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
        assert "无变更" in combined
        assert (target_b / "skill-b" / "SKILL.md").is_file()

    def test_collect_from_target_b_only(self, env):
        """target_b 有新 skill，target_a 没有 → 只从 target_b 收集"""
        source, target_a, target_b = env
        create_skill_in_category(source, "Code", "skill-a", "a")
        create_skill(target_a, "skill-a", "a")
        create_skill(target_b, "skill-a", "a")
        create_skill(target_b, "only-in-b", "b-content")

        plan = preview_bidirectional(source, [target_a, target_b])
        execute_bidirectional(plan, source, [target_a, target_b])

        assert (source / "Other" / "only-in-b" / "SKILL.md").read_text() == "b-content"
        assert (target_a / "only-in-b" / "SKILL.md").is_file()

    def test_collect_from_multiple_targets(self, env):
        """多个目标各有不同的新 skill，都应收集到 Other/ 并交叉分发"""
        source, target_a, target_b = env
        create_skill_in_category(source, "Code", "skill-a", "a")
        create_skill(target_a, "skill-a", "a")
        create_skill(target_a, "new-from-a", "from-a")
        create_skill(target_b, "skill-a", "a")
        create_skill(target_b, "new-from-b", "from-b")

        plan = preview_bidirectional(source, [target_a, target_b])
        execute_bidirectional(plan, source, [target_a, target_b])

        # 两个新 skill 都收集到 Other/
        assert (source / "Other" / "new-from-a" / "SKILL.md").read_text() == "from-a"
        assert (source / "Other" / "new-from-b" / "SKILL.md").read_text() == "from-b"
        # 交叉分发
        assert (target_a / "new-from-b" / "SKILL.md").is_file()
        assert (target_b / "new-from-a" / "SKILL.md").is_file()


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
        """S2: 在某个目标新增 skill → 收集到 Other/ → 分发到其他目标"""
        source, target_a, target_b = env
        create_skill_in_category(source, "Code", "skill-a", "a")
        create_skill(target_a, "skill-a", "a")
        create_skill(target_a, "created-in-codex", "codex-new")
        create_skill(target_b, "skill-a", "a")

        run_main(source, [target_a, target_b])

        # 收集到源 Other/
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

    def test_s4_source_updated_warns(self, env):
        """S4: 源目录修改 skill → 双向模式不会自动更新目标，但应警告用户"""
        source, target_a, target_b = env
        create_skill_in_category(source, "Code", "skill-a", "old")
        create_skill(target_a, "skill-a", "old")
        create_skill(target_b, "skill-a", "old")

        # 源目录修改
        time.sleep(0.1)
        (source / "Code" / "skill-a" / "SKILL.md").write_text("updated-in-source")

        plan = preview_bidirectional(source, [target_a, target_b])
        # 不应有 collect_update（因为是源更新，不是目标更新）
        assert len(plan.collect_update) == 0
        # 应有警告
        assert len(plan.warnings) >= 1
        assert any("skill-a" in w for w in plan.warnings)
        assert any("--force" in w for w in plan.warnings)

    def test_s6_multi_target_conflict(self, env):
        """S6: 多个目标同时修改同一 skill → 跳过自动合并，警告用户"""
        source, target_a, target_b = env
        create_skill_in_category(source, "Code", "skill-a", "original")
        create_skill(target_a, "skill-a", "original")
        create_skill(target_b, "skill-a", "original")

        # 两个目标都修改了同一个 skill
        time.sleep(0.1)
        (target_a / "skill-a" / "SKILL.md").write_text("updated-by-a")
        (target_b / "skill-a" / "SKILL.md").write_text("updated-by-b")

        plan = preview_bidirectional(source, [target_a, target_b])
        # 冲突时不应自动收集更新
        assert len(plan.collect_update) == 0
        # 应有警告
        assert len(plan.warnings) >= 1
        assert any("skill-a" in w and "多个目标" in w for w in plan.warnings)

    def test_s6b_source_and_target_both_modified(self, env):
        """S6b: 源和目标都修改了同一 skill → 冲突，跳过并警告"""
        source, target_a, target_b = env
        create_skill_in_category(source, "Code", "skill-a", "original")
        create_skill(target_a, "skill-a", "original")
        create_skill(target_b, "skill-a", "original")

        # 源先修改
        time.sleep(0.1)
        (source / "Code" / "skill-a" / "SKILL.md").write_text("updated-in-source")
        # 目标后修改（mtime 更大）
        time.sleep(0.1)
        (target_a / "skill-a" / "SKILL.md").write_text("updated-in-target")

        plan = preview_bidirectional(source, [target_a, target_b])
        # 不应自动收集（两边都改了是冲突）
        assert len(plan.collect_update) == 0
        # 应有冲突警告
        assert any("skill-a" in w and "都被修改" in w for w in plan.warnings)

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

        # 双向模式下，to-delete 被从目标收集回 Other/
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
