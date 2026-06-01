"""제품 추천 알고리즘.

입력:
  - measurement: AI 모델의 회귀/분류 출력
  - user_inputs: 자가진단 (skin_type / sensitivity / aging_score / lifestyle)
  - weather: (옵션) 습도 / UV 지수

처리:
  - Hard filter: 민감성 사용자에 안전한 제품만, skin_type 매칭
  - Soft score: 측정값/사용자 입력/날씨에 따라 카테고리 가산
  - Top K 반환

확장 포인트:
  - score_weights 정교화 (제품별)
  - 가격 필터 (사용자 예산)
  - 카테고리별 1개씩 (다양성)
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote


# ============================================================
# 성분 → 카테고리 자동 매핑 (제품 DB 의 카테고리가 빈약할 때 보강)
# ============================================================
# key 는 부분 일치 (lower) — INCI 와 한글 둘 다 잡힘
INGREDIENT_TO_CATEGORIES: Dict[str, List[str]] = {
    # 보습 — 다국어 root substring 매칭
    "히알루론": ["보습"], "hyaluron": ["보습"], "hialuron": ["보습"],
    "글리세린": ["보습"], "글리세롤": ["보습"], "glycerin": ["보습"], "glicerin": ["보습"], "glicerol": ["보습"], "glycerol": ["보습"],
    "세라마이드": ["보습", "진정"], "ceramid": ["보습", "진정"], "ceramida": ["보습", "진정"],
    "스쿠알란": ["보습"], "스쿠알렌": ["보습"], "squalane": ["보습"], "squalene": ["보습"],
    "판테놀": ["보습", "진정"], "panthenol": ["보습", "진정"], "pantenol": ["보습", "진정"],
    "베타인": ["보습"], "betaine": ["보습"],
    "트레할로스": ["보습"], "trehalose": ["보습"],
    "글루칸": ["보습"], "glucan": ["보습"],
    "콜레스테롤": ["보습"], "cholesterol": ["보습"],
    "쉐어버터": ["보습"], "shea butter": ["보습"], "butyrospermum": ["보습"],
    "호호바": ["보습"], "jojoba": ["보습"],
    "프로폴리스": ["보습", "진정"], "propolis": ["보습", "진정"],
    # 진정
    "알로에": ["진정"], "aloe": ["진정"],
    "마데카": ["진정"], "madecass": ["진정"], "centella": ["진정"], "asiaticoside": ["진정"],
    "병풀": ["진정"], "cica": ["진정"],
    "녹차": ["진정"], "green tea": ["진정"], "camellia": ["진정"],
    "어성초": ["진정"], "houttuynia": ["진정"],
    "알란토인": ["진정"], "allantoin": ["진정"],
    "비사보롤": ["진정"], "bisabolol": ["진정"],
    "카모마일": ["진정"], "chamomile": ["진정"], "matricaria": ["진정"],
    "라벤더": ["진정"], "lavender": ["진정"], "lavandula": ["진정"],
    "잔탄검": ["진정"], "xanthan": ["진정"],  # 보충제이긴 한데 일단 진정 카테고리
    # 미백/톤업
    "나이아신아마이드": ["미백"], "niacinamid": ["미백"], "nicotinamid": ["미백"],
    "비타민c": ["미백"], "ascorbic": ["미백"], "ascorbyl": ["미백"], "비타민 c": ["미백"],
    "알부틴": ["미백"], "arbutin": ["미백"],
    "트라넥삼산": ["미백"], "tranexamic": ["미백"],
    "감초": ["미백", "진정"], "licorice": ["미백", "진정"], "glycyrrhiza": ["미백", "진정"],
    # 모공/각질
    "살리실산": ["모공"], "salicylic": ["모공"],
    "글리콜산": ["모공"], "glycolic": ["모공"],
    "락트산": ["모공"], "lactic": ["모공"],
    "파파인": ["모공"], "papain": ["모공"],
    "활성탄": ["모공"], "charcoal": ["모공"],
    "카올린": ["모공"], "kaolin": ["모공"],
    "벤토나이트": ["모공"], "bentonite": ["모공"],
    "징크": ["모공"], "zinc oxide": ["모공"], "산화아연": ["모공"],
    # 탄력/항노화
    "레티놀": ["탄력"], "retinol": ["탄력"], "retinal": ["탄력"], "retinyl": ["탄력"],
    "펩타이드": ["탄력"], "peptide": ["탄력"],
    "콜라겐": ["탄력"], "collagen": ["탄력"], "colageno": ["탄력"],
    "egf": ["탄력"], "growth factor": ["탄력"],
    "아데노신": ["탄력"], "adenosine": ["탄력"],
    "코엔자임": ["탄력"], "coenzyme": ["탄력"],
    "토코페롤": ["탄력"], "tocopherol": ["탄력"],  # 비타민E
    "비타민e": ["탄력"], "vitamin e": ["탄력"],
}


# 성분 → 효과 문구 (사용자 친화적 한국어)
# 우선순위: 점수가 높은 핵심 성분이 카드 effect 에 노출됨
INGREDIENT_EFFECTS: Dict[str, Tuple[str, int]] = {
    # (효과 문구, 우선순위 — 높을수록 먼저). 다국어 root 매칭.
    "히알루론": ("히알루론산이 피부 속까지 수분을 전달", 10),
    "hyaluron": ("히알루론산이 피부 속까지 수분을 전달", 10),
    "hialuron": ("히알루론산이 피부 속까지 수분을 전달", 10),
    "나이아신아마이드": ("나이아신아마이드가 톤업과 피부 장벽 강화", 10),
    "niacinamid": ("나이아신아마이드가 톤업과 피부 장벽 강화", 10),
    "nicotinamid": ("나이아신아마이드가 톤업과 피부 장벽 강화", 10),
    "세라마이드": ("세라마이드가 피부 장벽을 단단하게 채워줍니다", 9),
    "ceramid": ("세라마이드가 피부 장벽을 단단하게 채워줍니다", 9),
    "ceramida": ("세라마이드가 피부 장벽을 단단하게 채워줍니다", 9),
    "판테놀": ("판테놀(프로비타민 B5)이 진정과 보습을 동시에", 9),
    "panthenol": ("판테놀(프로비타민 B5)이 진정과 보습을 동시에", 9),
    "마데카": ("마데카쇼사이드가 손상된 피부를 부드럽게 진정", 9),
    "madecass": ("마데카쇼사이드가 손상된 피부를 부드럽게 진정", 9),
    "centella": ("시카 성분이 자극받은 피부를 진정", 8),
    "cica": ("시카 성분이 자극받은 피부를 진정", 8),
    "병풀": ("병풀(시카) 성분이 자극받은 피부를 진정", 8),
    "알로에": ("알로에 베라가 자극받은 피부를 시원하게 진정", 8),
    "aloe": ("알로에 베라가 자극받은 피부를 시원하게 진정", 8),
    "녹차": ("녹차 추출물의 항산화 성분이 피부를 보호", 7),
    "green tea": ("녹차 추출물의 항산화 성분이 피부를 보호", 7),
    "camellia": ("동백/녹차 추출물의 항산화 성분이 피부를 보호", 7),
    "비타민c": ("비타민C가 칙칙한 톤을 환하게 정돈", 10),
    "ascorbic": ("비타민C가 칙칙한 톤을 환하게 정돈", 10),
    "ascorbyl": ("비타민C 유도체가 자극 없이 톤업", 9),
    "알부틴": ("알부틴이 색소침착을 완화", 8),
    "arbutin": ("알부틴이 색소침착을 완화", 8),
    "트라넥삼산": ("트라넥삼산이 기미·잡티를 케어", 8),
    "tranexamic": ("트라넥삼산이 기미·잡티를 케어", 8),
    "살리실산": ("살리실산(BHA)이 모공 속 노폐물을 부드럽게", 10),
    "salicylic": ("살리실산(BHA)이 모공 속 노폐물을 부드럽게", 10),
    "글리콜산": ("AHA(글리콜산)가 묵은 각질을 매끄럽게", 9),
    "glycolic": ("AHA(글리콜산)가 묵은 각질을 매끄럽게", 9),
    "락트산": ("락트산이 자극 적게 각질을 케어", 7),
    "lactic": ("락트산이 자극 적게 각질을 케어", 7),
    "레티놀": ("레티놀이 주름 개선과 탄력을 끌어올림", 10),
    "retinol": ("레티놀이 주름 개선과 탄력을 끌어올림", 10),
    "펩타이드": ("펩타이드가 콜라겐 생성을 도와 탄력 부스팅", 9),
    "peptide": ("펩타이드가 콜라겐 생성을 도와 탄력 부스팅", 9),
    "콜라겐": ("콜라겐이 피부 결을 매끄럽게", 7),
    "collagen": ("콜라겐이 피부 결을 매끄럽게", 7),
    "아데노신": ("아데노신이 주름 개선에 도움", 8),
    "adenosine": ("아데노신이 주름 개선에 도움", 8),
    "스쿠알란": ("스쿠알란이 유분 장벽을 보강해 수분 증발 차단", 8),
    "squalane": ("스쿠알란이 유분 장벽을 보강해 수분 증발 차단", 8),
    "토코페롤": ("토코페롤(비타민E)이 항산화 보호막 형성", 7),
    "tocopherol": ("토코페롤(비타민E)이 항산화 보호막 형성", 7),
    "쉐어버터": ("쉐어버터의 풍부한 유분이 건조함을 완화", 6),
    "shea butter": ("쉐어버터의 풍부한 유분이 건조함을 완화", 6),
    "butyrospermum": ("쉐어버터의 풍부한 유분이 건조함을 완화", 6),
    "호호바": ("호호바 오일이 피부 친화적 유분으로 보습", 6),
    "jojoba": ("호호바 오일이 피부 친화적 유분으로 보습", 6),
    "프로폴리스": ("프로폴리스가 진정과 영양을 동시에", 7),
    "propolis": ("프로폴리스가 진정과 영양을 동시에", 7),
    "감초": ("감초 추출물이 진정·미백 효과", 7),
    "licorice": ("감초 추출물이 진정·미백 효과", 7),
    "glycyrrhiza": ("감초 추출물이 진정·미백 효과", 7),
    "알란토인": ("알란토인이 피부를 부드럽게 정돈", 6),
    "allantoin": ("알란토인이 피부를 부드럽게 정돈", 6),
    "글리세린": ("글리세린이 피부 표면에 수분을 끌어당김", 4),
    "glycerin": ("글리세린이 피부 표면에 수분을 끌어당김", 4),
    "glicerin": ("글리세린이 피부 표면에 수분을 끌어당김", 4),
    "glicerol": ("글리세린이 피부 표면에 수분을 끌어당김", 4),
    "트레할로스": ("트레할로스가 깊은 수분 보존", 5),
    "trehalose": ("트레할로스가 깊은 수분 보존", 5),
    "베타인": ("베타인이 부드러운 수분 보충", 4),
    "betaine": ("베타인이 부드러운 수분 보충", 4),
    "산화아연": ("산화아연이 물리적 자외선 차단", 7),
    "zinc oxide": ("산화아연이 물리적 자외선 차단", 7),
}


# ============================================================
# 위험 성분 화이트리스트 — 실제로 사용자에게 알릴 가치 있는 것만
# ============================================================
# 매칭은 부분 문자열 (lower) 기준. 키워드는 false-positive 안 나도록 충분히 긴 것만.
TRULY_RISKY_KEYWORDS: Dict[str, str] = {
    # key: 매칭 키워드 (lower), value: 사용자에게 보일 라벨
    "파라벤": "파라벤(방부제)",
    "paraben": "파라벤(방부제)",
    "메칠클로로이소치아졸리논": "MIT/CMIT 방부제",
    "methylchloroisothiazolinone": "MIT/CMIT 방부제",
    "메칠이소치아졸리논": "MIT 방부제",
    "methylisothiazolinone": "MIT 방부제",
    "포름알데히드": "포름알데히드 방출 성분",
    "formaldehyde": "포름알데히드 방출 성분",
    "옥시벤존": "옥시벤존(화학 자외선차단제)",
    "oxybenzone": "옥시벤존(화학 자외선차단제)",
    "옥토크릴렌": "옥토크릴렌(화학 자외선차단제)",
    "octocrylene": "옥토크릴렌(화학 자외선차단제)",
    "에칠헥실메톡시신나메이트": "옥티노세이트(화학 자외선차단제)",
    "ethylhexyl methoxycinnamate": "옥티노세이트(화학 자외선차단제)",
    "homosalate": "호모살레이트(화학 자외선차단제)",
    "호모살레이트": "호모살레이트(화학 자외선차단제)",
    "트리클로산": "트리클로산",
    "triclosan": "트리클로산",
    "프탈레이트": "프탈레이트",
    "phthalate": "프탈레이트",
    "이미다졸리디닐우레아": "이미다졸리디닐우레아(방부제)",
    "imidazolidinyl urea": "이미다졸리디닐우레아(방부제)",
    "디아졸리디닐우레아": "디아졸리디닐우레아(방부제)",
    "diazolidinyl urea": "디아졸리디닐우레아(방부제)",
    "triethanolamine": "트리에탄올아민(자극 가능)",
    "diethanolamine": "디에탄올아민(자극 가능)",
    "변성알코올": "변성알코올(에탄올)",
    "alcohol denat": "변성알코올(에탄올)",
    "álcool desnaturado": "변성알코올(에탄올)",
}

# 카테고리 → 이모지/아이콘은 FE 에서 처리. BE 는 문자열만.


# ============================================================
# 서브라벨 — 성분 기반 작은 chip ("세라마이드 보습" / "비타민C 톤업" 등)
# ============================================================
# (매칭 키워드 lower, sub_label, 우선순위) — 우선순위 높은 게 카드에 먼저 노출
SUB_LABELS: List[Tuple[str, str, int]] = [
    # 보습 계열 — 핵심 성분별 세분화
    ("ceramid", "세라마이드 장벽 보습", 10),
    ("세라마이드", "세라마이드 장벽 보습", 10),
    ("hyaluron", "히알루론 수분 충전", 10),
    ("hialuron", "히알루론 수분 충전", 10),
    ("히알루론", "히알루론 수분 충전", 10),
    ("squalan", "스쿠알란 유분 보호", 8),
    ("스쿠알란", "스쿠알란 유분 보호", 8),
    ("shea butter", "쉐어버터 영양 보습", 7),
    ("butyrospermum", "쉐어버터 영양 보습", 7),
    ("쉐어버터", "쉐어버터 영양 보습", 7),
    ("trehalose", "트레할로스 수분 보존", 6),
    ("트레할로스", "트레할로스 수분 보존", 6),
    # 진정 계열
    ("madecass", "마데카쇼사이드 진정", 10),
    ("마데카", "마데카쇼사이드 진정", 10),
    ("centella", "시카 진정", 10),
    ("cica", "시카 진정", 10),
    ("병풀", "시카 진정", 10),
    ("판테놀", "판테놀 진정 보습", 9),
    ("panthenol", "판테놀 진정 보습", 9),
    ("aloe", "알로에 시원 진정", 8),
    ("알로에", "알로에 시원 진정", 8),
    ("camellia", "녹차 항산화", 7),
    ("녹차", "녹차 항산화", 7),
    ("allantoin", "알란토인 진정", 6),
    ("알란토인", "알란토인 진정", 6),
    ("propolis", "프로폴리스 영양 진정", 7),
    ("프로폴리스", "프로폴리스 영양 진정", 7),
    # 미백 / 톤업
    ("niacinamid", "나이아신아마이드 톤업", 10),
    ("nicotinamid", "나이아신아마이드 톤업", 10),
    ("나이아신아마이드", "나이아신아마이드 톤업", 10),
    ("ascorbic", "비타민C 브라이트닝", 10),
    ("비타민c", "비타민C 브라이트닝", 10),
    ("ascorbyl", "비타민C 유도체 톤업", 9),
    ("arbutin", "알부틴 색소 완화", 8),
    ("알부틴", "알부틴 색소 완화", 8),
    ("tranexamic", "트라넥삼산 잡티 케어", 8),
    ("트라넥삼산", "트라넥삼산 잡티 케어", 8),
    ("licorice", "감초 미백 진정", 7),
    ("감초", "감초 미백 진정", 7),
    # 모공 / 각질
    ("salicylic", "BHA 모공 클렌징", 10),
    ("살리실산", "BHA 모공 클렌징", 10),
    ("glycolic", "AHA 각질 정돈", 9),
    ("글리콜산", "AHA 각질 정돈", 9),
    ("lactic", "락트산 부드러운 각질", 7),
    ("락트산", "락트산 부드러운 각질", 7),
    ("zinc oxide", "산화아연 피지 케어", 7),
    ("산화아연", "산화아연 피지 케어", 7),
    ("kaolin", "카올린 클레이 케어", 6),
    ("카올린", "카올린 클레이 케어", 6),
    # 탄력 / 항노화
    ("retinol", "레티놀 주름 케어", 10),
    ("retinal", "레티날 항노화", 10),
    ("retinyl", "레티닐 항노화", 9),
    ("레티놀", "레티놀 주름 케어", 10),
    ("peptide", "펩타이드 탄력 부스팅", 9),
    ("펩타이드", "펩타이드 탄력 부스팅", 9),
    ("adenosine", "아데노신 주름 개선", 8),
    ("아데노신", "아데노신 주름 개선", 8),
    ("collagen", "콜라겐 결 케어", 6),
    ("콜라겐", "콜라겐 결 케어", 6),
    ("tocopherol", "비타민E 항산화", 5),
    ("토코페롤", "비타민E 항산화", 5),
]


# ============================================================
# 개인화 가중치 — 나이 / 피부타입 × 민감도 / 라이프스타일
# ============================================================
def _age_bias_categories(age: Optional[int]) -> Dict[str, float]:
    """나이대별 카테고리 가산점."""
    if not age:
        return {}
    if age < 25:
        return {"보습": 1.0, "진정": 0.5}
    elif age < 35:
        return {"미백": 1.0, "모공": 0.5}
    elif age < 45:
        return {"탄력": 1.0, "미백": 0.5}
    else:
        return {"탄력": 2.0, "미백": 0.5}


# 제품 DB — 여러 소스 머지
DATA_DIR = Path(__file__).parent / "data"
PRODUCT_DB_SOURCES = [
    DATA_DIR / "products_curated.json",         # K-beauty 골든 시드 (우선)
    DATA_DIR / "products.json",                  # 기존 (OBF 등)
    DATA_DIR / "products_kfda_functional.json", # 식약처 기능성 (양)
]
_PRODUCT_DB: Optional[List[dict]] = None


def get_product_db() -> List[dict]:
    """제품 DB lazy load — 여러 소스 머지.
    같은 id 면 우선순위 높은 소스가 이김 (curated > products > kfda).
    """
    global _PRODUCT_DB
    if _PRODUCT_DB is None:
        merged: List[dict] = []
        seen_ids = set()
        for src in PRODUCT_DB_SOURCES:
            if not src.exists():
                continue
            try:
                data = json.loads(src.read_text(encoding="utf-8"))
                products = data.get("products", []) if isinstance(data, dict) else data
                for p in products:
                    pid = p.get("id")
                    if pid and pid in seen_ids:
                        continue
                    if pid:
                        seen_ids.add(pid)
                    merged.append(p)
            except Exception as e:
                print(f"[product DB] {src.name} 로드 실패: {e}")
        _PRODUCT_DB = merged
        print(f"[product DB] 총 {len(merged)}건 로드 (sources: {[s.name for s in PRODUCT_DB_SOURCES if s.exists()]})")
    return _PRODUCT_DB


# ============================================================
# Hard filter — 탈락 조건
# ============================================================

def _has_truly_risky(product: dict) -> bool:
    """제품에 진짜로 알릴 만한 위험 성분 (TRULY_RISKY_KEYWORDS) 이 있는가.
    글리세린/토코페롤 같은 false-positive 는 무시.
    """
    pool: List[str] = []
    for ing in (product.get("risky_ingredients") or []):
        if isinstance(ing, dict):
            pool.append(str(ing.get("kr") or ing.get("inci") or "").lower())
        else:
            pool.append(str(ing).lower())
    pool.extend(_ingredient_strings(product))
    for kw in TRULY_RISKY_KEYWORDS:
        kw_lower = kw.lower()
        if any(kw_lower in s for s in pool):
            return True
    return False


def _passes_hard_filter(product: dict, user_inputs: dict) -> bool:
    """제품이 사용자에게 적합한가 (탈락 조건).

    민감도 처리:
      ≥5 (극민감): 무향 + 진짜 위험 성분 없음
      ≥4 (매우민감): 진짜 위험 성분 없음 (무향은 가산점)
      ≥3 (민감): 진짜 위험 성분 없음 + 향료/알코올 가산점
    """
    sensitivity = user_inputs.get("sensitivity", 0) or 0
    skin_type = user_inputs.get("skin_type", "")

    # 민감도 ≥5 → 가장 엄격
    if sensitivity >= 5:
        if product.get("fragrance_free") is False:
            return False
        if _has_truly_risky(product):
            return False

    # 민감도 ≥3 → 진짜 위험 성분 (파라벤, 옥시벤존 등) 만 제외
    elif sensitivity >= 3:
        if _has_truly_risky(product):
            return False

    # 피부타입 매칭 — for_skin 있는 제품만 체크 (없으면 통과)
    if skin_type and product.get("for_skin"):
        if skin_type not in product["for_skin"]:
            return False

    return True


# ============================================================
# Soft score — 점수 계산
# ============================================================

def _score(product: dict, measurement: dict, user_inputs: dict, weather: Optional[dict]) -> float:
    """제품에 대한 점수. 높을수록 적합."""
    score = 0.0
    # 성분 기반 카테고리 보강
    cats = set(_enrich_categories(product))
    ings_lower = _ingredient_strings(product)

    # 측정값 기반 — 약한 헤드일수록 해당 카테고리 가산
    # 회귀 (denormalized): moisture < 40 = 건조, pore_value > 300 = 모공 많음 등
    moisture = measurement.get("moisture", 50)
    pore_value = measurement.get("pore_value", 0)
    pigmentation_value = measurement.get("pigmentation_value", 0)
    wrinkle_value = measurement.get("wrinkle_value", 0)
    elasticity = measurement.get("elasticity_mean", 0.7)

    # 분류 등급 (낮을수록 좋음 — 등급이 높으면 해당 케어 필요)
    dryness_grade = measurement.get("dryness_grade", 0)
    wrinkle_grade = measurement.get("wrinkle_grade", 0)
    pigmentation_grade = measurement.get("pigmentation_grade", 0)
    pore_grade = measurement.get("pore_grade", 0)
    sagging_grade = measurement.get("sagging_grade", 0)

    # 보습 카테고리
    if "보습" in cats:
        if moisture < 30 or dryness_grade >= 3:
            score += 5
        elif moisture < 45:
            score += 3
        else:
            score += 1

    # 미백 카테고리
    if "미백" in cats:
        if pigmentation_value > 30 or pigmentation_grade >= 3:
            score += 5
        elif pigmentation_value > 15 or pigmentation_grade >= 2:
            score += 3
        else:
            score += 1

    # 모공 카테고리
    if "모공" in cats:
        if pore_value > 300 or pore_grade >= 3:
            score += 5
        elif pore_value > 200 or pore_grade >= 2:
            score += 3

    # 진정 카테고리 (민감도 사용자에게 강력 가산)
    if "진정" in cats:
        sens = user_inputs.get("sensitivity", 0) or 0
        if sens >= 4:
            score += 4
        elif sens >= 3:
            score += 2

    # 탄력/항노화 카테고리
    if "탄력" in cats:
        aging = user_inputs.get("aging_score", 0) or 0
        if aging >= 4 or wrinkle_grade >= 4 or sagging_grade >= 4:
            score += 5
        elif aging >= 3 or wrinkle_grade >= 3:
            score += 3

    # 피부타입 정확 매칭 보너스
    skin_type = user_inputs.get("skin_type", "")
    if skin_type and skin_type in product.get("for_skin", []):
        score += 1

    # 무향/저자극 보너스 (민감도 보고)
    sensitivity = user_inputs.get("sensitivity", 0) or 0
    if sensitivity >= 3:
        if product.get("fragrance_free"):
            score += 1
        if "저자극" in product.get("tags", []):
            score += 1

    # 날씨 보정 (옵션)
    if weather:
        humidity = weather.get("humidity", 60)
        uv_index = weather.get("uv_index", 0)
        if humidity < 40 and "보습" in cats:
            score += 1  # 건조한 날엔 보습 우선
        if uv_index >= 7 and product.get("subcategory") == "선크림":
            score += 3

    # ===== 개인화 — 나이대 카테고리 가산 =====
    age = user_inputs.get("age")
    age_bias = _age_bias_categories(age)
    for cat, bonus in age_bias.items():
        if cat in cats:
            score += bonus

    # ===== 개인화 — 피부타입 × 민감도 조합 =====
    skin = user_inputs.get("skin_type", "")
    if skin == "건성" and sensitivity >= 3:
        # 세라마이드/판테놀 함유 강한 가산
        if any(kw in s for s in ings_lower for kw in ("ceramid", "세라마이드", "panthenol", "판테놀")):
            score += 2
    if skin == "지성":
        # 가벼운 텍스처 선호 — 토너/세럼/젤
        sub = (product.get("subcategory") or "").lower()
        if any(t in sub for t in ("토너", "세럼", "젤", "lotion", "로션")):
            score += 1
        # 모공/피지 케어 보너스
        if any(kw in s for s in ings_lower for kw in ("salicylic", "살리실산", "zinc oxide", "산화아연", "niacinamid")):
            score += 1
    if skin == "복합성":
        # 균형 — 멀티 카테고리에 약하게 가산
        if len(cats) >= 2:
            score += 0.5
    if skin == "민감성":
        # 진정 강한 가산
        if "진정" in cats:
            score += 2

    # ===== 개인화 — 라이프스타일 플래그 =====
    lf = user_inputs.get("lifestyle_flags") or {}
    if isinstance(lf, dict):
        sleep = lf.get("sleep")
        if sleep in ("poor", "bad"):
            # 수면 부족 → 진정 + 다크서클 케어
            if "진정" in cats:
                score += 1
            if (product.get("subcategory") or "") in ("아이크림", "eye cream"):
                score += 2
        sunscreen = lf.get("sunscreen")
        if sunscreen in ("never", "rarely"):
            # 자외선 노출 多 → 미백 + 항노화 + 선크림
            if "미백" in cats:
                score += 1
            if "탄력" in cats:
                score += 1
            if (product.get("subcategory") or "") == "선크림":
                score += 3

    return score


# ============================================================
# Public API
# ============================================================

def recommend(
    measurement: Dict,
    user_inputs: Dict,
    weather: Optional[Dict] = None,
    top_k: int = 5,
    diversify_by_category: bool = True,
    filter_category: Optional[str] = None,
    filter_categories: Optional[List[str]] = None,
    seed: Optional[int] = None,
    max_per_brand: int = 2,
    exclude_ids: Optional[List[str]] = None,
) -> List[Dict]:
    """제품 추천 메인 함수.

    Args:
        measurement: AI 모델 출력 (regression / classification 값)
        user_inputs: 자가진단 결과
        weather: {humidity, uv_index, ...} (옵션)
        top_k: 반환 개수
        diversify_by_category: 다양성 모드 (카테고리/서브카테고리 분산)
        filter_category: 특정 카테고리만 추천 ("보습" / "미백" / "진정" / "모공" / "탄력")
        seed: 랜덤 시드 (None 이면 결정적 → 같은 입력 = 같은 결과 / 정수면 jitter 적용)
        max_per_brand: top_k 안에 같은 브랜드 최대 몇 개까지

    Returns:
        [{name, brand, category, score, ...}] 점수 내림차순
    """
    db = get_product_db()
    if not db:
        return []

    rng = random.Random(seed) if seed is not None else None
    excluded = set(exclude_ids or [])

    # Hard filter — 0건이면 단계적으로 완화
    candidates = [p for p in db if _passes_hard_filter(p, user_inputs)]
    if len(candidates) == 0:
        # 1차 완화: skin_type 매칭 무시 (민감도만 체크)
        relaxed_inputs = {**user_inputs}
        relaxed_inputs.pop("skin_type", None)
        candidates = [p for p in db if _passes_hard_filter(p, relaxed_inputs)]
        print(f"[recommend] hard filter 0건 → skin_type 무시로 완화: {len(candidates)}건")
    if len(candidates) == 0:
        # 2차 완화: 민감도도 무시 (전체 제품)
        candidates = list(db)
        print(f"[recommend] 여전히 0건 → 전체 제품으로 fallback: {len(candidates)}건")

    # 이미 본 제품 제외 (재추천 용)
    if excluded:
        before = len(candidates)
        candidates = [p for p in candidates if p.get("id") not in excluded]
        if before > 0 and len(candidates) == 0:
            print(f"[recommend] exclude_ids 로 모두 제외됨 — exclude 무시로 fallback")
            candidates = [p for p in db if _passes_hard_filter(p, user_inputs)]

    # 중복 제품 제거 (같은 브랜드+유사 이름 → 1개만)
    seen_dedup = set()
    unique_candidates = []
    for p in candidates:
        k = _dedup_key(p)
        if k in seen_dedup:
            continue
        seen_dedup.add(k)
        unique_candidates.append(p)
    candidates = unique_candidates

    # 카테고리 필터 — 여러 개 선택 시 OR 매칭 (어느 하나라도 매칭되면 통과)
    # filter_categories (배열) 우선, 없으면 filter_category (단일) 사용
    active_filters = set()
    if filter_categories:
        active_filters = {c for c in filter_categories if c}
    elif filter_category:
        active_filters = {filter_category}
    if active_filters:
        candidates = [
            p for p in candidates
            if active_filters & set(_enrich_categories(p))
        ]

    # Soft score
    scored_all: List[Tuple[dict, float]] = []
    for p in candidates:
        s = _score(p, measurement, user_inputs, weather)
        if rng is not None:
            s += rng.uniform(-0.5, 0.5)
        scored_all.append((p, s))

    # 0 초과 우선, 부족하면 0 이하라도 채움
    scored = [(p, s) for p, s in scored_all if s > 0]
    if len(scored) < top_k:
        rest = [(p, s) for p, s in scored_all if s <= 0]
        scored = scored + rest
    scored.sort(key=lambda x: -x[1])

    # 다양성: 카테고리 + 서브카테고리 + 브랜드 분산
    if diversify_by_category and len(scored) > top_k:
        result: List[Tuple[dict, float]] = []
        rest: List[Tuple[dict, float]] = []
        seen_cat_keys: set = set()
        seen_sub: dict = {}
        brand_count: dict = {}

        for p, s in scored:
            brand = p.get("brand", "?")
            sub = p.get("subcategory", "?")
            cat_key = tuple(sorted(_enrich_categories(p)))

            # 브랜드 상한
            if brand_count.get(brand, 0) >= max_per_brand:
                rest.append((p, s))
                continue
            # 카테고리 조합 새것 우선
            if cat_key in seen_cat_keys and seen_sub.get(sub, 0) >= 2:
                rest.append((p, s))
                continue

            result.append((p, s))
            seen_cat_keys.add(cat_key)
            seen_sub[sub] = seen_sub.get(sub, 0) + 1
            brand_count[brand] = brand_count.get(brand, 0) + 1

            if len(result) >= top_k:
                break

        # 부족하면 rest 로 채움
        if len(result) < top_k:
            for p, s in rest:
                brand = p.get("brand", "?")
                if brand_count.get(brand, 0) >= max_per_brand:
                    continue
                result.append((p, s))
                brand_count[brand] = brand_count.get(brand, 0) + 1
                if len(result) >= top_k:
                    break
        if len(result) < top_k:
            # 그래도 부족하면 브랜드 제한 풀고 채움
            for p, s in rest:
                if (p, s) in result:
                    continue
                result.append((p, s))
                if len(result) >= top_k:
                    break

        scored = result

    # 응답 포맷
    return [
        {
            "id": p["id"],
            "name": p.get("name_kr") or p.get("name_en"),
            "brand": p.get("brand", ""),
            "category": _enrich_categories(p),  # 보강된 카테고리 반환
            "subcategory": p.get("subcategory", ""),
            "main_ingredients": [m.get("kr", m.get("inci", "")) for m in p.get("main_ingredients", [])[:5]],
            "all_ingredients": [m.get("kr", m.get("inci", "")) for m in p.get("main_ingredients", [])],
            "fragrance_free": p.get("fragrance_free", False),
            "alcohol_free": p.get("alcohol_free", False),
            "for_skin": p.get("for_skin", []),
            "price_range": p.get("price_range", ""),
            "image_url": p.get("image_url", ""),
            "obf_url": p.get("obf_url", ""),
            "score": round(s, 2),
            "reason": _generate_reason(p, measurement, user_inputs, weather),
            "effect": _generate_effect(p, measurement, user_inputs),
            "sub_labels": _generate_sublabels(p),
            "purchase_url": _purchase_link(p),
            "warnings": _warning_badges(p),
        }
        for p, s in scored[:top_k]
    ]


# ============================================================
# 사용자 친화적 부가 정보 — 효과 / 구매 링크 / 주의 배지
# ============================================================

# 카테고리별 효과 문구 (사용자 친화적 한국어)
CATEGORY_EFFECTS = {
    "보습": "건조한 피부에 깊은 수분",
    "미백": "칙칙한 톤을 환하게",
    "진정": "민감해진 피부 진정",
    "모공": "넓어진 모공을 매끄럽게",
    "탄력": "탄력 있는 피부 결",
}


def _ingredient_strings(product: dict) -> List[str]:
    """제품의 main_ingredients 를 소문자 문자열 리스트로 평탄화."""
    out: List[str] = []
    for ing in (product.get("main_ingredients") or []):
        if isinstance(ing, dict):
            for k in ("kr", "inci", "name"):
                v = ing.get(k)
                if v:
                    out.append(str(v).lower())
        else:
            out.append(str(ing).lower())
    return out


def _enrich_categories(product: dict) -> List[str]:
    """제품 main_ingredients 기반으로 카테고리 동적 보강.
    예: 나이아신아마이드 함유 → 미백 카테고리 추가
    """
    cats = set(product.get("category", []) or [])
    ings = _ingredient_strings(product)
    for kw, added in INGREDIENT_TO_CATEGORIES.items():
        kw_lower = kw.lower()
        if any(kw_lower in s for s in ings):
            cats.update(added)
    return sorted(cats)


def _generate_sublabels(product: dict, max_n: int = 2) -> List[str]:
    """제품 성분 기반 sub-label chip 생성. 우선순위 높은 것부터 max_n 개."""
    ings = _ingredient_strings(product)
    matched: List[Tuple[str, int]] = []
    seen = set()
    for kw, label, prio in SUB_LABELS:
        if label in seen:
            continue
        kw_lower = kw.lower()
        if any(kw_lower in s for s in ings):
            matched.append((label, prio))
            seen.add(label)
    matched.sort(key=lambda x: -x[1])
    return [m for m, _ in matched[:max_n]]


def _dedup_key(product: dict) -> str:
    """제품 중복 판별 키 — 브랜드 + 정규화된 짧은 이름."""
    import re
    brand = (product.get("brand") or "?").strip().lower()
    name = (product.get("name_kr") or product.get("name_en") or "").lower()
    # 숫자/괄호 안/특수문자 제거하고 첫 4단어
    name = re.sub(r"\(.*?\)", " ", name)
    name = re.sub(r"[^a-zA-Z가-힣\s]", " ", name)
    tokens = [t for t in name.split() if t and t not in ("hand", "cream", "lotion", "creme", "crème", "mains")]
    short = " ".join(sorted(tokens[:3]))
    return f"{brand}|{short}"


def _generate_effect(product: dict, measurement: dict, user_inputs: dict) -> str:
    """이 제품으로 기대할 수 있는 효과 — 카드 상단에 표시될 한 줄.
    성분 기반으로 다양화. 성분이 매칭 안 되면 카테고리 fallback.
    """
    ings = _ingredient_strings(product)

    # 1) 성분 기반 효과 문구 수집 (중복 제거)
    seen_msgs = set()
    matched: List[Tuple[str, int]] = []
    for kw, (msg, prio) in INGREDIENT_EFFECTS.items():
        if msg in seen_msgs:
            continue
        kw_lower = kw.lower()
        if any(kw_lower in s for s in ings):
            matched.append((msg, prio))
            seen_msgs.add(msg)

    if matched:
        matched.sort(key=lambda x: -x[1])
        top = [m for m, _ in matched[:2]]
        return " · ".join(top)

    # 2) 카테고리 fallback
    cats = _enrich_categories(product)
    phrases = [CATEGORY_EFFECTS[c] for c in cats if c in CATEGORY_EFFECTS]
    if not phrases:
        return "데일리 케어로 피부 컨디션 유지"
    body = " · ".join(phrases[:2])
    return f"이 제품으로 {body} 효과를 기대해 보세요"


def _purchase_link(product: dict) -> str:
    """구매처 링크. 제품에 명시된 URL 있으면 우선, 없으면 네이버 쇼핑 검색."""
    if product.get("purchase_url"):
        return product["purchase_url"]
    brand = (product.get("brand") or "").strip()
    name = (product.get("name_kr") or product.get("name_en") or "").strip()
    query = f"{brand} {name}".strip()
    if not query:
        return ""
    return f"https://search.shopping.naver.com/search/all?query={quote(query)}"


# 태그/성분명 → 사용자 친화적 라벨 + 위험도 매핑
_TAG_LABEL = {
    "주의성분포함": ("주의 성분 함유", "medium"),
    "알코올": ("알코올 함유", "low"),
    "알코올 함유": ("알코올 함유", "low"),
    "향료": ("향료 함유", "low"),
    "향료 함유": ("향료 함유", "low"),
    "에센셜오일": ("에센셜 오일 함유", "low"),
    "파라벤": ("파라벤 함유", "high"),
}


def _warning_badges(product: dict) -> List[dict]:
    """주의 사항 — 화이트리스트 기반으로 진짜 알릴 만한 것만.
    [{label, level}] (level: high / medium / low)

    글리세린/토코페롤/정제수 같은 명백 안전 성분은 risky_ingredients 에 있어도 무시.
    실제로 알릴 가치 있는 성분 (TRULY_RISKY_KEYWORDS) 과 fragrance/alcohol 태그만 노출.
    """
    badges: List[dict] = []
    seen = set()

    def _add(label: str, level: str):
        if label and label not in seen:
            badges.append({"label": label, "level": level})
            seen.add(label)

    # 1) risky_ingredients 중 화이트리스트에 걸리는 것만
    risky_strings: List[str] = []
    for ing in (product.get("risky_ingredients") or []):
        if isinstance(ing, dict):
            ing_label = ing.get("kr") or ing.get("name") or ing.get("inci") or ""
        else:
            ing_label = str(ing)
        if ing_label:
            risky_strings.append(ing_label.lower())

    for kw, label in TRULY_RISKY_KEYWORDS.items():
        kw_lower = kw.lower()
        if any(kw_lower in s for s in risky_strings):
            _add(label, "high")

    # 2) main_ingredients 직접 스캔 (위험 성분이 risky_ingredients 에 없을 수도 있음)
    ings = _ingredient_strings(product)
    for kw, label in TRULY_RISKY_KEYWORDS.items():
        kw_lower = kw.lower()
        if any(kw_lower in s for s in ings):
            _add(label, "high")

    # 3) 향료/알코올 — fragrance_free 가 False 이면 향료 함유로 추정
    if product.get("fragrance_free") is False:
        # parfum/fragrance INCI 직접 확인
        if any(("parfum" in s or "fragrance" in s or "향료" in s) for s in ings):
            _add("향료 함유", "low")
        else:
            _add("향료 함유 가능", "low")

    if product.get("alcohol_free") is False:
        if any(("alcohol denat" in s or "ethanol" in s or "변성알코올" in s) for s in ings):
            _add("알코올 함유", "low")

    # 4) 태그 기반 (커스텀 라벨링 시)
    for tag in (product.get("tags") or []):
        if tag in _TAG_LABEL:
            label, level = _TAG_LABEL[tag]
            # "주의 성분 함유" 같은 모호한 라벨은 high 매칭 없을 때만 노출
            if level == "medium" and any(b["level"] == "high" for b in badges):
                continue
            _add(label, level)

    return badges


# ============================================================

def _generate_reason(product: dict, measurement: dict, user_inputs: dict, weather: Optional[dict]) -> str:
    """추천 이유를 한 줄로 생성. 측정값/사용자입력의 실제 수치 포함해 설득력 ↑."""
    reasons = []
    cats = set(product.get("category", []))

    # 측정값 기반 — 실제 수치 노출
    moisture = measurement.get("moisture")
    if "보습" in cats and moisture is not None:
        if moisture < 30:
            reasons.append(f"수분 {moisture:.0f} 부족 (보습 시급)")
        elif moisture < 45:
            reasons.append(f"수분 {moisture:.0f} 보통 (보충 권장)")

    pig = measurement.get("pigmentation_value")
    pig_grade = measurement.get("pigmentation_grade")
    if "미백" in cats:
        if pig is not None and pig > 30:
            reasons.append(f"색소반점 {int(pig)}개 (관리 권장)")
        elif pig_grade is not None and pig_grade >= 3:
            reasons.append(f"색소 등급 {pig_grade}/5 (개선 필요)")

    pore = measurement.get("pore_value")
    pore_grade = measurement.get("pore_grade")
    if "모공" in cats:
        if pore is not None and pore > 300:
            reasons.append(f"모공 두드러짐 (수치 {int(pore)})")
        elif pore_grade is not None and pore_grade >= 3:
            reasons.append(f"모공 등급 {pore_grade}/5")

    wrinkle = measurement.get("wrinkle_value")
    wrinkle_grade = measurement.get("wrinkle_grade")
    if "탄력" in cats:
        aging = user_inputs.get("aging_score", 0) or 0
        if aging >= 4:
            reasons.append(f"자가 노화 점수 {aging}/5")
        elif wrinkle_grade is not None and wrinkle_grade >= 4:
            reasons.append(f"주름 등급 {wrinkle_grade}/6")

    # 진정 — 민감성 점수 포함
    sensitivity = user_inputs.get("sensitivity", 0) or 0
    if "진정" in cats and sensitivity >= 3:
        reasons.append(f"민감도 {sensitivity}/5 — 자극 최소화")

    # 피부타입 매칭
    skin_type = user_inputs.get("skin_type", "")
    if skin_type and skin_type in product.get("for_skin", []):
        reasons.append(f"{skin_type} 피부 적합")

    # 제품 특성 — 민감도 ≥3 이면 무향 강조
    if sensitivity >= 3 and product.get("fragrance_free"):
        reasons.append("무향 처방")

    # 핵심 성분 1개 강조 (있으면)
    main_ings = product.get("main_ingredients", [])
    if main_ings:
        first_ing = main_ings[0]
        ing_name = first_ing.get("kr") or first_ing.get("inci", "")
        if ing_name and len(ing_name) < 20:
            reasons.append(f"주성분: {ing_name}")

    # 날씨 보정
    if weather:
        humidity = weather.get("humidity")
        if humidity is not None and humidity < 40 and "보습" in cats:
            reasons.append(f"오늘 습도 {int(humidity)}% (건조)")
        uv = weather.get("uv_index")
        if uv is not None and uv >= 7 and product.get("subcategory") == "선크림":
            reasons.append(f"UV 지수 {uv} (강함)")

    return " · ".join(reasons[:4]) if reasons else "범용 케어"


if __name__ == "__main__":
    # 간단 self-test
    sample_meas = {
        "moisture": 28, "elasticity_mean": 0.62,
        "pore_value": 320, "pigmentation_value": 35, "wrinkle_value": 3.2,
        "dryness_grade": 3, "pigmentation_grade": 3,
    }
    sample_user = {"skin_type": "건성", "sensitivity": 4, "aging_score": 2}
    sample_weather = {"humidity": 30, "uv_index": 6}

    results = recommend(sample_meas, sample_user, sample_weather, top_k=5)
    print(f"추천 {len(results)}개:")
    for r in results:
        print(f"  [{r['score']:.1f}] {r['brand']} {r['name']}")
        print(f"        카테고리: {', '.join(r['category'])} | 이유: {r['reason']}")
