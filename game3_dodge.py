"""
Game 3: 좌우 피하기 게임

7개 레인 중 위험 레인 표시 → 피해서 생존
초록 버튼: 왼쪽 이동
빨간 버튼: 오른쪽 이동
(시간 내 미입력 시 제자리 유지)

점수 = 성공 횟수 × 10
"""
import random
import time

import gpio_setup as g
import socket_server as ss

LANES = 7
START_POS = 4
INITIAL_TIME = 3.0
MIN_TIME = 0.8
POINTS_PER_DODGE = 10


def run_game3():
    print("\n" + "="*50)
    print("   ↔️  좌우 피하기 게임 시작!")
    print("="*50)
    print("위험 레인을 피하세요!")
    print("초록 버튼=왼쪽 이동  |  빨간 버튼=오른쪽 이동\n")

    ss.broadcast("game_start", {"game": "좌우 피하기 게임"})

    player_pos = START_POS
    score = 0
    stage = 1

    try:
        while True:
            dodge_time = max(MIN_TIME, INITIAL_TIME - (stage - 1) * 0.1)
            danger = random.choice([i for i in range(1, LANES + 1) if i != player_pos])

            print(f"\n── Stage {stage} | Score: {score} ──")
            print(f"위험 레인: {danger}  |  위치: {player_pos}  |  제한: {dodge_time:.1f}초")

            ss.broadcast("stage_update", {"stage": stage})
            ss.broadcast("dodge_state", {
                "player": player_pos,
                "danger": danger,
                "lanes": LANES,
                "stage": stage,
                "score": score,
                "time_limit": round(dodge_time, 1),
            })

            # 버튼 입력 (타임아웃 포함)
            color = g.read_game1_button_timed(dodge_time)

            if color == 'G':
                player_pos = max(1, player_pos - 1)
                print(f"← 왼쪽 이동 → 위치: {player_pos}")
            elif color == 'R':
                player_pos = min(LANES, player_pos + 1)
                print(f"→ 오른쪽 이동 → 위치: {player_pos}")
            else:
                print("⏸ 이동 없음 (타임아웃)")

            ss.broadcast("player_input", {"color": color, "player": player_pos})

            # 충돌 판정
            if player_pos == danger:
                print(f"\n💥 충돌! 게임 오버! 최종 점수: {score}점")
                g.led_blink(g.LED_RED, times=3, on_sec=0.15, off_sec=0.1)
                g.speak_tts('게임 오버')
                ss.broadcast("wrong", {"player": player_pos, "danger": danger})
                ss.broadcast("game_over", {"score": score, "stages_completed": stage - 1})
                break

            # 성공
            score += POINTS_PER_DODGE
            print(f"✅ 성공! +{POINTS_PER_DODGE}점 → 총 {score}점")
            g.led_blink(g.LED_GREEN, times=1, on_sec=0.2, off_sec=0.0)
            ss.broadcast("correct", {"score": score, "stage": stage})
            ss.broadcast("score_update", {"score": score})

            stage += 1
            time.sleep(0.3)

    except KeyboardInterrupt:
        print(f"\n\n게임 중단. 현재 점수: {score}점")
        ss.broadcast("game_over", {"score": score, "stages_completed": stage - 1})

    print(f"\n최종 점수: {score}점")
    return score


if __name__ == "__main__":
    g.setup_gpio()
    import atexit
    atexit.register(g.cleanup_gpio)

    ss.start_server()
    ss.start_http_server()

    try:
        run_game3()
    except KeyboardInterrupt:
        pass
    finally:
        g.cleanup_gpio()
