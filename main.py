"""
미니게임 서버 (WSL2/PC에서 실행)
게임 선택은 웹 대시보드(dashboard.html)에서 수행
라즈베리파이 클라이언트(pi_client.py)를 Pi에서 별도 실행해야 GPIO 입력이 동작합니다.
"""
import atexit
import os
import signal
import socket
import sys
import threading

import gpio_setup as g
import socket_server as ss

PORT = 8080   # HTTP + WebSocket 통합 포트


def _get_public_ip() -> str:
    """공인/접근 가능한 IP 결정: 인자 > 환경변수 > 자동 감지"""
    if len(sys.argv) > 1:
        return sys.argv[1]
    env_ip = os.environ.get("SERVER_IP")
    if env_ip:
        return env_ip
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

# ── 게임 스레드 관리 ─────────────────────────────────────────────
_game_thread: threading.Thread | None = None
_game_lock = threading.Lock()  # 동시에 두 게임 시작 방지


def _is_game_running() -> bool:
    return _game_thread is not None and _game_thread.is_alive()


def _run_game1():
    from game1_morse import run_game1
    try:
        run_game1()
    except Exception as e:
        print(f"[Game1] 오류: {e}")
    finally:
        ss.broadcast("game_ready", {"message": "게임을 선택하세요"})
        print("\n[대기] 웹 대시보드에서 게임을 선택하세요.")


def _run_game2():
    from game2_quiz import run_game2
    try:
        run_game2()
    except Exception as e:
        print(f"[Game2] 오류: {e}")
    finally:
        ss.broadcast("game_ready", {"message": "게임을 선택하세요"})
        print("\n[대기] 웹 대시보드에서 게임을 선택하세요.")


# ── WebSocket 명령 핸들러 ────────────────────────────────────────
def on_command(cmd_type: str, data: dict):
    """웹 대시보드에서 수신한 명령 처리"""
    global _game_thread

    if cmd_type == "start_game":
        with _game_lock:
            if _is_game_running():
                print("[명령] 게임 이미 진행 중 → 무시")
                ss.broadcast("error", {"message": "게임이 이미 진행 중입니다. 종료 후 다시 선택하세요."})
                return

            game_id = str(data.get("game", ""))
            if game_id == "1":
                target = _run_game1
                name = "컬러 메모리 게임"
            elif game_id == "2":
                target = _run_game2
                name = "AI 퀴즈 게임"
            else:
                print(f"[명령] 알 수 없는 게임 ID: {game_id}")
                return

            print(f"\n[명령] 게임 시작 요청: {name}")
            _game_thread = threading.Thread(target=target, name=f"Game{game_id}", daemon=True)
            _game_thread.start()

    elif cmd_type == "ping":
        ss.broadcast("pong", {"status": "ok", "game_running": _is_game_running()})

    else:
        print(f"[명령] 알 수 없는 명령: {cmd_type}")


# ── 종료 처리 ────────────────────────────────────────────────────
def _shutdown(signum=None, frame=None):
    print("\n\n[종료] 서버를 종료합니다...")
    g.cleanup_gpio()
    print("[GPIO] 정리 완료.")
    sys.exit(0)


# ── 메인 ────────────────────────────────────────────────────────
def main():
    server_ip = _get_public_ip()
    print("\n" + "="*52)
    print("   🍓 라즈베리파이 미니게임 센터")
    print("="*52)
    print(f"   서버 IP   : {server_ip}")
    print(f"   대시보드  : http://{server_ip}:{PORT}/dashboard.html")
    print(f"   WebSocket : ws://{server_ip}:{PORT}/ws")
    print("="*52)
    print(f"\n   Pi 클라이언트 실행 (라즈베리파이에서):")
    print(f"   python3 pi_client.py {server_ip}")
    print("="*52)

    # GPIO 초기화
    g.setup_gpio()
    atexit.register(g.cleanup_gpio)
    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    # 통합 서버 시작 (HTTP + WebSocket 포트 8080)
    print("\n[서버] 통합 서버 시작 중...", end=" ", flush=True)
    ss.set_command_handler(on_command)
    ss.start_server(host="0.0.0.0", port=PORT)
    print("완료")

    # 초기 상태 브로드캐스트
    ss.broadcast("game_ready", {"message": "게임을 선택하세요"})
    print(f"\n[대기] 웹 대시보드에서 게임을 선택하세요.")
    print(f"       → http://{server_ip}:{PORT}/dashboard.html\n")

    # 메인 스레드는 대기 (게임은 WebSocket 명령으로 별도 스레드에서 실행)
    try:
        threading.Event().wait()  # 영구 대기
    except KeyboardInterrupt:
        _shutdown()


if __name__ == "__main__":
    main()
