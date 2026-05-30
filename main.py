"""damda backend — FastAPI 서버.

ESP32-CAM 시연 + 사용자 자가진단 → 모델 추론 → narrative 반환.
프론트엔드 (FE/index.html) 가 호출하는 API.

엔드포인트 (Swagger UI: http://localhost:8000/docs):
  GET  /                        — 기본 인사 / 정적 파일 링크
  GET  /api/health              — 모델 로드 상태 + 메타
  GET  /api/scanner/health      — ESP32-CAM 스캐너 도달 여부
  GET  /api/questionnaire       — 자가진단 10문항 (UI 렌더링용)
  POST /api/questionnaire/score — 답변 채점 → user_inputs
  POST /api/predict             — 이미지 업로드 + 사용자입력 → 측정값 + narrative
  POST /api/measure             — ESP32 스캐너 trigger + 자동 측정 → 추론 → narrative

실행:
  cd BE
  pip install -r requirements.txt
  uvicorn main:app --reload --host 0.0.0.0 --port 8000

환경변수:
  DAMDA_CHECKPOINT   사용할 모델 ckpt 경로 (기본 ../AI/checkpoints/epoch045.pt)
  DAMDA_CONFIG       모델 config yaml (기본 ../AI/configs/baseline.yaml)
  DAMDA_ESP32_URL    ESP32-CAM 기본 URL (기본 http://10.174.185.100)
"""

from __future__ import annotations

import asyncio
import io
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

import httpx
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from PIL import Image

# AI 모듈 import — 프로젝트 루트에서 실행되어야 src 경로 해결됨
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "AI"))

from src.infer import DamdaInferenceModel  # noqa: E402

from questionnaire import QUESTIONS, score_answers, get_questions_for_ui  # noqa: E402
from narrative import generate_narrative  # noqa: E402
from recommend import recommend as recommend_products  # noqa: E402


# ============================================================
# 설정
# ============================================================

CHECKPOINT_PATH = os.getenv(
    "DAMDA_CHECKPOINT",
    str(PROJECT_ROOT / "AI" / "checkpoints" / "epoch045.pt"),
)
CONFIG_PATH = os.getenv(
    "DAMDA_CONFIG",
    str(PROJECT_ROOT / "AI" / "configs" / "baseline.yaml"),
)
ESP32_BASE_URL = os.getenv("DAMDA_ESP32_URL", "http://10.174.185.100")


# ============================================================
# Swagger 메타데이터
# ============================================================

TAGS_METADATA = [
    {
        "name": "기본",
        "description": "서버 / 모델 / 스캐너 상태 확인",
    },
    {
        "name": "자가진단",
        "description": (
            "사용자가 본인 피부 상태를 모를 때 10문항 자가진단으로 "
            "피부 타입 / 민감도 / 노화 점수를 자동 산정"
        ),
    },
    {
        "name": "측정",
        "description": (
            "이미지 업로드 (`/predict`) 또는 ESP32-CAM 스캐너 (`/measure`) 로 "
            "측정값 + 등급 + 자연어 narrative 반환"
        ),
    },
]

app = FastAPI(
    title="damda API",
    description=(
        "**담다 피부 측정 시연 API**\n\n"
        "- AI 모델 (`AI/src/infer.py`) 을 wrap 하는 FastAPI 서버\n"
        "- 자가진단 10문항으로 피부 타입 자동 산정\n"
        "- ESP32-CAM 스캐너 (FDC2112 수분 + VEML7700 조도 + OV2640 카메라) 연동\n"
        "- 측정값 → 자연어 평가 (narrative) + 케어 tip\n\n"
        "**시연 흐름**: `/api/questionnaire` → `/api/questionnaire/score` → `/api/measure` (ESP32) "
        "또는 `/api/predict` (직접 업로드)"
    ),
    version="0.2.0",
    openapi_tags=TAGS_METADATA,
)

# CORS — 프론트와 다른 origin 일 때 대비
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 시연 한정. 운영 시 origin 제한
    allow_methods=["*"],
    allow_headers=["*"],
)

# 정적 파일 (FE/) 서빙
FRONTEND_DIR = PROJECT_ROOT / "FE"
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


# ============================================================
# 모델 lazy load
# ============================================================

_model: Optional[DamdaInferenceModel] = None


