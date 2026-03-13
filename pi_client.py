"""
라즈베리파이 GPIO 클라이언트

서버(WSL2/PC)에 WebSocket으로 연결하여:
  - 물리 버튼 입력 → 서버로 전송
  - LED / 부저 명령 ← 서버에서 수신 후 GPIO 실행

라즈베리파이에서 실행:
  python3 pi_client.py <서버IP>

  예) python3 pi_client.py 192.168.110.100
"""
import asyncio
import json
import subprocess
import sys
import time

import RPi.GPIO as GPIO
import websockets

# ── 서버 설정 ────────────────────────────────────────────────────
SERVER_HOST = sys.argv[1] if len(sys.argv) > 1 else "192.168.110.100"
SERVER_PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8080
RECONNECT_DELAY = 3

# ── GPIO 핀 (BCM 기준) ───────────────────────────────────────────
LED_GREEN   = 17
LED_RED     = 27
BTN_GREEN   = 22   # Game1 초록 버튼
BTN_RED     = 23   # Game1 빨간 버튼
BTN1        = 5
BTN2        = 6
BTN3        = 13
BTN4        = 19
BUZZER      = 26

ANSWER_PINS = [BTN1, BTN2, BTN3, BTN4]
ALL_OUTPUT_PINS = (LED_GREEN, LED_RED, BUZZER)
ALL_INPUT_PINS  = (BTN_GREEN, BTN_RED, BTN1, BTN2, BTN3, BTN4)


# ── GPIO 초기화 ──────────────────────────────────────────────────
def setup_gpio():
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    for pin in ALL_OUTPUT_PINS:
        GPIO.setup(pin, GPIO.OUT, initial=GPIO.LOW)
    for pin in ALL_INPUT_PINS:
        GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)


# ── LED ──────────────────────────────────────────────────────────
def _led_on(pin):
    GPIO.output(pin, GPIO.HIGH)


def _led_off(pin):
    GPIO.output(pin, GPIO.LOW)


def _led_blink(pin, times=3, on_sec=0.2, off_sec=0.2):
    for _ in range(times):
        GPIO.output(pin, GPIO.HIGH)
        time.sleep(on_sec)
        GPIO.output(pin, GPIO.LOW)
        time.sleep(off_sec)


def _led_flash_sequence(sequence):
    """Game1 패턴 출력: G=초록, R=빨간"""
    for color in sequence:
        pin = LED_GREEN if color == 'G' else LED_RED
        GPIO.output(pin, GPIO.HIGH)
        time.sleep(0.5)
        GPIO.output(pin, GPIO.LOW)
        time.sleep(0.3)
    time.sleep(1.0)


# ── 버튼 ─────────────────────────────────────────────────────────
def _wait_game1_button():
    """BTN_GREEN 또는 BTN_RED 중 먼저 눌린 버튼 반환. 'G' 또는 'R'"""
    while True:
        for pin, color in ((BTN_GREEN, 'G'), (BTN_RED, 'R')):
            if GPIO.input(pin) == GPIO.LOW:
                time.sleep(0.05)
                if GPIO.input(pin) == GPIO.LOW:
                    while GPIO.input(pin) == GPIO.LOW:
                        time.sleep(0.01)
                    time.sleep(0.05)
                    return color
        time.sleep(0.01)


def _wait_for_any_button(pins):
    """여러 버튼 중 가장 먼저 눌린 버튼 인덱스 반환 (Game2용, 0-based)."""
    while True:
        for idx, pin in enumerate(pins):
            if GPIO.input(pin) == GPIO.LOW:
                time.sleep(0.05)
                if GPIO.input(pin) == GPIO.LOW:
                    while GPIO.input(pin) == GPIO.LOW:
                        time.sleep(0.01)
                    time.sleep(0.05)
                    return idx
        time.sleep(0.01)


# ── 부저 ─────────────────────────────────────────────────────────
def _buzzer_tone(frequency_hz, duration_sec):
    try:
        pwm = GPIO.PWM(BUZZER, frequency_hz)
        pwm.start(50)
        time.sleep(duration_sec)
        pwm.stop()
    except Exception:
        pass
    finally:
        GPIO.output(BUZZER, GPIO.LOW)


def _buzzer_correct():
    _buzzer_tone(1000, 0.15)
    time.sleep(0.05)
    _buzzer_tone(1500, 0.2)


def _buzzer_wrong():
    _buzzer_tone(300, 0.5)


