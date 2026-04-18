import argparse
from pathlib import Path
from types import SimpleNamespace

from sync_skills.config import save_config
from sync_skills.git_ops import GitSkillChange, GitStatus, git_init
from sync_skills.lifecycle import add_skill
from sync_skills.state import get_managed_skills
from tests.test_sync_skills import _create_v1_env


def make_args(config_path: Path, *, yes=False, dry_run=False, message=""):
    return argparse.Namespace(config=config_path, dry_run=dry_run, yes=yes, message=message)


class TestV1DoctorCommand:
    def test_doctor_dry_run_does_not_register_or_repair_links(self, tmp_path, capsys):
        from sync_skills.cli import cmd_doctor

        repo, repo_skills, agent_dirs, config = _create_v1_env(tmp_path)
        skill_dir = repo_skills / "unregistered"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# unregistered\n")

        config_path = tmp_path / "config.toml"
        save_config(config, config_path)

        cmd_doctor(argparse.Namespace(config=config_path, dry_run=True, yes=False))
        captured = capsys.readouterr()

        assert "补充登记" in captured.out
        assert "unregistered" in get_managed_skills(config.state_file)


class TestV1StatusCommand:
    def test_status_shows_broken_links_orphaned_and_unregistered(self, tmp_path, capsys):
        from sync_skills.cli import cmd_status
        from sync_skills.state import add_managed
        import os

        repo, repo_skills, agent_dirs, config = _create_v1_env(tmp_path)
        git_init(repo)
        add_skill("broken-skill", config)

        orphan = "orphan-skill"
        add_managed(orphan, config.state_file)

        unregistered_dir = repo_skills / "repo-only"
        unregistered_dir.mkdir()
        (unregistered_dir / "SKILL.md").write_text("# repo only\n")

        (agent_dirs[0] / "broken-skill").unlink()
        os.symlink(repo_skills / "missing-target", agent_dirs[0] / "broken-skill")

        config_path = tmp_path / "config.toml"
        save_config(config, config_path)

        cmd_status(argparse.Namespace(config=config_path))
        captured = capsys.readouterr()

        assert "断链/缺失 symlink" in captured.out
        assert "broken-skill" in captured.out
        assert "状态不一致" in captured.out
        assert orphan in captured.out
        assert "未登记" in captured.out
        assert "repo-only" in captured.out


class TestV1CommitCommand:
    def test_commit_success_calls_git_add_commit_with_default_message(self, tmp_path, capsys, monkeypatch):
        from sync_skills.cli import cmd_commit

        repo, repo_skills, agent_dirs, config = _create_v1_env(tmp_path)
        git_init(repo)
        config_path = tmp_path / "config.toml"
        save_config(config, config_path)

        called = []
        monkeypatch.setattr("sync_skills.cli.git_collect_skill_changes", lambda repo, repo_skills_dir: [GitSkillChange("M", "demo", "2026-04-19 10:00")])
        monkeypatch.setattr("sync_skills.cli.git_recent_commits", lambda repo: [])
        monkeypatch.setattr("sync_skills.cli.git_status", lambda repo: GitStatus(is_repo=True, branch="main", is_clean=False))
        monkeypatch.setattr("sync_skills.cli.git_add_commit", lambda repo, message: called.append(message) or True)
        monkeypatch.setattr("sync_skills.cli.datetime", SimpleNamespace(now=lambda: SimpleNamespace(strftime=lambda fmt: "2026-04-19 12:34")))

        cmd_commit(make_args(config_path, yes=True))
        captured = capsys.readouterr()

        assert called == ["update: demo (2026-04-19 12:34)"]
        assert "[OK] 已提交" in captured.out

    def test_commit_dry_run_does_not_call_git_add_commit(self, tmp_path, capsys, monkeypatch):
        from sync_skills.cli import cmd_commit

        repo, repo_skills, agent_dirs, config = _create_v1_env(tmp_path)
        git_init(repo)
        config_path = tmp_path / "config.toml"
        save_config(config, config_path)

        monkeypatch.setattr("sync_skills.cli.git_collect_skill_changes", lambda repo, repo_skills_dir: [])
        monkeypatch.setattr("sync_skills.cli.git_recent_commits", lambda repo: [])
        monkeypatch.setattr("sync_skills.cli.git_status", lambda repo: GitStatus(is_repo=True, branch="main", is_clean=False))

        called = []
        monkeypatch.setattr("sync_skills.cli.git_add_commit", lambda repo, message: called.append(message) or True)

        cmd_commit(make_args(config_path, dry_run=True))
        captured = capsys.readouterr()

        assert called == []
        assert "[DRY-RUN]" in captured.out


