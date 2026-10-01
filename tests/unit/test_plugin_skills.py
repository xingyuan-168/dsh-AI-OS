from __future__ import annotations

import ast
import inspect
import json
import re
from pathlib import Path

from aios.cli import mcp_server

EXPECTED_SKILLS = {
    "governance-entry",
    "open-source-research",
    "html-prototype",
    "frontend-design-review",
    "worktree-protocol",
    "document-impact",
    "memory-protocol",
    "finish-checklist",
}

PLUGIN_ROOT = Path(__file__).resolve().parents[2] / "plugins" / "ai-engineering-os"
SKILLS_ROOT = PLUGIN_ROOT / "skills"

# The host integration is a DSH Cordis bundle: a package manifest that declares
# dsh.bundle.patch, that patch layer, and the plugin entry it references.
PLUGIN_MANIFEST = "package.json"
PLUGIN_ENTRY = "src/index.js"
PLUGIN_MODULES = ("src/index.js", "src/kernel.js", "src/payload.js", "src/surfaces.js")
BUNDLE_PATCH = "cordis.patch.yml"
BUNDLE_ROW_ID = "ai-engineering-os"
CODEX_ARTIFACTS = (
    ".codex-plugin/plugin.json",
    ".mcp.json",
    "hooks/hooks.json",
    "hooks/pre_tool_use.py",
    "hooks/session_start.py",
)


def test_skill_set_is_converged() -> None:
    names = {path.name for path in SKILLS_ROOT.iterdir() if path.is_dir()}
    assert names == EXPECTED_SKILLS


def test_each_skill_has_a_manifest() -> None:
    for name in sorted(EXPECTED_SKILLS):
        skill_md = SKILLS_ROOT / name / "SKILL.md"
        assert skill_md.is_file(), name
        text = skill_md.read_text(encoding="utf-8")
        assert text.startswith("---"), name
        assert "name: " + name in text, name
        assert "description:" in text, name


def test_no_codex_host_artifacts_remain() -> None:
    for relative in CODEX_ARTIFACTS:
        assert not (PLUGIN_ROOT / relative).exists(), relative
    leftover = list(SKILLS_ROOT.glob("*/agents/openai.yaml"))
    assert leftover == [], "per-skill Codex agent profiles must not remain"


def test_plugin_manifest_is_a_dsh_bundle() -> None:
    """A package without dsh.bundle installs as a plain dependency and activates
    no layer, which is exactly how the first activation attempt failed."""

    manifest = json.loads((PLUGIN_ROOT / PLUGIN_MANIFEST).read_text(encoding="utf-8"))
    assert manifest["name"] == BUNDLE_ROW_ID
    assert manifest["type"] == "module"
    assert manifest["exports"]["."] == "./" + PLUGIN_ENTRY
    assert manifest["dsh"]["bundle"]["patch"] == "./" + BUNDLE_PATCH
    # Shipping the patch file is the documented packaging pitfall: without it the
    # layer never reaches the installing profile.
    assert BUNDLE_PATCH in manifest["files"], "the bundle patch must be shipped"
    assert "src" in manifest["files"]
    assert "skills" in manifest["files"]
    assert "mcpServers" not in manifest
    # Codex declared the skill directory by path; DSH receives skills through the
    # plugin's own provider registration instead.
    assert "skills" not in {key for key in manifest if key == "skills"}


def test_bundle_patch_inserts_the_governance_row() -> None:
    """New rows must use insert syntax: an override entry targets an existing id
    and silently matches nothing when the row does not exist yet."""

    import yaml

    layer = yaml.safe_load((PLUGIN_ROOT / BUNDLE_PATCH).read_text(encoding="utf-8"))
    assert isinstance(layer, list) and layer, "the patch layer is a non-empty array"
    inserted = [
        row for entry in layer if isinstance(entry, dict) for row in entry.get("insert", [])
    ]
    assert len(inserted) == 1, "exactly one row is inserted"
    row = inserted[0]
    assert row["id"] == BUNDLE_ROW_ID
    assert row["name"] == BUNDLE_ROW_ID
    # Later layers replace a row's whole config, so the defaults must be complete.
    assert row["config"] == {
        "strict": True,
        "kernelCommand": "aios",
        "timeoutMs": 10000,
        "failMode": "closed",
    }
    # Override entries in this layer would match no existing row.
    assert all("id" not in entry for entry in layer if isinstance(entry, dict))


def test_plugin_entry_declares_the_cordis_contract() -> None:
    for relative in PLUGIN_MODULES:
        assert (PLUGIN_ROOT / relative).is_file(), relative
    entry = (PLUGIN_ROOT / PLUGIN_ENTRY).read_text(encoding="utf-8")
    assert "export const name" in entry
    assert "export function apply" in entry or "export async function apply" in entry


def test_plugin_enforces_at_the_pre_dispatch_point_only() -> None:
    source = (PLUGIN_ROOT / PLUGIN_ENTRY).read_text(encoding="utf-8")
    assert "ctx.on('tools/pre-execute'" in source
    # The fs intent slots cannot deny anything, so registering a listener there
    # would imply write-time protection the host does not offer. They are only
    # mentioned in the module's explanation of that decision.
    assert "ctx.on('fs/" not in source


def test_skill_documents_are_compact() -> None:
    for name in sorted(EXPECTED_SKILLS):
        skill_md = SKILLS_ROOT / name / "SKILL.md"
        lines = skill_md.read_text(encoding="utf-8").splitlines()
        assert len(lines) <= 60, (name, len(lines))


def test_skill_python_examples_match_real_mcp_signatures() -> None:
    count = 0
    for name in sorted(EXPECTED_SKILLS):
        text = (SKILLS_ROOT / name / "SKILL.md").read_text(encoding="utf-8")
        for example in re.findall(r"```python\n(.*?)```", text, re.S):
            for node in ast.walk(ast.parse(example)):
                if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                    continue
                function = getattr(mcp_server, node.func.id)
                kwargs: dict[str, object] = {}
                for item in node.keywords:
                    assert item.arg is not None, "examples must use explicit keyword arguments"
                    kwargs[item.arg] = ast.literal_eval(item.value)
                inspect.signature(function).bind(**kwargs)
                count += 1
    assert count >= 6


def test_research_example_satisfies_document_contract(tmp_path: Path) -> None:
    from aios.core.gates import _research_findings

    text = (SKILLS_ROOT / "open-source-research/SKILL.md").read_text(encoding="utf-8")
    example = re.search(r"```markdown\n(.*?)```", text, re.S)
    assert example is not None
    document = tmp_path / "research.md"
    document.write_text(example.group(1), encoding="utf-8")
    assert not _research_findings(tmp_path, "major_feature", "REQ-EXAMPLE", "research.md")
