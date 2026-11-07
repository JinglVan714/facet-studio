"""Deterministic evidence access for the writing layer.

This package does not modify substrate v1.  It builds a consume index from
existing pack/transcript/source-map/frame artifacts and exposes small lookup
helpers for planners, writers, verifiers, and visual planning.
"""

from .consume_index import (
    build_consume_index,
    get_part,
    lookup_claim,
    lookup_frame,
    normalize_frames_index,
    slice_evidence,
    visual_lookup,
)

__all__ = [
    "build_consume_index",
    "get_part",
    "lookup_claim",
    "lookup_frame",
    "normalize_frames_index",
    "slice_evidence",
    "visual_lookup",
]
