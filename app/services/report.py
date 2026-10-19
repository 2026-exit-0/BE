"""피부 분석 리포트/케어 가이드 생성기.

결과 5지표 + 스캔 부위 + 설문(피부타입·고민·연령·성별) + 환경(날씨)에서
부위·설문과 정합되는 구조화 리포트를 만든다. 데모·실제 경로 공용.

원칙
- 부위 일치: 소견은 '스캔한 부위'에 대해서만. (얼굴 전체일 때만 일반 서술)
- 지표-설문 정합: 강조 지표는 결과의 실제 최약 지표에서 뽑는다(하드코딩 금지).
- 센서 표시값: 0~100 점수를 상식적인 센서 표기(%, 상태어)로 변환해 인용.

점수 의미: moisture/pore/elasticity/pigmentation 은 높을수록 양호.
sebum 은 '유분 수준'(적정 중앙, 과다·과소가 주의).
"""
from __future__ import annotations

from typing import Dict, List, Optional

METRIC_LABEL = {
    "moisture": "수분", "sebum": "유분", "pore": "모공",
    "elasticity": "탄력", "pigmentation": "색소침착",
}
GOODNESS = ("moisture", "pore", "elasticity", "pigmentation")  # 높을수록 좋음

# 스캔 부위(한글) → 리포트 서술용 라벨/초점
AREA_FOCUS = {
    "이마": ("이마", "피지 분비와 가로 주름이 관찰되기 쉬운 부위"),
    "코": ("코", "모공과 블랙헤드, 피지가 집중되는 부위"),
    "볼": ("볼", "수분·탄력 변화와 홍조가 잘 드러나는 부위"),
    "왼쪽 뺨": ("왼쪽 볼", "수분·탄력 변화와 홍조가 잘 드러나는 부위"),
    "오른쪽 뺨": ("오른쪽 볼", "수분·탄력 변화와 홍조가 잘 드러나는 부위"),
    "턱": ("턱", "호르몬성 트러블과 각질이 생기기 쉬운 부위"),
    "얼굴 전체": ("얼굴 전체", "부위별 편차를 함께 고려"),
}


def _band(key: str, s: float) -> str:
    if key == "sebum":
        if s > 68:
            return "주의"       # 과다(지성 경향)
        if s < 45:
            return "보통"       # 과소(건조 경향)
        return "좋음"            # 적정
    if s >= 70:
        return "좋음"
    if s >= 50:
        return "보통"
    return "주의"


def _need(key: str, s: float) -> float:
    """관리 시급도(0 양호 ~ 높을수록 시급). 최약 지표 선정용."""
    if key == "sebum":
        if s > 68:
            return (s - 68) * 2.2
        if s < 45:
            return (45 - s) * 1.4
        return 0.0
    return max(0.0, 70 - s) * 1.2


def sensor_display(key: str, s: float) -> str:
    """0~100 점수 → 상식적인 센서 표기."""
    r = round(s)
    if key == "moisture":
        state = "촉촉" if s >= 70 else ("보통" if s >= 50 else "건조")
        return f"{r}% · {state}"
    if key == "sebum":
        level = "많음" if s > 68 else ("적음" if s < 45 else "적정")
        return f"T존 유분 {level}"
    if key == "pore":
        state = "양호" if s >= 70 else ("보통" if s >= 50 else "넓은 편")
        return f"모공 {state}"
    if key == "elasticity":
        state = "우수" if s >= 70 else ("보통" if s >= 50 else "저하")
        return f"탄력 {state}"
    if key == "pigmentation":
        state = "경미" if s >= 70 else ("보통" if s >= 50 else "뚜렷")
        return f"색소 침착 {state}"
    return f"{r}"

