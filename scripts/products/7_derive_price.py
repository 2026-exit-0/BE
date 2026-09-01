"""price_range(구간 문자열) → 숫자 price(원) 파생.

추천/예산 필터(D.1.6, I.2.2)에 쓸 숫자 가격을 구간 대표값(midpoint)으로 채운다.
※ 대표값이라 실제가와 다를 수 있음. 정확한 가격이 필요하면
   6_enrich_naver_shopping.py (네이버 쇼핑 API) 로 실제가를 받아 덮어쓰면 된다.

실행 (BE 루트에서):
    python scripts/products/7_derive_price.py
    python scripts/products/7_derive_price.py --input data/products_curated.json --output data/products_curated.json
"""
from __future__ import annotations

import argparse
import json

# 구간 → 대표 가격(원). 필요시 값만 조정하면 된다.
BUCKET_PRICE = {
    "1만원 미만": 8000,
    "1-3만원": 20000,
    "3-5만원": 40000,
    "5-10만원": 75000,
    "10만원+": 120000,
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="data/products_curated.json")
    ap.add_argument("--output", default="data/products_curated.json")
    ap.add_argument("--overwrite", action="store_true",
                    help="이미 price 가 있어도 덮어씀 (기본: 있으면 건너뜀)")
    args = ap.parse_args()

    with open(args.input, encoding="utf-8") as f:
        data = json.load(f)
    products = data.get("products", data) if isinstance(data, dict) else data

    filled, skipped, unmatched = 0, 0, []
    for p in products:
        if p.get("price") and not args.overwrite:
            skipped += 1
            continue
        pr = str(p.get("price_range", "")).strip()
        price = BUCKET_PRICE.get(pr)
        if price is None:
            unmatched.append(pr)
            continue
        p["price"] = price
        filled += 1

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"price 채움: {filled}개 / 건너뜀(이미 있음): {skipped}개 / 전체: {len(products)}개")
    if unmatched:
        print(f"⚠ 매핑 안 된 price_range 값: {sorted(set(unmatched))}")
    print(f"저장: {args.output}")


if __name__ == "__main__":
    main()
