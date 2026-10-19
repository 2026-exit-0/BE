from pydantic import BaseModel

class SurveyIn(BaseModel):          # 입력값 (명세 D 입력)
    skin_type: str                  # 건성/지성/복합성/민감성
    age_band: str | None = None     # 10대/20대/30대/40대/50대/60대+ (선택, 데모 개인화)
    gender: str | None = None       # 남/여/기타 (선택)
    concerns: list[str] = []        # 고민 최대 3
    allergies: list[str] = []
    preferred_categories: list[str] = []
    budget_min: int | None = None
    budget_max: int | None = None

class SurveyOut(SurveyIn):          # 출력값
    id: int

    class Config:
        from_attributes = True
