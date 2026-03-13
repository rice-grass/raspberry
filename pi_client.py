"""
라즈베리파이 GPIO 클라이언트

서버(WSL2/PC)에 WebSocket으로 연결하여:
  - 물리 버튼 입력 → 서버로 전송
  - LED / 부저 / 7세그먼트 명령 ← 서버에서 수신 후 GPIO 실행

라즈베리파이에서 실행:
  python3 pi_client.py <서버IP>

  예) python3 pi_client.py 192.168.110.100
"""
import asyncio
import json
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
TM_CLK      = 23
TM_DIO      = 24

ANSWER_PINS = [BTN1, BTN2, BTN3, BTN4]
ALL_OUTPUT_PINS = (LED_GREEN, LED_RED, BUZZER, TM_CLK, TM_DIO)
ALL_INPUT_PINS  = (BTN_GREEN, BTN_RED, BTN1, BTN2, BTN3, BTN4)

# ── TM1637 세그먼트 인코딩 ───────────────────────────────────────
_DIGITS = [0x3F, 0x06, 0x5B, 0x4F, 0x66, 0x6D, 0x7D, 0x07, 0x7F, 0x6F, 0x00]
_BIT_DELAY = 0.0001


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
                time.sleep(0.05)  # 디바운스
                if GPIO.input(pin) == GPIO.LOW:
                    while GPIO.input(pin) == GPIO.LOW:
                        time.sleep(0.01)
                    time.sleep(0.05)
                    return color
        time.sleep(0.01)


def _wait_for_any_button(pins):
    """여러 버튼 중 가장 먼저 눌린 버튼 인덱스 반환 (Game2용, 0-based)"""
    while True:
        for idx, pin in enumerate(pins):
            if GPIO.input(pin) == GPIO.LOW:
                time.sleep(0.05)  # 디바운스
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


# ── TM1637 7세그먼트 (bit-bang) ──────────────────────────────────
def _tm_delay():
    time.sleep(_BIT_DELAY)


def _tm_start():
    GPIO.output(TM_DIO, GPIO.HIGH)
    GPIO.output(TM_CLK, GPIO.HIGH)
    _tm_delay()
    GPIO.output(TM_DIO, GPIO.LOW)
    _tm_delay()
    GPIO.output(TM_CLK, GPIO.LOW)
    _tm_delay()


def _tm_stop():
    GPIO.output(TM_CLK, GPIO.LOW)
    _tm_delay()
    GPIO.output(TM_DIO, GPIO.LOW)
    _tm_delay()
    GPIO.output(TM_CLK, GPIO.HIGH)
    _tm_delay()
    GPIO.output(TM_DIO, GPIO.HIGH)
    _tm_delay()


def _tm_write_byte(data):
    for _ in range(8):
        GPIO.output(TM_CLK, GPIO.LOW)
        _tm_delay()
        GPIO.output(TM_DIO, GPIO.HIGH if (data & 0x01) else GPIO.LOW)
        data >>= 1
        _tm_delay()
        GPIO.output(TM_CLK, GPIO.HIGH)
        _tm_delay()
    # ACK
    GPIO.output(TM_CLK, GPIO.LOW)
    _tm_delay()
    GPIO.setup(TM_DIO, GPIO.IN)
    _tm_delay()
    GPIO.output(TM_CLK, GPIO.HIGH)
    _tm_delay()
    GPIO.output(TM_CLK, GPIO.LOW)
    _tm_delay()
    GPIO.setup(TM_DIO, GPIO.OUT)


def _display_number(num):
    try:
        num = max(0, min(9999, int(num)))
        digits = [(num // 1000) % 10, (num // 100) % 10, (num // 10) % 10, num % 10]
        segs = []
        leading = True
        for i, d in enumerate(digits):
            if leading and d == 0 and i < 3:
                segs.append(0x00)
            else:
                leading = False
                segs.append(_DIGITS[d])
        _tm_start(); _tm_write_byte(0x40); _tm_stop()
        _tm_start(); _tm_write_byte(0xC0)
        for seg in segs:
            _tm_write_byte(seg)
        _tm_stop()
        _tm_start(); _tm_write_byte(0x88 | 7); _tm_stop()
    except Exception:
        pass


def _display_clear():
    try:
        _tm_start(); _tm_write_byte(0x40); _tm_stop()
        _tm_start(); _tm_write_byte(0xC0)
        for _ in range(4):
            _tm_write_byte(0x00)
        _tm_stop()
        _tm_start(); _tm_write_byte(0x80); _tm_stop()
    except Exception:
        pass


# ── 서버 명령 핸들러 ─────────────────────────────────────────────
# 서버에서 오는 게임 상태 메시지 (대시보드용) - Pi가 수신해도 무시
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

        elif cmd == "display_number":
            await loop.run_in_executor(None, _display_number, data["number"])

        elif cmd == "display_clear":
            await loop.run_in_executor(None, _display_clear)

        elif cmd == "await_button":
            btn_type = data.get("type")
            if btn_type == "game1":
                color = await loop.run_in_executor(
                    None, _wait_game1_button
                )
                await ws.send(json.dumps({
                    "type": "button_press",
                    "data": {"color": color}
                }))
                print(f"[Pi] 버튼 입력 ({'초록' if color == 'G' else '빨간'})")

            elif btn_type == "any":
                idx = await loop.run_in_executor(None, _wait_for_any_button, ANSWER_PINS)
                await ws.send(json.dumps({
                    "type": "button_press",
                    "data": {"button_index": idx}
                }))
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
                # Pi 클라이언트로 등록
                await ws.send(json.dumps({"type": "pi_register", "data": {}}))
                print("[Pi] 서버에 등록됨. GPIO 명령 대기 중...")

                async for raw in ws:
                    try:
                        msg = json.loads(raw)
                        cmd  = msg.get("type")
                        cdata = msg.get("data", {})
                        # 각 명령을 비동기 태스크로 처리 (LED는 논블로킹, 버튼은 응답 필요)
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