def get_model() -> DamdaInferenceModel:
    global _model
    if _model is None:
        if not Path(CHECKPOINT_PATH).exists():
            raise HTTPException(
                status_code=503,
                detail=(
                    f"Checkpoint 파일 없음: {CHECKPOINT_PATH}. "
                    f"환경변수 DAMDA_CHECKPOINT 로 경로 지정 가능."
                ),
            )
        _model = DamdaInferenceModel(
            checkpoint_path=CHECKPOINT_PATH,
            config_path=CONFIG_PATH,
        )
    return _model


# ============================================================
# Pydantic schemas (Swagger 표시용)
# ============================================================

class QuestionnaireAnswers(BaseModel):
    """자가진단 답변 — 각 질문 ID 와 선택한 옵션 인덱스의 dict."""
    answers: Dict[str, int] = Field(
        ...,
        description="질문 ID (A1, A2, B1, ...) → 선택한 옵션 index (0-base)",
        examples=[{"A1": 2, "A2": 1, "A3": 0, "B1": 1, "B2": 1, "B3": 0, "C1": 1, "C2": 1, "C3": 0, "D1": 1}],
    )


class QuestionOption(BaseModel):
    label: str = Field(..., description="UI 에 표시될 선택지 텍스트")


class QuestionItem(BaseModel):
    id: str = Field(..., description="질문 식별자 (A1, B1, C1, D1)")
    section: str = Field(..., description="섹션: skin_type | sensitivity | aging | lifestyle")
    text: str = Field(..., description="UI 에 표시될 한국어 질문")
    options: List[QuestionOption] = Field(..., description="선택지 리스트")


class QuestionnaireResponse(BaseModel):
    questions: List[QuestionItem] = Field(..., description="10개 질문 리스트")
    total: int = Field(..., description="질문 총 개수")


class ScoreResponse(BaseModel):
    skin_type: str = Field(..., description="피부 타입 (건성/지성/복합성/민감성/중성)")
    skin_type_scores: Dict[str, int] = Field(..., description="각 타입별 누적 점수 (디버깅용)")
    sensitivity: int = Field(..., ge=1, le=5, description="민감도 1~5")
    sensitivity_raw: int = Field(..., description="민감도 raw 합산")
    aging_score: int = Field(..., ge=1, le=5, description="노화 점수 1~5")
    aging_raw: int = Field(..., description="노화 raw 합산")
    lifestyle_flags: Dict[str, str] = Field(..., description="lifestyle flag dict (sunscreen 등)")
    incomplete: List[str] = Field(..., description="답변 누락된 질문 ID 들")


class HealthResponse(BaseModel):
    status: str = Field(..., description="ok / error")
    checkpoint: Optional[str] = Field(None, description="로드된 ckpt 경로")
    ckpt_epoch: Optional[int] = Field(None, description="ckpt 의 epoch 번호")
    regression_heads: Optional[List[str]] = Field(None, description="회귀 출력 헤드 이름")
    classification_heads: Optional[List[str]] = Field(None, description="분류 출력 헤드 이름")
    sensor_dim: Optional[int] = Field(None, description="모델이 받는 sensor 입력 차원")
    sensor_inputs: Optional[List[str]] = Field(None, description="sensor 입력 컬럼 이름 (학습 시 사용된 것)")
    error: Optional[str] = Field(None, description="status=error 일 때 에러 메시지")


class ScannerHealthResponse(BaseModel):
    status: str = Field(..., description="ok / unreachable")
    esp32_data: Optional[dict] = Field(None, description="ESP32 /data 응답 (살아있을 때)")
    error: Optional[str] = Field(None, description="unreachable 일 때 에러 메시지")


# ============================================================
# 엔드포인트 — 기본
# ============================================================

@app.get(
    "/",
    tags=["기본"],
    summary="API 루트 — 정적 파일 / 문서 링크",
    description="브라우저로 접속 시 frontend / docs 링크 안내.",
)
def root():
    return {
        "name": "damda API",
        "version": "0.2.0",
        "frontend": "/static/index.html",
        "docs": "/docs",
        "redoc": "/redoc",
    }


