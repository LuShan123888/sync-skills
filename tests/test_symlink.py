import os
from pathlib import Path

from sync_skills.symlink import check_and_repair_links, remove_agent_links, safe_create_link


def create_repo_skill(repo_skills_dir: Path, name: str, content: str = "") -> Path:
    skill_dir = repo_skills_dir / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(content or f"# {name}\n")
    return skill_dir


def make_agent_dir(base: Path, agent_name: str) -> Path:
    agent_dir = base / f".{agent_name}" / "skills"
    agent_dir.mkdir(parents=True, exist_ok=True)
    return agent_dir


class TestSymlink:
    def test_safe_create_link_conflict_returns_conflict_in_yes_mode(self, tmp_path):
        repo_skills_dir = tmp_path / "repo" / "skills"
        create_repo_skill(repo_skills_dir, "demo")
        agent_dir = make_agent_dir(tmp_path, "claude")

        conflict_dir = agent_dir / "demo"
        conflict_dir.mkdir()
        (conflict_dir / "SKILL.md").write_text("# local\n")

        success, status = safe_create_link("demo", repo_skills_dir, agent_dir, auto_confirm=True)

        assert (success, status) == (False, "conflict")
        assert conflict_dir.is_dir()
        assert not conflict_dir.is_symlink()

    def test_safe_create_link_replaces_real_dir_after_confirmation(self, tmp_path, monkeypatch):
        repo_skills_dir = tmp_path / "repo" / "skills"
        create_repo_skill(repo_skills_dir, "demo")
        agent_dir = make_agent_dir(tmp_path, "claude")

        conflict_dir = agent_dir / "demo"
        conflict_dir.mkdir()
        (conflict_dir / "SKILL.md").write_text("# local\n")

        monkeypatch.setattr("builtins.input", lambda _: "y")
        success, status = safe_create_link("demo", repo_skills_dir, agent_dir, auto_confirm=False)

        assert (success, status) == (True, "repaired")
        assert conflict_dir.is_symlink()
        assert conflict_dir.resolve() == (repo_skills_dir / "demo").resolve()

    def test_check_and_repair_links_repairs_broken_and_missing_only(self, tmp_path):
        repo_skills_dir = tmp_path / "repo" / "skills"
        create_repo_skill(repo_skills_dir, "demo")
        claude_dir = make_agent_dir(tmp_path, "claude")
        codex_dir = make_agent_dir(tmp_path, "codex")
        gemini_dir = make_agent_dir(tmp_path, "gemini")

        os.symlink(repo_skills_dir / "missing-target", claude_dir / "demo")
        conflict_dir = gemini_dir / "demo"
        conflict_dir.mkdir()
        (conflict_dir / "SKILL.md").write_text("# local\n")

        result = check_and_repair_links(
            repo_skills_dir,
            [claude_dir, codex_dir, gemini_dir],
            {"demo"},
            auto_confirm=True,
        )

        assert any("symlink 异常 → 已修复" in item for item in result["repaired"])
        assert any("缺失 symlink → 已创建" in item for item in result["repaired"])
        assert any("存在真实目录（非 symlink），跳过" in item for item in result["conflicts"])
        assert (claude_dir / "demo").is_symlink()
        assert (claude_dir / "demo").resolve() == (repo_skills_dir / "demo").resolve()
        assert (codex_dir / "demo").is_symlink()
        assert (codex_dir / "demo").resolve() == (repo_skills_dir / "demo").resolve()
        assert conflict_dir.is_dir()
        assert not conflict_dir.is_symlink()

    def test_remove_agent_links_only_removes_repo_pointing_symlinks(self, tmp_path):
        repo_skills_dir = tmp_path / "repo" / "skills"
        create_repo_skill(repo_skills_dir, "demo")
        claude_dir = make_agent_dir(tmp_path, "claude")
        codex_dir = make_agent_dir(tmp_path, "codex")
        gemini_dir = make_agent_dir(tmp_path, "gemini")

        os.symlink(repo_skills_dir / "demo", claude_dir / "demo")

        other_target = tmp_path / "other-skill"
        other_target.mkdir()
        (other_target / "SKILL.md").write_text("# other\n")
        os.symlink(other_target, codex_dir / "demo")

        real_dir = gemini_dir / "demo"
        real_dir.mkdir()
        (real_dir / "SKILL.md").write_text("# local\n")

        removed = remove_agent_links("demo", [claude_dir, codex_dir, gemini_dir], repo_skills_dir)

        assert removed == ["claude"]
        assert not (claude_dir / "demo").exists()
        assert (codex_dir / "demo").is_symlink()
        assert (codex_dir / "demo").resolve() == other_target.resolve()
        assert real_dir.is_dir()
        assert not real_dir.is_symlink()
