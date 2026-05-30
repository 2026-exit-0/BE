"""식약처 화장품 규제정보 전체 데이터 받아서 local CSV 로 저장.

API spec:
  - URL: https://apis.data.go.kr/1471000/CsmtcsReglMaterialInfoService/getCsmtcsReglMaterialInfoService
  - bulk listing only — 성분별 search 안 됨. 전체 페이지 받아 local lookup 으로 사용
  - 총 ~7257건. 페이지당 100건 → 73 페이지 / 약 1-2분 소요

응답 필드:
  - INGR_STD_NAME: 한국어 표준명
  - INGR_ENG_NAME: 영문 INCI
  - PROH_NATIONAL: 금지국가 (콤마구분)
  - LIMIT_NATIONAL: 제한국가 (콤마구분)

실행 (lab PC):
    set KFDA_API_KEY=<디코딩_키>
    python ...\\BE\\scripts\\products\\2a_fetch_kfda_all.py

결과:
    C:\\damda\\data\\products\\raw\\kfda_regulations.csv
"""

from __future__ import annotations

import argparse
import os
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd
import requests


URL = "https://apis.data.go.kr/1471000/CsmtcsReglMaterialInfoService/getCsmtcsReglMaterialInfoService"
PAGE_SIZE = 100


def fetch_page(api_key: str, page_no: int, num_rows: int = PAGE_SIZE) -> dict:
    """한 페이지 받아 XML 파싱 → dict 반환."""
    r = requests.get(
        URL,
        params={
            "serviceKey": api_key,
            "pageNo": page_no,
            "numOfRows": num_rows,
            "type": "xml",
        },
        timeout=15,
    )
    r.raise_for_status()
    root = ET.fromstring(r.text)

    # 헤더 확인
    result_code = root.findtext("header/resultCode")
    if result_code != "00":
        msg = root.findtext("header/resultMsg") or "?"
        raise RuntimeError(f"API 에러 (resultCode={result_code}): {msg}")

    # body parsing
    body = root.find("body")
    total_count = int(body.findtext("totalCount") or "0")
    items = []
    for item in body.findall("items/item"):
        items.append({
            "ingr_std_name": (item.findtext("INGR_STD_NAME") or "").strip(),
            "ingr_eng_name": (item.findtext("INGR_ENG_NAME") or "").strip(),
            "prohibited_countries": (item.findtext("PROH_NATIONAL") or "").strip(),
            "limited_countries": (item.findtext("LIMIT_NATIONAL") or "").strip(),
        })
    return {"total_count": total_count, "items": items}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default=r"C:\damda\data\products\raw\kfda_regulations.csv")
    ap.add_argument("--rate-limit", type=float, default=0.2, help="페이지 사이 sleep (초)")
    args = ap.parse_args()

    api_key = os.getenv("KFDA_API_KEY", "")
    if not api_key:
        print("⚠ KFDA_API_KEY 환경변수 없음")
        return

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"[fetch] page 1 시작 (총 페이지 계산용)")
    first = fetch_page(api_key, 1)
    total = first["total_count"]
    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
    print(f"[fetch] 총 {total:,}건 / {total_pages} 페이지")

    all_items = list(first["items"])
    for page in range(2, total_pages + 1):
        try:
            time.sleep(args.rate_limit)
            data = fetch_page(api_key, page)
            all_items.extend(data["items"])
            if page % 10 == 0:
                print(f"  [{page}/{total_pages}] 누적: {len(all_items):,}")
        except Exception as e:
            print(f"  ⚠ page {page} 실패: {e}")
            continue

    df = pd.DataFrame(all_items)
    df.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"[save] {out_path}  ({len(df):,}건)")
    print()
    print("[sample] 첫 3건:")
    for _, row in df.head(3).iterrows():
        print(f"  {row['ingr_std_name']}")
        print(f"    EN: {row['ingr_eng_name']}")
        print(f"    PROH: {row['prohibited_countries'] or '-'}")
        print(f"    LIMIT: {row['limited_countries'] or '-'}")


if __name__ == "__main__":
    main()
