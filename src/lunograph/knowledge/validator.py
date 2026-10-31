"""Reference-closure validation for KnowledgeSnapshot."""

from __future__ import annotations

from ..evidence.models import EvidenceSnapshot
from .builder import validate_knowledge_snapshot
from .models import KnowledgeSnapshot

__all__ = ["validate_knowledge_snapshot", "assert_valid_knowledge"]


def assert_valid_knowledge(
    knowledge: KnowledgeSnapshot, snapshot: EvidenceSnapshot
) -> None:
    errors = validate_knowledge_snapshot(knowledge, snapshot)
    if errors:
        raise ValueError("KnowledgeSnapshot 引用不闭合:\n" + "\n".join(errors[:20]))
