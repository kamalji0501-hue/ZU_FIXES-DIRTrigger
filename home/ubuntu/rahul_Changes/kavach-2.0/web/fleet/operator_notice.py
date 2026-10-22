"""Receive Command Center operator notices (text + optional file) into desk alerts."""

from __future__ import annotations

import base64
import logging
import os
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

logger = logging.getLogger("batman.kavach.operator_notice")

IST = ZoneInfo("Asia/Kolkata")
MAX_BYTES = 1_000_000
ALLOWED_MIME = {
    "image/png": "image",
    "image/jpeg": "image",
    "image/jpg": "image",
    "image/webp": "image",
    "image/gif": "image",
    "text/plain": "file",
    "text/markdown": "file",
    "application/pdf": "file",
}
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def _runtime_root() -> Path:
    env = (os.environ.get("BATMAN_RUNTIME_ROOT") or os.environ.get("TRADING_RUNTIME") or "").strip()
    if env:
        return Path(env)
    return Path("/home/ubuntu/Trading_Runtime_Rahul")


def notices_dir(day: str | None = None) -> Path:
    stamp = day or datetime.now(IST).strftime("%Y-%m-%d")
    return _runtime_root() / "Data" / "data" / "shared" / "cc_notices" / stamp


def _safe_filename(name: str) -> str:
    base = Path(str(name or "attachment").strip()).name or "attachment"
    base = _SAFE_NAME.sub("_", base)[:120]
    return base or "attachment"


def _guess_mime(name: str, given: str) -> str:
    mime = (given or "").strip().lower()
    if mime in ALLOWED_MIME:
        if mime == "image/jpg":
            return "image/jpeg"
        return mime
    ext = Path(name or "").suffix.lower()
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
        ".txt": "text/plain",
        ".md": "text/markdown",
        ".pdf": "application/pdf",
    }.get(ext, "")


def save_attachment(
    *,
    filename: str,
    content: bytes,
    content_type: str = "",
) -> dict[str, Any]:
    if not content:
        raise ValueError("empty_file")
    if len(content) > MAX_BYTES:
        raise ValueError(f"file_too_large:{len(content)}")
    mime = _guess_mime(filename, content_type)
    if mime not in ALLOWED_MIME:
        raise ValueError(f"unsupported_type:{mime or content_type or 'unknown'}")
    kind = ALLOWED_MIME[mime]
    att_id = uuid.uuid4().hex[:16]
    day = datetime.now(IST).strftime("%Y-%m-%d")
    folder = notices_dir(day)
    folder.mkdir(parents=True, exist_ok=True)
    safe = _safe_filename(filename)
    path = folder / f"{att_id}_{safe}"
    path.write_bytes(content)
    meta = {
        "id": att_id,
        "name": safe,
        "mime": mime,
        "kind": kind,
        "day": day,
        "path": str(path),
        "bytes": len(content),
    }
    import json as _json

    (folder / f"{att_id}.json").write_text(_json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return meta


def find_attachment(att_id: str) -> dict[str, Any] | None:
    aid = (att_id or "").strip()
    if not aid or "/" in aid or ".." in aid:
        return None
    root = _runtime_root() / "Data" / "data" / "shared" / "cc_notices"
    if not root.is_dir():
        return None
    # Prefer today's folder, then scan recent day folders
    days = sorted([p.name for p in root.iterdir() if p.is_dir()], reverse=True)
    for day in days[:14]:
        meta_path = root / day / f"{aid}.json"
        if not meta_path.is_file():
            continue
        try:
            meta = __import__("json").loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(meta, dict):
            continue
        path = Path(str(meta.get("path") or ""))
        if not path.is_file():
            # rebuild from naming convention
            matches = list((root / day).glob(f"{aid}_*"))
            matches = [p for p in matches if p.suffix != ".json"]
            if not matches:
                return None
            path = matches[0]
            meta["path"] = str(path)
        return meta
    return None


def receive_operator_notice(
    *,
    text: str,
    severity: str = "orange",
    filename: str = "",
    content: bytes | None = None,
    content_type: str = "",
    content_b64: str = "",
) -> dict[str, Any]:
    """Persist optional file and emit a Command Center desk alert."""
    msg = str(text or "").strip()
    if not msg:
        return {"ok": False, "error": "empty_message"}
    if len(msg) > 2000:
        msg = msg[:2000]

    raw = content
    if raw is None and content_b64:
        try:
            raw = base64.b64decode(content_b64, validate=False)
        except Exception:
            return {"ok": False, "error": "bad_base64"}

    attachment_meta = None
    log = msg
    if raw is not None:
        try:
            attachment_meta = save_attachment(
                filename=filename or "attachment",
                content=raw,
                content_type=content_type,
            )
            log = f"{msg}\n[Attachment: {attachment_meta.get('name')}]"
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        except Exception as exc:
            logger.exception("save attachment failed")
            return {"ok": False, "error": f"save_failed:{exc}"}

    from core.desk_alerts import emit_desk_alert

    row = emit_desk_alert(
        severity=severity or "orange",
        category="Command Center",
        alert="Notification from Command Center",
        log=log,
        attachment={
            "id": attachment_meta["id"],
            "name": attachment_meta["name"],
            "mime": attachment_meta["mime"],
            "kind": attachment_meta["kind"],
        }
        if attachment_meta
        else None,
    )
    if not row:
        return {"ok": False, "error": "alert_emit_failed"}
    out: dict[str, Any] = {"ok": True, "desk_alert": row}
    if attachment_meta:
        out["attachment"] = {
            "id": attachment_meta["id"],
            "name": attachment_meta["name"],
            "mime": attachment_meta["mime"],
            "kind": attachment_meta["kind"],
        }
    return out
