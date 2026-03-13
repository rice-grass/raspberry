"""
aiohttp 기반 통합 서버 (포트 8080 단일)
  GET /dashboard.html  → 대시보드 HTML 서빙
  GET /ws              → WebSocket (대시보드 + Pi 클라이언트 공용)

클라이언트 구분:
  - 대시보드 : start_game / ping 전송
  - Pi 클라이언트 : pi_register 등록 후 button_press 이벤트 전송
"""
import asyncio
import json
import os
import queue as _queue_module
import threading

import aiohttp
from aiohttp import web

# ── 내부 상태 ───────────────────────────────────────────────────
_loop: asyncio.AbstractEventLoop | None = None
_ready = threading.Event()

_dashboard_clients: set = set()          # aiohttp WebSocketResponse (대시보드)
_pi_ws: web.WebSocketResponse | None = None
_pi_lock = threading.Lock()

_button_queue: _queue_module.Queue = _queue_module.Queue()

_current_state: dict = {"game": None, "score": 0, "stage": 0, "game_running": False, "pi_connected": False}
_command_handler = None


def set_command_handler(fn):
    global _command_handler
    _command_handler = fn


# ── WebSocket 핸들러 (/ws) ───────────────────────────────────────
async def _ws_handler(request: web.Request) -> web.WebSocketResponse:
    global _pi_ws
    ws = web.WebSocketResponse(heartbeat=30)
    await ws.prepare(request)

    is_pi = False

    # 연결 직후: 대시보드로 간주하고 현재 상태 즉시 전송
    _dashboard_clients.add(ws)
    try:
        await ws.send_str(json.dumps({"type": "state_sync", "data": _current_state}))
    except Exception:
        pass

    async for msg in ws:
        if msg.type == aiohttp.WSMsgType.TEXT:
            try:
                data    = json.loads(msg.data)
                cmd     = data.get("type")
                payload = data.get("data", {})

                # Pi 등록
                if cmd == "pi_register":
                    is_pi = True
                    _dashboard_clients.discard(ws)
                    with _pi_lock:
                        _pi_ws = ws
                    _current_state["pi_connected"] = True
                    print(f"[Socket] 라즈베리파이 등록: {request.remote}")
                    asyncio.create_task(_broadcast_async("pi_status", {"connected": True}))
                    continue

                # Pi 이벤트
                if is_pi:
                    if cmd == "button_press":
                        _button_queue.put(payload)
                    continue

                # 대시보드 명령
                print(f"[Socket] 명령: {cmd} {payload}")
                if _command_handler and cmd:
                    threading.Thread(
                        target=_command_handler, args=(cmd, payload), daemon=True
                    ).start()

            except Exception as e:
                print(f"[Socket] 파싱 오류: {e}")

        elif msg.type in (aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSE):
            break

    # 연결 해제 정리
    if is_pi:
        with _pi_lock:
            if _pi_ws == ws:
                _pi_ws = None
        _current_state["pi_connected"] = False
        asyncio.create_task(_broadcast_async("pi_status", {"connected": False}))
        print("[Socket] 라즈베리파이 연결 해제")
    else:
        _dashboard_clients.discard(ws)
        print(f"[Socket] 대시보드 연결 해제 (총 {len(_dashboard_clients)}명)")

    return ws


# ── HTTP 핸들러 (/) ──────────────────────────────────────────────
async def _dashboard_handler(request: web.Request) -> web.FileResponse:
    base = os.path.dirname(os.path.abspath(__file__))
    return web.FileResponse(os.path.join(base, "dashboard.html"))


# ── 브로드캐스트 ─────────────────────────────────────────────────
async def _broadcast_async(event_type: str, data: dict):
    global _dashboard_clients
    msg = json.dumps({"type": event_type, "data": data}, ensure_ascii=False)
    dead = set()
    for ws in list(_dashboard_clients):
        try:
            await ws.send_str(msg)
        except Exception:
            dead.add(ws)
    _dashboard_clients -= dead


