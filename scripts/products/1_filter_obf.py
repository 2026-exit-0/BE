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
    "mask", "exfoliat", "sunscreen", "spf",
    "스킨케어", "세럼", "토너", "에센스", "크림", "앰플", "로션", "수분크림",
    "마스크", "팩", "선크림",
]

# 명백히 비-skincare — 제외 키워드 (product_name / brands / categories 어디든 매칭되면 제외)
EXCLUDE_KEYWORDS = [
    "shampoo", "conditioner", "hair-care", "hair care", "hair color", "hair dye",
    "샴푸", "린스", "트리트먼트",
    "deodorant", "antiperspirant", "데오드란트",
    "perfume", "fragrance", "eau de", "cologne", "향수",
    "shaving", "shave", "razor", "razors", "면도",
    "baby", "babies", "infant", "유아", "아기",
    "toothpaste", "dental", "mouth", "치약", "구강",
    "nail", "manicure", "polish", "네일",
    "lipstick", "lip color", "립스틱",
    "mascara", "마스카라", "eyeliner", "아이라이너",
    "foundation", "concealer", "파운데이션", "컨실러",
    "pet", "pets", "dog", "cat", "반려",
    "household", "laundry", "detergent", "세제",
    "tampon", "pad", "feminine",
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

    def s(col, frame=None):
        f = frame if frame is not None else df
        return f[col].fillna("").astype(str)

    # 0. 필수 컬럼 NaN 제거 — product_name 또는 ingredients_text 없으면 의미 없음
    n_before = len(df)
    df = df[(df["product_name"].notna()) & (df["product_name"].astype(str).str.strip() != "")
            & (df["ingredients_text"].notna()) & (df["ingredients_text"].astype(str).str.strip() != "")]
    df = df.copy()
    print(f"[filter] 이름/성분 있는 것: {n_before:,} → {len(df):,}")

    # 0.5. 명백히 비-skincare 제외 (shampoo / baby / perfume / lipstick 등)
    n_before = len(df)
    exclude_mask = (
        s("product_name").apply(lambda x: _contains_any(x, EXCLUDE_KEYWORDS))
        | s("categories").apply(lambda x: _contains_any(x, EXCLUDE_KEYWORDS))
        | s("categories_tags").apply(lambda x: _contains_any(x, EXCLUDE_KEYWORDS))
    )
    df = df[~exclude_mask].copy()
    print(f"[filter] 비-skincare 제외: {n_before:,} → {len(df):,}")

    # 1. 한국 시장 필터
    mask_kr = (
        s("countries").apply(lambda x: _contains_any(x, KR_KEYWORDS))
        | s("countries_tags").apply(lambda x: _contains_any(x, KR_KEYWORDS))
    )
    df_kr = df[mask_kr].copy()
    print(f"[filter] 한국 시장: {len(df_kr):,}")

    # 한국 시장만으로 부족하면 자동으로 글로벌 K-beauty 브랜드 추가
    auto_global = (len(df_kr) < 50) or args.global_also
    if auto_global:
        mask_kbrand = s("brands").apply(lambda x: _contains_any(x, PRIORITY_BRANDS))
        df_kbrand = df[mask_kbrand & ~mask_kr].copy()
        print(f"[filter] 한국외 K-beauty / 인기 브랜드: {len(df_kbrand):,}")
        df_kr = pd.concat([df_kr, df_kbrand], ignore_index=True)
        print(f"[filter] 한국 + 글로벌 합: {len(df_kr):,}")

    # 2. 스킨케어 카테고리 매칭 — 우선 strict 매칭만 별도 라벨
    skincare_mask = (
        df_kr["categories"].fillna("").astype(str).apply(lambda x: _contains_any(x, SKINCARE_KEYWORDS))
        | df_kr["categories_tags"].fillna("").astype(str).apply(lambda x: _contains_any(x, SKINCARE_KEYWORDS))
        | df_kr["product_name"].fillna("").astype(str).apply(lambda x: _contains_any(x, SKINCARE_KEYWORDS))
    )
    df_kr["_skincare_strict"] = skincare_mask
    n_strict = skincare_mask.sum()
    print(f"[filter] 스킨케어 strict 매칭: {n_strict:,}")

    if args.lax or n_strict < 30:
        if not args.lax:
            print(f"[filter] strict 부족 ({n_strict}) — 우선 strict 정렬 후 나머지 추가")
        df_skin = df_kr.copy()  # 모두 포함 (이미 EXCLUDE 적용된 상태)
    else:
        df_skin = df_kr[skincare_mask].copy()
    print(f"[filter] 스킨케어 후보: {len(df_skin):,}")

    # 3. 전성분 다시 확인 (위에서 한 번 했지만 K-beauty 글로벌 추가 후 재확인)
    df_ing = df_skin[df_skin["ingredients_text"].notna() & (df_skin["ingredients_text"].astype(str).str.strip() != "")].copy()
    print(f"[filter] 전성분 있음: {len(df_ing):,}")

    # 4. 우선순위 정렬: skincare strict > 우선 브랜드 > 이름 길이
    df_ing["_skincare_score"] = df_ing.get("_skincare_strict", False).astype(int)
    df_ing["_priority"] = df_ing["brands"].fillna("").astype(str).apply(
        lambda x: 1 if _contains_any(x, PRIORITY_BRANDS) else 0
    )
    df_ing["_name_len"] = df_ing["product_name"].fillna("").astype(str).str.len()
    df_ing = df_ing.sort_values(
        ["_skincare_score", "_priority", "_name_len"],
        ascending=[False, False, True],
    )

    # 5. 중복 제거 (같은 제품명 + 브랜드)
    df_ing = df_ing.drop_duplicates(subset=["product_name", "brands"], keep="first")
    print(f"[dedup] 중복 제거 후: {len(df_ing):,}")

    # 6. Top N
    top = df_ing.head(args.limit).copy()
    top = top.drop(columns=["_skincare_score", "_priority", "_name_len", "_skincare_strict"], errors="ignore")

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
