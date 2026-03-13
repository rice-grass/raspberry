# 🍓 라즈베리파이 미니게임 센터

WebSocket 기반 실시간 게임 플랫폼.
서버(PC/WSL2)에서 게임 로직을 실행하고, 라즈베리파이는 GPIO 클라이언트로 동작합니다.

---

## 아키텍처

```
[브라우저 대시보드]
        │  ws://서버IP:8080/ws
        ▼
[서버 PC / WSL2]  ← python3 main.py 119.200.3.240
  ├── HTTP  :8080  →  dashboard.html 서빙
  ├── WS    :8080/ws  →  대시보드 & Pi 공용
  ├── 게임 로직 (game1_morse.py, game2_quiz.py)
  └── OpenAI GPT-4o-mini (퀴즈 생성, 힌트)
        │  ws://서버IP:8080/ws
        ▼
[라즈베리파이 192.168.110.150]  ← python3 pi_client.py 서버IP
  ├── 버튼 입력 → 서버 전송
  └── LED / 부저 / 7세그먼트 명령 수신 후 GPIO 실행
```

---

## GPIO 핀 배치 (BCM 번호)

### 출력 핀

| 부품 | BCM 핀 | 물리 핀 | 설명 |
|------|--------|---------|------|
| 초록 LED | GPIO 17 | 11번 | 정답 피드백 / Game1 패턴 |
| 빨간 LED | GPIO 27 | 13번 | 오답 피드백 / Game1 패턴 |
| 부저 (PWM) | GPIO 26 | 37번 | 효과음 출력 |
| TM1637 CLK | GPIO 23 | 16번 | 7세그먼트 클록 |
| TM1637 DIO | GPIO 24 | 18번 | 7세그먼트 데이터 |

### 입력 핀 (내부 풀업 저항, 누름 = LOW)

| 부품 | BCM 핀 | 물리 핀 | 설명 |
|------|--------|---------|------|
| Game1 초록 버튼 | GPIO 22 | 15번 | 누름 → 초록 선택 |
| Game1 빨간 버튼 | GPIO 23 | 16번 | 누름 → 빨간 선택 |
| Game2 버튼 1 | GPIO 5 | 29번 | 답 선택 1번 |
| Game2 버튼 2 | GPIO 6 | 31번 | 답 선택 2번 |
| Game2 버튼 3 | GPIO 13 | 33번 | 답 선택 3번 |
| Game2 버튼 4 | GPIO 19 | 35번 | 답 선택 4번 |

---

## 회로 연결도

```
라즈베리파이 40핀 GPIO 헤더

3.3V  [1] [2]  5V
      [3] [4]  5V
      [5] [6]  GND ─── TM1637 GND / 부저 GND
      [7] [8]
 GND  [9] [10]
GPIO17[11]─── 330Ω ─── 초록LED(+) ─── LED(-) ─── GND
GPIO27[13]─── 330Ω ─── 빨간LED(+) ─── LED(-) ─── GND
GPIO23[16]─── 버튼 Game1 ──────────────────────────────── GND
GPIO23[16]─── TM1637 CLK
GPIO24[18]─── TM1637 DIO
3.3V [17] ─── TM1637 VCC
      [19] [20] GND
      [21] [22]
      [23] [24]
 GND [25]
GPIO26[37]─── 부저(+) ─── 부저(-) ─── GND (능동 부저)

GPIO5 [29]─── 버튼 1 ─── GND
GPIO6 [31]─── 버튼 2 ─── GND
GPIO13[33]─── 버튼 3 ─── GND
GPIO19[35]─── 버튼 4 ─── GND
```

> 버튼은 한쪽을 GPIO 핀에, 다른 쪽을 GND에 연결합니다.
> LED는 GPIO → 330Ω 저항 → LED 양극(긴 다리) → LED 음극(짧은 다리) → GND 순서입니다.

---

## 소프트웨어 구성

