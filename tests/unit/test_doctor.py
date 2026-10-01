from __future__ import annotations

import json
from pathlib import Path

import pytest

from aios.application.doctor import DoctorService


def test_doctor_core_environment_passes_without_plugin(
    project_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSH_HOME", str(project_root / "dsh-home"))
    report = DoctorService(project_root).run()
    names = [check.name for check in report.checks]
    assert {
        "python",
        "git",
        "sqlite",
        "path-encoding",
        "plugin-manifest",
        "dsh-profile",
        "plugin-loaded",
    } == set(names)
    for name in ("python", "git", "sqlite", "path-encoding"):
        check = next(item for item in report.checks if item.name == name)
        assert check.ok is True, (name, check.detail)
    for name in ("plugin-manifest", "dsh-profile", "plugin-loaded"):
        check = next(item for item in report.checks if item.name == name)
        assert check.required is False
        assert check.ok is None, (name, check.detail)
    assert report.ok is True
    assert report.path_encoding_corrupt is False


def test_doctor_reports_plugin_manifest(
    project_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSH_HOME", str(project_root / "dsh-home"))
    manifest = project_root / "plugins" / "ai-engineering-os" / "package.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({"name": "ai-engineering-os"}), encoding="utf-8")
    report = DoctorService(project_root).run()
    check = next(item for item in report.checks if item.name == "plugin-manifest")
    assert check.ok is True
    assert "ai-engineering-os" in check.detail


def test_doctor_reports_unreadable_plugin_manifest(
    project_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DSH_HOME", str(project_root / "dsh-home"))
    manifest = project_root / "plugins" / "ai-engineering-os" / "package.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text("{not json", encoding="utf-8")
    report = DoctorService(project_root).run()
    check = next(item for item in report.checks if item.name == "plugin-manifest")
    assert check.ok is False


def test_doctor_reports_profile_declaring_the_plugin(
    project_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = project_root / "dsh-home"
    profile = home / "profiles" / "desktop"
    profile.mkdir(parents=True)
    (profile / "cordis.patch.yml").write_text(
        '- id: ai-engineering-os\n  name: "ai-engineering-os"\n', encoding="utf-8"
    )
    monkeypatch.setenv("DSH_HOME", str(home))
    report = DoctorService(project_root).run()
    check = next(item for item in report.checks if item.name == "dsh-profile")
    # A declaration never proves that a running session loaded the plugin.
    assert check.ok is None
    assert "declares" in check.detail
    assert "desktop" in check.detail
