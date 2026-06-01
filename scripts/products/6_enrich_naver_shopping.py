"""네이버 쇼핑 검색 API 로 가격 / 이미지 / 구매처 URL 보강.

네이버 개발자 센터에서 발급:
  1. https://developers.naver.com/apps/#/register
  2. 애플리케이션 이름 입력, 사용 API 에 "검색" 추가
  3. 비로그인 오픈 API 서비스 환경: WEB 설정 (URL: localhost)
  4. 등록 후 Client ID / Client Secret 발급
  5. 일 25,000 호출 무료, 초당 10건 제한

응답 필드 (각 item):
  title, link, image, lprice, hprice, mallName, productId, productType, brand, maker, category1-4

실행:
    set NAVER_CLIENT_ID=<id>
    set NAVER_CLIENT_SECRET=<secret>
    python BE/scripts/products/6_enrich_naver_shopping.py --input data/products_curated.json --output data/products_curated.json

옵션:
    --input PATH       입력 JSON (products 키 안에 리스트)
    --output PATH      출력 (같으면 in-place 덮어쓰기)
    --max-items N      디버그용 상한
    --skip-priced      이미 가격이 있는 거 스킵 (이어서 처리)
    --rate-per-sec N   초당 호출 수 (기본 3, 안전 마진)

결과:
    각 제품에 image_url, price_range, purchase_url, naver_avg_price 채워짐
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from pathlib import Path
from typing import Dict, List, Optional

import requests


URL = "https://openapi.naver.com/v1/search/shop.json"


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--max-items", type=int, default=None)
    ap.add_argument("--skip-priced", action="store_true",
                    help="이미 image_url 이 있는 거 스킵 (이어 처리)")
    ap.add_argument("--retry-failed", action="store_true",
                    help="image_url 없는 것만 재시도 (1차 실패한 것만)")
    ap.add_argument("--rate-per-sec", type=float, default=3.0)
    ap.add_argument("--display", type=int, default=3, help="제품당 검색 결과 개수")
    return ap.parse_args()


def price_to_range(p: int) -> str:
    if p <= 0:
        return "?"
    if p < 10000:
        return "1만원 미만"
    if p < 30000:
        return "1-3만원"
    if p < 50000:
        return "3-5만원"
    if p < 100000:
        return "5-10만원"
    return "10만원+"


def strip_html(s: str) -> str:
    """네이버는 검색어 매치 부분에 <b></b> 박혀있음 — 제거."""
    return re.sub(r"<.*?>", "", s or "")


def search_one(query: str, client_id: str, client_secret: str, display: int = 3) -> List[dict]:
    """검색 → items 리스트 반환. 실패 시 빈 리스트."""
    try:
        r = requests.get(
            URL,
            headers={
                "X-Naver-Client-Id": client_id,
                "X-Naver-Client-Secret": client_secret,
            },
            params={"query": query, "display": display, "sort": "sim"},
            timeout=10,
        )
        r.raise_for_status()
        return r.json().get("items", [])
    except Exception as e:
        print(f"    검색 실패 ({query}): {e}")
        return []


def best_match(items: List[dict], brand_lower: str, name_lower: str) -> Optional[dict]:
    """검색 결과 중 브랜드/이름 매칭이 강한 것 선택."""
    if not items:
        return None
    # 1) 브랜드와 이름 토큰 둘 다 들어있는 거
    name_tokens = [t for t in name_lower.split() if len(t) > 1]
    scored = []
    for it in items:
        title = strip_html(it.get("title", "")).lower()
        brand_in_title = brand_lower and brand_lower in title
        matched_tokens = sum(1 for t in name_tokens if t in title)
        scored.append((it, (1 if brand_in_title else 0, matched_tokens)))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[0][0] if scored else None


def enrich_product(p: dict, client_id: str, client_secret: str, display: int) -> bool:
    """제품 1개 보강. 채워졌으면 True.
    1차: "brand name_kr" 풀텍스트
    2차 (실패시): "name_kr 의 앞 3토큰" 만
    3차 (실패시): "brand" 만 + 카테고리 키워드
    """
    brand = (p.get("brand") or "").strip()
    name = (p.get("name_kr") or p.get("name_en") or "").strip()
    if not name:
        return False

    queries: List[str] = []
    queries.append(f"{brand} {name}".strip())
    # fallback 1: 이름 앞 3토큰 (브랜드 빼고)
    tokens = [t for t in name.split() if len(t) > 1]
    if len(tokens) > 3:
        queries.append(" ".join(tokens[:3]))
    # fallback 2: 브랜드 + 카테고리 (첫번째) + 서브카테고리
    cats = p.get("category", [])
    sub = p.get("subcategory", "")
    if brand and (cats or sub):
        kw = (cats[0] if cats else "") + " " + (sub if sub and sub != "?" else "")
        queries.append(f"{brand} {kw.strip()}".strip())

    items = []
    used_query = ""
    for q in queries:
        items = search_one(q, client_id, client_secret, display=display)
        if items:
            used_query = q
            break
    if not items:
        return False

    pick = best_match(items, brand.lower(), name.lower())
    if not pick:
        return False
    if used_query != queries[0]:
        p["naver_query_used"] = used_query  # 디버그용 — 어떤 쿼리로 매칭됐는지

    # 가격 — 검색 결과 평균
    prices = []
    for it in items:
        lp = it.get("lprice")
        if lp and str(lp).isdigit():
            prices.append(int(lp))
    avg = sum(prices) // len(prices) if prices else 0

    # 보강 (덮어쓰지 말고 빈 값일 때만 채우기)
    if not p.get("image_url"):
        p["image_url"] = pick.get("image", "")
    if not p.get("purchase_url"):
        p["purchase_url"] = pick.get("link", "")
    if avg > 0:
        p["naver_avg_price"] = avg
        if p.get("price_range") in (None, "", "?"):
            p["price_range"] = price_to_range(avg)
    # 메타
    if pick.get("brand"):
        p.setdefault("naver_brand", pick.get("brand"))
    if pick.get("category2"):
        p.setdefault("naver_category", pick.get("category2"))
    return True


def main():
    args = parse_args()
    client_id = os.getenv("NAVER_CLIENT_ID")
    client_secret = os.getenv("NAVER_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise SystemExit("NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 환경변수 필요")

    data = json.loads(args.input.read_text(encoding="utf-8"))
    products = data.get("products") if isinstance(data, dict) else data
    if not isinstance(products, list):
        raise SystemExit(f"입력 포맷 인식 불가: {args.input}")

    targets = products
    if args.skip_priced:
        targets = [p for p in products if not p.get("naver_avg_price") and p.get("price_range") in (None, "", "?")]
    if args.retry_failed:
        targets = [p for p in products if not p.get("image_url")]
        print(f"    재시도 모드: image_url 비어있는 {len(targets)}건만 처리")
    if args.max_items:
        targets = targets[: args.max_items]
    print(f"[1] 입력 {len(products)}건 중 보강 대상: {len(targets)}")

    delay = 1.0 / max(0.5, args.rate_per_sec)
    enriched = 0
    failed = 0
    for i, p in enumerate(targets, 1):
        ok = enrich_product(p, client_id, client_secret, args.display)
        if ok:
            enriched += 1
        else:
            failed += 1
        if i % 20 == 0:
            print(f"    {i}/{len(targets)} (성공 {enriched} / 실패 {failed})")
        time.sleep(delay)

    print(f"[2] 보강 완료 — 성공 {enriched}, 실패 {failed}")

    if isinstance(data, dict):
        data["products"] = products
        out = data
    else:
        out = products

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[3] 저장: {args.output}")

    # 간단 통계
    from collections import Counter
    pr = Counter(p.get("price_range", "?") for p in products)
    print(f"    가격대 분포: {dict(pr.most_common())}")


if __name__ == "__main__":
    main()