```
Ras/
├── main.py          # 서버 진입점 (PC/WSL2에서 실행)
├── socket_server.py # aiohttp 기반 HTTP+WebSocket 통합 서버 (:8080)
├── gpio_setup.py    # GPIO 소켓 프록시 (서버 측)
├── game1_morse.py   # 컬러 메모리 게임
├── game2_quiz.py    # AI 객관식 퀴즈 게임
├── llm.py           # OpenAI GPT-4o-mini 연동
├── pi_client.py     # 라즈베리파이 GPIO 클라이언트
├── dashboard.html   # 웹 대시보드 (브라우저)
└── .env             # API 키 설정
```

---

## 설치

### 서버 (PC / WSL2)

```bash
pip install aiohttp websockets openai python-dotenv
```

### 라즈베리파이

```bash
pip install RPi.GPIO websockets
```

---

## 실행 방법

### 1. 서버 시작 (PC / WSL2)

```bash
python3 main.py <공인IP>

# 예시
python3 main.py 119.200.3.240
```

### 2. Pi GPIO 클라이언트 시작 (라즈베리파이)

```bash
python3 pi_client.py <서버IP>

# 예시
python3 pi_client.py 119.200.3.240
```

### 3. 브라우저에서 대시보드 접속

```
http://119.200.3.240:8080/dashboard.html
```

> 포트 **8080** 하나만 열려 있으면 HTTP + WebSocket 모두 동작합니다.

---

## 게임 설명

### 🎨 Game 1: 컬러 메모리 게임

- 초록/빨간 LED가 랜덤 순서로 점등
- 플레이어가 버튼으로 같은 순서 재현
  - **짧게 누름** (< 0.4초) → 초록
  - **길게 누름** (≥ 0.4초) → 빨간
- 스테이지마다 패턴 길이 1씩 증가
- **점수** = 스테이지 × 패턴길이 × 10

### 🧠 Game 2: AI 객관식 퀴즈

- GPT-4o-mini가 실시간으로 문제 생성 (IT/과학/상식)
- 버튼 4개(1~4번)로 답 선택
- 연속 3정답 시 난이도 자동 상승 (쉬움 → 보통 → 어려움)
- 총 10문제, 문제당 10점
- **만점** = 100점

---

## 환경 변수 (.env)

```env
OPENAI_API_KEY_CHAT=sk-proj-...
```

---

## 통신 프로토콜

### 대시보드 → 서버

| type | data | 설명 |
|------|------|------|
| `start_game` | `{"game": "1" 또는 "2"}` | 게임 시작 요청 |
| `ping` | `{}` | 연결 확인 |

### 서버 → 대시보드

| type | 설명 |
|------|------|
| `state_sync` | 최초 연결 시 현재 게임 상태 |
| `game_start` | 게임 시작 |
| `game_over` | 게임 종료 + 최종 점수 |
| `score_update` | 점수 변경 |
| `stage_update` | 스테이지/문제 번호 변경 |
| `pattern_show` | Game1 패턴 표시 |
| `question` | Game2 문제 + 보기 |
| `correct` / `wrong` | 정답/오답 피드백 |
| `difficulty_up` | 난이도 상승 |
| `hint` | GPT 힌트 메시지 |
| `pi_status` | Pi GPIO 연결 상태 변경 |

### 서버 ↔ Pi 클라이언트

| type | 방향 | 설명 |
|------|------|------|
| `pi_register` | Pi→서버 | Pi 클라이언트 등록 |
| `await_button` | 서버→Pi | 버튼 입력 대기 요청 |
| `button_press` | Pi→서버 | 버튼 입력 결과 전송 |
| `led_blink` | 서버→Pi | LED 깜빡임 |
| `led_flash_sequence` | 서버→Pi | Game1 패턴 출력 |
| `buzzer_correct` / `buzzer_wrong` | 서버→Pi | 효과음 |
| `display_number` / `display_clear` | 서버→Pi | 7세그먼트 표시 |
