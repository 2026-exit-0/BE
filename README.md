# 담다 BE (백엔드)

담다 서비스의 FastAPI 백엔드. 회원가입/로그인, 피부 설문, 스캔 세션(웹 업로드 · HW 기기 연동), 분석 결과/히스토리/리포트/케어가이드 조회, 화장품 추천, 날씨 연동 API를 제공한다.

> 이 저장소는 `2026-exit-0/BE` 자체가 git 루트다. AI 추론 서버·HW(ESP32-CAM) 스캐너·HW 릴레이 서버·프론트엔드는 전부 별도로 떠 있는 서비스이며, 이 BE는 환경변수로 지정한 주소로 그쪽에 HTTP 호출만 한다 (코드 안에 포함돼 있지 않음). 자세한 구성은 [저장소 밖 구성](#저장소-밖-구성) 참고.

## 폴더 구조

```
BE/
├── app/                   ← 실제 서비스 코드 (지금 이 문서가 다루는 대상)
│   ├── main.py            ← 앱 생성 + CORS + 라우터 등록
│   ├── core/              ← config(.env 로드) / database / deps(인증) / security(JWT) / errors
│   ├── models/             ← SQLAlchemy 모델
│   ├── schemas/            ← Pydantic 스키마
│   ├── routers/            ← API 엔드포인트
│   ├── services/           ← 외부 연동(AI 추론, 스캐너, HW 릴레이, 추천 계산, OAuth, 날씨)
│   └── crud/               ← 공용 DB 조회 로직
├── alembic/                ← DB 마이그레이션
├── scripts/                ← 더미 유저 시드, 제품 데이터 시드/가공 스크립트
├── data/                   ← 제품 데이터(JSON)
├── docs/
│   └── LEGACY_README.md   ← 구버전(prototype) README — 아래 "레거시 파일" 참고
├── Dockerfile, docker-compose.yml, requirements-web.txt
├── main.py, questionnaire.py, narrative.py, requirements.txt  ← 레거시 (아래 참고)
└── README.md / SETUP.md
```

## 설치 / 실행 (로컬 개발)

```bash
python -m venv .venv && source .venv/Scripts/activate   # mac/linux: source .venv/bin/activate
pip install -r requirements.txt       # 로컬 개발용(AI 스크립트 패키지 포함, 더 무거움)
cp .env.example .env                  # 값 채우기 (.env 는 git에 안 올라감)

docker compose up -d db               # MySQL만 띄우기 (개발 중 --reload 쓸 때)
alembic upgrade head                  # 마이그레이션 적용

uvicorn app.main:app --reload
# http://localhost:8000/docs  ← Swagger UI
```

세부 단계(더미 유저 시드 등)는 [SETUP.md](SETUP.md) 참고. 배포(컨테이너로 전체 기동)는 [배포](#배포) 섹션 참고.

## 환경 변수

`.env.example`에 정의된 변수 전체 (값은 전부 placeholder):

| 변수 | 설명 |
|---|---|
| `DATABASE_URL` | MySQL 연결 문자열 (`mysql+pymysql://...`) |
| `DEV_USER_ID` | 로그인 미연동 상태에서 토큰 없이 요청 시 쓰이는 개발용 더미 유저 ID |
| `JWT_SECRET` | JWT 서명 키 |
| `JWT_EXPIRE_DAYS` | JWT 만료일(일 단위) |
| `WEAHTER_API_KEY` | 날씨 외부 API 키 (원문 그대로 — 오타로 보이나 `.env.example` 표기를 그대로 옮김) |
| `KAKAO_CLIENT_ID` / `KAKAO_CLIENT_SECRET` | 카카오 소셜 로그인 앱 키 |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | 구글 소셜 로그인 앱 키 |
| `CORS_ORIGINS` | 허용 origin, **콤마로 구분한 문자열** (예: `https://a.com,http://localhost:5173`) |
| `DEVICE_API_KEY` | HW 중계 서버 인증용 키 — `/device/scans/*` 호출 시 `X-Device-Key` 헤더와 대조 |
| `SCAN_RELAY_URL` | 웹 스캔 트리거 시 촬영 명령을 전달할 HW 릴레이 서버 주소 (예: `http://<host>:8001`) |

`.env.example`엔 없지만 `app/core/config.py`에 기본값이 있어 선택적으로만 쓰는 변수: `AI_SERVICE_URL`(AI 추론 서버, 비면 실제 분석 불가), `SCANNER_URL`(ESP32-CAM 직접 pull용), `WEATHER_DEFAULT_LAT`/`WEATHER_DEFAULT_LON`/`WEATHER_CACHE_TTL`.

## API 목록

인증 방식 3가지가 있다 — **JWT**(`Authorization: Bearer <token>`, 토큰 없으면 `DEV_USER_ID`로 동작하는 과도기 하이브리드), **기기 키**(`X-Device-Key` 헤더, HW 전용), **공개**(인증 없음). 아래는 `app.main`에 등록된 전체 라우트를 코드로 직접 확인한 결과다.

### 공개 (인증 없음)
| Method | Path | 설명 |
|---|---|---|
| POST | `/auth/signup`, `/auth/login`, `/auth/kakao`, `/auth/google` | 회원가입/로그인 |
| GET | `/products`, `/products/{product_id}` | 제품 목록/상세 |
| GET | `/scanner/status` | ESP32-CAM(`SCANNER_URL`) 연결 상태 |
| GET | `/weather` | 날씨 + 피부 지수 |

### JWT 필요
| Method | Path | 설명 |
|---|---|---|
| GET/PUT | `/surveys/me` | 피부 설문 조회/저장 |
| GET/PATCH | `/mypage` | 내 프로필 조회/수정 |
| POST | `/auth/change-password` | 비밀번호 변경 |
| POST | `/scans` | 스캔 세션 생성 |
| **POST** | **`/scans/trigger`** | 스캔 트리거. `device_id`는 **선택**값 — 있으면 `SCAN_RELAY_URL`의 HW 릴레이에 촬영 명령 전달(실패 시 502), 세션에 `device_id` 저장. 없으면 순수 웹 트리거 |
| **GET** | **`/scans/status`** | 가장 최근 스캔 세션 상태 폴링. 응답에 `source`(`web`/`hardware`), `device_id` 포함 |
| POST | `/scans/{id}/analyze-mock`, `/analyze`, `/analyze-scan` | 분석 실행(목업/이미지 업로드/스캐너 pull) |
| GET/POST | `/scans/{id}/recommend` | 제품 추천 조회/생성 |
| **GET** | **`/result/{session_id}`** | 분석 결과 조회. `white_image_url`/`uv_image_url` 포함 — 해당 타입 이미지가 없으면 `null` |
| **GET** | **`/history`** | 내 스캔 기록 전체. 마찬가지로 `white_image_url`/`uv_image_url` 포함(없으면 `null`) |
| GET | `/report`, `/report/{id}`, `/report/{id}/pdf` | 분석 리포트 목록/상세/PDF |
| GET | `/care/{session_id}` | 케어가이드 조회 |
| GET/POST/DELETE | `/wishlist`, `/products/{id}/wishlist` | 찜 목록/추가/삭제 |
| **POST** | **`/device/link`** | 현재 로그인한 사용자를 `device_id`에 연결(기존 연결 있으면 교체) |
| **DELETE** | **`/device/link/{device_id}`** | 내가 연결한 기기만 연결 해제 (본인 아니면 403) |

### 기기 키 (`X-Device-Key`) 필요
| Method | Path | 설명 |
|---|---|---|
| **POST** | **`/device/scans/trigger`** | HW 전용 스캔 세션 생성. `device_id`에 연결된 사용자가 없으면 400 |
| **POST** | **`/device/scans/done`** | HW 스캔 완료 콜백 — 수분/유분/사진 2장 저장 |

### 기기 키 또는 JWT (둘 중 하나면 통과)
| Method | Path | 설명 |
|---|---|---|
| **GET** | **`/device/link/{device_id}`** | 기기 연결 상태 조회. 연결 없으면 `{"device_id": ..., "user_id": null}` |

## 스캔 흐름

**웹 스캔(기기 없이)**: `POST /scans` 또는 `/scans/trigger`(device_id 없이) → `processing` → `/scans/{id}/analyze-mock`(또는 `analyze`/`analyze-scan`)로 분석 → `done`. 이 경로는 5개 지표(수분/유분/모공/탄력/색소침착) + 종합점수 + 케어 조언이 **모두 채워진다**.

**HW(물리 스캐너) 흐름**:
1. 사용자가 로그인한 상태에서 `POST /device/link`로 "지금 이 기기는 내 것"으로 연결
2. 사용자가 `POST /scans/trigger`(device_id 포함)를 호출하면 BE가 `SCAN_RELAY_URL`에 촬영 명령을 전달하거나, HW/중계서버가 직접 `POST /device/scans/trigger`를 호출 — 세션이 `processing`으로 생성되고 **이 시점의 연결된 user_id로 세션 소유자가 확정**된다 (이후 기기 연결이 바뀌어도 이미 시작된 세션엔 영향 없음)
3. HW가 측정을 마치면 `POST /device/scans/done`으로 수분(`moisture`)·유분(`oil`)·백색 LED 사진(`white_img`)·UV 사진(`uv_img`)을 전달 — **넷 다 있어야** `done` 처리되고(하나라도 빠지면 422), 세션이 `done`으로 바뀐다
4. 같은 완료 알림이 중복으로 와도(`device_id`+시각 일치) 에러 없이 기존 결과를 그대로 반환(멱등성)

**⚠️ HW 흐름의 현재 한계**: `/device/scans/done`은 수분·유분만 저장한다. **모공·탄력·색소침착, 종합점수, 케어 조언은 AI 서버 연동 전이라 물리 스캔 결과에서는 비어 있다(`null`, 혹은 케어가이드는 404).** 웹 스캔(`analyze-mock` 등)과 달리 이 다섯 지표를 보완하는 로직이 HW 완료 콜백엔 없다.

## 배포

- 주소: `https://api.damdads.kro.kr` — Nginx 리버스 프록시 사용 (세부 설정은 이 저장소에 없음)
- `docker-compose.yml`에 `db`(MySQL) + `api`(이 FastAPI 앱, `Dockerfile` 빌드) 두 서비스. `api`는 `db`가 healthy해진 뒤 기동되고, 시작 시 `alembic upgrade head`를 자동 실행한 뒤 `uvicorn app.main:app`을 띄운다
- **`.env`를 바꾼 뒤엔 반드시 재빌드/재기동해야 반영된다** — `docker compose restart`는 이미 떠 있는 컨테이너에 주입된 환경변수를 그대로 쓰기 때문에 **반영되지 않는다**. 아래처럼 해야 한다:
  ```bash
  docker compose up -d --build
  ```

## 저장소 밖 구성

이 저장소(BE)만으로는 전체 시스템이 완성되지 않는다. 아래는 BE 코드가 "호출한다"는 사실만 확인된 것이고, 반대쪽(그 서비스 자체의 동작)은 이 저장소에서 확인할 수 없다.

- **HW 릴레이 서버 (포트 8001)**: 이 저장소에 코드가 없다. BE는 `SCAN_RELAY_URL` 설정값으로 그 서버의 `/scan-command`를 호출만 한다(`app/services/relay.py`). 그 서버가 실제로 어떻게 동작하는지, Docker로 뜨는지 등은 **팀 공유 사항이며 이 저장소에서는 확인 불가**.
- **AI 추론 서버**: `AI_SERVICE_URL`로 호출(`app/services/ai.py`). 이 저장소엔 코드 없음.
- **ESP32-CAM 스캐너**: `SCANNER_URL`로 직접 pull(`app/services/scanner.py`). 펌웨어는 이 저장소에 없음.
- **Nginx**: 설정 파일이 이 저장소에 없다. "리버스 프록시로 쓰고 있다"는 사실까지만 여기 적고, 세부 구성(업스트림, SSL 등)은 생략한다.

## 레거시 파일

아래 파일들은 **삭제되지 않고 저장소에 남아 있지만**, 지금 서비스(`app/` 패키지, 위 API 목록)는 이 파일들을 import하거나 실행하지 않는다. 구버전 아키텍처(별도 데모 서버) 당시의 코드다. 각 파일의 상세 사용법/엔드포인트/환경변수는 전부 [docs/LEGACY_README.md](docs/LEGACY_README.md)에 그대로 보존돼 있다.

| 파일 | 역할(레거시) |
|---|---|
| `main.py` | 독립 실행 가능한 구버전 FastAPI 서버 (`uvicorn main:app`) — AI 모델 직접 로딩 + ESP32 연동 + 자가진단 + narrative 생성을 한 파일에서 처리. **현재 어디서 쓰이는지 확인 안 됨(사용 여부 미확인)** — 삭제는 하지 않았다 |
| `questionnaire.py` | `main.py`가 쓰는 자가진단 10문항 + 채점 로직 |
| `narrative.py` | `main.py`가 쓰는 측정값→자연어 평가 변환 로직 |
| `requirements.txt` | `main.py` 등 레거시 포함, torch 등 AI 추론 패키지까지 전부 포함(로컬 개발용). 배포 이미지는 `requirements-web.txt`(torch 제외) 사용 |

## 이전 README에서 바뀐 내용

구버전 `README.md` 전체는 [docs/LEGACY_README.md](docs/LEGACY_README.md)에 그대로 보존했다(git 이력으로도 이전 커밋에서 원문 확인 가능). 아래는 각 항목이 어떻게 처리됐는지 요약.

| 구버전 항목 | 처리 | 비고 |
|---|---|---|
| 디렉토리 구조(`damda/AI,BE,FE,HW`) | 현재 기준 재작성 | BE 자체가 독립 저장소이고, AI/HW/FE는 폴더가 아니라 환경변수로 연동하는 별도 서비스 — [저장소 밖 구성](#저장소-밖-구성) |
| 의존성 설치(AI venv 공유) | 현재 기준 업데이트 | `requirements.txt`(로컬) / `requirements-web.txt`(배포, torch 제외) 구분 명시 |
| 서버 실행(`uvicorn main:app`), 관련 환경변수(`DAMDA_CHECKPOINT` 등) | 레거시 파일 안내로 이동 | [레거시 파일](#레거시-파일) — `main.py`가 아직 쓰는 중인지 미확인 |
| `/static/index.html` 프론트 서빙 | 레거시 파일 안내로 이동 | `app/main.py`엔 `StaticFiles` 마운트 없음 |
| 엔드포인트 표(`/api/health` 등 6개) | 레거시 파일 안내로 이동 | 지금 API는 위 [API 목록](#api-목록) 참고 |
| 환경 변수 표(`DAMDA_*`) | 레거시 파일 안내로 이동 | 지금 환경변수는 위 [환경 변수](#환경-변수) 참고 |
| 자가진단 질문지 수정법(`questionnaire.py`) | 레거시 파일 안내로 이동 | 지금은 `app/schemas/survey.py`에서 `skin_type`을 사용자가 직접 선택(퀴즈 채점 없음) |
| Narrative 평가 기준(`narrative.py`) | 레거시 파일 안내로 이동 | 지금 조언 생성은 `app/routers/scan.py`의 고정 문구 템플릿 방식 |
| 개발 노트 — 모델 lazy load/추론 속도 | 레거시 파일 안내로 이동 | 지금은 `app/services/ai.py`가 외부 AI 서버에 HTTP 호출(인프로세스 모델 로딩 아님) |
| 개발 노트 — "CORS: `*` 허용" | **삭제(틀린 내용), 여기 기록** | `app/`은 `CORS_ORIGINS` 환경변수로 제한됨(와일드카드 아님). 레거시 `main.py`는 지금도 `allow_origins=["*"]` 하드코딩 그대로 — 둘이 다름 |
| 개발 노트 — 정적 파일 서빙 | 레거시 파일 안내로 이동 | 위 `/static` 항목과 동일 |
| 시연 시나리오(자가진단 10문항→측정방식 A/B) | **삭제, 여기 기록** | 퀴즈 기반 `skin_type` 자동산정 자체가 `app/`엔 없음 — 위 [스캔 흐름](#스캔-흐름)으로 신규 작성 |
| ESP32-CAM 사전 점검(`/api/scanner/health`) | 현재 엔드포인트로 재작성 | 지금은 인증 없는 `GET /scanner/status`(응답: `{"connected": bool, "status": "ok"/"unreachable"}`). IP는 `<ESP32_IP>`로 placeholder 처리 |
