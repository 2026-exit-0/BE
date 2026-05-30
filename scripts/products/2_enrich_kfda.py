"""식약처 화장품 규제정보 API 로 위험/제한 성분 자동 flag.

각 제품의 메인 성분에 대해 식약처 DB 조회 → 제한/금지 국가 있으면 위험 표시.
API 응답은 캐시 (raw/kfda_responses/) — 같은 성분 반복 조회 안 함.

실행 (lab PC):
    set KFDA_API_KEY=<발급받은_키>
    python ...\\BE\\scripts\\products\\2_enrich_kfda.py

API 신청:
    https://www.data.go.kr/data/15111773/openapi.do  (화장품 규제정보)
    https://www.data.go.kr/data/15111774/openapi.do  (화장품 원료성분정보)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from pathlib import Path
from typing import List, Optional

import pandas as pd
import requests


KFDA_KEY = os.getenv("KFDA_API_KEY", "")
CACHE_DIR = Path(r"C:\damda\data\products\raw\kfda_responses")
TIMEOUT = 10  # 초


def _safe_filename(s: str) -> str:
    """파일명 안전화."""
    return re.sub(r"[^\w\-_.]", "_", s)[:80]


def query_regulation(inci_name: str, lang: str = "en") -> dict:
    """식약처 규제정보 API 조회. 결과 캐시.

    Args:
        inci_name: 성분명 (영문 INCI 권장. 한국어도 가능)
        lang: en | ko
    """
    cache_file = CACHE_DIR / f"reg_{_safe_filename(inci_name)}.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text(encoding="utf-8"))

    if not KFDA_KEY:
        return {"_error": "KFDA_API_KEY 환경변수 없음"}

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        r = requests.get(
            "http://apis.data.go.kr/1471000/CsmtcsRgltInfoService/getCsmtcsRgltInfo",
            params={
                "serviceKey": KFDA_KEY,
                "INGR_NM_KO" if lang == "ko" else "INGR_NM_EN": inci_name,
                "type": "json",
                "numOfRows": 5,
                "pageNo": 1,
            },
            timeout=TIMEOUT,
        )
        data = r.json() if r.status_code == 200 else {"_error": f"HTTP {r.status_code}"}
    except Exception as e:
        data = {"_error": str(e)}

    cache_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    time.sleep(0.1)  # rate limit 예의
    return data


def is_restricted(reg_response: dict) -> bool:
    """규제 응답에서 제한/금지 국가 있는지 판정."""
    if "_error" in reg_response:
        return False
    items = reg_response.get("response", {}).get("body", {}).get("items", [])
    if isinstance(items, dict):
        items = items.get("item", [])
    if not items:
        return False
    if not isinstance(items, list):
        items = [items]
    # 금지국가 또는 제한국가 정보 있으면 위험
    for item in items:
        if item.get("PRHIBT_CNTRY_NM") or item.get("RSTRCT_CNTRY_NM"):
            return True
    return False


def parse_main_ingredients(ingredients_text: str, max_n: int = 10) -> List[str]:
    """전성분 텍스트에서 메인 성분 N개 추출.
    INCI 는 보통 함량 내림차순이라 앞 N개가 메인.
    """
    if not ingredients_text or pd.isna(ingredients_text):
        return []
    # 쉼표/세미콜론 구분
    parts = re.split(r"[,;]", ingredients_text)
    cleaned = []
    for p in parts:
        # 괄호 안 (대체 표기) 제거
        p = re.sub(r"\([^)]*\)", "", p).strip()
        # 숫자/특수문자만 제외
        if p and len(p) > 1:
            cleaned.append(p)
    return cleaned[:max_n]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=r"C:\damda\data\products\output\obf_filtered.csv")
    ap.add_argument("--output", default=r"C:\damda\data\products\output\obf_enriched.csv")
    ap.add_argument("--max-products", type=int, default=100)
    ap.add_argument("--skip-api", action="store_true",
                    help="API 키 없을 때 — 위험 flag 없이 진행")
    args = ap.parse_args()

    if not KFDA_KEY and not args.skip_api:
        print("⚠ KFDA_API_KEY 환경변수 없음. --skip-api 로 진행하거나 키 설정 필요.")
        print("  https://www.data.go.kr/data/15111773/openapi.do 신청")
        return

    df = pd.read_csv(args.input, encoding="utf-8-sig")
    df = df.head(args.max_products).copy()
    print(f"[load] {len(df)} 제품")

    risky_flags = []
    risky_ingredients_list = []
    main_ingredients_list = []

    for idx, row in df.iterrows():
        ing_text = row.get("ingredients_text_en") or row.get("ingredients_text") or ""
        mains = parse_main_ingredients(ing_text, max_n=8)
        main_ingredients_list.append("|".join(mains))

        if args.skip_api:
            risky_flags.append(False)
            risky_ingredients_list.append("")
            continue

        risky = []
        for ing in mains:
            reg = query_regulation(ing, lang="en")
            if is_restricted(reg):
                risky.append(ing)
        risky_flags.append(len(risky) > 0)
        risky_ingredients_list.append("|".join(risky))

        if (idx + 1) % 10 == 0:
            print(f"  처리: {idx + 1}/{len(df)}")

    df["main_ingredients"] = main_ingredients_list
    df["risky_ingredients"] = risky_ingredients_list
    df["has_risky"] = risky_flags

    df.to_csv(args.output, index=False, encoding="utf-8-sig")
    print(f"[save] {args.output}")
    print(f"  위험성분 포함: {sum(risky_flags)} 제품")


if __name__ == "__main__":
    main()
