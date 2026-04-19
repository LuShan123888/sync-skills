from pathlib import Path

from sync_skills.cli import SyncOp, SyncPlan, ask_confirmation, find_skills_in_source, execute_bidirectional, show_preview, verify_sync


def _create_skill(path: Path, name: str, content: str = "# skill"):
    skill_dir = path / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(content)
    return skill_dir


def _create_nested_skill(path: Path, category: str, name: str, content: str = "# skill"):
    skill_dir = path / category / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(content)
    return skill_dir


def test_ask_confirmation_default_no(tmp_path, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "")
    assert ask_confirmation(False) is False


def test_ask_confirmation_yes_variants(tmp_path, monkeypatch):
    for answer in ["y", "Y", "yes", "YES"]:
        monkeypatch.setattr("builtins.input", lambda _, a=answer: a)
        assert ask_confirmation(False) is True


def test_ask_confirmation_no_variants(tmp_path, monkeypatch):
    for answer in ["n", "N", "no", "NO", "foo"]:
        monkeypatch.setattr("builtins.input", lambda _, a=answer: a)
        assert ask_confirmation(False) is False


def test_ask_confirmation_auto_confirm(monkeypatch):
    assert ask_confirmation(True) is True


def test_ask_confirmation_interrupt_returns_false(monkeypatch):
    def raise_interrupt(prompt: str = ""):
        raise KeyboardInterrupt

    monkeypatch.setattr("builtins.input", raise_interrupt)
    assert ask_confirmation(False) is False


def test_find_skills_in_source_skips_hidden_directory(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    _create_nested_skill(source, "Visible", "good", "good")
    _create_nested_skill(source, ".hidden", "secret", "secret")

    skills = find_skills_in_source(source)
    rel_paths = {s.rel_path for s in skills}
    assert rel_paths == {"Visible/good"}


def test_show_preview_no_changes_returns_false(tmp_path, capsys):
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()

    plan = SyncPlan()
    result = show_preview(plan, source, [target], force=False)
    captured = capsys.readouterr()

    assert result is False
    assert "无需同步" in captured.out


def test_show_preview_warnings_only_returns_false(tmp_path, capsys):
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()

    plan = SyncPlan(warnings=["skill 'a' 内容不一致，请手动处理"])
    result = show_preview(plan, source, [target], force=False)
    captured = capsys.readouterr()

    assert result is False
    assert "⚠" in captured.out
    assert "除以上提示外，无需执行变更" in captured.out


def test_verify_sync_matches_when_content_equal(tmp_path, capsys):
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()
    _create_nested_skill(source, "Code", "skill-a", "# same")
    _create_skill(target, "skill-a", "# same")

    result = verify_sync(source, [target])
    captured = capsys.readouterr()

    assert result is True
    assert "✓" in captured.out


def test_verify_sync_detects_mismatch(tmp_path, capsys):
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()
    _create_nested_skill(source, "Code", "skill-a", "# source")
    _create_skill(target, "skill-a", "# target")

    result = verify_sync(source, [target])
    captured = capsys.readouterr()

    assert result is False
    assert "内容不一致" in captured.out


def test_execute_bidirectional_skips_missing_origin(tmp_path):
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()

    plan = SyncPlan(sync_ops=[
        SyncOp("missing", source, target, dest_rel=None, origin_rel=None),
    ])
    stats = execute_bidirectional(plan, source, [target])

    assert stats["synced"] == 0
    assert stats["deleted"] == 0


def test_execute_bidirectional_deletes_stale_copy(tmp_path):
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()
    _create_skill(target, "stale", "old")

    plan = SyncPlan(deletes=[("stale", target)])
    stats = execute_bidirectional(plan, source, [target])

    assert stats["deleted"] == 1
    assert not (target / "stale").exists()
