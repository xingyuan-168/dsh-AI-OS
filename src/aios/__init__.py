"""AI Engineering OS runtime package."""

from aios.domain.versions import RUNTIME_VERSIONS

__version__ = RUNTIME_VERSIONS.software

__all__ = ["RUNTIME_VERSIONS", "__version__"]
