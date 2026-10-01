from __future__ import annotations

from pathlib import Path

import pytest

from aios.application.migration import MigrationError, migrate_runtime

CONFIG = "schema_version: '1.2'\nproject_id: PROJECT-TEST\nname: Test\nroot: .\ncode_paths: [src]\n"


def _legacy_project(tmp_path: Path) -> Path:
    legacy = tmp_path / ".codex-os"
    (legacy / "state").mkdir(parents=True)
    (legacy / "project.yaml").write_text(CONFIG, encoding="utf-8")
    (legacy / "state" / "state.db").write_bytes(b"SQLite format 3\x00legacy-runtime")
    return tmp_path


def test_missing_legacy_directory_is_a_no_op(tmp_path: Path) -> None:
    result = migrate_runtime(tmp_path)
    assert result.migrated is False
    assert result.moved == ()
    assert "no legacy runtime directory" in result.detail


def test_known_runtime_is_moved_with_a_backup(tmp_path: Path) -> None:
    root = _legacy_project(tmp_path)
    result = migrate_runtime(root)

    assert result.migrated is True
    assert (root / ".aios/project.yaml").is_file()
    assert (root / ".aios/state/state.db").is_file()
    assert ".codex-os" not in {path.name for path in root.iterdir()}

    assert result.backup is not None
    backup = root / str(result.backup)
    assert backup.is_file()
    assert backup.read_bytes() == b"SQLite format 3\x00legacy-runtime"
    sidecar = backup.with_name(backup.name + ".sha256")
    assert sidecar.is_file()
    assert backup.name in sidecar.read_text(encoding="ascii")


def test_unrecognized_structure_is_refused(tmp_path: Path) -> None:
    legacy = tmp_path / ".codex-os"
    legacy.mkdir()
    (legacy / "random.txt").write_text("unknown", encoding="utf-8")

    with pytest.raises(MigrationError, match="MIGRATION_UNKNOWN_STRUCTURE"):
        migrate_runtime(tmp_path)
    # Nothing was touched.
    assert (legacy / "random.txt").is_file()


def test_unrecognized_entries_are_preserved_and_reported(tmp_path: Path) -> None:
    root = _legacy_project(tmp_path)
    (root / ".codex-os" / "artifacts").mkdir()
    (root / ".codex-os" / "artifacts" / "old.bin").write_bytes(b"keep me")

    result = migrate_runtime(root)

    assert result.migrated is True
    assert "artifacts/old.bin" in result.unknown
    assert (root / ".codex-os/artifacts/old.bin").read_bytes() == b"keep me"
    # The legacy directory survives because it still holds unrecognized data.
    assert (root / ".codex-os").is_dir()


def test_existing_target_config_is_never_overwritten(tmp_path: Path) -> None:
    root = _legacy_project(tmp_path)
    (root / ".aios").mkdir()
    (root / ".aios/project.yaml").write_text("schema_version: '1.3'\n", encoding="utf-8")

    result = migrate_runtime(root)

    assert (root / ".aios/project.yaml").read_text(encoding="utf-8").startswith(
        "schema_version: '1.3'"
    )
    assert ".aios/project.yaml" not in result.moved
    assert (root / ".aios/state/state.db").is_file()


def test_migration_is_idempotent(tmp_path: Path) -> None:
    root = _legacy_project(tmp_path)
    migrate_runtime(root)
    second = migrate_runtime(root)
    assert second.migrated is False
    assert second.moved == ()
