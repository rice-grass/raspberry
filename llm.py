"""
LLM (GPT API) 호출 모듈
OpenAI gpt-4o-mini 사용, 실패 시 로컬 fallback 자동 전환
"""
import json
import os

from dotenv import load_dotenv

load_dotenv()

# ── OpenAI 클라이언트 초기화 ────────────────────────────────────
try:
    from openai import OpenAI
    _client = OpenAI(api_key=os.getenv("OPENAI_API_KEY_CHAT"))
    _OPENAI_AVAILABLE = True
except Exception:
    _OPENAI_AVAILABLE = False
    _client = None

MODEL = "gpt-4o-mini"
API_TIMEOUT = 10  # 초


# ── Fallback 퀴즈 문제 5개 ──────────────────────────────────────
FALLBACK_QUIZ_QUESTIONS = [
    {
        "question": "파이썬에서 리스트를 역순으로 정렬하는 메서드는?",
        "options": ["list.sort(reverse=True)", "list.reverse_sort()", "list.flip()", "list.order(-1)"],
        "answer": 1,
        "explanation": "sort(reverse=True)로 역순 정렬하거나, sorted(list, reverse=True)를 사용할 수 있습니다.",
    },
    {
        "question": "라즈베리파이의 GPIO 핀 개수는?",
        "options": ["26개", "40개", "32개", "48개"],
        "answer": 2,
        "explanation": "라즈베리파이 3B+/4/5 기준으로 40핀 GPIO 헤더를 제공합니다.",
    },
    {
        "question": "HTTP 상태코드 404의 의미는?",
        "options": ["서버 오류", "권한 없음", "요청 성공", "페이지 없음"],
        "answer": 4,
        "explanation": "404 Not Found는 요청한 리소스를 서버에서 찾을 수 없다는 의미입니다.",
    },
    {
        "question": "LED의 긴 다리(양극)는 어디에 연결해야 하는가?",
        "options": ["GND", "3.3V 또는 GPIO HIGH", "5V 전용", "어디든 상관없음"],
        "answer": 2,
        "explanation": "LED 양극(긴 다리)은 전원(GPIO HIGH 또는 VCC)에, 음극(짧은 다리)은 GND에 연결합니다.",
    },
    {
        "question": "WebSocket과 HTTP의 차이점으로 올바른 것은?",
        "options": [
            "WebSocket은 단방향 통신만 지원한다",
            "HTTP는 연결을 계속 유지한다",
            "WebSocket은 양방향 실시간 통신을 지원한다",
            "둘 다 동일한 프로토콜이다",
        ],
        "answer": 3,
        "explanation": "WebSocket은 초기 핸드셰이크 후 양방향 지속 연결을 유지하여 실시간 통신이 가능합니다.",
    },
]

_fallback_index = 0  # fallback 문제 순환 인덱스


# ── Game1: 스테이지 힌트 생성 ────────────────────────────────────
def get_stage_hint(stage: int) -> str:
    """
    컬러 메모리 게임 스테이지별 힌트 문장 생성.
    실패 시 기본 문장 반환.
    """
    if not _OPENAI_AVAILABLE:
        return _default_hint(stage)

    try:
        response = _client.chat.completions.create(
            model=MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "당신은 신나는 색깔 메모리 게임의 진행자입니다. "
                        "한 문장으로 짧고 재미있는 격려 메시지를 한국어로 생성하세요."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"스테이지 {stage}를 시작합니다. "
                        f"패턴 길이는 {stage}개입니다. "
                        "짧은 격려 힌트를 한 문장으로 알려주세요."
                    ),
                },
            ],
            max_tokens=80,
            timeout=API_TIMEOUT,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"[LLM] 힌트 생성 실패 (fallback 사용): {e}")
        return _default_hint(stage)


def _default_hint(stage: int) -> str:
    hints = [
        f"Stage {stage}: 색깔 순서를 잘 기억하세요!",
        f"Stage {stage}: 집중! LED 불빛을 따라하세요.",
        f"Stage {stage}: 더 길어졌어요. 끝까지 파이팅!",
        f"Stage {stage}: 당신은 할 수 있어요!",
        f"Stage {stage}: 천천히, 확실하게 눌러보세요.",
    ]
    return hints[(stage - 1) % len(hints)]


# ── Game2: 퀴즈 문제 생성 ────────────────────────────────────────
def get_quiz_question(difficulty: str = "easy") -> dict:
    """
    GPT로 객관식 퀴즈 문제 생성.
    실패 시 FALLBACK_QUIZ_QUESTIONS 순환 반환.

    반환 형식:
    {
        "question": str,
        "options": [str, str, str, str],  # 1~4번
        "answer": int,                     # 1~4
        "explanation": str
    }
    """
    global _fallback_index

    if not _OPENAI_AVAILABLE:
        return _get_fallback_question()

    difficulty_map = {
        "easy": "쉬운",
        "medium": "중간 난이도의",
        "hard": "어려운",
    }
    diff_str = difficulty_map.get(difficulty, "쉬운")

    try:
        response = _client.chat.completions.create(
            model=MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "당신은 퀴즈 출제 전문가입니다. "
                        "요청한 JSON 형식만 반환하고, 다른 텍스트는 절대 포함하지 마세요."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"{diff_str} 객관식 퀴즈 문제를 1개 출제해주세요. "
                        "IT, 과학, 상식 중 하나의 분야로 출제하세요. "
                        "반드시 아래 JSON 형식으로만 응답하세요:\n"
                        '{"question": "문제 내용", '
                        '"options": ["1번 보기", "2번 보기", "3번 보기", "4번 보기"], '
                        '"answer": 1, '
                        '"explanation": "해설 내용"}'
                    ),
                },
            ],
            response_format={"type": "json_object"},
            max_tokens=300,
            timeout=API_TIMEOUT,
        )
        raw = response.choices[0].message.content.strip()
        data = json.loads(raw)

        # 유효성 검증
        assert "question" in data
        assert isinstance(data.get("options"), list) and len(data["options"]) == 4
        assert isinstance(data.get("answer"), int) and 1 <= data["answer"] <= 4
        assert "explanation" in data

        return data

    except Exception as e:
        print(f"[LLM] 문제 생성 실패 (fallback 사용): {e}")
        return _get_fallback_question()


def _get_fallback_question() -> dict:
    global _fallback_index
    q = FALLBACK_QUIZ_QUESTIONS[_fallback_index % len(FALLBACK_QUIZ_QUESTIONS)]
    _fallback_index += 1
    return q


# ── 단독 실행 테스트 ────────────────────────────────────────────
if __name__ == "__main__":
    print("=== LLM 모듈 테스트 ===")
    print("\n[Game1] 스테이지 힌트:")
    for s in range(1, 4):
        print(f"  Stage {s}: {get_stage_hint(s)}")

    print("\n[Game2] 퀴즈 문제 (easy):")
    q = get_quiz_question("easy")
    print(f"  Q: {q['question']}")
    for i, opt in enumerate(q["options"], 1):
        mark = "★" if i == q["answer"] else " "
        print(f"  {mark}{i}. {opt}")
    print(f"  해설: {q['explanation']}")

    print("\n[Game2] fallback 테스트 (5개):")
    for i in range(5):
        fq = _get_fallback_question()
        print(f"  {i+1}. {fq['question'][:40]}...")
