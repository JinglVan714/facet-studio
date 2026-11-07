"""Small deterministic text helpers shared by writing/media stage inputs.

The helpers here are deliberately narrow: they cap prompt-facing text while
reporting the full length, so a view can be compact without silently losing
the audit trail.
"""

from __future__ import annotations

# Frame captions are VLM/OCR screen text.  The brief and visual planner need
# enough to recognize the frame, not the whole code/UI dump; the full caption
# stays in the consume index and the compiled evidence text.
CAPTION_PROMPT_CHARS = 240


def truncate_caption(
    text: str, limit: int = CAPTION_PROMPT_CHARS
) -> tuple[str, int, bool]:
    """Return ``(prompt_text, full_chars, truncated)`` for a frame caption.

    The returned text is capped at ``limit`` characters and ends with an
    ellipsis when truncated.  Callers must persist ``full_chars`` and
    ``truncated`` so the reader can see that the prompt view is not the full
    caption.
    """
    full = (text or "").strip()
    full_chars = len(full)
    if full_chars <= limit:
        return full, full_chars, False
    return full[:limit].rstrip() + "…", full_chars, True
