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
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests

# Windows cp949 콘솔에서도 한글/유니코드 출력 안전하게
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


# 데이터포털에서 발급 후 정확한 URL 은 마이페이지 → API 신청 내역에서 확인
# 보통 다음 패턴 중 하나:
URL_CANDIDATES = [
    # 가장 흔한 패턴 - 사용자가 실제 URL 로 교체할 것
    "https://apis.data.go.kr/1471000/MdcinPrdtPrmsnInfoService06/getMdcinPrdtItem01",
    "https://apis.data.go.kr/1471000/CsmtcsItemRptInfoService02/getCsmtcsItemRptInfo",
]
URL = os.getenv("KFDA_FUNCTIONAL_URL", URL_CANDIDATES[0])
PAGE_SIZE = 100


# 텍스트 (EE_NAME / 제품명) → category 키워드 매핑
TEXT_TO_CATEGORY: Dict[str, List[str]] = {
    "미백": ["미백"], "화이트": ["미백"], "톤업": ["미백"], "브라이트": ["미백"],
    "주름": ["탄력"], "탄력": ["탄력"], "안티에이징": ["탄력"], "리프팅": ["탄력"],
    "자외선": ["모공"], "선크림": ["모공"], "썬": ["모공"], "sun ": ["모공"],
    "여드름": ["모공", "진정"], "트러블": ["진정", "모공"],
    "아토피": ["보습", "진정"],
    "튼살": ["탄력"],
    "보습": ["보습"], "수분": ["보습"], "하이드라": ["보습"], "워터": ["보습"],
    "시카": ["진정"], "센텔라": ["진정"], "병풀": ["진정"], "cica": ["진정"],
    "진정": ["진정"], "민감": ["진정"],
    "모공": ["모공"], "포어": ["모공"],
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
    ap.add_argument("--checkpoint", type=Path,
                    default=Path(__file__).resolve().parents[2] / "data" / "_kfda_fetch_checkpoint.json",
                    help="중간 저장 파일 (페이지 X마다 저장, 끊겨도 재개 가능)")
    ap.add_argument("--save-every", type=int, default=50,
                    help="N 페이지마다 체크포인트 저장")
    ap.add_argument("--resume", action="store_true",
                    help="체크포인트 있으면 거기서 이어 받음")
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
    """책임판매업자가 한국인지 휴리스틱 판단."""
    seller = raw.get("ENTP_NAME", "") or raw.get("ITEM_PRDC_BIZ_NAME", "") or raw.get("BIZRNO_NM", "")
    if not seller:
        return False
    if re.search(r"[가-힣]", seller):
        return True
    KR_BRAND_EN = ("amorepacific", "lg h&h", "missha", "innisfree", "laneige",
                   "etude", "tonymoly", "cosrx", "torriden", "dr.jart", "dr. jart",
                   "ahc", "the face shop", "iope", "sulwhasoo", "the history of whoo")
    return any(b in seller.lower() for b in KR_BRAND_EN)


def derive_categories_from_raw(raw: dict) -> List[str]:
    """실제 API 응답 기준 카테고리 도출.

    우선순위:
      1) EFFECT_YN1/2/3 boolean 플래그
      2) SPF / PA 값 있음 → 모공 (선크림)
      3) EE_NAME 텍스트 매칭
      4) ITEM_NAME 키워드 매칭
    """
    cats = set()

    # 1) 효능 플래그
    if raw.get("EFFECT_YN1", "").strip() == "Y":
        cats.add("미백")
    if raw.get("EFFECT_YN2", "").strip() == "Y":
        cats.add("탄력")
    if raw.get("EFFECT_YN3", "").strip() == "Y":
        cats.add("모공")

    # 2) SPF/PA 값 있음 → 선크림
    spf = (raw.get("SPF") or "").strip()
    pa = (raw.get("PA") or "").strip()
    if spf or pa:
        cats.add("모공")

    # 3) EE_NAME (효능명 텍스트)
    ee_name = (raw.get("EE_NAME") or "").lower()
    for kw, mapped in TEXT_TO_CATEGORY.items():
        if kw.lower() in ee_name:
            cats.update(mapped)

    # 4) ITEM_NAME 키워드
    item_name = (raw.get("ITEM_NAME") or "").lower()
    for kw, mapped in TEXT_TO_CATEGORY.items():
        if kw.lower() in item_name:
            cats.update(mapped)

    return sorted(cats) if cats else []


def derive_subcategory(name: str) -> str:
    name_l = name.lower()
    for kw, sub in NAME_TO_SUBCATEGORY:
        if kw in name_l:
            return sub
    return "?"


def normalize_one(raw: dict, next_id: int) -> Optional[dict]:
    """원본 → 우리 스키마. 카테고리 매핑 실패하면 None (스킵)."""
    name = (raw.get("ITEM_NAME") or "").strip()
    brand = (raw.get("ENTP_NAME") or "?").strip()
    report_no = (raw.get("COSMETIC_REPORT_SEQ") or raw.get("DEPT_RECEIPT_NO") or "").strip()
    ee_name = (raw.get("EE_NAME") or "").strip()

    if not name:
        return None

    # 모발/탈모 등 명백한 제외
    for ex in EXCLUDE_FUNCTIONAL:
        if ex in name or ex in ee_name:
            return None

    cats = derive_categories_from_raw(raw)
    if not cats:
        # 카테고리 매핑 실패하면 스킵 (보습 fallback 안 함 - 다양성 위해)
        return None

    # 효능 플래그 / SPF / PA - 디버그 및 functional_desc 재구성용
    flag_summary = []
    if raw.get("EFFECT_YN1") == "Y": flag_summary.append("미백")
    if raw.get("EFFECT_YN2") == "Y": flag_summary.append("주름개선")
    if raw.get("EFFECT_YN3") == "Y": flag_summary.append("자외선차단")
    spf = (raw.get("SPF") or "").strip()
    pa = (raw.get("PA") or "").strip()
    if spf: flag_summary.append(f"SPF{spf}")
    if pa: flag_summary.append(f"PA{pa}")

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
        "functional_desc": " · ".join(flag_summary + [ee_name]) if (flag_summary or ee_name) else "",
        "source": "KFDA_functional",
        "note": "",
    }