@app.get(
    "/api/health",
    response_model=HealthResponse,
    tags=["기본"],
    summary="모델 로드 상태 확인",
    description=(
        "현재 로드된 모델 ckpt 정보 + 출력 헤드 + sensor 설정을 반환합니다.\n\n"
        "최초 호출 시 모델 로드 (~5초 lazy load) 가 발생하므로 "
        "**서버 기동 후 첫 호출은 다소 느릴 수 있습니다**.\n\n"
        "이후 호출은 즉시 응답."
    ),
    responses={
        200: {"description": "정상 — 모델 로드 완료 또는 에러 상세"},
        503: {"description": "Checkpoint 파일 없음"},
    },
)
def health():
    try:
        model = get_model()
        return HealthResponse(
            status="ok",
            checkpoint=CHECKPOINT_PATH,
            ckpt_epoch=model.ckpt_epoch,
            regression_heads=model.regression_target_names(),
            classification_heads=model.classification_head_names(),
            sensor_dim=model.sensor_dim,
            sensor_inputs=model.sensor_inputs,
        )
    except HTTPException:
        raise
    except Exception as e:
        return HealthResponse(status="error", error=str(e))


@app.get(
    "/api/scanner/health",
    response_model=ScannerHealthResponse,
    tags=["기본"],
    summary="ESP32-CAM 스캐너 도달 여부 확인",
    description=(
        f"환경변수 `DAMDA_ESP32_URL` (기본 `{ESP32_BASE_URL}`) 의 "
        "`/data` 엔드포인트를 호출해 ESP32 가 살아있는지 확인합니다.\n\n"
        "**시연 전 필수 체크** — ESP32 가 같은 Wi-Fi 망에 있어야 하고, "
        "응답이 오지 않으면 `unreachable` 반환."
    ),
)
async def scanner_health():
    async with httpx.AsyncClient(timeout=3.0) as client:
        try:
            r = await client.get(f"{ESP32_BASE_URL}/data")
            return ScannerHealthResponse(status="ok", esp32_data=r.json())
        except Exception as e:
            return ScannerHealthResponse(status="unreachable", error=str(e))


# ============================================================
# 엔드포인트 — 자가진단
# ============================================================

@app.get(
    "/api/questionnaire",
    response_model=QuestionnaireResponse,
    tags=["자가진단"],
    summary="자가진단 10문항 fetch",
    description=(
        "프론트엔드 렌더링용 질문 리스트.\n\n"
        "**4섹션 구성**:\n"
        "- A. 피부 타입 (3문항): 세안 후 상태 / T존 vs U존 / 모공\n"
        "- B. 민감도 (3문항): 화장품 자극 / 햇볕 / 환절기\n"
        "- C. 노화 (3문항): 탄력 / 주름 / 색소\n"
        "- D. 라이프스타일 (1문항): 자외선 차단제\n\n"
        "내부 점수 가중치 (`scores` 필드) 는 제외하고 표시용 텍스트만 반환."
    ),
)
def get_questionnaire():
    return QuestionnaireResponse(
        questions=get_questions_for_ui(),
        total=len(QUESTIONS),
    )


@app.post(
    "/api/questionnaire/score",
    response_model=ScoreResponse,
    tags=["자가진단"],
    summary="자가진단 답변 채점",
    description=(
        "사용자 답변 dict 를 받아 다음을 산정해 반환:\n\n"
        "- **skin_type**: 5개 타입 중 max-score 방식 (민감도 raw ≥ 6 이면 자동으로 '민감성' 격상)\n"
        "- **sensitivity**: 1~5 (raw / max 비율로 정규화)\n"
        "- **aging_score**: 1~5 (raw / max 비율로 정규화)\n"
        "- **lifestyle_flags**: dict (sunscreen 등 narrative 보조 정보)\n\n"
        "답변 누락 가능 — `incomplete` 필드로 누락된 질문 ID 알림. "
        "부분 답변도 점수는 산출 (낮게 나옴)."
    ),
)
def score_questionnaire(payload: QuestionnaireAnswers):
    result = score_answers(payload.answers)
    return ScoreResponse(**result)


# ============================================================
# 엔드포인트 — 측정 (이미지 업로드)
# ============================================================

