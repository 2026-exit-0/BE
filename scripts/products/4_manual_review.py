"""인터랙티브 라벨링 — OBF 데이터를 우리 스키마로 변환.

각 제품에 대해 사용자가 입력 (또는 자동 추정 확인):
  - category (보습/미백/진정/모공/탄력)
  - subcategory (토너/세럼/크림/팩/클렌저)
  - for_skin (건성/지성/복합성/민감성/중성)
  - fragrance_free / alcohol_free
  - price_range

자동 추정 (성분 텍스트 보고):
  - category: 활성 성분 키워드 매칭
  - subcategory: 제품명 키워드 매칭
  - fragrance_free: "Fragrance" 키워드 부재
  - alcohol_free: "Alcohol Denat" 키워드 부재

진행 중 저장: 매 5개 마다 자동 save. Ctrl+C 로 중단 시에도 진행분 보존.
다시 실행하면 중단 지점부터 이어서.

실행:
    python ...\\BE\\scripts\\products\\4_manual_review.py
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Optional

import pandas as pd


# 자동 카테고리 추정 키워드 (소문자, 영문/한글)
CATEGORY_KEYWORDS = {
    "보습": ["hyaluronic", "ceramide", "glycerin", "squalane", "panthenol", "trehalose",
            "shea butter", "moistur", "hydrat", "히알루론산", "세라마이드", "보습", "수분"],
    "미백": ["niacinamide", "ascorbic", "ascorbyl", "arbutin", "kojic", "tranexamic",
            "vitamin c", "brighten", "white", "나이아신", "비타민c", "미백", "톤업"],
    "진정": ["centella", "madecass", "aloe", "allantoin", "panthenol", "houttuynia",
            "chamomile", "calendula", "tea tree", "soothing", "병풀", "알로에", "진정", "수딩"],
    "모공": ["bha", "salicylic", "glycolic", "kaolin", "bentonite", "charcoal",
            "pore", "exfoli", "모공", "각질", "필링"],
    "탄력": ["adenosine", "retinol", "peptide", "collagen", "argireline", "egf",
            "firming", "anti-aging", "elasticity", "wrinkle", "탄력", "주름", "에이징"],
}

SUBCATEGORY_KEYWORDS = {
    "토너": ["toner", "토너"],
    "세럼": ["serum", "ampoule", "essence", "세럼", "앰플", "에센스"],
    "크림": ["cream", "moisturiser", "moisturizer", "크림"],
    "로션": ["lotion", "emulsion", "로션", "에멀젼"],
    "팩": ["mask", "pack", "팩", "마스크"],
    "클렌저": ["cleanser", "cleansing", "foam", "오일", "클렌저", "클렌징"],
    "선크림": ["sunscreen", "spf", "uv", "선크림", "자외선"],
    "아이크림": ["eye cream", "eye serum", "아이크림"],
}

SKIN_TYPES = ["건성", "지성", "복합성", "민감성", "중성"]


def _safe_str(x) -> str:
    """NaN / float / None → 빈 문자열 안전 변환."""
    if x is None:
        return ""
    try:
        if pd.isna(x):
            return ""
    except (TypeError, ValueError):
        pass
    return str(x)


def auto_category(ing_text) -> list:
    """성분 텍스트 보고 카테고리 추정 (multi-label)."""
    text = _safe_str(ing_text)
    if not text:
        return []
    text_lower = text.lower()
    matched = []
    for cat, kws in CATEGORY_KEYWORDS.items():
        if any(kw in text_lower for kw in kws):
            matched.append(cat)
    return matched


def auto_subcategory(name) -> str:
    """제품명 보고 subcategory 추정."""
    text = _safe_str(name)
    if not text:
        return "?"
    text_lower = text.lower()
    for sub, kws in SUBCATEGORY_KEYWORDS.items():
        if any(kw in text_lower for kw in kws):
            return sub
    return "?"


def auto_fragrance_free(ing_text) -> bool:
    """전성분에 향료 없으면 무향."""
    text = _safe_str(ing_text)
    if not text:
        return False
    keywords = ["fragrance", "parfum", "perfume", "향료"]
    text_lower = text.lower()
    return not any(kw in text_lower for kw in keywords)


def auto_alcohol_free(ing_text) -> bool:
    """전성분에 알코올 (변성알코올) 없으면 무알코올."""
    text = _safe_str(ing_text)
    if not text:
        return False
    text_lower = text.lower()
    if "alcohol denat" in text_lower or "변성알코올" in text_lower:
        return False
    if "ethanol" in text_lower and "phenoxy" not in text_lower:
        return False
    return True


def prompt(msg: str, default: str = "", choices: Optional[list] = None) -> str:
    """사용자 입력 — Enter 누르면 default."""
    hint = f" [{default}]" if default else ""
    if choices:
        hint += f" ({'/'.join(choices)})"
    val = input(f"{msg}{hint}: ").strip()
    return val or default


def review_one(row: pd.Series, idx: int, total: int, auto: bool = False) -> dict:
    """한 제품 인터랙티브 라벨링."""
    name = _safe_str(row.get("product_name")) or "?"
    brand = _safe_str(row.get("brands")) or "?"
    ing_en = _safe_str(row.get("ingredients_text_en")) or _safe_str(row.get("ingredients_text"))
    ing_kor = _safe_str(row.get("main_ingredients_kor"))

    print(f"\n{'=' * 60}")
    print(f"[{idx + 1}/{total}] {brand}")
    print(f"  {name}")
    print(f"  성분 (top): {ing_kor[:100]}")
    risky_text = _safe_str(row.get("risky_ingredients_kor")) or _safe_str(row.get("risky_ingredients"))
    print(f"  위험성분 포함: {'⚠️ ' + risky_text[:80] if row.get('has_risky') else '✓ 안전'}")
    print()

    # 자동 추정
    cats = auto_category(ing_en)
    sub = auto_subcategory(name)
    ff = auto_fragrance_free(ing_en)
    af = auto_alcohol_free(ing_en)

    if auto:
        # 자동 모드 — 추정값 그대로 사용
        cat_str = ",".join(cats) or "보습"
        sub_str = sub
        skin_str = "중성,건성,지성,복합성"  # 광범위 — 추천에서 score 로 차등
        ff_str = "y" if ff else "n"
        af_str = "y" if af else "n"
        price_str = "?"
        note_str = ""
    else:
        # 인터랙티브 모드
        cat_str = prompt(f"카테고리 (comma)", default=",".join(cats) or "보습")
        sub_str = prompt(f"세부", default=sub)
        skin_str = prompt(f"적합 피부타입 (comma)", default="중성,건성")
        ff_str = prompt(f"무향?", default="y" if ff else "n", choices=["y", "n"])
        af_str = prompt(f"무알코올?", default="y" if af else "n", choices=["y", "n"])
        price_str = prompt(f"가격대 (예: 2만원대)", default="?")
        note_str = prompt(f"메모 (옵션)", default="")

    # 모든 row 필드는 _safe_str 로 NaN 안전 처리
    name_ko = _safe_str(row.get("product_name_ko")) or name
    name_en_field = _safe_str(row.get("product_name_en")) or name
    barcode = _safe_str(row.get("code"))
    main_ings_raw = _safe_str(row.get("main_ingredients"))
    main_ings_kor = _safe_str(row.get("main_ingredients_kor"))
    risky_kor = _safe_str(row.get("risky_ingredients_kor"))
    image = _safe_str(row.get("image_front_url")) or _safe_str(row.get("image_url"))
    url = _safe_str(row.get("url"))

    return {
        "id": f"P{idx + 1:03d}",
        "name_kr": name_ko,
        "name_en": name_en_field,
        "brand": brand,
        "barcode": barcode,
        "category": [c.strip() for c in cat_str.split(",") if c.strip()],
        "subcategory": sub_str,
        "for_skin": [s.strip() for s in skin_str.split(",") if s.strip() in SKIN_TYPES],
        "main_ingredients": [
            {"inci": en.strip(), "kr": kr.strip()}
            for en, kr in zip(main_ings_raw.split("|"), main_ings_kor.split("|"))
            if en.strip()
        ][:8],
        "tags": ["저자극"] if not row.get("has_risky") else ["주의성분포함"],
        "fragrance_free": ff_str == "y",
        "alcohol_free": af_str == "y",
        "risky_ingredients": risky_kor.split("|") if risky_kor else [],
        "price_range": price_str,
        "image_url": image,
        "obf_url": url,
        "source": "OBF + auto" if auto else "OBF + manual",
        "note": note_str,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=r"C:\damda\data\products\output\obf_localized.csv")
    ap.add_argument("--output", default=r"C:\damda\data\products\output\products.json")
    ap.add_argument("--max", type=int, default=50, help="최대 라벨링 개수 (기본 50)")
    ap.add_argument("--resume", action="store_true", help="중단 지점부터 이어서")
    ap.add_argument("--auto", action="store_true",
                    help="자동 모드 — 사용자 입력 없이 추정값 그대로 저장 (시연 prototype 용)")
    args = ap.parse_args()

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # 기존 진행분 로드 (resume)
    products = []
    if args.resume and out_path.exists():
        existing = json.loads(out_path.read_text(encoding="utf-8"))
        products = existing.get("products", [])
        print(f"[resume] 기존 {len(products)} 제품 로드")

    df = pd.read_csv(args.input, encoding="utf-8-sig").head(args.max)

    start_idx = len(products)
    for idx in range(start_idx, len(df)):
        try:
            p = review_one(df.iloc[idx], idx, len(df), auto=args.auto)
            products.append(p)
        except (KeyboardInterrupt, EOFError):
            print("\n[중단] 진행분 저장 후 종료")
            break

        # 매 5개마다 자동 저장
        if (idx + 1) % 5 == 0:
            out_path.write_text(
                json.dumps({"version": "0.1", "products": products}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"\n[autosave] {len(products)}/{len(df)}")

    # 최종 저장
    out_path.write_text(
        json.dumps({"version": "0.1", "products": products}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n[save] {out_path}  ({len(products)} 제품)")


if __name__ == "__main__":
    main()
