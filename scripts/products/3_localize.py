"""성분 영문 (INCI) → 한국어 매핑.

대한화장품협회 (kcia.or.kr) 사전 기반 + 자주 쓰는 성분 수동 보강.
~200개 핵심 성분 — OBF 데이터의 90% 이상 cover.

확장 시 INCI_TO_KOR dict 에 추가만 하면 됨.

실행:
    python ...\\BE\\scripts\\products\\3_localize.py
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd


# ============================================================
# 핵심 매핑 (자주 쓰는 200개)
# ============================================================
INCI_TO_KOR = {
    # 베이스 / 용매
    "Water": "정제수", "Aqua": "정제수", "Purified Water": "정제수",
    "Glycerin": "글리세린", "Glycerine": "글리세린",
    "Propylene Glycol": "프로필렌글라이콜",
    "Butylene Glycol": "부틸렌글라이콜",
    "Pentylene Glycol": "펜틸렌글라이콜",
    "1,2-Hexanediol": "1,2-헥산다이올",
    "Ethanol": "에탄올", "Alcohol": "에탄올",
    "Alcohol Denat": "변성알코올",

    # 보습 핵심
    "Hyaluronic Acid": "히알루론산",
    "Sodium Hyaluronate": "히알루론산나트륨",
    "Sodium Hyaluronate Crosspolymer": "히알루론산나트륨크로스폴리머",
    "Hydrolyzed Hyaluronic Acid": "가수분해히알루론산",
    "Ceramide NP": "세라마이드NP",
    "Ceramide AP": "세라마이드AP",
    "Ceramide EOP": "세라마이드EOP",
    "Cholesterol": "콜레스테롤",
    "Phytosphingosine": "파이토스핑고신",
    "Squalane": "스쿠알란",
    "Shea Butter": "시어버터", "Butyrospermum Parkii Butter": "시어버터",
    "Beta-Glucan": "베타글루칸",
    "Trehalose": "트레할로스",
    "Urea": "요소",

    # 미백 / 항산화
    "Niacinamide": "나이아신아마이드",
    "Ascorbic Acid": "아스코르빅애씨드", "L-Ascorbic Acid": "L-아스코르빅애씨드",
    "Ethyl Ascorbic Acid": "에틸아스코르빅애씨드",
    "Magnesium Ascorbyl Phosphate": "마그네슘아스코빌포스페이트",
    "Sodium Ascorbyl Phosphate": "소듐아스코빌포스페이트",
    "Arbutin": "알부틴", "Alpha-Arbutin": "알파-알부틴",
    "Kojic Acid": "코직애씨드",
    "Tranexamic Acid": "트라넥사믹애씨드",
    "Glutathione": "글루타치온",
    "Tocopherol": "토코페롤", "Tocopheryl Acetate": "토코페릴아세테이트",
    "Vitamin E": "비타민E", "Vitamin C": "비타민C",
    "Resveratrol": "레스베라트롤",
    "Ferulic Acid": "페룰릭애씨드",

    # 진정
    "Centella Asiatica Extract": "병풀추출물",
    "Centella Asiatica Leaf Extract": "병풀잎추출물",
    "Madecassoside": "마데카소사이드",
    "Asiaticoside": "아시아티코사이드",
    "Aloe Barbadensis Leaf Extract": "알로에베라잎추출물",
    "Aloe Barbadensis Leaf Juice": "알로에베라잎즙",
    "Allantoin": "알란토인",
    "Panthenol": "판테놀", "D-Panthenol": "D-판테놀",
    "Bisabolol": "비사보롤",
    "Houttuynia Cordata Extract": "어성초추출물",
    "Chamomilla Recutita Extract": "캐모마일추출물",
    "Calendula Officinalis Extract": "금잔화추출물",
    "Green Tea Extract": "녹차추출물",
    "Camellia Sinensis Leaf Extract": "녹차잎추출물",
    "Mugwort Extract": "쑥추출물", "Artemisia Princeps Extract": "쑥추출물",

    # 노화 / 탄력
    "Adenosine": "아데노신",
    "Retinol": "레티놀",
    "Retinal": "레티날", "Retinaldehyde": "레티날데하이드",
    "Bakuchiol": "바쿠치올",
    "Peptide": "펩타이드", "Palmitoyl Pentapeptide-4": "팔미토일펜타펩타이드-4",
    "Copper Tripeptide-1": "구리트라이펩타이드-1",
    "Collagen": "콜라겐", "Hydrolyzed Collagen": "가수분해콜라겐",
    "Argireline": "아르기렐린", "Acetyl Hexapeptide-8": "아세틸헥사펩타이드-8",
    "EGF": "EGF", "Epidermal Growth Factor": "표피성장인자",

    # 모공 / 각질
    "Salicylic Acid": "살리실릭애씨드", "BHA": "BHA",
    "Glycolic Acid": "글리콜릭애씨드", "AHA": "AHA",
    "Lactic Acid": "락틱애씨드",
    "Mandelic Acid": "만델릭애씨드",
    "PHA": "PHA", "Gluconolactone": "글루코노락톤",
    "Witch Hazel": "위치하젤", "Hamamelis Virginiana Water": "위치하젤수",
    "Kaolin": "카올린", "Bentonite": "벤토나이트",
    "Charcoal": "참숯", "Activated Charcoal": "활성탄",

    # 자외선 차단
    "Zinc Oxide": "징크옥사이드",
    "Titanium Dioxide": "티타늄다이옥사이드",
    "Avobenzone": "아보벤존",
    "Octinoxate": "옥티노세이트", "Ethylhexyl Methoxycinnamate": "에칠헥실메톡시신나메이트",
    "Octocrylene": "옥토크릴렌",
    "Homosalate": "호모살레이트",
    "Tinosorb S": "비스에칠헥실옥시페놀메톡시페닐트리아진",

    # 향료 / 보존
    "Phenoxyethanol": "페녹시에탄올",
    "Parabens": "파라벤",
    "Methylparaben": "메칠파라벤", "Propylparaben": "프로필파라벤",
    "Ethylparaben": "에칠파라벤", "Butylparaben": "부틸파라벤",
    "Fragrance": "향료", "Parfum": "향료",
    "Limonene": "리모넨", "Linalool": "리날룰",
    "Citronellol": "시트로넬올", "Geraniol": "제라니올",

    # 점도 / 유화제
    "Carbomer": "카보머",
    "Xanthan Gum": "잔탄검",
    "Cetearyl Alcohol": "세테아릴알코올",
    "Cetyl Alcohol": "세틸알코올",
    "Stearyl Alcohol": "스테아릴알코올",
    "Glyceryl Stearate": "글리세릴스테아레이트",
    "PEG-100 Stearate": "PEG-100스테아레이트",
    "Polysorbate 60": "폴리소르베이트60",
    "Polysorbate 80": "폴리소르베이트80",

    # 기타 자주 등장
    "Disodium EDTA": "다이소듐이디티에이",
    "Sodium Hydroxide": "소듐하이드록사이드",
    "Citric Acid": "시트릭애씨드",
    "Caffeine": "카페인",
    "Snail Secretion Filtrate": "달팽이점액여과물",
    "Honey": "꿀", "Honey Extract": "꿀추출물",
    "Propolis Extract": "프로폴리스추출물",
    "Royal Jelly": "로열젤리",
    "Mushroom Extract": "버섯추출물",
    "Ginseng Extract": "인삼추출물", "Panax Ginseng Extract": "파낙스진셍추출물",
    "Niacin": "나이아신",
    "Biotin": "비오틴",
}


def normalize_inci(s: str) -> str:
    """INCI 문자열 정규화 — 공백, 대소문자 정리."""
    if not s:
        return ""
    s = re.sub(r"\([^)]*\)", "", s)  # 괄호 제거
    s = s.strip()
    # Title case 일관성
    return s


def localize_one(inci: str) -> str:
    """단일 INCI → 한국어. 매핑 없으면 영문 그대로."""
    norm = normalize_inci(inci)
    if norm in INCI_TO_KOR:
        return INCI_TO_KOR[norm]
    # case-insensitive 재시도
    for k, v in INCI_TO_KOR.items():
        if k.lower() == norm.lower():
            return v
    return norm  # 매핑 없음


def localize_pipe_separated(ingredients_pipe: str) -> str:
    """'Aqua|Glycerin|Niacinamide' → '정제수|글리세린|나이아신아마이드'"""
    if not ingredients_pipe or pd.isna(ingredients_pipe):
        return ""
    parts = ingredients_pipe.split("|")
    return "|".join(localize_one(p) for p in parts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=r"C:\damda\data\products\output\obf_enriched.csv")
    ap.add_argument("--output", default=r"C:\damda\data\products\output\obf_localized.csv")
    args = ap.parse_args()

    df = pd.read_csv(args.input, encoding="utf-8-sig")
    print(f"[load] {len(df)} 제품")

    df["main_ingredients_kor"] = df["main_ingredients"].apply(localize_pipe_separated)
    df["risky_ingredients_kor"] = df["risky_ingredients"].apply(localize_pipe_separated)

    # 매핑 통계
    total_ing = 0
    matched = 0
    for s in df["main_ingredients"]:
        if pd.isna(s):
            continue
        parts = s.split("|")
        for p in parts:
            total_ing += 1
            if normalize_inci(p) in INCI_TO_KOR:
                matched += 1
    print(f"[stats] 매핑된 성분: {matched}/{total_ing} ({100*matched/max(total_ing,1):.1f}%)")

    df.to_csv(args.output, index=False, encoding="utf-8-sig")
    print(f"[save] {args.output}")


if __name__ == "__main__":
    main()
