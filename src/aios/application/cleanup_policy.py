"""Read-only checks for literal cleanup targets, not an execution/ownership service."""

from __future__ import annotations

import os
import re
import shlex
import tempfile
from pathlib import Path

from aios.adapters.git import GitRunner
from aios.infrastructure.config import locate_checkout

DELETE_COMMAND = re.compile(r"\b(?:remove-item|rm|rmdir|rd|del|erase)\b", re.I)
_FLAGS = frozenset(
    {
        "-literalpath",
        "-path",
        "-recurse",
        "-force",
        "-r",
        "-f",
        "-rf",
        "-fr",
        "--recursive",
        "--force",
        "--",
        "/s",
        "/q",
        "/f",
    }
)
_PROTECTED = frozenset({"input", "output", ".git", "credentials", ".env", "project.yaml"})


def literal_tokens(command: str) -> list[str]:
    # Deliberately bounded grammar: no expansion, pipelines, wrappers or compound shell.
    if re.search(r"[\n\r;|&<>`$%*?(){}]", command):
        raise ValueError("use one literal command with an exact target; expressions are unresolved")
    tokens = shlex.split(command, posix=False)
    return [
        token[1:-1] if token[:1] in {"'", '"'} and token[-1:] == token[:1] else token
        for token in tokens
    ]


def is_reparse(path: Path) -> bool:
    return path.is_symlink() or path.is_junction()


def check_cleanup(command: str, cwd: Path, checkout: Path) -> tuple[str, str, tuple[str, ...]]:
    """Check filesystem scope only; DSH must separately establish task ownership."""
    try:
        tokens = literal_tokens(command)
        if not tokens or tokens[0].casefold() not in {
            "remove-item",
            "rm",
            "rmdir",
            "rd",
            "del",
            "erase",
        }:
            raise ValueError("destructive command is wrapped or cannot be resolved")
        targets = []
        for token in tokens[1:]:
            if token.casefold() in _FLAGS:
                continue
            if token.startswith("-"):
                raise ValueError("unsupported cleanup option: " + token)
            targets.append(token)
        if len(targets) != 1 or any(c in targets[0] for c in "\"'"):
            raise ValueError("exactly one literal cleanup target is required")
        raw = Path(targets[0])
        if not raw.is_absolute():
            raw = cwd / raw
        if str(raw).startswith(("\\\\", "//")):
            raise ValueError("network/device cleanup targets are not automatically authorized")
        if any(is_reparse(p) for p in (raw, *raw.parents)):
            raise ValueError("cleanup target traverses a symlink or junction")
        target = raw.resolve()
        if any(part.casefold() in _PROTECTED for part in target.parts):
            raise ValueError("target traverses a protected asset directory")
        roots = [
            Path(tempfile.gettempdir()).resolve(),
            checkout / "build",
            checkout / "dist",
            checkout / ".aios/tmp",
        ]
        broad = {Path.home().resolve(), checkout.resolve(), *roots}
        if target in broad or target.parent == target:
            raise ValueError("broad cleanup root is forbidden")
        if not any(target != root and target.is_relative_to(root) for root in roots):
            raise ValueError("target is not a task leaf under temp, build, dist or .aios/tmp")
        if not target.exists():
            raise ValueError("target does not exist; its contents cannot be checked")
        repo = locate_checkout(target)
        if (repo / ".git").exists():
            relative = target.relative_to(repo).as_posix()
            if any(
                part.casefold() in {"input", "output", ".git", "credentials"}
                for part in Path(relative).parts
            ):
                raise ValueError("target includes a protected asset directory")
            tracked = GitRunner(repo).run("ls-files", "-z", "--", relative, timeout=5)
            if tracked.returncode != 0 or tracked.stdout:
                raise ValueError("target contains tracked files or Git inspection failed")

        def unreadable(error: OSError) -> None:
            raise error

        for directory, dirs, files in os.walk(target, followlinks=False, onerror=unreadable):
            for name in (*dirs, *files):
                child = Path(directory) / name
                if is_reparse(child):
                    raise ValueError("target contains a symlink or junction")
                if name.casefold() in _PROTECTED:
                    raise ValueError("target contains a protected asset directory")
        return (
            "CLEANUP_TARGET_CHECKED",
            "target checks passed; DSH must confirm task ownership and host approval",
            (str(target),),
        )
    except (OSError, ValueError) as exc:
        return "CLEANUP_TARGET_UNSAFE", str(exc), ()
