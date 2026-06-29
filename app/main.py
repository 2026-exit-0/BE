from fastapi import FastAPI

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
]

app = FastAPI(title="담다 API", version="0.1.0", openapi_tags=tags_metadata)


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
