"""
Game 3: 바운스볼 게임

Breakout 스타일 공 튕기기 게임
초록 버튼: 패들 왼쪽 이동
빨간 버튼: 패들 오른쪽 이동
(버튼 홀드 지원)

점수: 벽돌 파괴 × 10점
목숨: 3개
"""
import math
import time

import gpio_setup as g
import socket_server as ss

COLS = 11
ROWS = 15
PADDLE_W = 3
PADDLE_ROW = ROWS - 1   # 14번 행
BRICK_ROWS = 3           # 상단 0~2행: 벽돌
TICK = 0.08              # 80ms per frame (~12.5fps)

BRICK_COLORS = ['#f44336', '#ff9800', '#ffeb3b']  # row 0,1,2


def _make_bricks():
    return [[True] * COLS for _ in range(BRICK_ROWS)]


def run_game3():
    print("\n" + "="*50)
    print("   🎾 바운스볼 게임 시작!")
    print("="*50)
    print("초록 버튼=왼쪽  |  빨간 버튼=오른쪽\n")

    # 스트리밍 버튼 시작
    g.start_button_stream()
    time.sleep(0.2)

    paddle_x = COLS // 2 - PADDLE_W // 2
    lives = 3
    score = 0
    stage = 1

    bricks = _make_bricks()
    bricks_left = COLS * BRICK_ROWS

    # 공 초기 상태
    bx = COLS / 2.0
    by = float(ROWS - 3)
    dx = 0.45
    dy = -0.65

    ss.broadcast("game_start", {"game": "바운스볼 게임"})
    ss.broadcast("stage_update", {"stage": stage})

    try:
        while lives > 0:
            t0 = time.time()

            # ── 버튼 입력 처리 (복수 이벤트 처리) ──────────────────
            while True:
                event = g.get_button_nowait()
                if not event:
                    break
                color = event.get("color")
                if color == 'G':
                    paddle_x = max(0, paddle_x - 1)
                elif color == 'R':
                    paddle_x = min(COLS - PADDLE_W, paddle_x + 1)

            # ── 공 이동 ─────────────────────────────────────────────
            bx += dx
            by += dy

            # 좌우 벽 반사
            if bx < 0:
                bx = -bx
                dx = abs(dx)
            elif bx > COLS - 1:
                bx = 2.0 * (COLS - 1) - bx
                dx = -abs(dx)

            # 천장 반사
            if by < 0:
                by = -by
                dy = abs(dy)

            # 벽돌 충돌
            bi = int(by)
            bj = min(COLS - 1, max(0, int(bx + 0.5)))
            if 0 <= bi < BRICK_ROWS and bricks[bi][bj]:
                bricks[bi][bj] = False
                bricks_left -= 1
                score += 10
                dy = -dy
                g.led_blink(g.LED_GREEN, times=1, on_sec=0.05, off_sec=0.0)
                ss.broadcast("score_update", {"score": score})

            # 패들 충돌
            if by >= PADDLE_ROW and dy > 0:
                bj = min(COLS - 1, max(0, int(bx + 0.5)))
                if paddle_x <= bj < paddle_x + PADDLE_W:
                    # 패들 히트: 반사
                    dy = -abs(dy)
                    by = PADDLE_ROW - 0.1
                    # 히트 위치에 따라 각도 조정
                    rel = (bx - (paddle_x + PADDLE_W / 2.0)) / (PADDLE_W / 2.0)
                    spd = math.sqrt(dx * dx + dy * dy)
                    dx = rel * spd * 0.85
                    if abs(dx) < 0.15:
                        dx = 0.15 * (1 if dx >= 0 else -1)
                    # 속도 정규화
                    ns = math.sqrt(dx * dx + dy * dy)
                    if ns > 0:
                        dx = dx / ns * spd
                        dy = -abs(dy / ns * spd)

            # 바닥 탈출 → 목숨 감소
            if by > PADDLE_ROW:
                lives -= 1
                print(f"💔 목숨 감소! 남은 목숨: {lives}")
                if lives > 0:
                    # 공 리셋
                    bx = COLS / 2.0
                    by = float(ROWS - 3)
                    dx = 0.45
                    dy = -0.65
                    paddle_x = COLS // 2 - PADDLE_W // 2
                    g.led_blink(g.LED_RED, times=1, on_sec=0.4, off_sec=0.0)
                    time.sleep(0.8)

            # 벽돌 전부 제거 → 스테이지 클리어
            if bricks_left == 0:
                stage += 1
                bricks = _make_bricks()
                bricks_left = COLS * BRICK_ROWS
                # 속도 증가
                spd = math.sqrt(dx * dx + dy * dy) * 1.08
                dx = (dx / abs(dx) if dx != 0 else 0.45) * spd * 0.55
                dy = -abs(dy / abs(dy) if dy != 0 else -0.65) * spd * 0.83
                g.led_blink(g.LED_GREEN, times=2, on_sec=0.15, off_sec=0.1)
                print(f"🎉 Stage {stage} 시작! 속도 증가")
                ss.broadcast("stage_update", {"stage": stage})

            # ── 상태 브로드캐스트 ───────────────────────────────────
            ss.broadcast("bounce_state", {
                "ball":   [round(bx, 1), round(by, 1)],
                "paddle": [paddle_x, PADDLE_W],
                "bricks": bricks,
                "cols":   COLS,
                "rows":   ROWS,
                "score":  score,
                "lives":  lives,
                "stage":  stage,
            })

            # 프레임 타이밍
            elapsed = time.time() - t0
            wait = TICK - elapsed
            if wait > 0:
                time.sleep(wait)

    except KeyboardInterrupt:
        print(f"\n\n게임 중단. 현재 점수: {score}점")

    finally:
        g.stop_button_stream()

    # 게임 오버
    print(f"\n💥 게임 오버! 최종 점수: {score}점 (Stage {stage})")
    g.led_blink(g.LED_RED, times=3, on_sec=0.15, off_sec=0.1)
    g.speak_tts('게임 오버')
    ss.broadcast("game_over", {
        "score": score,
        "stages_completed": stage - 1,
    })
    return score


if __name__ == "__main__":
    g.setup_gpio()
    import atexit
    atexit.register(g.cleanup_gpio)

    ss.start_server()

    try:
        run_game3()
    except KeyboardInterrupt:
        pass
    finally:
        g.cleanup_gpio()
