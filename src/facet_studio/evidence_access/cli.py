"""CLI entry point for the consume-index builder.

Use ``python -m facet_studio.evidence_access.cli ...``.  The builder itself stays
in ``consume_index.py``; this thin entry avoids running the imported module
directly via ``-m``.
"""

from __future__ import annotations

from .consume_index import main

if __name__ == "__main__":
    raise SystemExit(main())