# ── TTS ───────────────────────────────────────────────────────────
def _speak_tts(text):
    """espeak-ng으로 한국어 TTS 재생"""
    try:
        subprocess.run(
            ['espeak-ng', '-v', 'ko', '-s', '140', text],
            timeout=10, check=False
        )
    except Exception as e:
        print(f"[Pi] TTS 오류: {e}")


# ── 서버 명령 핸들러 ─────────────────────────────────────────────
_IGNORE_TYPES = frozenset({
    "state_sync", "game_start", "game_over", "score_update",
    "stage_update", "pattern_show", "question", "correct", "wrong",
    "hint", "difficulty_up", "game_ready", "pong", "pi_status", "error",
})


async def handle_command(ws, cmd, data, loop):
    """서버로부터 수신한 명령을 executor에서 실행"""
    if cmd in _IGNORE_TYPES:
        return

    try:
        if cmd == "led_on":
            await loop.run_in_executor(None, _led_on, data["pin"])

        elif cmd == "led_off":
            await loop.run_in_executor(None, _led_off, data["pin"])

        elif cmd == "led_blink":
            pin     = data["pin"]
            times   = data.get("times", 3)
            on_sec  = data.get("on_sec", 0.2)
            off_sec = data.get("off_sec", 0.2)
            await loop.run_in_executor(None, _led_blink, pin, times, on_sec, off_sec)

        elif cmd == "led_flash_sequence":
            await loop.run_in_executor(None, _led_flash_sequence, data["sequence"])

        elif cmd == "buzzer_tone":
            freq = data["frequency"]
            dur  = data["duration"]
            await loop.run_in_executor(None, _buzzer_tone, freq, dur)

        elif cmd == "buzzer_correct":
            await loop.run_in_executor(None, _buzzer_correct)

        elif cmd == "buzzer_wrong":
            await loop.run_in_executor(None, _buzzer_wrong)

        elif cmd == "speak":
            text = data.get("text", "")
            await loop.run_in_executor(None, _speak_tts, text)

        elif cmd == "await_button":
            btn_type = data.get("type")

            if btn_type == "game1":
                color = await loop.run_in_executor(None, _wait_game1_button)
                await ws.send(json.dumps({"type": "button_press", "data": {"color": color}}))
                print(f"[Pi] 버튼 입력 ({'초록' if color == 'G' else '빨간'})")

            elif btn_type == "any":
                idx = await loop.run_in_executor(None, _wait_for_any_button, ANSWER_PINS)
                await ws.send(json.dumps({"type": "button_press", "data": {"button_index": idx}}))
                print(f"[Pi] 버튼 입력 (index={idx}, 버튼 {idx + 1}번)")

        else:
            print(f"[Pi] 알 수 없는 명령: {cmd}")

    except Exception as e:
        print(f"[Pi] 명령 처리 오류 ({cmd}): {e}")


# ── 메인 클라이언트 루프 ─────────────────────────────────────────
async def run_client():
    ws_url = f"ws://{SERVER_HOST}:{SERVER_PORT}/ws"
    loop = asyncio.get_event_loop()

    while True:
        try:
            print(f"[Pi] 서버 연결 시도: {ws_url}")
            async with websockets.connect(ws_url, ping_interval=20, ping_timeout=10) as ws:
                await ws.send(json.dumps({"type": "pi_register", "data": {}}))
                print("[Pi] 서버에 등록됨. GPIO 명령 대기 중...")

                async for raw in ws:
                    try:
                        msg = json.loads(raw)
                        cmd   = msg.get("type")
                        cdata = msg.get("data", {})
                        asyncio.create_task(handle_command(ws, cmd, cdata, loop))
                    except Exception as e:
                        print(f"[Pi] 메시지 처리 오류: {e}")

        except (websockets.exceptions.ConnectionClosed,
                ConnectionRefusedError, OSError) as e:
            print(f"[Pi] 연결 오류: {e}")
        except Exception as e:
            print(f"[Pi] 예외: {e}")

        print(f"[Pi] {RECONNECT_DELAY}초 후 재연결...")
        await asyncio.sleep(RECONNECT_DELAY)


# ── 진입점 ───────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 50)
    print("   🍓 라즈베리파이 GPIO 클라이언트")
    print("=" * 50)
    print(f"   서버: ws://{SERVER_HOST}:{SERVER_PORT}/ws")
    print("=" * 50)
    print()

    setup_gpio()
    print("[Pi] GPIO 초기화 완료\n")

    try:
        asyncio.run(run_client())
    except KeyboardInterrupt:
        print("\n[Pi] 종료 중...")
    finally:
        GPIO.cleanup()
        print("[Pi] GPIO 정리 완료")
