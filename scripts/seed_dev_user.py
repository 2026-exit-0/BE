"""개발용 더미 유저 시드.

로그인 구현 전까지 get_current_user 가 반환할 유저를 만든다.
실행: python -m scripts.seed_dev_user
"""
from app.core.config import settings
from app.core.database import SessionLocal
from app.models.user import User


def main() -> None:
    db = SessionLocal()
    try:
        exists = db.query(User).filter(User.user_id == settings.DEV_USER_ID).first()
        if exists:
            print("이미 존재:", exists.user_id, exists.nickname)
            return
        user = User(
            user_id=settings.DEV_USER_ID,
            email="dev@damda.local",
            nickname="개발자",
            login_type="EMAIL",
            email_verified=True,
        )
        db.add(user)
        db.commit()
        print("더미 유저 생성 완료:", user.user_id)
    finally:
        db.close()


if __name__ == "__main__":
    main()
