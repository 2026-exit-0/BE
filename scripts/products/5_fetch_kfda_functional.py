"""식약처 기능성화장품 보고품목정보 (pk 15095680) 대량 수집.

기능성 종류 → category 자동 매핑:
  - 미백 → ["미백"]
  - 주름개선 → ["탄력"]
  - 자외선차단 → ["모공"]  (선크림 부카테고리)
  - 여드름성 피부 완화 → ["모공", "진정"]
  - 아토피성 피부 보습 → ["보습", "진정"]
  - 튼살로 인한 붉은 선 → ["탄력"]
  - 모발 색상 변화 → 제외 (염색약)
  - 체모 제거 → 제외 (제모)
  - 탈모 증상 완화 → 제외 (모발용)

실행 (한 번에 만~수만 건 받아서 products_kfda_functional.json 으로 저장):
    set KFDA_API_KEY=<디코딩_키>
    python BE/scripts/products/5_fetch_kfda_functional.py

옵션:
    --korea-only       한국 책임판매업자만 (기본 True)
    --max-pages N      디버그용 상한
    --output PATH      출력 경로 (기본 BE/data/products_kfda_functional.json)

다음 단계:
    Phase 3 (네이버 쇼핑) 으로 image_url / price_range / purchase_url 보강.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests


# 데이터포털에서 발급 후 정확한 URL 은 마이페이지 → API 신청 내역에서 확인
# 보통 다음 패턴 중 하나:
URL_CANDIDATES = [
    # 가장 흔한 패턴 — 사용자가 실제 URL 로 교체할 것
    "https://apis.data.go.kr/1471000/MdcinPrdtPrmsnInfoService06/getMdcinPrdtItem01",
    "https://apis.data.go.kr/1471000/CsmtcsItemRptInfoService02/getCsmtcsItemRptInfo",
]
URL = os.getenv("KFDA_FUNCTIONAL_URL", URL_CANDIDATES[0])
PAGE_SIZE = 100


# 기능성 표시 문구 → category 매핑
FUNCTIONAL_TO_CATEGORY: Dict[str, List[str]] = {
    "미백": ["미백"],
    "주름": ["탄력"],
    "탄력": ["탄력"],
    "자외선차단": ["모공"],  # 선크림 — UV
    "자외선 차단": ["모공"],
    "여드름": ["모공", "진정"],
    "아토피": ["보습", "진정"],
    "튼살": ["탄력"],
    "보습": ["보습"],
    "안티에이징": ["탄력"],
}

# 기능성 표시 문구 → subcategory 추정
NAME_TO_SUBCATEGORY: List[Tuple[str, str]] = [
    ("토너", "토너"), ("스킨", "토너"),
    ("에센스", "세럼"), ("앰플", "세럼"), ("세럼", "세럼"),
    ("로션", "로션"), ("에멀젼", "로션"),
    ("크림", "크림"), ("밤", "크림"),
    ("선", "선크림"), ("sun ", "선크림"), ("spf", "선크림"), ("자외선", "선크림"),
    ("마스크", "팩"), ("팩", "팩"),
    ("클렌저", "클렌저"), ("폼", "클렌저"), ("워시", "클렌저"),
    ("아이", "아이크림"),
    ("립", "립케어"),
]

EXCLUDE_FUNCTIONAL = ("모발", "탈모", "체모", "염색", "두피", "헤어")


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--korea-only", action="store_true", default=True)
    ap.add_argument("--max-pages", type=int, default=None)
    ap.add_argument("--output", type=Path,
                    default=Path(__file__).resolve().parents[2] / "data" / "products_kfda_functional.json")
    return ap.parse_args()


def fetch_page(api_key: str, page_no: int) -> Tuple[List[dict], int]:
    """한 페이지 → (items, total_count)"""
    r = requests.get(
        URL,
        params={
            "serviceKey": api_key,
            "pageNo": page_no,
            "numOfRows": PAGE_SIZE,
            "type": "xml",
        },
        timeout=20,
    )
    r.raise_for_status()
    root = ET.fromstring(r.text)

    result_code = root.findtext("header/resultCode") or root.findtext(".//resultCode")
    if result_code and result_code != "00":
        msg = root.findtext("header/resultMsg") or "?"
        raise RuntimeError(f"API 에러 (code={result_code}): {msg}")

    total = int(root.findtext(".//totalCount") or 0)
    items = []
    for item in root.findall(".//item"):
        d = {child.tag: (child.text or "").strip() for child in item}
        items.append(d)
    return items, total


def is_korean_manufacturer(raw: dict) -> bool:
    """책임판매업자가 한국인지 휴리스틱 판단.
    국문 한자 자가 들어있고 명백한 해외 패턴 없으면 True.
    """
    seller = raw.get("ENTP_NAME", "") or raw.get("ITEM_PRDC_BIZ_NAME", "") or raw.get("BIZRNO_NM", "")
    if not seller:
        return False
    # 한글 포함
    if re.search(r"[가-힣]", seller):
        return True
    # 영문이지만 흔한 한국 브랜드 영문명 패턴
    KR_BRAND_EN = ("amorepacific", "lg h&h", "missha", "innisfree", "laneige",
                   "etude", "tonymoly", "cosrx", "torriden", "dr.jart", "dr. jart",
                   "ahc", "the face shop", "iope", "sulwhasoo", "the history of whoo")
    return any(b in seller.lower() for b in KR_BRAND_EN)


def derive_categories(functional_desc: str) -> List[str]:
    cats = set()
    for kw, mapped in FUNCTIONAL_TO_CATEGORY.items():
        if kw in functional_desc:
            cats.update(mapped)
    return sorted(cats) if cats else []


def derive_subcategory(name: str) -> str:
    name_l = name.lower()
    for kw, sub in NAME_TO_SUBCATEGORY:
        if kw in name_l:
            return sub
    return "?"


def normalize_one(raw: dict, next_id: int) -> Optional[dict]:
    """원본 → 우리 스키마. 못 쓸 거면 None."""
    # 필드명은 API spec 에 따라 다름 — 실제 응답 확인 후 매핑
    name = raw.get("ITEM_NAME", "") or raw.get("CSMR_ENG_NAME", "") or raw.get("PRDLST_NM", "")
    brand = raw.get("ENTP_NAME", "") or raw.get("ITEM_PRDC_BIZ_NAME", "") or "?"
    functional = raw.get("EFCY_QESITM", "") or raw.get("FUNC_KIND", "") or raw.get("DOC_TEXT", "")
    report_no = raw.get("ITEM_SEQ", "") or raw.get("DOC_NUM", "")

    if not name or not brand:
        return None

    # 기능성 표시 문구에 헤어/탈모 등 제외 키워드 있으면 스킵
    if any(ex in functional for ex in EXCLUDE_FUNCTIONAL):
        return None
    if any(ex in name for ex in EXCLUDE_FUNCTIONAL):
        return None

    cats = derive_categories(functional)
    if not cats:
        # 카테고리 추정 안 되면 기본 보습으로
        cats = ["보습"]

    return {
        "id": f"KF{next_id:04d}",
        "name_kr": name,
        "name_en": "",
        "brand": brand,
        "category": cats,
        "subcategory": derive_subcategory(name),
        "for_skin": [],  # 식약처엔 없음 — Phase 4 (성분 룰) 로 추후 보강
        "main_ingredients": [],  # 식약처엔 없음 — 라벨 OCR 단계에서 보강
        "fragrance_free": None,
        "alcohol_free": None,
        "tags": [],
        "risky_ingredients": [],
        "price_range": "?",
        "image_url": "",
        "report_no": report_no,
        "functional_desc": functional[:200],
        "source": "KFDA_functional",
        "note": "",
    }


def main():
    args = parse_args()
    api_key = os.getenv("KFDA_API_KEY")
    if not api_key:
        raise SystemExit("KFDA_API_KEY 환경변수 필요 (디코딩 키)")

    out_path = args.output
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"[1] 페이지 1 받아서 totalCount 확인...")
    items, total = fetch_page(api_key, 1)
    print(f"    totalCount: {total}, 첫 페이지: {len(items)}건")

    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
    if args.max_pages:
        total_pages = min(total_pages, args.max_pages)
    print(f"    총 {total_pages} 페이지 수집 예정")

    all_items: List[dict] = list(items)
    for page in range(2, total_pages + 1):
        try:
            items, _ = fetch_page(api_key, page)
        except Exception as e:
            print(f"    [page {page}] 실패: {e} — 스킵")
            time.sleep(2)
            continue
        all_items.extend(items)
        if page % 10 == 0:
            print(f"    page {page}/{total_pages} 누적 {len(all_items)}건")
        time.sleep(0.3)  # rate limit 매너

    print(f"[2] 원본 {len(all_items)}건 정규화 + 한국 책임판매업자 필터")
    products: List[dict] = []
    next_id = 1
    skipped_foreign = 0
    skipped_invalid = 0
    for raw in all_items:
        if args.korea_only and not is_korean_manufacturer(raw):
            skipped_foreign += 1
            continue
        norm = normalize_one(raw, next_id)
        if norm is None:
            skipped_invalid += 1
            continue
        products.append(norm)
        next_id += 1

    print(f"    한국 책임판매 외 제외: {skipped_foreign}")
    print(f"    필수 필드 누락 제외: {skipped_invalid}")
    print(f"    최종 {len(products)}건")

    out_path.write_text(
        json.dumps({"products": products, "source": "KFDA_functional", "fetched_at": time.strftime("%Y-%m-%d")},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[3] 저장: {out_path}")

    # 카테고리 분포 출력
    from collections import Counter
    cc = Counter()
    for p in products:
        for c in p["category"]:
            cc[c] += 1
    print(f"    카테고리 분포: {dict(cc.most_common())}")


if __name__ == "__main__":
    main()