def save_checkpoint(path: Path, last_page: int, all_items: List[dict]):
    """페이지 N까지 받은 raw item 들을 저장."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"last_page": last_page, "items": all_items}, ensure_ascii=False),
        encoding="utf-8",
    )


def load_checkpoint(path: Path):
    if not path.exists():
        return 0, []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return int(data.get("last_page", 0)), data.get("items", [])
    except Exception as e:
        print(f"    체크포인트 로드 실패 (무시): {e}")
        return 0, []


def main():
    args = parse_args()
    api_key = os.getenv("KFDA_API_KEY")
    if not api_key:
        raise SystemExit("KFDA_API_KEY 환경변수 필요 (디코딩 키)")

    out_path = args.output
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # 재개 모드 - 체크포인트에서 이어받음
    start_page = 1
    all_items: List[dict] = []
    if args.resume:
        last_page, prev_items = load_checkpoint(args.checkpoint)
        if last_page > 0:
            start_page = last_page + 1
            all_items = prev_items
            print(f"[*] 체크포인트 발견 - page {last_page} 까지 {len(prev_items)}건 받음, page {start_page} 부터 이어 받기")

    print(f"[1] 페이지 1 받아서 totalCount 확인...")
    first_items, total = fetch_page(api_key, 1)
    print(f"    totalCount: {total}, 첫 페이지: {len(first_items)}건")

    if not all_items:
        all_items = list(first_items)

    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
    if args.max_pages:
        total_pages = min(total_pages, args.max_pages)
    print(f"    총 {total_pages} 페이지 수집 예정 (start: {start_page})")

    for page in range(max(start_page, 2), total_pages + 1):
        try:
            items, _ = fetch_page(api_key, page)
        except Exception as e:
            print(f"    [page {page}] 실패: {e} - 스킵")
            time.sleep(2)
            continue
        all_items.extend(items)
        if page % 10 == 0:
            print(f"    page {page}/{total_pages} 누적 {len(all_items)}건")
        # 중간 저장
        if page % args.save_every == 0:
            save_checkpoint(args.checkpoint, page, all_items)
        time.sleep(0.3)  # rate limit 매너
    # 끝나면 마지막 체크포인트
    save_checkpoint(args.checkpoint, total_pages, all_items)

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
