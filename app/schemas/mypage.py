from pydantic import BaseModel


class MypageOut(BaseModel):             # 출력값 (명세 J.1)
    user_id: str
    email: str
    nickname: str
    profile_image_url: str | None = None
    notify_analysis: bool
    notify_recommend: bool

    class Config:
        from_attributes = True


class MypageUpdate(BaseModel):          # 수정 입력값 (명세 J.1.3)
    nickname: str | None = None
    profile_image_url: str | None = None
    notify_analysis: bool | None = None
    notify_recommend: bool | None = None
