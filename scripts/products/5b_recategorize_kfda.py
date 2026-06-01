"""이미 받아둔 KFDA raw 데이터 (_kfda_fetch_checkpoint.json) 를 가지고
필드명 매핑 / 카테고리 분류만 다시 돌리는 스크립트.

API 재호출 없이 빠르게 재처리. 매핑 규칙 (FIELD_MAP / FUNCTIONAL_TO_CATEGORY) 만
조정하고 이 스크립트 돌리면 됨.

실행:
    python BE/scripts/products/5b_recategorize_kfda.py

옵션:
    --input PATH       체크포인트 경로 (기본 data/_kfda_fetch_checkpoint.json)
    --output PATH      정규화 결과 (기본 data/products_kfda_functional.json)
    --debug-n N        앞 N 건의 raw 필드 출력 (매핑 디버그용)
"""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# 필드명 후보 (여러 후보 중 첫 매치) — 실제 응답 확인 후 조정
FIELD_MAP: Dict[str, List[str]] = {
    "name":       ["ITEM_NAME", "PRDLST_NM", "itemName", "prdlstNm", "ITEM_NM"],
    "brand":      ["ENTP_NAME", "BIZRNO_NM", "ITEM_PRDC_BIZ_NAME", "entpName"],
    "functional": ["EFCY_QESITM", "FNCTV_CONT", "CHK_FNCTV", "FUNC_KIND", "fnctvCont", "efcyQesitm", "DOC_TEXT"],
    "report_no":  ["ITEM_SEQ", "DOC_NUM", "itemSeq", "RPT_NUM", "REPORT_NUM"],
    "ingredient": ["ITEM_INGR_NAME", "ingrName", "INGR"],
}


FUNCTIONAL_TO_CATEGORY: Dict[str, List[str]] = {
    "미백": ["미백"],
    "주름": ["탄력"],
    "탄력": ["탄력"],
    "안티에이징": ["탄력"],
    "자외선차단": ["모공"],
    "자외선 차단": ["모공"],
    "여드름": ["모공", "진정"],
    "아토피": ["보습", "진정"],
    "튼살": ["탄력"],
    "보습": ["보습"],
    "수분": ["보습"],
    "진정": ["진정"],
    "트러블": ["진정", "모공"],
    "민감": ["진정"],
}

NAME_TO_SUBCATEGORY: List[Tuple[str, str]] = [
    ("토너", "토너"), ("스킨", "토너"),
    ("에센스", "에센스"), ("앰플", "세럼"), ("세럼", "세럼"),
    ("로션", "로션"), ("에멀젼", "로션"),
    ("밤 ", "크림"), ("크림", "크림"),
    ("선", "선크림"), ("sun ", "선크림"), ("spf", "선크림"), ("자외선", "선크림"),
    ("마스크", "팩"), ("팩", "팩"),
    ("클렌저", "클렌저"), ("폼", "클렌저"), ("워시", "클렌저"),
    ("아이", "아이크림"),
    ("립", "립케어"),
]

EXCLUDE_KEYWORDS_NAME = ("모발", "탈모", "체모", "염색", "두피", "헤어", "샴푸", "린스")


def first_present(raw: dict, candidates: List[str]) -> str:
    """후보 키 중 처음으로 값 있는 거 반환."""
    for k in candidates:
        v = raw.get(k)
        if v:
            return str(v).strip()
    return ""


def derive_categories(functional: str) -> List[str]:
    cats = set()
    for kw, mapped in FUNCTIONAL_TO_CATEGORY.items():
        if kw in functional:
            cats.update(mapped)
    return sorted(cats) if cats else []


def derive_subcategory(name: str) -> str:
    name_l = name.lower()
    for kw, sub in NAME_TO_SUBCATEGORY:
        if kw in name_l:
            return sub
    return "?"


def normalize(raw: dict, next_id: int) -> Optional[dict]:
    name = first_present(raw, FIELD_MAP["name"])
    brand = first_present(raw, FIELD_MAP["brand"]) or "?"
    functional = first_present(raw, FIELD_MAP["functional"])
    report_no = first_present(raw, FIELD_MAP["report_no"])

    if not name:
        return None

    # 모발/탈모 등 제외
    for ex in EXCLUDE_KEYWORDS_NAME:
        if ex in name or ex in functional:
            return None

    cats = derive_categories(functional)
    if not cats:
        # 매핑 실패 시 — 일단 보습으로 (fallback 비중 줄이려면 None 반환해서 스킵해도 됨)
        cats = ["보습"]
        uncategorized = True
    else:
        uncategorized = False

    return {
        "id": f"KF{next_id:05d}",
        "name_kr": name,
        "name_en": "",
        "brand": brand,
        "category": cats,
        "subcategory": derive_subcategory(name),
        "for_skin": [],
        "main_ingredients": [],
        "fragrance_free": None,
        "alcohol_free": None,
        "tags": [],
        "risky_ingredients": [],
        "price_range": "?",
        "image_url": "",
        "report_no": report_no,
        "functional_desc": functional[:200],
        "source": "KFDA_functional",
        "uncategorized": uncategorized,  # 디버그용 — 매핑 실패한 거 표시
        "note": "",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", type=Path,
                    default=Path(__file__).resolve().parents[2] / "data" / "_kfda_fetch_checkpoint.json")
    ap.add_argument("--output", type=Path,
                    default=Path(__file__).resolve().parents[2] / "data" / "products_kfda_functional.json")
    ap.add_argument("--debug-n", type=int, default=0,
                    help="앞 N 건의 raw 필드 출력 후 종료 (디버그용)")
    args = ap.parse_args()

    if not args.input.exists():
        raise SystemExit(f"입력 없음: {args.input}")

    data = json.loads(args.input.read_text(encoding="utf-8"))
    items = data.get("items", [])
    print(f"[1] raw 로드: {len(items)} 건")

    if args.debug_n > 0:
        print(f"\n=== 앞 {args.debug_n} 건의 raw 필드 ===")
        for i, raw in enumerate(items[: args.debug_n]):
            print(f"--- item {i} ---")
            for k, v in raw.items():
                print(f"  {k}: {(str(v)[:120] if v else v)}")
        return

    products: List[dict] = []
    next_id = 1
    skipped = 0
    for raw in items:
        norm = normalize(raw, next_id)
        if norm is None:
            skipped += 1
            continue
        products.append(norm)
        next_id += 1

    cat_counter = Counter()
    uncat_count = 0
    for p in products:
        for c in p["category"]:
            cat_counter[c] += 1
        if p.get("uncategorized"):
            uncat_count += 1

    print(f"[2] 정규화: {len(products)} 건 (스킵 {skipped})")
    print(f"    카테고리 분포: {dict(cat_counter.most_common())}")
    print(f"    매핑 실패해서 보습 fallback 으로 떨어진 거: {uncat_count}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps({"products": products, "source": "KFDA_functional",
                    "processed_at": time.strftime("%Y-%m-%d %H:%M:%S")},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[3] 저장: {args.output}")


if __name__ == "__main__":
    main()
