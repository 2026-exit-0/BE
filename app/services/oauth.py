"""소셜 로그인 — provider 인가코드 → 토큰 → 프로필 (명세 C.1.2).

반환 형태 통일: {"social_id": str, "email": str|None, "nickname": str|None}
실패 시 provider 의 실제 에러 응답을 서버 로그(damda)에 남겨 디버깅을 돕는다.
"""
from __future__ import annotations

import logging

import httpx
from fastapi import HTTPException

from app.core.config import settings

logger = logging.getLogger("damda")


def exchange_kakao(code: str, redirect_uri: str) -> dict:
    data = {
        "grant_type": "authorization_code",
        "client_id": settings.KAKAO_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "code": code,
    }
    if settings.KAKAO_CLIENT_SECRET:
        data["client_secret"] = settings.KAKAO_CLIENT_SECRET

    tok = httpx.post("https://kauth.kakao.com/oauth/token", data=data, timeout=10.0)
    if tok.status_code != 200:
        logger.warning("Kakao token error %s: %s", tok.status_code, tok.text)
        raise HTTPException(status_code=401, detail="카카오 인증에 실패했습니다")

    access = tok.json().get("access_token")
    me = httpx.get("https://kapi.kakao.com/v2/user/me",
                   headers={"Authorization": f"Bearer {access}"}, timeout=10.0)
    if me.status_code != 200:
        logger.warning("Kakao profile error %s: %s", me.status_code, me.text)
        raise HTTPException(status_code=401, detail="카카오 인증에 실패했습니다")

    j = me.json()
    acc = j.get("kakao_account", {})
    return {
        "social_id": str(j.get("id")),
        "email": acc.get("email"),
        "nickname": (acc.get("profile") or {}).get("nickname"),
    }


def exchange_google(code: str, redirect_uri: str) -> dict:
    data = {
        "grant_type": "authorization_code",
        "client_id": settings.GOOGLE_CLIENT_ID,
        "client_secret": settings.GOOGLE_CLIENT_SECRET,
        "redirect_uri": redirect_uri,
        "code": code,
    }
    tok = httpx.post("https://oauth2.googleapis.com/token", data=data, timeout=10.0)
    if tok.status_code != 200:
        logger.warning("Google token error %s: %s", tok.status_code, tok.text)
        raise HTTPException(status_code=401, detail="구글 인증에 실패했습니다")

    access = tok.json().get("access_token")
    me = httpx.get("https://www.googleapis.com/oauth2/v2/userinfo",
                   headers={"Authorization": f"Bearer {access}"}, timeout=10.0)
    if me.status_code != 200:
        logger.warning("Google profile error %s: %s", me.status_code, me.text)
        raise HTTPException(status_code=401, detail="구글 인증에 실패했습니다")

    j = me.json()
    return {
        "social_id": str(j.get("id")),
        "email": j.get("email"),
        "nickname": j.get("name"),
    }
