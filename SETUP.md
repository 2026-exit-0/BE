# 담다 BE — 초기 세팅

> FastAPI + SQLAlchemy + Alembic + MySQL. 폴더/네이밍/패턴은 표준 컨벤션 가이드 참고.
> 프로젝트 개요, 환경변수 전체 목록, API 목록, 배포 방법은 [README.md](README.md) 참고 — 여기선 "처음 셋업"만 다룬다.

## 1. 사전 준비
- Python 3.10+
- MySQL 8 (로컬 설치 or `docker compose up -d db` 로 띄우기)

## 2. 설치
```bash
python -m venv .venv && source .venv/Scripts/activate   # mac/linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # 값 채우기 — 전체 변수 설명은 README.md "환경 변수" 참고
```
> 참고: requirements 의 torch 등 AI 패키지는 AI 레포 연결 시에만 필요. 웹 개발만 할 땐 DB 패키지 위주로 설치돼도 무방. 배포용 이미지는 torch가 빠진 `requirements-web.txt`를 쓴다(`Dockerfile` 참고).

## 3. DB 띄우기 (도커 사용 시)
```bash
docker compose up -d db     # 호스트 3307 → 컨테이너 3306 에 MySQL(db: damda)
```
`docker-compose.yml`엔 `db`(MySQL) 외에 이 FastAPI 앱 자체를 띄우는 `api` 서비스도 있다. `api`는 `db`가 healthy해진 뒤 기동되고, 컨테이너 시작 시 `alembic upgrade head`를 자동 실행한다. 로컬에서 `--reload`로 개발할 땐 `db`만 띄우고 아래처럼 앱은 직접 실행하면 된다. 전체(`db`+`api`)를 컨테이너로 띄우는 배포 절차는 [README.md "배포"](README.md#배포) 참고.

## 4. 마이그레이션 (테이블 반영)
모델은 `app/models/` 에 정의돼 있고 `app/models/__init__.py` 에서 전부 import 된다. 마이그레이션 파일은 `alembic/versions/`에 이미 3개 있다(초기 스키마 → HW 컬럼 추가 → `device_connections`/`member` 삭제) — 처음 셋업할 땐 새로 만들 필요 없이 그냥 적용만 하면 된다.
```bash
alembic upgrade head
```
모델을 바꾸면(새 PR 작업 시) `alembic revision --autogenerate -m "설명"` 으로 새 마이그레이션을 추가하고 `alembic upgrade head`로 반영한다. **기존 마이그레이션 파일은 수정하지 말 것** — 항상 새 리비전을 추가한다.

## 5. 개발용 더미 유저 시드
로그인(JWT) 토큰 없이 요청하면 `get_current_user`가 반환하는 유저. (`DEV_USER_ID` 환경변수, README 참고)
```bash
python -m scripts.seed_dev_user
```

## 6. 실행
```bash
uvicorn app.main:app --reload
# http://localhost:8000/docs  ← Swagger 에서 API 확인/테스트
```

## 폴더 구조

최신 폴더 구조와 각 디렉토리 역할은 [README.md "폴더 구조"](README.md#폴더-구조)로 옮겼다.

## 다음 작업 (담당자별)
각자 `app/routers/<도메인>.py` + `app/schemas/<도메인>.py` 를 컨벤션 가이드 4번 템플릿대로 작성 →
`app/main.py` 에 `include_router` 등록. 역할 분담은 역할분담 시트 참고.
