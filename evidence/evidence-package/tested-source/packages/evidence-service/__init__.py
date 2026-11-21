"""Installed JSON evidence catalog and bounded audit contexts."""

from .evidence_audit import EvidenceCatalog, EvidenceError
from .evidence_service import EvidenceService

__all__ = ["EvidenceCatalog", "EvidenceError", "EvidenceService"]
__version__ = "0.1.0"
