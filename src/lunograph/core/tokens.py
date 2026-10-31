"""Conservative, offline token estimation.

We deliberately avoid a network-dependent tokenizer in the deterministic
kernel.  The estimate is conservative for mixed Chinese/English content:
one token per CJK character plus roughly one token per three ASCII characters,
with a small JSON overhead allowance.
"""

from __future__ import annotations

import json
import math
import re
from typing import Any

_CJK = re.compile(r"[㐀-鿿豈-﫿぀-ヿ가-힯]")
_ASCII_WS = re.compile(r"\s+")


def estimate_text_tokens(text: str) -> int:
    if not text:
        return 0
    cjk = len(_CJK.findall(text))
    ascii_chars = len(_ASCII_WS.sub("", _CJK.sub("", text)))
    return max(1, math.ceil(cjk * 1.0 + ascii_chars / 3.2))


def estimate_tokens(value: Any) -> int:
    if isinstance(value, str):
        return estimate_text_tokens(value)
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
    return estimate_text_tokens(text)
