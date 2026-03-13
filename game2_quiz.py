"""
Game 2: AI 객관식 퀴즈 게임

GPT가 생성한 객관식 문제를 버튼 4개로 풀기
연속 정답 3개 시 난이도 자동 상승
10문제 후 게임 종료

하드웨어:
  - 버튼 4개 (GPIO 5, 6, 13, 19): 1~4번 답 선택
  - 초록 LED (GPIO 17): 정답 피드백
  - 빨간 LED (GPIO 27): 오답 피드백
  - 부저 (GPIO 26): 효과음
  - 7세그먼트 TM1637 (GPIO 23/24): 점수 표시
"""
import time

import gpio_setup as g
import socket_server as ss
from llm import get_quiz_question

# ── 게임 상수 ───────────────────────────────────────────────────
TOTAL_QUESTIONS     = 10
POINTS_PER_CORRECT  = 10
STREAK_FOR_LEVELUP  = 3  # 연속 정답 시 난이도 상승

ANSWER_PINS = [g.BTN1, g.BTN2, g.BTN3, g.BTN4]  # GPIO 5, 6, 13, 19

DIFFICULTY_ORDER = ["easy", "medium", "hard"]
DIFFICULTY_LABEL = {"easy": "쉬움", "medium": "보통", "hard": "어려움"}


def _next_difficulty(current: str) -> str:
    idx = DIFFICULTY_ORDER.index(current)
    if idx < len(DIFFICULTY_ORDER) - 1:
        return DIFFICULTY_ORDER[idx + 1]
    return current


def _display_question(q: dict, q_num: int, total: int, difficulty: str):
    """터미널에 문제 + 보기 출력"""
    diff_label = DIFFICULTY_LABEL.get(difficulty, difficulty)
    print(f"\n── 문제 {q_num}/{total}  [{diff_label}] ──────────────────────────")
    print(f"Q. {q['question']}")
    print()
    for i, opt in enumerate(q["options"], 1):
        print(f"  [{i}] {opt}")
    print()
    print("버튼 1~4로 답을 선택하세요...")


def run_game2():
    """AI 퀴즈 게임 메인 루프"""
    print("\n" + "="*50)
    print("   🧠 AI 객관식 퀴즈 게임 시작!")
    print("="*50)
    print(f"총 {TOTAL_QUESTIONS}문제, 문제당 {POINTS_PER_CORRECT}점")
    print(f"연속 정답 {STREAK_FOR_LEVELUP}개마다 난이도 상승\n")

    ss.broadcast("game_start", {"game": "AI 퀴즈 게임"})

    # LED 초기화 (이전 게임에서 켜진 상태 초기화)
    g.led_off(g.LED_RED)
    g.led_off(g.LED_GREEN)

    score = 0
    streak = 0
    difficulty = "easy"

    try:
        for q_num in range(1, TOTAL_QUESTIONS + 1):
            # 스테이지 업데이트
            ss.broadcast("stage_update", {
                "question_num": q_num,
                "difficulty": difficulty,
                "difficulty_label": DIFFICULTY_LABEL[difficulty],
            })

            # 문제 가져오기 (GPT or fallback)
            print(f"\n[문제 {q_num}] 생성 중...", end=" ", flush=True)
            q = get_quiz_question(difficulty)
            print("완료")

            # 문제 출력
            _display_question(q, q_num, TOTAL_QUESTIONS, difficulty)

            # 웹 대시보드에 문제 전송
            ss.broadcast("question", {
                "question_num": q_num,
                "question": q["question"],
                "options": q["options"],
                "difficulty": difficulty,
            })

            # 버튼 입력 대기
            idx = g.wait_for_any_button(ANSWER_PINS)

            # 타임아웃 → 게임 오버
            if idx == -1:
                print(f"\n⏰ 시간 초과! 게임 오버! 최종 점수: {score}점")
                g.led_blink(g.LED_RED, times=3, on_sec=0.1, off_sec=0.1)
                g.speak_tts('시간 초과입니다')
                ss.broadcast("wrong", {"timeout": True})
                ss.broadcast("game_over", {
                    "score": score,
                    "total_questions": TOTAL_QUESTIONS,
                    "max_score": TOTAL_QUESTIONS * POINTS_PER_CORRECT,
                    "reason": "timeout",
                })
                return score

            answer_given = idx + 1  # 1-based
            print(f"\n선택: {answer_given}번 → {q['options'][idx]}")
            ss.broadcast("player_input", {"answer": answer_given})

            # 정답 판정
            if answer_given == q["answer"]:
                score += POINTS_PER_CORRECT
                streak += 1

                print(f"✅ 정답! +{POINTS_PER_CORRECT}점 → 총 {score}점")
                print(f"   💡 {q['explanation']}")

                g.led_blink(g.LED_GREEN, times=2, on_sec=0.2, off_sec=0.1)
                g.buzzer_correct()

                ss.broadcast("correct", {
                    "answer": q["answer"],
                    "explanation": q["explanation"],
                    "score": score,
                    "streak": streak,
                })
                ss.broadcast("score_update", {"score": score})

                # 연속 정답으로 난이도 상승
                if streak >= STREAK_FOR_LEVELUP:
                    prev = difficulty
                    difficulty = _next_difficulty(difficulty)
                    streak = 0
                    if difficulty != prev:
                        print(f"\n⬆️  난이도 상승: {DIFFICULTY_LABEL[prev]} → {DIFFICULTY_LABEL[difficulty]}")
                        ss.broadcast("difficulty_up", {
                            "from": prev,
                            "to": difficulty,
                            "from_label": DIFFICULTY_LABEL[prev],
                            "to_label": DIFFICULTY_LABEL[difficulty],
                        })

            else:
                streak = 0
                correct_opt = q["options"][q["answer"] - 1]
                print(f"❌ 오답! 정답은 {q['answer']}번: {correct_opt}")

                g.led_blink(g.LED_RED, times=2, on_sec=0.2, off_sec=0.1)
                g.speak_tts('틀렸습니다')

                ss.broadcast("wrong", {
                    "given": answer_given,
                    "correct_answer": q["answer"],
                    "correct_option": correct_opt,
                })

            time.sleep(1.0)  # 다음 문제 전 잠시 대기

    except KeyboardInterrupt:
        print(f"\n\n게임 중단. 현재 점수: {score}점")

    # 최종 결과
    print("\n" + "="*50)
    print(f"   🏁 퀴즈 완료!")
    print(f"   최종 점수: {score} / {TOTAL_QUESTIONS * POINTS_PER_CORRECT}점")
    print("="*50)

    ss.broadcast("game_over", {
        "score": score,
        "total_questions": TOTAL_QUESTIONS,
        "max_score": TOTAL_QUESTIONS * POINTS_PER_CORRECT,
    })

    return score


# ── 단독 실행 테스트 ────────────────────────────────────────────
if __name__ == "__main__":
    g.setup_gpio()
    import atexit
    atexit.register(g.cleanup_gpio)

    ss.start_server()
    ss.start_http_server()

    try:
        run_game2()
    except KeyboardInterrupt:
        pass
    finally:
        g.cleanup_gpio()
