import json
from pathlib import Path

from sync_skills.state import add_managed, align_state_with_repo, get_managed_skills, remove_managed


def create_repo_skill(repo_skills_dir: Path, name: str, content: str = "") -> Path:
    skill_dir = repo_skills_dir / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(content or f"# {name}\n")
    return skill_dir


class TestState:
    def test_add_managed_is_idempotent(self, tmp_path):
        state_file = tmp_path / "skills.json"

        add_managed("demo", state_file)
        add_managed("demo", state_file)

        assert get_managed_skills(state_file) == {"demo"}
        data = json.loads(state_file.read_text())
        assert data == {"skills": {"demo": {"source": "sync-skills"}}}

    def test_remove_managed_missing_name_keeps_state_valid(self, tmp_path):
        state_file = tmp_path / "skills.json"
        add_managed("demo", state_file)

        remove_managed("ghost", state_file)

        assert get_managed_skills(state_file) == {"demo"}

    def test_align_state_with_repo_registers_repo_skills_without_deleting_orphaned_entries(self, tmp_path):
        state_file = tmp_path / "skills.json"
        repo_skills_dir = tmp_path / "repo" / "skills"
        repo_skills_dir.mkdir(parents=True)

        create_repo_skill(repo_skills_dir, "repo-skill")
        add_managed("orphan", state_file)

        added, orphaned = align_state_with_repo(state_file, repo_skills_dir)

        assert added == ["repo-skill"]
        assert orphaned == ["orphan"]
        assert get_managed_skills(state_file) == {"repo-skill", "orphan"}

    def test_align_state_with_repo_ignores_non_skill_directories(self, tmp_path):
        state_file = tmp_path / "skills.json"
        repo_skills_dir = tmp_path / "repo" / "skills"
        repo_skills_dir.mkdir(parents=True)

        (repo_skills_dir / "not-a-skill").mkdir()
        (repo_skills_dir / ".hidden").mkdir()

        added, orphaned = align_state_with_repo(state_file, repo_skills_dir)

        assert added == []
        assert orphaned == []
        assert get_managed_skills(state_file) == set()
