# 담다 백엔드(FastAPI) 배포용 이미지
FROM python:3.11-slim

WORKDIR /app

# WeasyPrint(PDF 리포트, H.7.1) 런타임 의존성
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libcairo2 \
    && rm -rf /var/lib/apt/lists/*

# 의존성 먼저 설치 (레이어 캐시 활용)
COPY requirements-web.txt .
RUN pip install --no-cache-dir -r requirements-web.txt

# 앱 코드 복사
COPY . .

EXPOSE 8000

# 컨테이너 시작 시: DB 마이그레이션 → 서버 실행
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
