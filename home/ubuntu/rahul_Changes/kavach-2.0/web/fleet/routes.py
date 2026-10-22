"""Starlette routes for /fleet + desk export endpoints used by aggregator."""

from __future__ import annotations

import logging
from pathlib import Path

from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from web.fleet import auth as fleet_auth

logger = logging.getLogger("batman.kavach.fleet")

FLEET_STATIC = Path(__file__).resolve().parent / "static"


def _secret_pw() -> tuple[str, str]:
    return fleet_auth.ensure_fleet_secrets()


def _fleet_authed(request: Request) -> bool:
    secret, _ = _secret_pw()
    return fleet_auth.valid_session(secret, request.cookies.get(fleet_auth.COOKIE))


def _copy_key_ok(request: Request) -> bool:
    try:
        from modules.copy_trading import load_key, _eq_key

        expect = load_key()
        got = (request.headers.get("x-copy-key") or "").strip()
        return bool(_eq_key(got, expect))
    except Exception:
        return False


def _desk_session_ok(request: Request) -> bool:
    try:
        import os

        from dotenv import load_dotenv

        from web import auth as web_auth

        path = web_auth.web_env_path()
        if path.is_file():
            load_dotenv(path, override=True)
        secret = (os.environ.get("KAVACH_WEB_SESSION_SECRET") or "").strip()
        if not secret:
            _pw, secret = web_auth.ensure_web_secrets()
        return web_auth.valid_session(secret, request.cookies.get(web_auth.COOKIE))
    except Exception:
        return False


def _desk_or_copy_auth(request: Request) -> bool:
    """Desk session cookie OR shared copy key (for fleet master polls)."""
    if _desk_session_ok(request):
        return True
    return _copy_key_ok(request)


async def fleet_page(request: Request) -> Response:
    html = FLEET_STATIC / "fleet.html"
    if not html.is_file():
        return JSONResponse({"ok": False, "error": "fleet_ui_missing"}, status_code=500)
    return FileResponse(str(html))


async def fleet_login(request: Request) -> Response:
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


async def fleet_logout(request: Request) -> Response:
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(fleet_auth.COOKIE, path="/")
    return resp


async def fleet_me(request: Request) -> Response:
    if not _fleet_authed(request):
        return JSONResponse({"ok": False, "auth": False}, status_code=401)
    return JSONResponse({"ok": True, "auth": True})


async def fleet_snapshot(request: Request) -> Response:
    if not _fleet_authed(request):
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
    from web.fleet.aggregator import get_snapshot, refresh_once

    if request.query_params.get("refresh") == "1":
        try:
            refresh_once(force_margin=request.query_params.get("margin") == "1")
        except Exception as exc:
            logger.exception("fleet refresh failed")
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)
    snap = get_snapshot()
    # IST clock hint for UI (client also runs its own clock)
    import datetime as _dt

    try:
        from zoneinfo import ZoneInfo

        now = _dt.datetime.now(ZoneInfo("Asia/Kolkata"))
        snap["ist"] = now.strftime("%H:%M:%S")
        snap["ist_date"] = now.strftime("%Y-%m-%d")
    except Exception:
        snap["ist"] = None
    return JSONResponse(snap)


async def fleet_control(request: Request) -> Response:
    if not _fleet_authed(request):
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}
    if not body.get("confirm"):
        return JSONResponse({"ok": False, "error": "confirm_required"}, status_code=400)
    desk_id = str(body.get("desk_id") or "").strip()
    action = str(body.get("action") or "").strip()
    from web.fleet.aggregator import control

    return JSONResponse(control(desk_id, action))


async def api_host_health(request: Request) -> Response:
    if not _desk_or_copy_auth(request):
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
    from web.fleet.host_metrics import collect_host_health

    return JSONResponse(collect_host_health())


async def api_margin(request: Request) -> Response:
    if not _desk_or_copy_auth(request):
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
    force = request.query_params.get("force") == "1"
    from web.fleet.margin_cache import get_margin

    return JSONResponse(get_margin(force=force))


