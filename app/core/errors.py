"""공통 에러 처리 (인프라 8).

모든 에러 응답을 {detail, code} 형태로 통일하고, 예상 못한 예외/DB 오류의
내부 정보 노출을 막는다. 스택트레이스는 서버 로그에만 남긴다.

응답 포맷:
    { "detail": "사람이 읽을 메시지", "code": "NOT_FOUND" }
    (422 검증 오류는 "errors": [{field, message}] 추가)
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger("damda")

# HTTP 상태코드 → 에러 코드 문자열
STATUS_CODE = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    409: "CONFLICT",
    422: "VALIDATION_ERROR",
    500: "INTERNAL",
}


def _code_for(status: int) -> str:
    return STATUS_CODE.get(status, "ERROR")


def _error(status: int, detail, code: str | None = None, **extra) -> JSONResponse:
    body = {"detail": detail, "code": code or _code_for(status)}
    body.update(extra)
    return JSONResponse(status_code=status, content=body)


def register_exception_handlers(app: FastAPI) -> None:
    """앱에 전역 예외 핸들러를 등록한다. main.py 에서 1회 호출."""

    @app.exception_handler(HTTPException)
    async def _http(request: Request, exc: HTTPException):
        # 라우터의 raise HTTPException(404, "...") 를 표준 포맷으로 감싼다
        return _error(exc.status_code, exc.detail, getattr(exc, "code", None))

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        errors = [
            {
                "field": ".".join(str(x) for x in e["loc"][1:]) or str(e["loc"][-1]),
                "message": e["msg"],
            }
            for e in exc.errors()
        ]
        return _error(422, "입력값이 올바르지 않습니다", "VALIDATION_ERROR", errors=errors)

    @app.exception_handler(SQLAlchemyError)
    async def _db(request: Request, exc: SQLAlchemyError):
        logger.exception("DB error at %s %s", request.method, request.url.path)
        return _error(500, "데이터 처리 중 오류가 발생했습니다", "DB_ERROR")

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        logger.exception("Unhandled error at %s %s", request.method, request.url.path)
        return _error(500, "서버 내부 오류가 발생했습니다", "INTERNAL")