@app.post(
    "/api/predict",
    tags=["측정"],
    summary="이미지 업로드 + 사용자입력 → 모델 추론 + narrative",
    description=(
        "사용자가 직접 업로드한 이미지로 추론합니다 (ESP32 미사용).\n\n"
        "## 필수 입력\n"
        "- **image**: multipart 이미지 파일 (JPG / PNG)\n"
        "- **region**: 측정 부위 (FOREHEAD / GLABELLA / L_EYE / R_EYE / "
        "L_CHEEK / R_CHEEK / LIP / CHIN / PART_0)\n\n"
        "## 선택 입력\n"
        "**사용자 정보** (narrative 보강, 약한 헤드 대체):\n"
        "- skin_type: 건성/지성/복합성/민감성/중성\n"
        "- sensitivity: 1~5\n"
        "- aging_score: 1~5\n"
        "- age / gender / sleep_flag / sunscreen_flag\n\n"
        "**센서값** (학습에 사용된 sensor_inputs 와 매칭):\n"
        "- moisture: FDC2112 측정값 (또는 corneometer 단위)\n"
        "- illuminance: VEML7700 조도\n\n"
        "## 반환\n"
        "- `predictions.regression`: 회귀 4개 헤드 (denormalized)\n"
        "- `predictions.classification`: 분류 7개 헤드 (predicted class index)\n"
        "- `narrative`: summary + per_metric + tips + overall_score (0~100)\n"
        "- `meta`: 모델 epoch / sensor_dim / region 정보\n\n"
        "**스캐너 직접 측정은 `/api/measure` 사용.**"
    ),
    responses={
        200: {"description": "정상 추론 + narrative"},
        400: {"description": "이미지 디코드 실패 또는 알 수 없는 region"},
        500: {"description": "모델 추론 실패"},
        503: {"description": "Checkpoint 파일 없음"},
    },
)
async def predict(
    image: UploadFile = File(..., description="피부 측정 이미지 (JPG/PNG)"),
    region: str = Form(..., description="측정 부위 (FOREHEAD, L_CHEEK 등)"),
    skin_type: Optional[str] = Form(None, description="사용자 입력 피부 타입"),
    sensitivity: Optional[int] = Form(None, description="민감도 1~5"),
    aging_score: Optional[int] = Form(None, description="노화 점수 1~5"),
    age: Optional[int] = Form(None, description="나이"),
    gender: Optional[str] = Form(None, description="성별 (M/F)"),
    moisture: Optional[float] = Form(None, description="FDC2112 수분 센서값"),
    illuminance: Optional[float] = Form(None, description="VEML7700 조도 센서값"),
    sleep_flag: Optional[str] = Form(None, description="수면 패턴 flag"),
    sunscreen_flag: Optional[str] = Form(None, description="자외선 차단제 flag (daily/occasional/rare)"),
):
    img_bytes = await image.read()
    try:
        pil_img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"이미지 디코드 실패: {e}")

    sensor: Dict[str, float] = {}
    if moisture is not None:
        sensor["moisture"] = moisture
    if illuminance is not None:
        sensor["illuminance"] = illuminance

    try:
        model = get_model()
        pred = model.predict(
            image_path=pil_img,
            region=region,
            sensor=sensor if sensor else None,
            return_probs=False,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"추론 실패: {e}")

    user_inputs = _collect_user_inputs(
        skin_type, sensitivity, aging_score, age, gender,
        sleep_flag, sunscreen_flag,
    )
    narrative = generate_narrative(
        region=region,
        regression=pred["regression"],
        classification=pred["classification"],
        user_inputs=user_inputs,
    )

    # 제품 추천 — 측정값 + 사용자 입력 기반
    try:
        recommendations = recommend_products(
            measurement={**pred["regression"], **pred["classification"]},
            user_inputs=user_inputs,
            weather=None,  # TODO: 기상 API 통합
            top_k=5,
        )
    except Exception as e:
        recommendations = []
        print(f"[recommend] 실패 (무시): {e}")

    return {
        "predictions": {
            "regression": pred["regression"],
            "classification": pred["classification"],
        },
        "narrative": narrative,
        "recommended_products": recommendations,
        "user_inputs": user_inputs,
        "sensor": sensor,
        "meta": pred["meta"],
    }


# ============================================================
# 엔드포인트 — 측정 (ESP32 스캐너)
# ============================================================

