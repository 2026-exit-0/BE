# 담다 BE — 초기 세팅

> FastAPI + SQLAlchemy + Alembic + MySQL. 폴더/네이밍/패턴은 표준 컨벤션 가이드 참고.

## 1. 사전 준비
- Python 3.10+
- MySQL 8 (로컬 설치 or `docker compose up -d` 로 띄우기)

## 2. 설치
```bash
python -m venv .venv && source .venv/Scripts/activate   # mac/linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # DATABASE_URL 등 확인/수정
```
> 참고: requirements 의 torch 등 AI 패키지는 AI 레포 연결 시에만 필요. 웹 개발만 할 땐 DB 패키지 위주로 설치돼도 무방.

## 3. DB 띄우기 (도커 사용 시)
```bash
docker compose up -d        # localhost:3306 에 MySQL(db: damda)
```

## 4. 마이그레이션 (테이블 생성)
모델은 `app/models/` 에 정의돼 있고 `app/models/__init__.py` 에서 전부 import 된다.
```bash
alembic revision --autogenerate -m "init schema"   # 최초 1회
alembic upgrade head                                # 테이블 생성/반영
```
이후 모델을 바꾸면 `revision --autogenerate` → `upgrade head` 반복.

## 5. 개발용 더미 유저 시드
로그인 붙기 전까지 `get_current_user` 가 반환할 유저.
```bash
python -m scripts.seed_dev_user
```

## 6. 실행
```bash
uvicorn app.main:app --reload
# http://localhost:8000/docs  ← Swagger 에서 API 확인/테스트
```

## 폴더 구조
```
app/
  main.py          # 앱 생성 + 라우터 등록 (도메인 라우터는 담당자가 추가)
  core/            # config / database / deps(get_current_user)
  models/          # SQLAlchemy 모델 (테이블) — 작성 완료
  schemas/         # Pydantic 스키마 (담당자가 도메인별 추가)
  routers/         # API 엔드포인트 (담당자가 도메인별 추가)
  crud/            # (선택) DB 접근 로직
alembic/           # 마이그레이션
scripts/seed_dev_user.py
```

## 다음 작업 (담당자별)
각자 `app/routers/<도메인>.py` + `app/schemas/<도메인>.py` 를 컨벤션 가이드 4번 템플릿대로 작성 →
`app/main.py` 에 `include_router` 등록. 역할 분담은 역할분담 시트 참고.
