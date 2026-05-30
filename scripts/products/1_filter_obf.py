"""OBF (Open Beauty Facts) CSV 덤프를 K-beauty / 스킨케어로 필터링.

입력:  C:\\damda\\data\\products\\raw\\en.openbeautyfacts.org.products.csv
출력:  C:\\damda\\data\\products\\output\\obf_filtered.csv (Top 100)

실행 (lab PC):
    cd C:\\damda\\data\\products
    python C:\\damda\\AI\\..\\BE\\scripts\\products\\1_filter_obf.py
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


# OBF CSV 의 컬럼이 많아서 필요한 것만 로드 (메모리 절약)
USE_COLS = [
    "code", "product_name", "product_name_en", "product_name_ko",
    "brands", "categories", "categories_tags",
    "ingredients_text", "ingredients_text_en", "ingredients_text_ko",
    "image_url", "image_front_url", "countries", "countries_tags",
    "url",
]

# 한국 시장 표기 (countries 컬럼 여러 형태)
KR_KEYWORDS = ["korea", "south korea", "kr", "한국", "대한민국", "republic-of-korea"]

# 스킨케어 카테고리 키워드 (OBF categories 필드)
SKINCARE_KEYWORDS = [
    "skincare", "skin-care", "skin care", "face-care", "face care",
    "cream", "serum", "toner", "lotion", "essence", "ampoule",
    "moisturizer", "moisturiser", "face-cream", "facial",
    "스킨케어", "세럼", "토너", "에센스", "크림", "앰플", "로션", "수분크림",
]

# 우선순위 K-beauty 브랜드 (소문자 매칭)
PRIORITY_BRANDS = [
    "innisfree", "이니스프리",
    "laneige", "라네즈",
    "etude", "에뛰드",
    "ahc",
    "doctorjart", "닥터자르트", "dr.jart", "dr jart",
    "tonymoly", "토니모리",
    "missha", "미샤",
    "iope", "아이오페",
    "sulwhasoo", "설화수",
    "skinfood", "스킨푸드",
    "klairs", "클레어스",
    "cosrx",
    "isntree", "이즌트리",
    "purito", "퓨리토",
    "round lab", "라운드랩",
    "anua", "아누아",
    "torriden", "토리든",
    "beauty of joseon", "조선미녀",
    "the ordinary",
    "cetaphil", "세타필",
    "cerave", "세라비",
    "neutrogena", "뉴트로지나",
]


def _contains_any(text: str, keywords: list) -> bool:
    if not text:
        return False
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in keywords)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=r"C:\damda\data\products\raw\en.openbeautyfacts.org.products.csv")
    ap.add_argument("--output", default=r"C:\damda\data\products\output\obf_filtered.csv")
    ap.add_argument("--limit", type=int, default=100, help="최종 출력 개수 (기본 100)")
    ap.add_argument("--global-also", action="store_true",
                    help="한국 시장 외 글로벌 K-beauty / 인기 브랜드도 포함")
    ap.add_argument("--lax", action="store_true",
                    help="스킨케어 카테고리 필터 비활성 — 한국 시장 + 전성분 있는 모든 제품")
    args = ap.parse_args()

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"[load] {args.input}")
    df = pd.read_csv(
        args.input,
        sep="\t",
        on_bad_lines="skip",
        usecols=lambda c: c in USE_COLS,
        low_memory=False,
        encoding="utf-8",
    )
    print(f"[load] 전체 행: {len(df):,}")
    print(f"[load] 실제 컬럼: {sorted(df.columns)}")

    # 누락 컬럼은 빈 값으로 보완 (OBF 덤프마다 컬럼 다를 수 있음)
    for col in USE_COLS:
        if col not in df.columns:
            df[col] = ""

    def safe_str(col):
        return df[col].fillna("").astype(str)

    # 1. 한국 시장 필터 (countries 또는 countries_tags 에 KR)
    mask_kr = (
        safe_str("countries").apply(lambda x: _contains_any(x, KR_KEYWORDS))
        | safe_str("countries_tags").apply(lambda x: _contains_any(x, KR_KEYWORDS))
    )
    df_kr = df[mask_kr].copy()
    print(f"[filter] 한국 시장: {len(df_kr):,}")

    # 글로벌 옵션 — K-beauty 브랜드는 한국 시장 아니어도 추가
    if args.global_also:
        mask_kbrand = safe_str("brands").apply(lambda x: _contains_any(x, PRIORITY_BRANDS))
        df_kbrand = df[mask_kbrand & ~mask_kr].copy()
        print(f"[filter] 한국외 K-beauty 브랜드: {len(df_kbrand):,}")
        df_kr = pd.concat([df_kr, df_kbrand], ignore_index=True)
        print(f"[filter] 한국 + K-beauty 합: {len(df_kr):,}")

    def s(col_name):
        return df_kr[col_name].fillna("").astype(str)

    # 2. 스킨케어 카테고리 필터 — 4개 컬럼 어디든 매칭되면 OK
    mask_skin = (
        s("categories").apply(lambda x: _contains_any(x, SKINCARE_KEYWORDS))
        | s("categories_tags").apply(lambda x: _contains_any(x, SKINCARE_KEYWORDS))
        | s("product_name").apply(lambda x: _contains_any(x, SKINCARE_KEYWORDS))
        | s("product_name_en").apply(lambda x: _contains_any(x, SKINCARE_KEYWORDS))
        | s("product_name_ko").apply(lambda x: _contains_any(x, SKINCARE_KEYWORDS))
    )
    df_skin = df_kr[mask_skin].copy()
    print(f"[filter] 스킨케어 (엄격): {len(df_skin):,}")

    # 매칭이 너무 적으면 (10개 미만) 카테고리 필터 완화 — 한국 시장 + 전성분 있는 거 다 포함
    if len(df_skin) < 30 and not args.lax:
        print(f"[filter] 스킨케어 매칭 부족 ({len(df_skin)}) — 카테고리 필터 완화 적용")
        df_skin = df_kr.copy()

    # 3. 전성분 텍스트 있는 것만 (덤프마다 컬럼 다름 — 있는 것 사용)
    ing_cols = [c for c in ["ingredients_text", "ingredients_text_en", "ingredients_text_ko"]
                if c in df_skin.columns]
    if not ing_cols:
        print("[filter] 전성분 컬럼 없음 — 모두 통과")
        df_ing = df_skin.copy()
    else:
        mask_ing = pd.Series([False] * len(df_skin), index=df_skin.index)
        for c in ing_cols:
            mask_ing = mask_ing | df_skin[c].notna()
        df_ing = df_skin[mask_ing].copy()
    print(f"[filter] 전성분 있음: {len(df_ing):,}")

    # 4. 우선순위 정렬: 우선 브랜드 → 이름 길이 (짧은 게 보통 인기 메인 제품)
    df_ing["_priority"] = df_ing["brands"].fillna("").apply(
        lambda x: 1 if _contains_any(x, PRIORITY_BRANDS) else 0
    )
    df_ing["_name_len"] = df_ing["product_name"].fillna("").str.len()
    df_ing = df_ing.sort_values(["_priority", "_name_len"], ascending=[False, True])

    # 5. 중복 제거 (같은 제품명 + 브랜드)
    df_ing = df_ing.drop_duplicates(subset=["product_name", "brands"], keep="first")
    print(f"[dedup] 중복 제거 후: {len(df_ing):,}")

    # 6. Top N
    top = df_ing.head(args.limit).copy()
    top = top.drop(columns=["_priority", "_name_len"], errors="ignore")

    top.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"[save] {out_path}  ({len(top)}행)")
    print()
    print("[sample] 상위 10개:")
    for i, row in top.head(10).iterrows():
        brand = str(row.get("brands") or "?")[:20].ljust(20)
        name = str(row.get("product_name") or "?")[:50]
        print(f"  {brand} | {name}")


if __name__ == "__main__":
    main()
