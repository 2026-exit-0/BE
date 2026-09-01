from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.survey import UserSurvey
from app.schemas.survey import SurveyIn, SurveyOut

router = APIRouter(prefix="/surveys", tags=["survey"])

@router.get("/me", response_model=SurveyOut, summary="[D] 내 설문 조회")
def get_my_survey(db: Session = Depends(get_db), user=Depends(get_current_user)):
    survey = db.query(UserSurvey).filter(UserSurvey.user_id == user.user_id).first()
    if not survey:
        raise HTTPException(status_code=404, detail="설문이 없습니다")
    return survey

@router.put("/me", response_model=SurveyOut, summary="[D] 내 설문 저장/수정")
def upsert_my_survey(data: SurveyIn, db: Session = Depends(get_db),
                     user=Depends(get_current_user)):
    survey = db.query(UserSurvey).filter(UserSurvey.user_id == user.user_id).first()
    
    if survey:                                   # 있으면 수정 (D.3)
        for k, v in data.model_dump().items():
            setattr(survey, k, v)
    else:                                        # 없으면 생성 (D.2)
        survey = UserSurvey(user_id=user.user_id, **data.model_dump())
        db.add(survey)
        
    db.commit()
    db.refresh(survey)
    return survey