@app.post(
    "/api/measure",
    tags=["측정"],
    summary="ESP32-CAM 스캐너로 자동 측정 + 추론 + narrative",
    description=(
        "ESP32-CAM 의 `/scan` 을 trigger 하고, 완료될 때까지 polling 한 뒤 "
        "캡처 이미지 + 센서값을 모델에 넣어 추론합니다.\n\n"
        "## 흐름 (총 ~6초)\n"
        "1. ESP32 `/scan` 호출 → 스캔 시작 (LED 점등)\n"
        "2. ESP32 `/data` polling (0.5초 간격, 최대 12초) → state='done' 까지 대기\n"
        "3. ESP32 `/capture/white` GET → 백색 LED 사진 받음\n"
        "4. 모델 추론 + narrative 생성 → 반환\n\n"
        "## 필수 입력\n"
        "- **region**: 측정 부위 — 사용자가 UI 에서 선택 (ESP32 는 부위 모름)\n\n"
        "## 선택 입력\n"
        "사용자 정보 (predict 와 동일).\n\n"
        "## 환경 의존\n"
        "- ESP32-CAM 이 켜져있고 같은 Wi-Fi 망에 있어야 함\n"
        "- `DAMDA_ESP32_URL` 환경변수 (기본 `http://10.174.185.100`)\n\n"
        "## 반환\n"
        "`/predict` 와 동일한 구조 + `sensor` 필드에 ESP32 raw 값 추가:\n"
        "- `sensor.moisture_raw`: FDC2112 raw\n"
        "- `sensor.moisture_pct`: 0~100 정규화 (HW analysis 로직)\n"
        "- `sensor.reflected_lux`: 백색 LED 반사광 (유분 추정용)\n"
        "- `sensor.ambient_lux`: 주변광"
    ),
    responses={
        200: {"description": "정상 측정 + 추론 + narrative"},
        409: {"description": "ESP32 가 다른 측정 진행 중 (busy)"},
        500: {"description": "이미지 디코드 / 추론 실패"},
        502: {"description": "ESP32 연결 실패 또는 비정상 응답"},
        504: {"description": "ESP32 스캔 timeout (12초 내 완료 안 됨)"},
        503: {"description": "Checkpoint 파일 없음"},
    },
)
async def measure_via_scanner(
    region: str = Form(..., description="측정 부위 (FOREHEAD, L_CHEEK 등)"),
    skin_type: Optional[str] = Form(None, description="사용자 입력 피부 타입"),
    sensitivity: Optional[int] = Form(None, description="민감도 1~5"),
    aging_score: Optional[int] = Form(None, description="노화 점수 1~5"),
    age: Optional[int] = Form(None, description="나이"),
    gender: Optional[str] = Form(None, description="성별 (M/F)"),
    sleep_flag: Optional[str] = Form(None, description="수면 flag"),
    sunscreen_flag: Optional[str] = Form(None, description="자외선 차단제 flag"),
):
    async with httpx.AsyncClient(timeout=15.0) as client:
        # 1) 스캔 trigger
        try:
            r = await client.get(f"{ESP32_BASE_URL}/scan")
        except httpx.RequestError as e:
            raise HTTPException(status_code=502, detail=f"ESP32 연결 실패: {e}")
        if r.status_code != 200:
            raise HTTPException(status_code=502, detail=f"ESP32 /scan 비정상 응답: {r.status_code}")
        try:
            scan_status = r.json().get("status")
        except Exception:
            scan_status = None
        if scan_status == "busy":
            raise HTTPException(status_code=409, detail="ESP32 가 다른 측정 진행 중")

        # 2) DONE polling (최대 12초)
        moisture_raw = 0
        reflected_lux = 0.0
        ambient_lux = 0.0
        done = False
        for _ in range(24):  # 0.5s × 24 = 12s
            await asyncio.sleep(0.5)
            try:
                r = await client.get(f"{ESP32_BASE_URL}/data")
                d = r.json()
            except Exception:
                continue
            if d.get("state") == "done":
                moisture_raw = d.get("raw", 0)
                reflected_lux = d.get("reflectedLux", 0.0)
                ambient_lux = d.get("ambientLux", 0.0)
                done = True
                break
        if not done:
            raise HTTPException(status_code=504, detail="ESP32 스캔 timeout (12초)")

        # 3) 이미지 fetch
        try:
            r = await client.get(f"{ESP32_BASE_URL}/capture/white")
        except httpx.RequestError as e:
            raise HTTPException(status_code=502, detail=f"ESP32 이미지 fetch 실패: {e}")
        if r.status_code != 200:
            raise HTTPException(status_code=502, detail="ESP32 이미지 응답 비정상")
        img_bytes = r.content

    # 4) 추론
    try:
        pil_img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ESP32 이미지 디코드 실패: {e}")

    # FDC2112 raw → 0~100% 변환 (HW analysis.h 의 calcMoisturePct 로직 미러)
    # BASELINE=7, MIN_VAL=3 — raw 가 작을수록 수분 많음
    moisture_pct = max(0, min(100, int((7 - moisture_raw) / (7 - 3) * 100)))
    sensor = {"moisture": float(moisture_pct), "illuminance": ambient_lux}

    try:
        model = get_model()
        pred = model.predict(image_path=pil_img, region=region, sensor=sensor, return_probs=False)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"추론 실패: {e}")

    user_inputs = _collect_user_inputs(
        skin_type, sensitivity, aging_score, age, gender,
        sleep_flag, sunscreen_flag,
    )
    narrative = generate_narrative(
        region=region,
        regression=pred["regression"],
        classification=pred["classification"],
        user_inputs=user_inputs,
    )

    # 제품 추천 — 측정값 + 사용자 입력 기반
    try:
        recommendations = recommend_products(
            measurement={**pred["regression"], **pred["classification"]},
            user_inputs=user_inputs,
            weather=None,
            top_k=5,
        )
    except Exception as e:
        recommendations = []
        print(f"[recommend] 실패 (무시): {e}")

    return {
        "predictions": {
            "regression": pred["regression"],
            "classification": pred["classification"],
        },
        "narrative": narrative,
        "recommended_products": recommendations,
        "user_inputs": user_inputs,
        "sensor": {
            "moisture_raw": moisture_raw,
            "moisture_pct": moisture_pct,
            "reflected_lux": reflected_lux,
            "ambient_lux": ambient_lux,
        },
        "meta": pred["meta"],
    }


