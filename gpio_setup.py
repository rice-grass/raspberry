"""
GPIO 핀 설정 및 공통 유틸리티 모듈 (서버 측 - 소켓 기반)

실제 GPIO 제어는 라즈베리파이 클라이언트(pi_client.py)가 담당.
이 모듈은 게임 로직에서 GPIO 호출 시:
  - Pi에 명령을 소켓으로 전송
  - 버튼 입력은 Pi → 소켓 → 이 모듈 로 수신
모든 핀 번호는 BCM 기준 (참조용)
"""
import queue
import time

import socket_server as ss

# ── 핀 상수 정의 (BCM 기준, 참조용) ────────────────────────────
LED_GREEN   = 17   # 초록 LED
LED_RED     = 27   # 빨간 LED

BTN_GREEN   = 22   # Game1 초록 버튼
BTN_RED     = 23   # Game1 빨간 버튼

BTN1        = 5    # Game2 답 버튼 1
BTN2        = 6    # Game2 답 버튼 2
BTN3        = 13   # Game2 답 버튼 3
BTN4        = 19   # Game2 답 버튼 4

BUZZER      = 26   # 부저 (PWM)

TM_CLK      = 23   # TM1637 7세그먼트 CLK
TM_DIO      = 24   # TM1637 7세그먼트 DIO

# 짧은/긴 누름 구분 기준 (초)
PRESS_THRESHOLD = 0.4


# ── GPIO 초기화 / 정리 ──────────────────────────────────────────
def setup_gpio():
    print("[GPIO] 소켓 기반 GPIO 모드 활성화")
    print("[GPIO] 라즈베리파이 클라이언트(pi_client.py)를 Pi에서 실행하세요.")


def cleanup_gpio():
    pass


# ── LED 유틸리티 ─────────────────────────────────────────────────
def led_on(pin):
    ss.send_to_pi("led_on", {"pin": pin})


def led_off(pin):
    ss.send_to_pi("led_off", {"pin": pin})


def led_blink(pin, times=3, on_sec=0.2, off_sec=0.2):
    """Pi에 LED 깜빡임 명령 전송 후 완료까지 대기"""
    ss.send_to_pi("led_blink", {
        "pin": pin, "times": times, "on_sec": on_sec, "off_sec": off_sec
    })
    # Pi의 GPIO 실행 시간 동기화
    time.sleep(times * (on_sec + off_sec) + 0.05)


def led_flash_sequence(sequence):
    """
    Game1 패턴 출력: Pi에 명령 전송 + 대시보드 LED 애니메이션 동기 broadcast.
    sequence: list of 'G' or 'R'
    각 색상 0.5초 점등, 0.3초 소등, 마지막 1.0초 대기
    """
    ss.send_to_pi("led_flash_sequence", {"sequence": sequence})
    ss.broadcast("game_phase", {"phase": "showing_pattern", "label": "📺 패턴 표시 중..."})
    for i, color in enumerate(sequence):
        ss.broadcast("led_step", {"color": color, "index": i, "on": True})
        time.sleep(0.5)
        ss.broadcast("led_step", {"color": color, "index": i, "on": False})
        time.sleep(0.3)
    time.sleep(1.0)
    ss.broadcast("game_phase", {"phase": "waiting_input", "label": "⌨️ 버튼을 눌러 입력하세요!"})


# ── 버튼 유틸리티 ────────────────────────────────────────────────
COUNTDOWN_SEC = 9   # 버튼 입력 제한 시간


def read_game1_button():
    """
    Game1 두 버튼 입력 수신 (9초 카운트다운 포함).
    반환: 'G' 또는 'R', 타임아웃 시 None
    """
    ss.clear_button_queue()
    ss.send_to_pi("await_button", {"type": "game1", "timeout": COUNTDOWN_SEC})
    try:
        event = ss.get_button_event(timeout=COUNTDOWN_SEC + 3)
        if event.get("timeout"):
            print("[GPIO] 시간 초과")
            return None
        return event.get("color", "G")
    except queue.Empty:
        print("[GPIO] 버튼 큐 타임아웃")
        return None


def wait_for_any_button(pins):
    """
    Pi 버튼 중 가장 먼저 눌린 버튼 인덱스 수신 (Game2용, 9초 카운트다운 포함).
    반환: 0-based 인덱스, 타임아웃 시 -1
    """
    ss.clear_button_queue()
    ss.send_to_pi("await_button", {"type": "any", "pins": list(pins), "timeout": COUNTDOWN_SEC})
    try:
        event = ss.get_button_event(timeout=COUNTDOWN_SEC + 3)
        if event.get("timeout"):
            print("[GPIO] 시간 초과")
            return -1
        return event.get("button_index", 0)
    except queue.Empty:
        print("[GPIO] 버튼 큐 타임아웃")
        return -1


# ── 부저 유틸리티 ────────────────────────────────────────────────
def buzzer_tone(frequency_hz, duration_sec):
    ss.send_to_pi("buzzer_tone", {"frequency": frequency_hz, "duration": duration_sec})
    time.sleep(duration_sec)


def buzzer_correct():
    """정답 효과음: 1000Hz→1500Hz"""
    ss.send_to_pi("buzzer_correct", {})
    time.sleep(0.4)


def buzzer_wrong():
    """오답 효과음: 300Hz"""
    ss.send_to_pi("buzzer_wrong", {})
    time.sleep(0.5)


# ── TTS 유틸리티 ─────────────────────────────────────────────────
def speak_tts(text):
    """Pi 스피커로 TTS 재생"""
    ss.send_to_pi("speak", {"text": text})


# ── TM1637 7세그먼트 드라이버 (소켓 기반 프록시) ────────────────
class TM1637Display:
    """TM1637 디스플레이 프록시 - 실제 제어는 Pi 클라이언트가 수행"""

    def __init__(self, clk=TM_CLK, dio=TM_DIO):
        pass  # 핀 번호 불필요 (Pi 클라이언트가 관리)

    def show_number(self, num):
        ss.send_to_pi("display_number", {"number": int(num)})

    def clear(self):
        ss.send_to_pi("display_clear", {})