# 지표·밴드별 (의미, 추정 원인, 관리법)
_TEXT = {
    "moisture": {
        "좋음": ("각질층 수분이 충분히 유지되고 있어요.", "꾸준한 보습과 생활 습관이 잘 지켜지는 상태입니다.", "지금의 수분 루틴을 유지하세요."),
        "보통": ("수분이 평균 범위지만 환경에 따라 쉽게 떨어질 수 있어요.", "건조한 실내 환경이나 세안 후 방치가 영향을 줍니다.", "세안 직후 3분 내 토너·세럼으로 수분을 바로 채우세요."),
        "주의": ("각질층 수분이 부족해 당김과 각질이 생기기 쉬운 상태예요.", "과도한 세안, 낮은 습도, 보습 부족이 주요 원인입니다.", "고보습 세럼과 수분팩을 주 2~3회 더하고 미지근한 물로 세안하세요."),
    },
    "sebum": {
        "좋음": ("유분이 적정 수준으로 수분·유분 밸런스가 안정적이에요.", "현재 피지 관리가 잘 이뤄지고 있습니다.", "현재 밸런스를 유지하되 계절 변화에 맞춰 조절하세요."),
        "보통": ("유분이 다소 적어 건조함과 함께 나타날 수 있어요.", "유분막이 얇아 수분 증발이 빨라질 수 있습니다.", "가벼운 오일·밤 타입으로 유분을 보충해 수분 손실을 막으세요."),
        "주의": ("유분 분비가 많아 번들거림과 모공·트러블로 이어지기 쉬워요.", "피지 과다, 호르몬·식습관, 오버클렌징 반동이 원인일 수 있습니다.", "피지 조절 젤 타입을 쓰고 하루 2회 이내로 세안, 오버클렌징을 피하세요."),
    },
    "pore": {
        "좋음": ("모공이 눈에 띄지 않게 관리되고 있어요.", "피지·각질 관리가 잘 되는 상태입니다.", "현재 각질 관리 주기를 유지하세요."),
        "보통": ("부분적으로 모공이 보이는 평균 상태예요.", "피지와 각질이 쌓이면 더 넓어 보일 수 있습니다.", "BHA 토너를 주 1~2회 더해 모공 속 피지를 정돈하세요."),
        "주의": ("모공이 넓어 보이고 피지·블랙헤드가 관찰돼요.", "피지 과다와 각질 축적, 탄력 저하가 겹친 결과입니다.", "BHA·클레이 마스크로 피지를 관리하고 탄력 케어를 병행하세요."),
    },
    "elasticity": {
        "좋음": ("피부 탄력이 잘 유지되고 있어요.", "콜라겐 상태와 생활 습관이 양호합니다.", "자외선 차단과 항산화 관리를 꾸준히 유지하세요."),
        "보통": ("탄력이 평균 범위로, 관리에 따라 달라질 수 있어요.", "자외선 노출과 수분 부족이 탄력에 영향을 줍니다.", "펩타이드·항산화 성분과 자외선 차단을 생활화하세요."),
        "주의": ("탄력 저하가 보여 잔주름·처짐으로 이어질 수 있어요.", "광노화(자외선), 수분·콜라겐 부족이 주요 원인입니다.", "펩타이드·레티놀 나이트 케어와 철저한 자외선 차단을 권장합니다."),
    },
    "pigmentation": {
        "좋음": ("색소 침착이 적어 톤이 균일한 편이에요.", "자외선 관리가 잘 이뤄지고 있습니다.", "자외선 차단을 유지해 현재 톤을 지키세요."),
        "보통": ("부분적인 색소·잡티가 관찰되는 평균 상태예요.", "누적 자외선과 염증 후 색소 침착이 원인입니다.", "비타민C·나이아신아마이드로 톤을 관리하고 자외선을 차단하세요."),
        "주의": ("색소 침착이 뚜렷해 잡티·칙칙함이 두드러져요.", "장기 자외선 노출과 멜라닌 활성이 주요 원인입니다.", "브라이트닝 세럼과 고자외선차단을 병행하고 자극을 피하세요."),
    },
}


def _routines(weakest: str, skin_type: Optional[str]) -> Dict[str, List[str]]:
    morning = ["약산성 클렌저로 가볍게 세안", "토너로 피부 결 정돈", "수분 세럼으로 보습", "자외선 차단제 SPF50+ 마무리"]
    night = ["메이크업·선크림 꼼꼼히 클렌징(이중세안)", "토너로 정돈", "기능성 앰플·세럼", "보습 크림으로 마무리"]
    add = {
        "moisture": ("고보습 수분 앰플 추가", "수분팩 주 2~3회"),
        "sebum": ("피지 조절 젤 타입 사용", "오버클렌징 주의, 유분막 보호"),
        "pore": ("모공 토너·BHA 주 1~2회", "클레이 마스크 주 1회"),
        "elasticity": ("펩타이드 세럼 추가", "레티놀 나이트 케어(저농도부터)"),
        "pigmentation": ("비타민C 브라이트닝 세럼", "자외선 차단 2~3시간마다 덧바르기"),
    }.get(weakest)
    if add:
        morning.insert(2, add[0])
        night.insert(2, add[1])
    if skin_type == "민감성":
        night.append("저자극·무향 제품 위주, 새 제품은 패치 테스트")
    return {"morning": morning, "night": night}


