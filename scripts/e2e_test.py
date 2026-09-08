"""전체 API 흐름 E2E 테스트.

전제: docker compose (db + api) 가 떠서 http://localhost:8000 에서 서빙 중이어야 한다.
실행 (BE 루트에서):
    python -m scripts.e2e_test
    BASE_URL=http://localhost:8000 python -m scripts.e2e_test   # URL 바꾸고 싶으면

각 단계 통과/실패를 ✅/❌ 로 찍고, 실패 시 상태코드+응답 본문을 같이 보여준다.
마지막에 총 22개 중 몇 개 통과했는지 요약한다.
"""
from __future__ import annotations

import os
import sys
import uuid

import requests

# Windows 콘솔 기본 cp949 로는 ✅/❌ 를 못 찍어서 UnicodeEncodeError 남 → UTF-8 강제
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000")

results: list[tuple[int, str, bool, str]] = []


def _rand_email() -> str:
    # email-validator 가 .local/.test 같은 RFC 2606 예약 TLD 를 거부하므로 임의 도메인 사용
    return f"e2e_{uuid.uuid4().hex[:12]}@e2e-damda-test.com"


def check(step_no: int, desc: str, passed: bool, detail: str = "") -> bool:
    mark = "✅" if passed else "❌"
    line = f"{mark} [{step_no:2}] {desc}"
    if not passed and detail:
        line += f"\n       -> {detail}"
    print(line)
    results.append((step_no, desc, passed, detail))
    return passed


