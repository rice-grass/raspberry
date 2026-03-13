"""
Game 1: 컬러 메모리 게임

초록/빨간 LED가 랜덤 순서로 점등 → 플레이어가 동일 순서 재현
버튼 1개 (GPIO 22):
  - 짧게 누름 (< 0.4s) → 초록 선택
  - 길게 누름 (≥ 0.4s) → 빨간 선택

점수 = 스테이지 × 패턴길이 × 10
"""
import random
import time

import gpio_setup as g
import socket_server as ss
from llm import get_stage_hint

# ── 게임 상수 ───────────────────────────────────────────────────
COLORS = ['G', 'R']
COLOR_LABEL = {'G': '초록', 'R': '빨간'}

CORRECT_FLASH_TIMES = 2     # 정답 시 초록 LED 깜빡임 횟수
WRONG_FLASH_TIMES   = 3     # 오답 시 빨간 LED 깜빡임 횟수


def _generate_pattern(length: int) -> list:
    """랜덤 색깔 패턴 생성"""
    return [random.choice(COLORS) for _ in range(length)]


def _collect_player_input(length: int) -> list:
    """
    플레이어에게 length번의 버튼 입력을 받아 색상 리스트로 반환.
    짧게(<0.4s) → 'G', 길게(≥0.4s) → 'R'
    """
    player_input = []
    for i in range(length):
        print(f"  입력 {i+1}/{length}: 초록 또는 빨간 버튼을 누르세요...", end=" ", flush=True)
        color = g.read_game1_button()
        label = COLOR_LABEL[color]
        print(f"→ {label}")

        # 입력 즉시 시각 피드백
        pin = g.LED_GREEN if color == 'G' else g.LED_RED
        g.led_blink(pin, times=1, on_sec=0.2, off_sec=0.0)

        player_input.append(color)
        ss.broadcast("player_input", {"color": color, "label": label, "index": i})

    return player_input


def run_game1():
    """컬러 메모리 게임 메인 루프"""
    print("\n" + "="*50)
    print("   🎨 컬러 메모리 게임 시작!")
    print("="*50)
    print("LED 패턴을 보고 같은 순서로 버튼을 누르세요.")
    print("초록 버튼 = 초록  |  빨간 버튼 = 빨간\n")

    ss.broadcast("game_start", {"game": "컬러 메모리 게임"})

    stage = 1
    score = 0

    try:
        while True:
            print(f"\n── Stage {stage} ─────────────────────────────────")
            ss.broadcast("stage_update", {"stage": stage})

            # GPT 힌트 메시지
            hint = get_stage_hint(stage)
            print(f"💬 {hint}")
            ss.broadcast("hint", {"message": hint, "stage": stage})
            time.sleep(0.5)

            # 패턴 생성
            pattern = _generate_pattern(stage)
            pattern_labels = [COLOR_LABEL[c] for c in pattern]
            print(f"\n패턴 표시 중... ({stage}개)")
            ss.broadcast("pattern_show", {"pattern": pattern, "labels": pattern_labels, "stage": stage})

            # LED로 패턴 출력
            g.led_flash_sequence(pattern)

            # 플레이어 입력 수집
            print("\n입력하세요:")
            player_input = _collect_player_input(stage)

            # 정답 판정
            if player_input == pattern:
                # 정답
                score += stage * len(pattern) * 10
                print(f"\n✅ 정답! +{stage * len(pattern) * 10}점 → 총 {score}점")
                g.led_blink(g.LED_GREEN, CORRECT_FLASH_TIMES, 0.15, 0.15)

                ss.broadcast("correct", {"stage": stage})
                ss.broadcast("score_update", {"score": score})

                stage += 1
                time.sleep(0.5)

            else:
                # 오답
                print(f"\n❌ 오답!")
                print(f"   정답 패턴: {' → '.join(pattern_labels)}")
                print(f"   내 입력:   {' → '.join(COLOR_LABEL[c] for c in player_input)}")
                print(f"\n🏁 게임 오버! 최종 점수: {score}점 (스테이지 {stage}까지 클리어)")

                g.led_blink(g.LED_RED, WRONG_FLASH_TIMES, 0.1, 0.1)
                g.buzzer_wrong()

                ss.broadcast("wrong", {
                    "expected": pattern,
                    "got": player_input,
                    "expected_labels": pattern_labels,
                    "got_labels": [COLOR_LABEL[c] for c in player_input],
                })
                ss.broadcast("game_over", {
                    "score": score,
                    "stages_completed": stage - 1,
                })
                break

    except KeyboardInterrupt:
        print(f"\n\n게임 중단. 현재 점수: {score}점")
        ss.broadcast("game_over", {"score": score, "stages_completed": stage - 1})

    print(f"\n최종 점수: {score}점")
    return score


# ── 단독 실행 테스트 ────────────────────────────────────────────
if __name__ == "__main__":
    g.setup_gpio()
    import atexit
    atexit.register(g.cleanup_gpio)

    ss.start_server()
    ss.start_http_server()

    try:
        run_game1()
    except KeyboardInterrupt:
        pass
    finally:
        g.cleanup_gpio()
