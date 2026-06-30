from pydantic import BaseModel

class SurveyIn(BaseModel):          # 입력값 (명세 D 입력)
    skin_type: str                  # 건성/지성/복합성/민감성
    concerns: list[str] = []        # 고민 최대 3
    allergies: list[str] = []
    preferred_categories: list[str] = []
    budget_min: int | None = None
    budget_max: int | None = None

class SurveyOut(SurveyIn):          # 출력값
    id: int

    class Config:
        from_attributes = True