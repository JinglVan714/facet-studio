"""产物写入的**唯一闸门**：换版必须并存，不许就地覆盖（spec §8.0）。

## 为什么要有这个模块

2026-10-15 有一次真实事故：`--out-suffix` 的补丁没生效，写入分支仍写 `assertions.jsonl`，
于是 `BV1B5411A7ax` 的 **v4 底稿被 v5 直接覆盖**，且没有任何备份。
那条底稿是一次模型调用 + 人工校准过的，**而且不可逐字节重建**（同设置两次跑，选中集合 Jaccard 只有 0.622）。

事后只在 spec 里写了两句纪律。**纪律写在文档里，挡不住下一次手滑。** 这个模块把它变成代码。

## 判据（三条，缺一不可）

1. 目标不存在 → 写；
2. 目标存在且**逐字节相同** → 不写（幂等，重跑不产生噪音）；
3. 目标存在且不同 → **拒绝**，并告诉调用方两条出路：换后缀并存，或走显式提升。

第 3 条是全部价值所在。**"尽力而为地覆盖"正是那场事故的做法。**

## 为什么连 `*_reduced.jsonl` 也要管

`project.load_assertions()` **优先读 `assertions_reduced.jsonl`**。
所以覆盖那个文件，效果等同于覆盖默认产物——下游会**静默地**改读另一份数据，而文件名看起来完全正常。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

DEFAULT_NAMES = ("assertions.jsonl", "relations.jsonl",
                 "assertions_reduced.jsonl", "relations_reduced.jsonl")


class OverwriteRefused(RuntimeError):
    """目标已存在且内容不同。**这不是错误路径，是保护生效了**。"""


def _sha_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha_file(path: Path) -> str:
    """文件级 SHA256。`promote_variant.py` 与 `evals.regenerate_once` 共用这一份。"""
    return _sha_bytes(path.read_bytes())


def backup_verified(path: Path, suffix: str) -> Path | None:
    """把 `path` 复制成 `名字+suffix+扩展名`，**并校验复制结果与源逐字节一致**。

    返回备份路径；源不存在返回 `None`；**校验不过或目标已被占用（且内容不同）也返回
    `None`——调用方必须据此中止**，不许"尽力而为地覆盖"（spec §8.0）。

    这个动作此前只存在于 `scripts/promote_variant.py` 里。`evals.regenerate_once`
    要重建底稿时同样需要它，所以提到这里——**同一件事只能有一份实现**。
    """
    if not path.exists():
        return None
    dest = path.with_name(f"{path.stem}{suffix}{path.suffix}")
    src_sha = sha_file(path)
    if dest.exists():
        # 幂等：同名备份已存在且就是现在这份 ⇒ 直接复用；否则一律拒绝（不覆盖别人的备份）
        return dest if sha_file(dest) == src_sha else None
    dest.write_bytes(path.read_bytes())
    return dest if sha_file(dest) == src_sha else None


def render_jsonl(rows: list[dict]) -> bytes:
    """规范形态：**LF 行尾**。"""
    return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows).encode("utf-8")


def _existing_eol(path: Path) -> bytes:
    """沿用已存在文件的行尾约定；首次创建用 LF。"""
    b = path.read_bytes()
    return b"\r\n" if b.count(b"\r\n") else b"\n"


def _read_lf(path: Path) -> bytes:
    """读进来并归一化到 LF。

    ⚠️ **不归一化会让闸门自己变成障碍**：本项目在 Windows 上，历史上用
    `open("w", encoding="utf-8")`（文本模式）写盘 ⇒ `\\n` 被翻译成 `\\r\\n`，
    现有 `assertions.jsonl` / `units.jsonl` / `contract.json` **全是 CRLF**。
    而 `write_bytes` 写出来是 LF。**内容逐条相同的重跑会被判成"内容不同"而被拒绝。**
    （实测踩到：自己写的闸门第一次复跑就在同一条数据上误报。）
    """
    return path.read_bytes().replace(b"\r\n", b"\n")


def guarded_write_jsonl(path: Path, rows: list[dict], *, what: str = "",
                        allow_overwrite: bool = False) -> dict:
    """写 jsonl，带覆盖保护。返回 {written, reason, sha256, bytes}。

    `allow_overwrite=True` 只给**显式提升**用（`scripts/promote_variant.py` 那条路），
    普通管线一律不给。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = render_jsonl(rows)
    new_sha = _sha_bytes(payload)
    label = what or path.name
    if not path.exists():
        path.write_bytes(payload)
        return {"written": True, "reason": "新建", "sha256": new_sha, "bytes": len(payload)}
    old_lf = _read_lf(path)
    old_sha = _sha_bytes(old_lf)
    if old_lf == payload:
        # **按内容判等，不按字节判等**——行尾差异不是"内容不同"。
        return {"written": False, "reason": "内容相同，跳过（幂等）",
                "sha256": _sha_bytes(path.read_bytes()), "bytes": path.stat().st_size}
    if allow_overwrite:
        eol = _existing_eol(path)
        out = payload if eol == b"\n" else payload.replace(b"\n", eol)
        path.write_bytes(out)
        return {"written": True, "reason": "显式覆盖", "sha256": _sha_bytes(out), "bytes": len(out)}
    raise OverwriteRefused(
        f"拒绝覆盖 {label}：目标已存在且内容不同 "
        f"（现有 {old_sha[:12]} / 本次 {new_sha[:12]}）。\n"
        f"  spec §8.0：换版必须并存，不许就地覆盖。两条出路：\n"
        f"   ① 并存 —— 用 `--out-suffix _xxx` 写到新名字，比对通过后再显式提升；\n"
        f"   ② 提升 —— 先 `scripts/promote_variant.py <vid> --from _xxx --dry-run` 看清单，再去掉 --dry-run。\n"
        f"  若确认要就地覆盖（例如重跑同一版本）：删掉 {path} 或显式传 allow_overwrite=True。")


def guarded_write_json(path: Path, obj: dict, *, what: str = "",
                       allow_overwrite: bool = False) -> dict:
    """写单个 JSON（报告类），同一套判据。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(obj, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    new_sha = _sha_bytes(payload)
    label = what or path.name
    if not path.exists():
        path.write_bytes(payload)
        return {"written": True, "reason": "新建", "sha256": new_sha}
    old_lf = _read_lf(path)
    if old_lf == payload:                      # 同 `guarded_write_jsonl`：按内容判等
        return {"written": False, "reason": "内容相同，跳过（幂等）",
                "sha256": _sha_bytes(path.read_bytes())}
    if allow_overwrite:
        eol = _existing_eol(path)
        out = payload if eol == b"\n" else payload.replace(b"\n", eol)
        path.write_bytes(out)
        return {"written": True, "reason": "显式覆盖", "sha256": _sha_bytes(out)}
    raise OverwriteRefused(
        f"拒绝覆盖 {label}：内容不同（现有 {_sha_bytes(old_lf)[:12]} / 本次 {new_sha[:12]}）。"
        f"要并存就换后缀；要覆盖就删掉它或显式传 allow_overwrite=True。")
