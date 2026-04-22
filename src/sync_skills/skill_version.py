"""Skill 版本号读写与提交前自动递增。"""

import re
import subprocess
from pathlib import Path

from .metadata import match_frontmatter

_VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def parse_patch_version(version: str) -> tuple[int, int, int] | None:
    match = _VERSION_RE.match(version.strip())
    if not match:
        return None
    return tuple(int(part) for part in match.groups())


def bump_patch(version: str) -> str:
    parsed = parse_patch_version(version)
    if parsed is None:
        raise ValueError(f"非法版本号: {version}")
    major, minor, patch = parsed
    return f"{major}.{minor}.{patch + 1}"


def read_skill_version(skill_md_path: Path) -> str | None:
    if not skill_md_path.is_file():
        return None
    content = skill_md_path.read_text(encoding="utf-8")
    return extract_version_from_content(content)


def extract_version_from_content(content: str) -> str | None:
    match = match_frontmatter(content)
    if not match:
        return None
    frontmatter = match.group("frontmatter")
    version_match = re.search(r'^version:\s*["\']?([^"\'\n]+)["\']?\s*$', frontmatter, re.MULTILINE)
    if not version_match:
        return None
    return version_match.group(1).strip()


def read_head_skill_version(repo_path: Path, skill_name: str) -> str | None:
    result = subprocess.run(
        ["git", "-C", str(repo_path), "show", f"HEAD:skills/{skill_name}/SKILL.md"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        return None
    return extract_version_from_content(result.stdout)


def write_skill_version(skill_md_path: Path, new_version: str) -> None:
    content = skill_md_path.read_text(encoding="utf-8")
    updated = set_version_in_content(content, new_version)
    skill_md_path.write_text(updated, encoding="utf-8")



def set_version_in_content(content: str, new_version: str) -> str:
    match = match_frontmatter(content)
    if not match:
        frontmatter = f"---\nversion: {new_version}\n---\n\n"
        return frontmatter + content.lstrip("\n")

    frontmatter = match.group("frontmatter")
    if re.search(r'^version:\s*["\']?([^"\'\n]+)["\']?\s*$', frontmatter, re.MULTILINE):
        new_frontmatter = re.sub(
            r'^version:\s*["\']?([^"\'\n]+)["\']?\s*$',
            f"version: {new_version}",
            frontmatter,
            count=1,
            flags=re.MULTILINE,
        )
    else:
        new_frontmatter = frontmatter.rstrip() + f"\nversion: {new_version}\n"

    new_frontmatter = new_frontmatter.rstrip("\n") + "\n"
    return f"---\n{new_frontmatter}---\n" + content[match.end():]



def ensure_skill_version_bumped(repo_path: Path, repo_skills_dir: Path, skill_name: str) -> bool:
    skill_md_path = repo_skills_dir / skill_name / "SKILL.md"
    if not skill_md_path.is_file():
        return False

    current_version = read_skill_version(skill_md_path)
    head_version = read_head_skill_version(repo_path, skill_name)

    if current_version is None:
        write_skill_version(skill_md_path, "0.0.1")
        return True

    if parse_patch_version(current_version) is None:
        raise ValueError(f"skill '{skill_name}' 的版本号非法: {current_version}")

    if head_version is None:
        return False

    if parse_patch_version(head_version) is None:
        raise ValueError(f"HEAD 中 skill '{skill_name}' 的版本号非法: {head_version}")

    if current_version != head_version:
        return False

    write_skill_version(skill_md_path, bump_patch(current_version))
    return True
