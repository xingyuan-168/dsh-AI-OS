"""Project initialization use case (governance-core surface, ADR-0016)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from aios.domain.config import (
    GitPushPolicy,
    ProjectConfig,
    ProjectType,
)
from aios.infrastructure.config import load_project_config
from aios.infrastructure.database import Database
from aios.infrastructure.documents import DocumentCheckReport, DocumentManager


@dataclass(frozen=True, slots=True)
class ProjectInitResult:
    config: ProjectConfig
    created_paths: tuple[str, ...]
    context_path: Path
    document_report: DocumentCheckReport
    database_path: Path
    repository_ready: bool
    repository_blockers: tuple[str, ...]


class ProjectInitializer:
    def initialize(
        self,
        project_root: Path,
        *,
        project_id: str,
        name: str,
        project_type: ProjectType,
        git_push_policy: GitPushPolicy = GitPushPolicy.REMOTE_REQUIRED,
        include: frozenset[str] | set[str] = frozenset(),
    ) -> ProjectInitResult:
        root = project_root.resolve()
        root.mkdir(parents=True, exist_ok=True)
        documents = DocumentManager(root)
        config_path = root / ".aios" / "project.yaml"
        created: list[str] = []
        new_project = not config_path.is_file()

        if not new_project:
            config = load_project_config(root)
        else:
            config = ProjectConfig(
                project_id=project_id,
                name=name,
                root=root,
                project_type=project_type,
                git_push_policy=git_push_policy,
            )
            config_text = yaml.safe_dump(
                _serializable_config(config),
                allow_unicode=True,
                sort_keys=False,
            )
            if documents.write_atomic(".aios/project.yaml", config_text, overwrite=False):
                created.append(".aios/project.yaml")

        for relative, content in _runtime_entry_files().items():
            if documents.write_atomic(relative, content, overwrite=False):
                created.append(relative)

        created.extend(
            documents.initialize_documents(
                config.name,
                config.project_type.value,
                include=include,
            )
        )
        context_path = documents.generate_context()

        database_path = root / ".aios" / "state" / "state.db"
        Database(database_path).migrate()

        report = documents.check(include=include)
        repository_ready, repository_blockers = self._repository_readiness(root, config)
        return ProjectInitResult(
            config=config,
            created_paths=tuple(created),
            context_path=context_path,
            document_report=report,
            database_path=database_path,
            repository_ready=repository_ready,
            repository_blockers=repository_blockers,
        )

    @staticmethod
    def _repository_readiness(root: Path, config: ProjectConfig) -> tuple[bool, tuple[str, ...]]:
        if config.git_push_policy is GitPushPolicy.FIXTURE_LOCAL_ONLY:
            return True, ()
        git_marker = root / ".git"
        if not git_marker.exists():
            return False, ("NOT_GIT_REPOSITORY",)
        return False, ("REPOSITORY_CHECK_REQUIRED",)


def _serializable_config(config: ProjectConfig) -> dict[str, object]:
    data = config.model_dump(mode="json")
    data["root"] = "."
    data["source_of_truth"] = config.source_of_truth.relative_to(config.root).as_posix()
    return {str(key): value for key, value in data.items()}


def _runtime_entry_files() -> dict[str, str]:
    return {
        ".gitignore": (
            ".aios/state/\n.aios/logs/\n.aios/cache/\n"
            ".aios/context/\n.aios/tmp/\n.aios/artifacts/\n.worktrees/\n"
            ".venv/\n__pycache__/\n*.py[cod]\n.pytest_cache/\npytest-of-*/\n.ruff_cache/\n"
            ".env\nnode_modules/\ntarget/\n.next/\ndist/\nbuild/\n*.log\n"
        ),
    }