def main() -> None:
    session = requests.Session()
    session_id: str | None = None
    product_id: str | None = None
    recommend_created = None

    # 1. 회원가입
    email = _rand_email()
    try:
        r = session.post(f"{BASE_URL}/auth/signup", json={
            "email": email, "password": "test1234", "nickname": "e2e테스터",
        })
        ok = r.status_code == 201
        token = r.json().get("access_token") if ok else None
        check(1, "POST /auth/signup -> 201, 토큰 저장", ok, f"status={r.status_code} body={r.text}")
    except requests.RequestException as e:
        check(1, "POST /auth/signup -> 201, 토큰 저장", False, f"요청 자체 실패: {e}")
        token = None

    if token:
        session.headers["Authorization"] = f"Bearer {token}"

    # 2. GET /mypage
    r = session.get(f"{BASE_URL}/mypage")
    check(2, "GET /mypage -> 200", r.status_code == 200, f"status={r.status_code} body={r.text}")

    # 3. PUT /surveys/me
    survey_payload = {
        "skin_type": "복합성",
        "concerns": ["모공", "건조"],
        "allergies": [],
        "preferred_categories": ["보습"],
        "budget_min": 10000,
        "budget_max": 50000,
    }
    r = session.put(f"{BASE_URL}/surveys/me", json=survey_payload)
    check(3, "PUT /surveys/me -> 200", r.status_code == 200, f"status={r.status_code} body={r.text}")

    # 4. GET /surveys/me 저장값 일치
    r = session.get(f"{BASE_URL}/surveys/me")
    if r.status_code == 200:
        body = r.json()
        mismatches = {k: (v, body.get(k)) for k, v in survey_payload.items() if body.get(k) != v}
        check(4, "GET /surveys/me 저장값 일치", not mismatches,
              f"불일치 필드(기대,실제)={mismatches}" if mismatches else "")
    else:
        check(4, "GET /surveys/me 저장값 일치", False, f"status={r.status_code} body={r.text}")

    # 5. POST /scans
    r = session.post(f"{BASE_URL}/scans", json={})
    ok = r.status_code == 201
    if ok:
        session_id = r.json().get("session_id")
    check(5, "POST /scans -> session_id 획득", ok and bool(session_id), f"status={r.status_code} body={r.text}")

    # 6. POST /scans/{id}/analyze-mock
    if session_id:
        r = session.post(f"{BASE_URL}/scans/{session_id}/analyze-mock")
        check(6, "POST /scans/{id}/analyze-mock -> 200", r.status_code == 200, f"status={r.status_code} body={r.text}")
    else:
        check(6, "POST /scans/{id}/analyze-mock -> 200", False, "5번 단계 실패로 session_id 없음 — 스킵")

    # 7. GET /result/{id}
    if session_id:
        r = session.get(f"{BASE_URL}/result/{session_id}")
        check(7, "GET /result/{id} -> 200", r.status_code == 200, f"status={r.status_code} body={r.text}")
    else:
        check(7, "GET /result/{id} -> 200", False, "session_id 없음 — 스킵")

    # 8. GET /care/{id}
    if session_id:
        r = session.get(f"{BASE_URL}/care/{session_id}")
        check(8, "GET /care/{id} -> 200", r.status_code == 200, f"status={r.status_code} body={r.text}")
    else:
        check(8, "GET /care/{id} -> 200", False, "session_id 없음 — 스킵")

    # 9. POST /scans/{id}/recommend
    if session_id:
        r = session.post(f"{BASE_URL}/scans/{session_id}/recommend")
        ok = r.status_code == 200
        if ok:
            recommend_created = r.json()
        check(9, "POST /scans/{id}/recommend -> 200", ok, f"status={r.status_code} body={r.text}")
    else:
        check(9, "POST /scans/{id}/recommend -> 200", False, "session_id 없음 — 스킵")

    # 10. GET /scans/{id}/recommend 재계산 없이 동일 결과
    if session_id and recommend_created is not None:
        r = session.get(f"{BASE_URL}/scans/{session_id}/recommend")
        ok = r.status_code == 200
        same = ok and r.json() == recommend_created
        check(10, "GET /scans/{id}/recommend 재계산 없이 동일 결과", same,
              f"status={r.status_code} 생성직후={recommend_created} 재조회={r.json() if ok else r.text}")
    else:
        check(10, "GET /scans/{id}/recommend 재계산 없이 동일 결과", False, "9번 단계 실패로 스킵")

    # 11. GET /history 방금 세션 포함
    r = session.get(f"{BASE_URL}/history")
    if r.status_code == 200 and session_id:
        body = r.json()
        included = any(x.get("session_id") == session_id for x in body)
        check(11, "GET /history 방금 세션 포함", included, f"session_id={session_id} 가 결과에 없음: {body}")
    else:
        check(11, "GET /history 방금 세션 포함", False, f"status={r.status_code} body={r.text}")

    # 12. GET /report 방금 세션 포함
    r = session.get(f"{BASE_URL}/report")
    if r.status_code == 200 and session_id:
        body = r.json()
        included = any(x.get("session_id") == session_id for x in body)
        check(12, "GET /report 방금 세션 포함", included, f"session_id={session_id} 가 결과에 없음: {body}")
    else:
        check(12, "GET /report 방금 세션 포함", False, f"status={r.status_code} body={r.text}")

    # 13. GET /report/{id}
    if session_id:
        r = session.get(f"{BASE_URL}/report/{session_id}")
        check(13, "GET /report/{id} -> 200", r.status_code == 200, f"status={r.status_code} body={r.text}")
    else:
        check(13, "GET /report/{id} -> 200", False, "session_id 없음 — 스킵")

    # 14. GET /report/{id}/pdf
    if session_id:
        r = session.get(f"{BASE_URL}/report/{session_id}/pdf")
        content_type = r.headers.get("content-type", "")
        ok = (r.status_code == 200
              and content_type.startswith("application/pdf")
              and r.content[:4] == b"%PDF")
        check(14, "GET /report/{id}/pdf -> 200, application/pdf, %PDF 매직바이트", ok,
              f"status={r.status_code} content-type={content_type} magic={r.content[:8]!r}")
    else:
        check(14, "GET /report/{id}/pdf -> 200, application/pdf, %PDF 매직바이트", False, "session_id 없음 — 스킵")

    # 15. GET /products
    r = session.get(f"{BASE_URL}/products")
    ok = r.status_code == 200
    if ok:
        products = r.json()
        product_id = products[0]["product_id"] if products else None
    check(15, "GET /products -> 200", ok, f"status={r.status_code} body={r.text[:300]}")

    # 16. POST /products/{id}/wishlist
    if product_id:
        session.delete(f"{BASE_URL}/products/{product_id}/wishlist")  # 이전 실행 잔여물 있으면 정리(없으면 404, 무시)
        r = session.post(f"{BASE_URL}/products/{product_id}/wishlist")
        check(16, "POST /products/{id}/wishlist -> 201", r.status_code == 201, f"status={r.status_code} body={r.text}")
    else:
        check(16, "POST /products/{id}/wishlist -> 201", False, "product_id 없음(제품 0건?) — 스킵")

    # 17. GET /wishlist 방금 찜한 항목 포함
    r = session.get(f"{BASE_URL}/wishlist")
    if r.status_code == 200 and product_id:
        body = r.json()
        included = any(x.get("product_id") == product_id for x in body)
        check(17, "GET /wishlist 방금 찜한 항목 포함", included, f"product_id={product_id} 가 결과에 없음: {body}")
    else:
        check(17, "GET /wishlist 방금 찜한 항목 포함", False, f"status={r.status_code} body={r.text}")

    # 18. DELETE /products/{id}/wishlist
    if product_id:
        r = session.delete(f"{BASE_URL}/products/{product_id}/wishlist")
        check(18, "DELETE /products/{id}/wishlist -> 204", r.status_code == 204, f"status={r.status_code} body={r.text}")
    else:
        check(18, "DELETE /products/{id}/wishlist -> 204", False, "product_id 없음 — 스킵")

    # 19. GET /wishlist 찜취소 반영 확인 (해당 항목 없어야 함)
    r = session.get(f"{BASE_URL}/wishlist")
    if r.status_code == 200 and product_id:
        body = r.json()
        excluded = not any(x.get("product_id") == product_id for x in body)
        check(19, "GET /wishlist 찜취소 반영 확인", excluded, f"product_id={product_id} 가 여전히 있음: {body}")
    else:
        check(19, "GET /wishlist 찜취소 반영 확인", False, f"status={r.status_code} body={r.text}")

    # ── 예외 케이스 ──

    # 20. GET /result/존재하지않는id -> 404
    fake_id = f"does-not-exist-{uuid.uuid4().hex[:8]}"
    r = session.get(f"{BASE_URL}/result/{fake_id}")
    check(20, "GET /result/존재하지않는id -> 404", r.status_code == 404, f"status={r.status_code} body={r.text}")

    # 21. Authorization 헤더 없이 GET /mypage -> 401
    r = requests.get(f"{BASE_URL}/mypage")   # session 대신 별도 요청 (Authorization 헤더 없음)
    check(21, "Authorization 없이 GET /mypage -> 401", r.status_code == 401, f"status={r.status_code} body={r.text}")

    # 22. 같은 제품 두 번 찜 -> 두 번째는 409
    if product_id:
        r1 = session.post(f"{BASE_URL}/products/{product_id}/wishlist")
        r2 = session.post(f"{BASE_URL}/products/{product_id}/wishlist")
        ok = r1.status_code == 201 and r2.status_code == 409
        check(22, "같은 제품 중복 찜 -> 409", ok,
              f"1차 status={r1.status_code} 2차 status={r2.status_code} 2차 body={r2.text}")
        session.delete(f"{BASE_URL}/products/{product_id}/wishlist")   # 테스트 잔여물 정리
    else:
        check(22, "같은 제품 중복 찜 -> 409", False, "product_id 없음 — 스킵")

    # ── 요약 ──
    total = len(results)
    passed = sum(1 for *_r, ok, _d in results if ok)
    print()
    print(f"=== 요약: {passed}/{total} 통과 ===")
    if passed < total:
        print("실패한 단계:")
        for step_no, desc, ok, detail in results:
            if not ok:
                print(f"  [{step_no}] {desc}" + (f" — {detail}" if detail else ""))

    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
