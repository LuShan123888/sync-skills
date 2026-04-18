import argparse
from types import SimpleNamespace
from unittest.mock import Mock

from sync_skills.cli import _build_default_git_message, _check_state, _commit_repo, main
from sync_skills.config import Config
from sync_skills.git_ops import GitSkillChange, GitStatus


def make_config(tmp_path):
    repo = tmp_path / "repo"
    repo_skills_dir = repo / "skills"
    state_file = tmp_path / "skills.json"
    agent_dir = tmp_path / ".claude" / "skills"
    repo_skills_dir.mkdir(parents=True)
    agent_dir.mkdir(parents=True)
    return Config(repo=repo, state_file=state_file, agent_dirs=[agent_dir])


class TestCliRouting:
    def test_main_routes_list_to_legacy_mode(self, monkeypatch):
        called = []
        monkeypatch.setattr("sync_skills.sync_legacy.main_legacy", lambda argv: called.append(argv))

        main(["list"])

        assert called == [["list"]]

    def test_main_routes_fix_alias_to_doctor(self, tmp_path, monkeypatch):
        called = []
        monkeypatch.setattr("sync_skills.cli.cmd_doctor", lambda args: called.append(args))

        config_path = tmp_path / "config.toml"
        config_path.write_text("")
        main(["--config", str(config_path), "fix", "-y"])

        assert len(called) == 1
        assert called[0].yes is True

    def test_build_default_git_message_uses_single_skill_name(self, tmp_path, monkeypatch):
        config = make_config(tmp_path)
        monkeypatch.setattr(
            "sync_skills.cli.git_collect_skill_changes",
            lambda repo, repo_skills_dir: [GitSkillChange("M", "demo", "2026-04-19 12:00")],
        )
        fake_now = Mock()
        fake_now.strftime.return_value = "2026-04-19 12:34"
        monkeypatch.setattr("sync_skills.cli.datetime", SimpleNamespace(now=lambda: fake_now))

        message = _build_default_git_message(config)

        assert message == "update: demo (2026-04-19 12:34)"

    def test_check_state_reports_broken_orphaned_and_unregistered(self, tmp_path, monkeypatch):
        config = make_config(tmp_path)
        broken_skill = config.repo_skills_dir / "broken-skill"
        broken_skill.mkdir()
        (broken_skill / "SKILL.md").write_text("# broken-skill\n")

        repo_skill = config.repo_skills_dir / "repo-only"
        repo_skill.mkdir()
        (repo_skill / "SKILL.md").write_text("# repo-only\n")

        monkeypatch.setattr("sync_skills.cli.get_managed_skills", lambda _: {"broken-skill", "orphan"})

        (config.effective_agent_dirs[0] / "broken-skill").mkdir(parents=True, exist_ok=True)
        (config.effective_agent_dirs[0] / "broken-skill" / "SKILL.md").write_text("# local\n")

        def fake_verify(name, repo_skills_dir, agent_dirs):
            if name == "broken-skill":
                return SimpleNamespace(agent_links_broken=["claude"], agent_links_missing=["codex"])
            return SimpleNamespace(agent_links_broken=[], agent_links_missing=[])

        monkeypatch.setattr("sync_skills.cli.verify_links", fake_verify, raising=False)
        import sync_skills.symlink as symlink_module
        monkeypatch.setattr(symlink_module, "verify_links", fake_verify)

        state = _check_state(config)

        assert state == {
            "orphaned": ["orphan"],
            "unregistered": ["repo-only"],
            "broken_links": ["broken-skill: claude", "broken-skill: codex"],
        }

    def test_commit_repo_skips_clean_workspace(self, tmp_path, capsys, monkeypatch):
        repo = tmp_path / "repo"
        repo.mkdir()
        monkeypatch.setattr("sync_skills.cli.git_status", lambda _: GitStatus(is_repo=True, is_clean=True))

        result = _commit_repo(repo, "message")
        captured = capsys.readouterr()

        assert result is True
        assert "无变更，跳过 commit" in captured.out

    def test_commit_repo_reports_failure(self, tmp_path, capsys, monkeypatch):
        repo = tmp_path / "repo"
        repo.mkdir()
        monkeypatch.setattr("sync_skills.cli.git_status", lambda _: GitStatus(is_repo=True, is_clean=False))
        monkeypatch.setattr("sync_skills.cli.git_add_commit", lambda repo, message: False)

        result = _commit_repo(repo, "message")
        captured = capsys.readouterr()

        assert result is False
        assert "提交失败" in captured.out
