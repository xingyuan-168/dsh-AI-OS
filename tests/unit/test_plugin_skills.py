from __future__ import annotations

import ast
import inspect
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

SKILLS_ROOT = Path(__file__).resolve().parents[2] / "plugins" / "ai-engineering-os" / "skills"


def test_skill_set_is_converged() -> None:
    names = {path.name for path in SKILLS_ROOT.iterdir() if path.is_dir()}
    assert names == EXPECTED_SKILLS


def test_each_skill_has_manifest_and_agent_profile() -> None:
    for name in sorted(EXPECTED_SKILLS):
        skill_md = SKILLS_ROOT / name / "SKILL.md"
        assert skill_md.is_file(), name
        text = skill_md.read_text(encoding="utf-8")
        assert text.startswith("---"), name
        assert "name: " + name in text, name
        assert "description:" in text, name
        assert (SKILLS_ROOT / name / "agents" / "openai.yaml").is_file(), name


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
