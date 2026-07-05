"""제품 데이터 시드: data/products_curated.json → products 테이블.

추천/필터 테스트용 제품을 DB 에 적재한다. id 기준이라 여러 번 돌려도 중복 안 생김.

실행 (BE 루트에서, venv 활성화 상태):
    python -m scripts.seed_products
옵션:
    --file data/products_curated.json   입력 JSON
    --update                            기존 제품도 최신 값으로 덮어씀
"""
from __future__ import annotations

import argparse
import json

from app.core.database import SessionLocal
from app.models.product import Product


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default="data/products_curated.json")
    ap.add_argument("--update", action="store_true", help="기존 제품도 덮어씀")
    args = ap.parse_args()

    with open(args.file, encoding="utf-8") as f:
        data = json.load(f)
    items = data.get("products", data) if isinstance(data, dict) else data

    db = SessionLocal()
    inserted = updated = skipped = 0
    try:
        for p in items:
            pid = p.get("id")
            if not pid or not p.get("name_kr"):
                continue  # 필수값 없으면 스킵

            fields = dict(
                name_kr=p.get("name_kr"),
                name_en=p.get("name_en"),
                brand=p.get("brand"),
                category=p.get("category"),
                subcategory=p.get("subcategory"),
                ingredients=p.get("main_ingredients"),   # [{inci, kr}]
                for_skin=p.get("for_skin"),
                tags=p.get("tags"),
                price=p.get("price"),
                price_range=p.get("price_range"),
                image_url=p.get("image_url"),
                purchase_url=p.get("purchase_url"),
                alcohol_free=bool(p.get("alcohol_free", False)),
                fragrance_free=bool(p.get("fragrance_free", False)),
            )

            existing = db.query(Product).filter(Product.product_id == pid).first()
            if existing:
                if args.update:
                    for k, v in fields.items():
                        setattr(existing, k, v)
                    updated += 1
                else:
                    skipped += 1
                continue

            db.add(Product(product_id=pid, **fields))
            inserted += 1

        db.commit()
    finally:
        db.close()

    print(f"제품 시드 완료 — 추가 {inserted} / 수정 {updated} / 건너뜀 {skipped} / 파일 {len(items)}개")


if __name__ == "__main__":
    main()