def _lifestyle(weakest: str, environment: Optional[dict]) -> List[str]:
    tips = ["하루 1.5~2L 수분 섭취", "7시간 이상 숙면으로 피부 재생 돕기", "자외선 차단 생활화"]
    if weakest == "moisture":
        tips.append("실내 습도 40~60% 유지(가습기 활용)")
    if weakest in ("elasticity", "pigmentation"):
        tips.append("외출 20분 전 자외선 차단제 도포, 모자·선글라스 병행")
    env = environment or {}
    uv = env.get("uv_index")
    if uv and str(uv) in ("높음", "매우 높음", "high", "veryHigh"):
        tips.append(f"오늘 자외선 지수 '{uv}' — 외출 시 차단 강화 권장")
    hum = env.get("humidity")
    try:
        if hum is not None and float(hum) < 40:
            tips.append("건조한 날씨 — 보습 단계를 한 겹 더하세요")
    except (TypeError, ValueError):
        pass
    return tips


def build_report(metrics: Dict[str, Optional[float]], scan_area: str = "얼굴 전체",
                 skin_type: Optional[str] = None, concerns: Optional[List[str]] = None,
                 age_band: Optional[str] = None, gender: Optional[str] = None,
                 environment: Optional[dict] = None) -> dict:
    present = {k: float(v) for k, v in metrics.items() if v is not None}
    if not present:
        return {}

    # 최약 지표(관리 시급도 최대)
    weakest = max(present, key=lambda k: _need(k, present[k]))
    weakest_label = METRIC_LABEL[weakest]
    overall = round(sum(present.values()) / len(present))

    area_label, area_focus = AREA_FOCUS.get(scan_area, (scan_area, ""))

    metric_cards = []
    for k, s in present.items():
        b = _band(k, s)
        meaning, cause, care = _TEXT[k][b]
        metric_cards.append({
            "key": k, "label": METRIC_LABEL[k], "score": round(s, 1),
            "sensor": sensor_display(k, s), "band": b,
            "meaning": meaning, "cause": cause, "care": care,
        })
    # 시급도 높은 순 정렬(리포트 상단에 주의 지표 먼저)
    metric_cards.sort(key=lambda c: _need(c["key"], c["score"]), reverse=True)

    st = skin_type or "복합성"
    summary = (
        f"{area_label} 측정 결과, {st} 피부 경향이며 종합 점수는 {overall}점입니다. "
        f"특히 {weakest_label} 관리가 가장 필요한 상태로, 아래 지표별 소견과 맞춤 루틴을 참고하세요."
    )

    # 부위 소견 — 스캔한 부위에 대해서만 서술(다른 부위 언급 금지)
    region_note = (
        f"이번 측정은 '{area_label}'를 촬영했습니다. "
        f"{area_label}는 {area_focus}로, 측정값 기준 {weakest_label}에 주의가 필요합니다."
        if area_focus else
        f"이번 측정 부위는 '{area_label}'이며, {weakest_label} 중심으로 관리하세요."
    )

    routines = _routines(weakest, skin_type)
    top_concern = (concerns or [None])[0]
    recommend_basis = (
        f"{st} 피부"
        + (f" · '{top_concern}' 고민" if top_concern else "")
        + f" · {weakest_label} 보완을 우선 기준으로 제품을 매칭했습니다."
    )

    return {
        "skin_type": st,
        "overall_score": overall,
        "scan_area": area_label,
        "weakest": weakest,
        "weakest_label": weakest_label,
        "summary": summary,
        "metrics": metric_cards,
        "region_note": region_note,
        "routine_morning": routines["morning"],
        "routine_night": routines["night"],
        "lifestyle": _lifestyle(weakest, environment),
        "recommend_basis": recommend_basis,
        "next_scan_days": 14,
    }
