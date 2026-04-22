from pathlib import Path

import pytest

from sync_skills.skill_version import (
    bump_patch,
    ensure_skill_version_bumped,
    extract_version_from_content,
    parse_patch_version,
    set_version_in_content,
)


def create_skill(repo_skills_dir: Path, name: str, version: str | None = None, body: str = "# demo\n"):
    skill_dir = repo_skills_dir / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    if version is None:
        content = f"---\nname: {name}\ndescription: \"demo\"\n---\n\n{body}"
    else:
        content = f"---\nname: {name}\nversion: {version}\ndescription: \"demo\"\n---\n\n{body}"
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")
    return skill_dir


class TestSkillVersion:
    def test_parse_patch_version(self):
        assert parse_patch_version("1.2.3") == (1, 2, 3)
        assert parse_patch_version("1.2") is None

    def test_bump_patch(self):
        assert bump_patch("1.2.3") == "1.2.4"

    def test_extract_version_from_content(self):
        content = "---\nname: demo\nversion: 1.2.3\n---\n\n# demo\n"
        assert extract_version_from_content(content) == "1.2.3"

    def test_extract_version_from_legacy_attached_delimiter(self):
        content = "---\nname: demo\nversion: 1.2.3---\n# demo\n"
        assert extract_version_from_content(content) == "1.2.3"

    def test_extract_version_from_legacy_attached_delimiter_with_body_rule(self):
        content = "---\nname: demo\nversion: 1.2.3---\n# demo\n\n---\nbody\n"
        assert extract_version_from_content(content) == "1.2.3"

    def test_set_version_in_content_adds_missing_version(self):
        content = "---\nname: demo\ndescription: \"demo\"\n---\n\n# demo\n"
        updated = set_version_in_content(content, "0.0.1")
        assert "version: 0.0.1" in updated
        assert "version: 0.0.1\n---\n" in updated
        assert extract_version_from_content(updated) == "0.0.1"

    def test_set_version_in_content_replaces_existing_version(self):
        content = "---\nname: demo\nversion: 1.2.3\n---\n\n# demo\n"
        updated = set_version_in_content(content, "1.2.4")
        assert "version: 1.2.4" in updated
        assert "version: 1.2.3" not in updated
        assert "version: 1.2.4\n---\n" in updated
        assert extract_version_from_content(updated) == "1.2.4"

    def test_set_version_in_content_repairs_legacy_attached_delimiter(self):
        content = "---\nname: demo\nversion: 1.2.3---\n# demo\n"
        updated = set_version_in_content(content, "1.2.4")
        assert "version: 1.2.4\n---\n" in updated
        assert "version: 1.2.3---" not in updated
        assert extract_version_from_content(updated) == "1.2.4"

    def test_ensure_skill_version_bumped_sets_default_for_missing_version(self, tmp_path):
        repo = tmp_path / "repo"
        repo_skills_dir = repo / "skills"
        create_skill(repo_skills_dir, "demo", version=None)

        changed = ensure_skill_version_bumped(repo, repo_skills_dir, "demo")

        assert changed is True
        content = (repo_skills_dir / "demo" / "SKILL.md").read_text(encoding="utf-8")
        assert "version: 0.0.1" in content

    def test_ensure_skill_version_bumped_increments_when_head_matches(self, tmp_path, monkeypatch):
        repo = tmp_path / "repo"
        repo_skills_dir = repo / "skills"
        create_skill(repo_skills_dir, "demo", version="1.2.3")

        monkeypatch.setattr("sync_skills.skill_version.read_head_skill_version", lambda repo, name: "1.2.3")
        changed = ensure_skill_version_bumped(repo, repo_skills_dir, "demo")

        assert changed is True
        content = (repo_skills_dir / "demo" / "SKILL.md").read_text(encoding="utf-8")
        assert "version: 1.2.4" in content

    def test_ensure_skill_version_bumped_skips_when_version_already_changed(self, tmp_path, monkeypatch):
        repo = tmp_path / "repo"
        repo_skills_dir = repo / "skills"
        create_skill(repo_skills_dir, "demo", version="1.2.4")

        monkeypatch.setattr("sync_skills.skill_version.read_head_skill_version", lambda repo, name: "1.2.3")
        changed = ensure_skill_version_bumped(repo, repo_skills_dir, "demo")

        assert changed is False
        content = (repo_skills_dir / "demo" / "SKILL.md").read_text(encoding="utf-8")
        assert "version: 1.2.4" in content

    def test_ensure_skill_version_bumped_rejects_invalid_version(self, tmp_path):
        repo = tmp_path / "repo"
        repo_skills_dir = repo / "skills"
        create_skill(repo_skills_dir, "demo", version="1.2")

        with pytest.raises(ValueError):
            ensure_skill_version_bumped(repo, repo_skills_dir, "demo")
