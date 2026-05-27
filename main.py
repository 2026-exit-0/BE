"""damda backend — FastAPI 서버.

ESP32-CAM 시연 + 사용자 자가진단 → 모델 추론 → narrative 반환.
프론트엔드 (frontend/index.html) 가 호출하는 API.

엔드포인트:
  GET  /                        — 기본 인사 (health check)
  GET  /api/health              — 모델 로드 상태
  GET  /api/questionnaire       — 자가진단 질문지 (UI 렌더링용)
  POST /api/questionnaire/score — 답변 채점 → user_inputs
  POST /api/predict             — 메인: 이미지 + 부위 + 사용자입력 → 측정값 + narrative

실행:
  cd backend
  pip install -r requirements.txt
  uvicorn main:app --reload --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import base64
import io
import os
import sys
from pathlib import Path
from typing import Dict, Optional

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from PIL import Image

# AI 모듈 import — 프로젝트 루트에서 실행되어야 src 경로 해결됨
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "AI"))

from src.infer import DamdaInferenceModel  # noqa: E402

from questionnaire import QUESTIONS, score_answers, get_questions_for_ui  # noqa: E402
from narrative import generate_narrative  # noqa: E402


# ============================================================
# 설정
# ============================================================

# 시연 사용 ckpt — 환경변수로 override 가능
CHECKPOINT_PATH = os.getenv(
    "DAMDA_CHECKPOINT",
    str(PROJECT_ROOT / "AI" / "checkpoints" / "epoch045.pt"),  # 기본은 v3 best
)
CONFIG_PATH = os.getenv(
    "DAMDA_CONFIG",
    str(PROJECT_ROOT / "AI" / "configs" / "baseline.yaml"),
)


# ============================================================
# FastAPI app
# ============================================================

app = FastAPI(
    title="damda API",
    description="ESP32-CAM 시연용 피부 측정 API",
    version="0.1.0",
)

# CORS — 프론트엔드와 다른 포트에서 돌 때를 위해
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 시연 환경 한정. 운영 시 제한 필요
    allow_methods=["*"],
    allow_headers=["*"],
)

# 정적 파일 (FE/) 서빙 — 같은 서버에서 html 도 띄움
FRONTEND_DIR = PROJECT_ROOT / "FE"
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


# ============================================================
# 모델 lazy load (서버 시작 시 1회)
# ============================================================

_model: Optional[DamdaInferenceModel] = None


def get_model() -> DamdaInferenceModel:
    global _model
    if _model is None:
        if not Path(CHECKPOINT_PATH).exists():
            raise HTTPException(
                status_code=503,
                detail=f"Checkpoint not found: {CHECKPOINT_PATH}. "
                f"환경변수 DAMDA_CHECKPOINT 로 경로 지정 가능.",
            )
        _model = DamdaInferenceModel(
            checkpoint_path=CHECKPOINT_PATH,
            config_path=CONFIG_PATH,
        )
    return _model


# ============================================================
# Pydantic schemas
# ============================================================

class QuestionnaireAnswers(BaseModel):
    answers: Dict[str, int]  # {question_id: option_index}


class UserInputs(BaseModel):
    """사용자가 직접 제공 (자가진단 또는 직접 입력 둘 다)."""
    skin_type: Optional[str] = None       # "건성"/"지성"/"복합성"/"민감성"/"중성"
    sensitivity: Optional[int] = None     # 1~5
    aging_score: Optional[int] = None     # 1~5
    age: Optional[int] = None
    gender: Optional[str] = None          # "M"/"F"
    lifestyle_flags: Optional[Dict[str, str]] = None


class SensorInputs(BaseModel):
    """ESP32-CAM 하드웨어 측정값."""
    moisture: Optional[float] = None      # FDC2112
    illuminance: Optional[float] = None   # VEML7700


# ============================================================
# 엔드포인트
# ============================================================

@app.get("/")
def root():
    return {
        "name": "damda API",
        "version": "0.1.0",
        "frontend": "/static/index.html",
        "docs": "/docs",
    }


@app.get("/api/health")
def health():
    """모델 로드 상태 확인 (서버 startup latency 큼 — 첫 호출 시 ckpt 로드)."""
    try:
        model = get_model()
        return {
            "status": "ok",
            "checkpoint": CHECKPOINT_PATH,
            "ckpt_epoch": model.ckpt_epoch,
            "regression_heads": model.regression_target_names(),
            "classification_heads": model.classification_head_names(),
            "sensor_dim": model.sensor_dim,
            "sensor_inputs": model.sensor_inputs,
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.get("/api/questionnaire")
def get_questionnaire():
    """자가진단 질문지 — 프론트 렌더링용."""
    return {
        "questions": get_questions_for_ui(),
        "total": len(QUESTIONS),
    }


@app.post("/api/questionnaire/score")
def score_questionnaire(payload: QuestionnaireAnswers):
    """답변 채점. 답변 누락 있어도 부분 점수 산출 (incomplete 필드로 알림)."""
    result = score_answers(payload.answers)
    return result


@app.post("/api/predict")
async def predict(
    image: UploadFile = File(...),
    region: str = Form(...),
    skin_type: Optional[str] = Form(None),
    sensitivity: Optional[int] = Form(None),
    aging_score: Optional[int] = Form(None),
    age: Optional[int] = Form(None),
    gender: Optional[str] = Form(None),
    moisture: Optional[float] = Form(None),
    illuminance: Optional[float] = Form(None),
    sleep_flag: Optional[str] = Form(None),
    sunscreen_flag: Optional[str] = Form(None),
):
    """메인 추론 엔드포인트.

    multipart/form-data 로 받음 (이미지 + 메타). JSON 으로 결과 반환.

    Returns:
        {
            "predictions": {regression: {...}, classification: {...}},
            "narrative": {summary, per_metric, tips, overall_score, ...},
            "meta": {region, ckpt_epoch, ...},
        }
    """
    # 이미지 디코드
    img_bytes = await image.read()
    try:
        pil_img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"이미지 디코드 실패: {e}")

    # 센서 입력 dict
    sensor: Dict[str, float] = {}
    if moisture is not None:
        sensor["moisture"] = moisture
    if illuminance is not None:
        sensor["illuminance"] = illuminance

    # 모델 추론
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"추론 실패: {e}")

    # 사용자 입력 dict 구성
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

    # Narrative 생성
    narrative = generate_narrative(
        region=region,
        regression=pred["regression"],
        classification=pred["classification"],
        user_inputs=user_inputs,
    )

    return {
        "predictions": {
            "regression": pred["regression"],
            "classification": pred["classification"],
        },
        "narrative": narrative,
        "user_inputs": user_inputs,
        "sensor": sensor,
        "meta": pred["meta"],
    }


if __name__ == "__main__":
    # 직접 실행 시 — 권장은 uvicorn 명령
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
