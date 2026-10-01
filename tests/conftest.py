from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

PROJECT_CONFIG = (
    "schema_version: '1.3'\nproject_id: PROJECT-TEST\nname: Test\nroot: .\ncode_paths: [src]\n"
)


@pytest.fixture(autouse=True)
def git_discovery_ceiling(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Stop Git from discovering the repository that hosts pytest's temporary root.

    The OS temp directory is not writable from the project interpreter here, so
    pytest's temporary root lands inside this repository. Without a ceiling a
    fixture that runs Git would resolve to *this* project instead of the
    fixture, and repository checks would report the wrong root.
    """

    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    """A temporary project root that owns its governance boundary.

    Root resolution walks up to the nearest ``.git`` or ``.aios/project.yaml``.
    Because pytest's temporary root sits inside this repository, a bare
    ``tmp_path`` resolves to the real project: tests would then read or write
    tracked facts such as ``docs/memory/memory.jsonl``. Tests that construct a
    root-resolving component (MemoryStore, Doctor, governance services) must
    use this fixture instead of ``tmp_path``.
    """

    (tmp_path / ".aios").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".aios" / "project.yaml").write_text(PROJECT_CONFIG, encoding="utf-8")
    return tmp_path


@pytest.fixture
def governed_repo(tmp_path: Path) -> Path:
    root = tmp_path / "项目"
    root.mkdir()
    for args in (
        ("init", "-q", "-b", "main"),
        ("config", "user.name", "Fixture"),
        ("config", "user.email", "fixture@example.com"),
    ):
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)
    (root / ".aios").mkdir()
    (root / ".aios/project.yaml").write_text(PROJECT_CONFIG, encoding="utf-8")
    (root / ".gitignore").write_text(
        ".aios/state/\n.worktrees/\nbuild/\ndist/\n", encoding="utf-8"
    )
    for args in (("add", "."), ("commit", "-qm", "fixture baseline")):
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)
    return root