class TestV1PushCommand:
    def test_push_success_commits_then_pushes_with_yes(self, tmp_path, capsys, monkeypatch):
        from sync_skills.cli import cmd_push

        repo, repo_skills, agent_dirs, config = _create_v1_env(tmp_path)
        git_init(repo)
        config_path = tmp_path / "config.toml"
        save_config(config, config_path)

        monkeypatch.setattr("sync_skills.cli.git_collect_skill_changes", lambda repo, repo_skills_dir: [])
        monkeypatch.setattr("sync_skills.cli.git_recent_commits", lambda repo: [])
        monkeypatch.setattr("sync_skills.cli.git_status", lambda repo: GitStatus(is_repo=True, branch="main", is_clean=False))
        import sync_skills.git_ops as git_ops_module
        monkeypatch.setattr(git_ops_module, "git_has_remote", lambda repo: True)
        monkeypatch.setattr(git_ops_module, "git_get_tracking_branch", lambda repo: "origin/main")
        monkeypatch.setattr(git_ops_module, "git_get_remote_url", lambda repo: "git@example.com:repo.git")

        committed = []
        pushed = []
        monkeypatch.setattr("sync_skills.cli.git_add_commit", lambda repo, message: committed.append(message) or True)
        monkeypatch.setattr("sync_skills.cli.git_push", lambda repo: pushed.append(repo) or (True, ""))
        monkeypatch.setattr("sync_skills.cli.datetime", SimpleNamespace(now=lambda: SimpleNamespace(strftime=lambda fmt: "2026-04-19 12:34")))

        cmd_push(make_args(config_path, yes=True))
        captured = capsys.readouterr()

        assert len(committed) == 1
        assert pushed == [repo]
        assert "[OK] 已推送到远程" in captured.out

    def test_push_dry_run_does_not_commit_or_push(self, tmp_path, capsys, monkeypatch):
        from sync_skills.cli import cmd_push

        repo, repo_skills, agent_dirs, config = _create_v1_env(tmp_path)
        git_init(repo)
        config_path = tmp_path / "config.toml"
        save_config(config, config_path)

        monkeypatch.setattr("sync_skills.cli.git_collect_skill_changes", lambda repo, repo_skills_dir: [])
        monkeypatch.setattr("sync_skills.cli.git_recent_commits", lambda repo: [])
        monkeypatch.setattr("sync_skills.cli.git_status", lambda repo: GitStatus(is_repo=True, branch="main", is_clean=False))
        import sync_skills.git_ops as git_ops_module
        monkeypatch.setattr(git_ops_module, "git_has_remote", lambda repo: True)
        monkeypatch.setattr(git_ops_module, "git_get_tracking_branch", lambda repo: "origin/main")
        monkeypatch.setattr(git_ops_module, "git_get_remote_url", lambda repo: "git@example.com:repo.git")

        committed = []
        pushed = []
        monkeypatch.setattr("sync_skills.cli.git_add_commit", lambda repo, message: committed.append(message) or True)
        monkeypatch.setattr("sync_skills.cli.git_push", lambda repo: pushed.append(repo) or (True, ""))

        cmd_push(make_args(config_path, dry_run=True))
        captured = capsys.readouterr()

        assert committed == []
        assert pushed == []
        assert "[DRY-RUN]" in captured.out


class TestV1PullCommand:
    def test_pull_success_calls_git_pull_then_doctor(self, tmp_path, capsys, monkeypatch):
        from sync_skills.cli import cmd_pull

        repo, repo_skills, agent_dirs, config = _create_v1_env(tmp_path)
        git_init(repo)
        config_path = tmp_path / "config.toml"
        save_config(config, config_path)

        monkeypatch.setattr("sync_skills.cli.git_status", lambda repo: GitStatus(is_repo=True, branch="main", is_clean=True))
        import sync_skills.git_ops as git_ops_module
        monkeypatch.setattr(git_ops_module, "git_get_tracking_branch", lambda repo: "origin/main")
        monkeypatch.setattr("sync_skills.cli.git_pull", lambda repo: (True, "pull 成功"))

        called = []
        monkeypatch.setattr("sync_skills.cli._do_doctor", lambda config, auto_confirm=False: called.append(auto_confirm))

        cmd_pull(argparse.Namespace(config=config_path, dry_run=False, yes=True))
        captured = capsys.readouterr()

        assert called == [True]
        assert "[OK] pull 成功" in captured.out

    def test_pull_dry_run_does_not_call_git_pull_or_doctor(self, tmp_path, capsys, monkeypatch):
        from sync_skills.cli import cmd_pull

        repo, repo_skills, agent_dirs, config = _create_v1_env(tmp_path)
        git_init(repo)
        config_path = tmp_path / "config.toml"
        save_config(config, config_path)

        monkeypatch.setattr("sync_skills.cli.git_status", lambda repo: GitStatus(is_repo=True, branch="main", is_clean=True))
        import sync_skills.git_ops as git_ops_module
        monkeypatch.setattr(git_ops_module, "git_get_tracking_branch", lambda repo: "origin/main")

        pulled = []
        monkeypatch.setattr("sync_skills.cli.git_pull", lambda repo: pulled.append(repo) or (True, "pull 成功"))
        repaired = []
        monkeypatch.setattr("sync_skills.cli._do_doctor", lambda config, auto_confirm=False: repaired.append(auto_confirm))

        cmd_pull(argparse.Namespace(config=config_path, dry_run=True, yes=False))
        captured = capsys.readouterr()

        assert pulled == []
        assert repaired == []
        assert "[DRY-RUN]" in captured.out
