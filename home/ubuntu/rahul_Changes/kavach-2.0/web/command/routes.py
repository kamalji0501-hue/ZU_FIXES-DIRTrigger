"""Starlette routes for /command Command Center."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from web.fleet import auth as fleet_auth

logger = logging.getLogger("batman.kavach.command")

COMMAND_STATIC = Path(__file__).resolve().parent / "static"
_DISPLAY_REF = Path(
    os.environ.get(
        "COMMAND_DISPLAY_REF",
        "/home/ubuntu/Trading_Runtime_Rahul/Data/data/shared/command_display_ref.json",
    )
)


def _secret_pw() -> tuple[str, str]:
    return fleet_auth.ensure_fleet_secrets()


def _authed(request: Request) -> bool:
    secret, _ = _secret_pw()
    return fleet_auth.valid_session(secret, request.cookies.get(fleet_auth.COOKIE))


async def command_page(request: Request) -> Response:
    html = COMMAND_STATIC / "command.html"
    if not html.is_file():
        return JSONResponse({"ok": False, "error": "command_ui_missing"}, status_code=500)
    return FileResponse(str(html))


async def command_login(request: Request) -> Response:
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}
    secret, password = _secret_pw()
    if not fleet_auth.password_ok(password, str(body.get("password") or "")):
        return JSONResponse({"ok": False, "error": "bad password"}, status_code=401)
    resp = JSONResponse({"ok": True})
    resp.set_cookie(
        fleet_auth.COOKIE,
        fleet_auth.make_session(secret),
        httponly=True,
        samesite="lax",
        max_age=fleet_auth.TTL_S,
        path="/",
    )
    return resp


async def command_logout(request: Request) -> Response:
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(fleet_auth.COOKIE, path="/")
    return resp


async def command_me(request: Request) -> Response:
    if not _authed(request):
        return JSONResponse({"ok": False, "auth": False}, status_code=401)
    return JSONResponse({"ok": True, "auth": True})


async def command_snapshot(request: Request) -> Response:
    if not _authed(request):
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
    from web.command.aggregator import get_snapshot, refresh_once

    if request.query_params.get("refresh") == "1":
        try:
            refresh_once(force_margin=request.query_params.get("margin") == "1")
        except Exception as exc:
            logger.exception("command refresh failed")
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)
    snap = get_snapshot()
    import datetime as _dt

    try:
        from zoneinfo import ZoneInfo

        now = _dt.datetime.now(ZoneInfo("Asia/Kolkata"))
        snap["ist"] = now.strftime("%H:%M:%S")
        snap["ist_date"] = now.strftime("%d %b %Y IST")
    except Exception:
        snap["ist"] = None
    return JSONResponse(snap)


def _read_display_ref() -> dict:
    try:
        if _DISPLAY_REF.is_file():
            data = json.loads(_DISPLAY_REF.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                w = int(data.get("w") or 0)
                h = int(data.get("h") or 0)
                if w >= 1600 and h >= 850:
                    return {"ok": True, "w": w, "h": h}
    except Exception:
        logger.exception("display-ref read failed")
    return {"ok": True, "w": 2560, "h": 1440}


async def command_display_ref_get(request: Request) -> Response:
    if not _authed(request):
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
    return JSONResponse(_read_display_ref())


async def command_desk_pnl(request: Request) -> Response:
    if not _authed(request):
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}
    inst_id = str(body.get("id") or "").strip()
    if not inst_id:
        return JSONResponse({"ok": False, "error": "missing id"}, status_code=400)
    from web.command.aggregator import fetch_desk_pnl_split

    out = fetch_desk_pnl_split(inst_id)
    status = 200 if out.get("ok") else 502
    return JSONResponse(out, status_code=status)


async def command_desk_pnl_all(request: Request) -> Response:
    if not _authed(request):
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
    from web.command.aggregator import fetch_all_desk_pnl_splits

    out = fetch_all_desk_pnl_splits(concurrency=4)
    return JSONResponse(out)


async def command_broadcast(request: Request) -> Response:
    """Broadcast text + optional base64 file to all Kavach desks (ALERT LOGS)."""
    if not _authed(request):
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
    import base64

    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}
    text = str(body.get("text") or "")
    severity = str(body.get("severity") or "orange")
    filename = str(body.get("filename") or "")
    content_type = str(body.get("content_type") or "")
    content_b64 = str(body.get("content_b64") or "")
    raw_ids = body.get("desk_ids")
    desk_ids: list[str] | None = None
    if isinstance(raw_ids, list):
        desk_ids = [str(x).strip() for x in raw_ids if str(x).strip()]
    if content_b64:
        try:
            raw_len = len(base64.b64decode(content_b64, validate=False))
        except Exception:
            return JSONResponse({"ok": False, "error": "bad_base64"}, status_code=400)
        if raw_len > 1_000_000:
            return JSONResponse({"ok": False, "error": "file_too_large_max_1mb"}, status_code=400)

    from web.command.aggregator import broadcast_operator_notice

    out = broadcast_operator_notice(
        text=text,
        severity=severity,
        filename=filename,
        content_b64=content_b64,
        content_type=content_type,
        desk_ids=desk_ids,
        concurrency=4,
    )
    status = 200 if out.get("ok") else 400
    return JSONResponse(out, status_code=status)


async def command_display_ref_put(request: Request) -> Response:
    if not _authed(request):
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}
    try:
        w = int(body.get("w") or 0)
        h = int(body.get("h") or 0)
    except Exception:
        return JSONResponse({"ok": False, "error": "bad size"}, status_code=400)
    if w < 1600 or h < 850:
        return JSONResponse({"ok": False, "error": "size too small"}, status_code=400)
    try:
        _DISPLAY_REF.parent.mkdir(parents=True, exist_ok=True)
        _DISPLAY_REF.write_text(
            json.dumps({"ok": True, "w": w, "h": h}, indent=2) + "\n",
            encoding="utf-8",
        )
    except Exception as exc:
        logger.exception("display-ref write failed")
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)
    return JSONResponse({"ok": True, "w": w, "h": h})


def command_routes() -> list:
    return [
        Route("/command", command_page),
        Route("/api/command/login", command_login, methods=["POST"]),
        Route("/api/command/logout", command_logout, methods=["POST"]),
        Route("/api/command/me", command_me),
        Route("/api/command/snapshot", command_snapshot),
        Route("/api/command/desk-pnl", command_desk_pnl, methods=["POST"]),
        Route("/api/command/desk-pnl-all", command_desk_pnl_all, methods=["POST"]),
        Route("/api/command/broadcast", command_broadcast, methods=["POST"]),
        Route("/api/command/display-ref", command_display_ref_get, methods=["GET"]),
        Route("/api/command/display-ref", command_display_ref_put, methods=["POST"]),
        Mount("/command/static", StaticFiles(directory=str(COMMAND_STATIC)), name="command-static"),
    ]


def on_startup() -> None:
    try:
        from web.command.aggregator import start_aggregator

        start_aggregator()
    except Exception:
        logger.exception("command aggregator failed to start")
