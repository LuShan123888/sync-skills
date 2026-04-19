from pathlib import Path

from sync_skills.classification import classify_all_skills, classify_skill


def _create_skill(root: Path, name: str) -> Path:
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(f"# {name}\n")
    return skill_dir


def test_classify_skill_managed_with_link_and_repos_and_agents(tmp_path):
    managed = {"agent-managed"}
    repo_dir = tmp_path / "repo"
    agent_dir = tmp_path / "agent"
    repo_dir.mkdir()
    agent_dir.mkdir()

    _create_skill(repo_dir, "agent-managed")
    (agent_dir / "agent-managed").symlink_to(repo_dir / "agent-managed")

    result = classify_skill("agent-managed", managed, repo_skills_dir=repo_dir, agent_dirs=[agent_dir])

    assert result.skill_type == "custom"
    assert result.managed is True
    assert result.custom_path == repo_dir / "agent-managed"
    assert result.agent_path == agent_dir / "agent-managed"
    assert result.has_custom_link is True


def test_classify_skill_managed_without_repo_or_agents_is_custom(tmp_path):
    managed = {"ghost-skill"}
    repo_dir = tmp_path / "repo"
    agent_dir = tmp_path / "agent"
    repo_dir.mkdir()
    agent_dir.mkdir()

    result = classify_skill("ghost-skill", managed, repo_skills_dir=repo_dir, agent_dirs=[agent_dir])

    assert result.skill_type == "custom"
    assert result.managed is True
    assert result.custom_path is None
    assert result.agent_path is None
    assert result.has_custom_link is False


def test_classify_skill_unknown_when_only_agent_exists(tmp_path):
    managed = set()
    repo_dir = tmp_path / "repo"
    agent_dir = tmp_path / "agent"
    repo_dir.mkdir()
    agent_dir.mkdir()

    _create_skill(agent_dir, "agent-only")

    result = classify_skill("agent-only", managed, repo_skills_dir=repo_dir, agent_dirs=[agent_dir])

    assert result.skill_type == "unknown"
    assert result.managed is False
    assert result.custom_path is None
    assert result.agent_path == agent_dir / "agent-only"


def test_classify_skill_unknown_when_not_found(tmp_path):
    managed = set()
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    result = classify_skill("not-exists", managed, repo_skills_dir=repo_dir)

    assert result.skill_type == "unknown"
    assert result.managed is False
    assert result.custom_path is None
    assert result.agent_path is None


def test_classify_all_skills_collects_all_and_sorts_by_type(tmp_path):
    managed = {"managed-link", "managed-state"}
    repo_dir = tmp_path / "repo"
    agent_a = tmp_path / "agent_a"
    agent_b = tmp_path / "agent_b"
    repo_dir.mkdir()
    agent_a.mkdir()
    agent_b.mkdir()

    _create_skill(repo_dir, "managed-link")
    _create_skill(repo_dir, "repo-only")
    _create_skill(agent_a, "agent-only")

    (agent_a / "managed-link").symlink_to(repo_dir / "managed-link")

    classifications = classify_all_skills(
        managed,
        repo_skills_dir=repo_dir,
        agent_dirs=[agent_a, agent_b],
    )

    custom = [c.name for c in classifications if c.skill_type == "custom"]
    unknown = [c.name for c in classifications if c.skill_type == "unknown"]

    assert custom == ["managed-link", "managed-state"]
    assert unknown == ["agent-only", "repo-only"]
