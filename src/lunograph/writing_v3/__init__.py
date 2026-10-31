"""v3 writing prototypes: evidence pack + skill-driven writer.

This package is intentionally independent of ``lunograph.writing_v2``.  It
reads the existing evidence/knowledge snapshots and builds a compact,
context-preserving evidence pack for one Writer call.
"""

from .evidence_pack import build_evidence_pack

__all__ = ["build_evidence_pack"]
