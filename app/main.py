from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings

# 명세 A~L 구조를 Swagger(/docs) 에 그대로 그룹핑
tags_metadata = [
    {"name": "system", "description": "헬스체크 등 운영"},
    {"name": "auth", "description": "C. 회원가입 / 로그인"},
    {"name": "survey", "description": "D. 피부 설문조사"},
    {"name": "scan", "description": "G. 피부 스캔"},
    {"name": "result", "description": "H. 분석 결과"},
    {"name": "product", "description": "I. 화장품 추천"},
    {"name": "mypage", "description": "J. 마이페이지"},
    {"name": "care", "description": "K. 케어 가이드"},
    {"name": "report", "description": "L. 분석 리포트"},
    {"name": "weather", "description": "E.2/F.3 날씨·환경"},
]

app = FastAPI(title="담다 API", version="0.1.0", openapi_tags=tags_metadata)

# CORS — FE 배포 도메인 + 로컬 개발 서버만 허용 (CORS_ORIGINS, .env 로 관리)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 전역 에러 핸들러 등록 (응답 포맷 통일 + 내부 정보 노출 방지)
from app.core.errors import register_exception_handlers

register_exception_handlers(app)


@app.get("/health", tags=["system"])
def health():
    return {"status": "ok"}


# ── 도메인 라우터 등록 ──────────────────────────────────────────
# 각 담당자가 app/routers/<도메인>.py 작성 후 아래처럼 등록한다.
# (작성 패턴은 표준 컨벤션 가이드 4번 참고)
#
#   from app.routers import survey
#   app.include_router(survey.router)
# ────────────────────────────────────────────────────────────────

from app.routers import survey, scan, mypage, recommend, product, weather, result, history, report, auth, care

app.include_router(auth.router)
app.include_router(survey.router)
app.include_router(scan.router)
app.include_router(mypage.router)
app.include_router(recommend.router)
app.include_router(product.router)
app.include_router(product.wishlist_router)
app.include_router(weather.router)
app.include_router(result.router)
app.include_router(history.router)
app.include_router(report.router)
app.include_router(care.router)