# ============================================================
# 헬퍼
# ============================================================

def _collect_user_inputs(
    skin_type: Optional[str],
    sensitivity: Optional[int],
    aging_score: Optional[int],
    age: Optional[int],
    gender: Optional[str],
    sleep_flag: Optional[str],
    sunscreen_flag: Optional[str],
) -> dict:
    """form 으로 들어온 사용자 입력들을 dict 로 정리."""
    user_inputs: Dict = {}
    if skin_type:
        user_inputs["skin_type"] = skin_type
    if sensitivity is not None:
        user_inputs["sensitivity"] = sensitivity
    if aging_score is not None:
        user_inputs["aging_score"] = aging_score
    if age is not None:
        user_inputs["age"] = age
    if gender:
        user_inputs["gender"] = gender
    lifestyle: Dict[str, str] = {}
    if sleep_flag:
        lifestyle["sleep"] = sleep_flag
    if sunscreen_flag:
        lifestyle["sunscreen"] = sunscreen_flag
    if lifestyle:
        user_inputs["lifestyle_flags"] = lifestyle
    return user_inputs


# ============================================================
# 엔드포인트 — 추천 재요청 (필터 / 새로고침 용)
# ============================================================

class RecommendRequest(BaseModel):
    """FE 에서 측정 결과 기억해뒀다가 필터/새로고침 시 다시 호출."""
    measurement: Dict = Field(default_factory=dict, description="회귀+분류 결과 dict")
    user_inputs: Dict = Field(default_factory=dict, description="자가진단 결과")
    weather: Optional[Dict] = Field(default=None, description="습도/UV")
    filter_category: Optional[str] = Field(default=None, description="보습/미백/진정/모공/탄력")
    seed: Optional[int] = Field(default=None, description="랜덤 시드 (새로고침용)")
    top_k: int = Field(default=5, ge=1, le=20)


@app.post(
    "/api/recommend",
    tags=["측정"],
    summary="제품 추천 (필터/새로고침)",
    description=(
        "이미 측정된 결과를 다시 추천 알고리즘에 통과시킴. "
        "filter_category 로 특정 케어 카테고리만 받거나, "
        "seed 를 바꿔서 같은 측정값에 대해 다른 추천 풀을 받을 수 있음."
    ),
)
async def api_recommend(req: RecommendRequest) -> Dict:
    try:
        recommendations = recommend_products(
            measurement=req.measurement,
            user_inputs=req.user_inputs,
            weather=req.weather,
            top_k=req.top_k,
            filter_category=req.filter_category,
            seed=req.seed,
        )
    except Exception as e:
        print(f"[/api/recommend] 실패: {e}")
        raise HTTPException(status_code=500, detail=f"추천 실패: {e}")

    return {
        "recommended_products": recommendations,
        "filter_category": req.filter_category,
        "count": len(recommendations),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