async def api_fleet_desk_snapshot(request: Request) -> Response:
    if not _desk_or_copy_auth(request):
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
    include_margin = request.query_params.get("margin", "1") != "0"
    force = request.query_params.get("force") == "1"
    from web.fleet.desk_export import build_desk_snapshot

    return JSONResponse(build_desk_snapshot(include_margin=include_margin, force_margin=force))


async def api_fleet_desk_pnl_split(request: Request) -> Response:
    """On-demand booked (realised) + running (unrealised) Day PnL split."""
    if not _desk_or_copy_auth(request):
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
    refresh = request.query_params.get("refresh", "1") != "0"
    broker = None
    if refresh:
        try:
            from web.runtime import get_runtime

            rt = get_runtime()
            broker = getattr(rt, "broker", None) if rt is not None else None
        except Exception:
            broker = None
    try:
        from core.day_pnl_cache import booked_running_pnl

        out = booked_running_pnl(refresh=refresh, broker=broker)
    except Exception as exc:
        logger.exception("desk-pnl-split failed")
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)
    return JSONResponse(out)


async def api_fleet_remote(request: Request) -> Response:
    if not _desk_or_copy_auth(request):
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}
    from web.fleet.desk_export import apply_remote_action

    result = apply_remote_action(str(body.get("action") or ""))
    ok = True
    if isinstance(result, dict) and result.get("ok") is False:
        ok = False
    return JSONResponse({"ok": ok, "result": result})


async def api_fleet_operator_notice(request: Request) -> Response:
    """Command Center → desk: text + optional base64 attachment → ALERT LOGS."""
    if not _desk_or_copy_auth(request):
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}
    from web.fleet.operator_notice import receive_operator_notice

    out = receive_operator_notice(
        text=str(body.get("text") or ""),
        severity=str(body.get("severity") or "orange"),
        filename=str(body.get("filename") or body.get("name") or ""),
        content_type=str(body.get("content_type") or body.get("mime") or ""),
        content_b64=str(body.get("content_b64") or ""),
    )
    status = 200 if out.get("ok") else 400
    return JSONResponse(out, status_code=status)


async def api_cc_notice_file(request: Request) -> Response:
    """Desk user download/preview for a CC attachment (session cookie)."""
    if not _desk_session_ok(request):
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
    att_id = str(request.path_params.get("att_id") or "").strip()
    from pathlib import Path

    from starlette.responses import FileResponse

    from web.fleet.operator_notice import find_attachment

    meta = find_attachment(att_id)
    if not meta:
        return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
    path = Path(str(meta.get("path") or ""))
    if not path.is_file():
        return JSONResponse({"ok": False, "error": "missing_file"}, status_code=404)
    mime = str(meta.get("mime") or "application/octet-stream")
    name = str(meta.get("name") or path.name)
    return FileResponse(
        str(path),
        media_type=mime,
        filename=name,
        content_disposition_type="inline" if mime.startswith("image/") else "attachment",
    )


def fleet_routes() -> list:
    return [
        Route("/fleet", fleet_page),
        Route("/api/fleet/login", fleet_login, methods=["POST"]),
        Route("/api/fleet/logout", fleet_logout, methods=["POST"]),
        Route("/api/fleet/me", fleet_me),
        Route("/api/fleet/snapshot", fleet_snapshot),
        Route("/api/fleet/control", fleet_control, methods=["POST"]),
        Route("/api/host-health", api_host_health),
        Route("/api/margin", api_margin),
        Route("/api/fleet/desk-snapshot", api_fleet_desk_snapshot),
        Route("/api/fleet/desk-pnl-split", api_fleet_desk_pnl_split),
        Route("/api/fleet/remote", api_fleet_remote, methods=["POST"]),
        Route("/api/fleet/operator-notice", api_fleet_operator_notice, methods=["POST"]),
        Route("/api/cc-notice/{att_id}", api_cc_notice_file, methods=["GET"]),
        Mount("/fleet/static", StaticFiles(directory=str(FLEET_STATIC)), name="fleet-static"),
    ]


def on_startup() -> None:
    try:
        from web.fleet.aggregator import start_aggregator

        start_aggregator()
    except Exception:
        logger.exception("fleet aggregator failed to start")
