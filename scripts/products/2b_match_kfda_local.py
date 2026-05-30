"""local 식약처 규제 CSV (2a 산출) 기반 제품 매칭.

각 제품의 메인 성분을 식약처 규제 DB 와 대조 → 위험성분 flag.
- prohibited_countries 있음 → "금지성분포함" tag
- limited_countries 있음 → "제한성분포함" tag
- 한국 (KR) 명시되면 "한국규제" 우선 tag

실행:
    python ...\\BE\\scripts\\products\\2b_match_kfda_local.py
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Dict, Set

import pandas as pd


def _normalize(s: str) -> str:
    """성분명 정규화 — 매칭률 ↑."""
    if not s:
        return ""
    s = s.strip().lower()
    # 괄호 안 제거
    s = re.sub(r"\([^)]*\)", "", s)
    # 특수문자 → 공백
    s = re.sub(r"[,;:\.\-/\\]", " ", s)
    # 다중 공백 정리
    s = re.sub(r"\s+", " ", s).strip()
    return s


def build_lookup(kfda_csv: Path) -> Dict[str, Dict]:
    """식약처 CSV → 정규화된 성분명 → {info} 사전.

    매칭 정확도를 위해:
    - 한국어 표준명 / 영문 INCI 양쪽 모두 키로 등록
    - 정규화 적용 (lowercase, 특수문자 제거)
    """
    df = pd.read_csv(kfda_csv, encoding="utf-8-sig")
    lookup: Dict[str, Dict] = {}
    for _, row in df.iterrows():
        info = {
            "kor": row.get("ingr_std_name", "") or "",
            "eng": row.get("ingr_eng_name", "") or "",
            "prohibited": row.get("prohibited_countries", "") or "",
            "limited": row.get("limited_countries", "") or "",
        }
        for k in (info["kor"], info["eng"]):
            norm = _normalize(k)
            if norm:
                lookup[norm] = info
    return lookup


def check_ingredient(ing_text: str, lookup: Dict) -> Dict:
    """단일 성분이 규제 DB 에 있나 확인. 일치하면 info 반환."""
    norm = _normalize(ing_text)
    if not norm:
        return {}
    # 정확 매칭
    if norm in lookup:
        return lookup[norm]
    # 부분 매칭 (정규화된 키가 검색어에 포함되거나 그 반대)
    for key, info in lookup.items():
        if key in norm or norm in key:
            return info
    return {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=r"C:\damda\data\products\output\obf_filtered.csv")
    ap.add_argument("--kfda-csv", default=r"C:\damda\data\products\raw\kfda_regulations.csv")
    ap.add_argument("--output", default=r"C:\damda\data\products\output\obf_enriched.csv")
    args = ap.parse_args()

    kfda_path = Path(args.kfda_csv)
    if not kfda_path.exists():
        print(f"⚠ 식약처 CSV 없음: {kfda_path}")
        print(f"  먼저 2a_fetch_kfda_all.py 실행 필요")
        return

    print(f"[load] 식약처 lookup 구축")
    lookup = build_lookup(kfda_path)
    print(f"[load] 등록된 성분 키: {len(lookup):,}")

    df = pd.read_csv(args.input, encoding="utf-8-sig")
    print(f"[load] 제품: {len(df)}")

    risky_lists = []
    risky_flags = []
    prohibited_in_kr = []
    main_ings_list = []

    for _, row in df.iterrows():
        ing_text = str(row.get("ingredients_text") or "")
        if not ing_text:
            risky_lists.append("")
            risky_flags.append(False)
            prohibited_in_kr.append(False)
            main_ings_list.append("")
            continue

        # 메인 성분 추출 (앞 10개)
        parts = re.split(r"[,;]", ing_text)
        mains = []
        for p in parts:
            p = re.sub(r"\([^)]*\)", "", p).strip()
            if p and len(p) > 1:
                mains.append(p)
        mains = mains[:10]
        main_ings_list.append("|".join(mains))

        risky = []
        kr_prohibited = False
        for ing in mains:
            info = check_ingredient(ing, lookup)
            if info:
                tag = info["kor"] or info["eng"]
                if info.get("prohibited"):
                    risky.append(f"{tag} [금지:{info['prohibited']}]")
                    if "한국" in info["prohibited"]:
                        kr_prohibited = True
                elif info.get("limited"):
                    risky.append(f"{tag} [제한:{info['limited']}]")

        risky_lists.append("|".join(risky))
        risky_flags.append(len(risky) > 0)
        prohibited_in_kr.append(kr_prohibited)

    df["main_ingredients"] = main_ings_list
    df["risky_ingredients"] = risky_lists
    df["has_risky"] = risky_flags
    df["has_kr_prohibited"] = prohibited_in_kr

    df.to_csv(args.output, index=False, encoding="utf-8-sig")
    n_risky = sum(risky_flags)
    n_kr = sum(prohibited_in_kr)
    print(f"[save] {args.output}")
    print(f"  위험성분 포함: {n_risky}/{len(df)} ({100*n_risky/len(df):.0f}%)")
    print(f"  한국 금지성분 포함: {n_kr}/{len(df)}")


if __name__ == "__main__":
    main()
