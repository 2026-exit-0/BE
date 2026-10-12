# damda BE (백엔드)

FastAPI 기반 시연용 API 서버. AI 모델 추론 + 자가진단 채점 + narrative 생성.

## 디렉토리 구조

```
damda/
├── AI/                   ← 모델 학습/추론 코드
│   └── src/infer.py     ← DamdaInferenceModel 클래스
├── BE/                   ← 본 폴더 (FastAPI)
│   ├── main.py          ← API 엔드포인트
│   ├── questionnaire.py ← 자가진단 15문항 + 채점
│   ├── narrative.py     ← 측정값 → 자연어 평가
│   ├── requirements.txt
│   └── README.md
├── FE/                   ← 프론트엔드 (정적 HTML/CSS/JS)
│   ├── index.html
│   ├── style.css
│   └── script.js
└── HW/                   ← ESP32-CAM 펌웨어
```

## 설치 & 실행

### 1. 의존성 설치

AI/ 의 venv 와 같이 쓰는 경우:
```cmd
cd damda\AI
call .venv\Scripts\activate.bat
cd ..\BE
pip install -r requirements.txt
```

별도 venv 만드는 경우:
```cmd
cd damda\BE
python -m venv .venv
call .venv\Scripts\activate.bat
pip install -r requirements.txt
pip install -r ..\AI\requirements.txt
```

### 2. 서버 실행

```cmd
cd damda\BE
:: 기본 — v3 ckpt 사용
uvicorn main:app --host 0.0.0.0 --port 8000

:: v5 ckpt 사용
set DAMDA_CHECKPOINT=C:\path\to\AI\checkpoints\epoch020.pt
uvicorn main:app --host 0.0.0.0 --port 8000

:: --reload 옵션 — 개발 중 코드 변경 시 자동 재시작
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 3. 프론트 접속

브라우저에서:
- `http://localhost:8000/static/index.html` — 시연 UI
- `http://localhost:8000/docs` — API 문서 (Swagger UI, FastAPI 자동 생성)

## 엔드포인트

| Method | Path | 설명 |
|---|---|---|
| GET | `/` | 기본 인사 + 링크 |
| GET | `/api/health` | 모델 로드 상태 + 메타 |
| GET | `/api/scanner/health` | ESP32-CAM 도달 여부 (3초 timeout) |
| GET | `/api/questionnaire` | 자가진단 질문지 (10개) |
| POST | `/api/questionnaire/score` | 답변 채점 (JSON body: `{answers: {qid: opt_idx, ...}}`) |
| POST | `/api/predict` | 이미지 업로드 추론 (multipart: image + region + 사용자입력 + 센서) |
| POST | `/api/measure` | ESP32 스캐너 자동 측정 + 추론 (~6초, multipart: region + 사용자입력) |

## 환경 변수

| 변수 | 기본값 | 설명 |
|---|---|---|
| `DAMDA_CHECKPOINT` | `AI/checkpoints/epoch045.pt` | 사용할 ckpt 경로 |
| `DAMDA_CONFIG` | `AI/configs/baseline.yaml` | 모델 config 경로 |
| `DAMDA_ESP32_URL` | `http://10.174.185.100` | ESP32-CAM 기본 URL (시연 환경 Wi-Fi) |

## 자가진단 질문지 수정

`questionnaire.py` 의 `QUESTIONS` 리스트 수정. 각 옵션의 `scores` 가중치는 cosmetology 문헌 / 피부과 자가진단표 참고해 조정. 추가/삭제 가능.

## Narrative 평가 기준 수정

`narrative.py` 상단의 `THRESHOLDS_LOWER_BETTER`, `THRESHOLDS_HIGHER_BETTER`, `GRADE_RATINGS` 값 조정. AI-Hub 028 의 실제 분포 (P50/P75/P90) 보고 보정 권장.

## 개발 노트

- 모델 로드는 첫 `/api/health` 또는 `/api/predict` 호출 시 (lazy)
- 첫 호출 시 ~5초 지연 (ResNet-50 + ckpt 로드)
- 이후 추론은 ~50-200ms (CPU) / ~10-30ms (CUDA)
- CORS: `*` 허용 (시연 한정, 운영 시 제한 필요)
- 정적 파일: FastAPI 가 `/static/*` 에서 FE/ 디렉토리 서빙

## 시연 시나리오

1. 사용자가 브라우저에서 `http://<host>:8000/static/index.html` 접속
2. "내 피부 알아요" / "잘 모르겠어요" 선택
3. (모르면) 10개 질문 자가진단 → skin_type, sensitivity, aging_score 자동 산정
4. 측정 부위 선택 + 두 가지 방식 중 선택:
   - **방식 A**: ESP32-CAM 스캐너에 부위 대고 "스캐너로 측정" → POST `/api/measure` (~6초)
   - **방식 B**: 사진 직접 업로드 + 센서값 수동 입력 → POST `/api/predict`
5. 결과 화면 — 종합 점수 + 헤드별 평가 + 케어 tip 표시

## ESP32-CAM 사전 점검

시연 전 필수:

```cmd
:: 1. ESP32 와 BE 서버가 같은 Wi-Fi 인지 확인
ping 10.174.185.100

:: 2. BE 띄운 상태에서
curl http://localhost:8000/api/scanner/health
:: 또는 브라우저 → http://localhost:8000/api/scanner/health
:: → {"status":"ok", "esp32_data":{...}} 면 OK
:: → {"status":"unreachable", "error":"..."} 면 Wi-Fi / IP / 펌웨어 확인 필요
```

ESP32 의 자체 UI `http://10.174.185.100` 가 브라우저에서 바로 떠야 정상 동작 보장.