def broadcast(event_type: str, data: dict):
    """어느 스레드에서나 안전하게 호출 가능한 대시보드 브로드캐스트."""
    global _current_state

    if _loop is None:
        return

    # 상태 업데이트
    if event_type == "game_start":
        _current_state.update({"game": data.get("game"), "score": 0, "stage": 0, "game_running": True})
    elif event_type == "score_update":
        _current_state["score"] = data.get("score", 0)
    elif event_type == "stage_update":
        _current_state["stage"] = data.get("stage", data.get("question_num", 0))
    elif event_type in ("game_over", "game_ready"):
        _current_state.update({"game": None, "game_running": False})

    _print_event(event_type, data)
    asyncio.run_coroutine_threadsafe(_broadcast_async(event_type, data), _loop)


# ── Pi 전송 ─────────────────────────────────────────────────────
async def _send_pi_async(msg: str):
    global _pi_ws
    if _pi_ws is not None and not _pi_ws.closed:
        try:
            await _pi_ws.send_str(msg)
        except Exception as e:
            print(f"[Socket] Pi 전송 오류: {e}")
            with _pi_lock:
                _pi_ws = None


def send_to_pi(event_type: str, data: dict):
    if _loop is None or _pi_ws is None:
        return
    msg = json.dumps({"type": event_type, "data": data}, ensure_ascii=False)
    asyncio.run_coroutine_threadsafe(_send_pi_async(msg), _loop)


# ── 버튼 큐 ─────────────────────────────────────────────────────
def get_button_event(timeout: float = 120.0):
    return _button_queue.get(timeout=timeout)


def clear_button_queue():
    while not _button_queue.empty():
        try:
            _button_queue.get_nowait()
        except _queue_module.Empty:
            break


def get_button_nowait():
    """논블로킹 버튼 이벤트 확인. 없으면 None 반환."""
    try:
        return _button_queue.get_nowait()
    except _queue_module.Empty:
        return None


# ── 서버 시작 ────────────────────────────────────────────────────
async def _run_app(host: str, port: int):
    global _loop
    _loop = asyncio.get_running_loop()

    app = web.Application()
    app.router.add_get("/ws", _ws_handler)
    app.router.add_get("/", _dashboard_handler)
    app.router.add_get("/dashboard.html", _dashboard_handler)

    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, host, port, reuse_address=True)
    await site.start()

    print(f"[서버] 통합 서버 시작: http://{host}:{port}/dashboard.html  |  ws://{host}:{port}/ws")
    _ready.set()
    await asyncio.Event().wait()   # 영구 대기


def start_server(host: str = "0.0.0.0", port: int = 8080):
    t = threading.Thread(target=lambda: asyncio.run(_run_app(host, port)), daemon=True)
    t.start()
    _ready.wait()


def start_http_server(directory: str = None, port: int = 8080):
    """호환성 유지를 위한 no-op (HTTP는 start_server에서 통합 처리)"""
    pass


# ── 로그 ─────────────────────────────────────────────────────────
def _print_event(event_type: str, data: dict):
    important = {"game_start", "game_over", "correct", "wrong", "score_update", "stage_update", "game_ready"}
    if event_type not in important:
        return
    prefix = {
        "game_start": "🎮 게임 시작", "game_over": "🏁 게임 종료",
        "correct": "✅ 정답",        "wrong": "❌ 오답",
        "score_update": "📊 점수",   "stage_update": "📍 스테이지",
        "game_ready": "⏳ 대기 중",
    }.get(event_type, event_type)

    if event_type == "score_update":
        print(f"  [{prefix}] {data.get('score', 0)}점")
    elif event_type == "stage_update":
        print(f"  [{prefix}] {data.get('stage', data.get('question_num', '?'))}")
    elif event_type in ("game_start", "game_ready"):
        print(f"  [{prefix}] {data.get('game', data.get('message', ''))}")
    elif event_type == "game_over":
        print(f"  [{prefix}] 최종 점수: {data.get('score', 0)}점")
    elif event_type == "correct":
        expl = data.get("explanation", "")
        print(f"  [{prefix}]{' | ' + expl if expl else ''}")
    elif event_type == "wrong":
        print(f"  [{prefix}] {data}")
