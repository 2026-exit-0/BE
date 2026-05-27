"""자가진단 questionnaire — 사용자가 본인 피부 상태를 모를 때 2분 진단.

10개 질문 4섹션으로 사용자가 답하면 다음을 산정:
  - skin_type: 건성 / 지성 / 복합성 / 민감성 / 중성 (max-score 방식)
  - sensitivity: 1~5 (점수 합산 → 5단계)
  - aging_score: 1~5 (탄력/주름/색소 종합)
  - lifestyle_flags: dict (자외선 차단제 등 narrative 보조 정보)

질문 선정 원칙:
  - 모델 출력 헤드와 1:1 매핑되는 자가인식 질문 우선 (C1=sagging, C2=wrinkle, C3=pigment, A3=pore)
  - 민감도는 3가지 다른 메커니즘 cover (B1 화학 / B2 UV / B3 환경)
  - 복합성 식별은 A2 만 가능 (T존 vs U존 차이) — 필수 보존
  - 모델 분류 7헤드 전부 user input 으로 보강 가능

질문 텍스트와 점수 가중치는 cosmetology 도메인 지식 기반 placeholder.
실제 피부과 자가진단표 / annotator agreement 데이터 참고해 추후 조정 권장.

사용 예:
    from questionnaire import QUESTIONS, score_answers

    # UI 에서 사용자 답변 수집
    answers = {"A1": 0, "A2": 1, "B1": 2, ...}  # question_id -> option_idx
    result = score_answers(answers)
    # result = {"skin_type": "건성", "sensitivity": 3, "aging_score": 2, "lifestyle_flags": {...}}
"""

from __future__ import annotations

from typing import Dict, List, Tuple


# ============================================================
# 질문 데이터
# ============================================================
# 각 질문은 다음 구조:
#   id          : 식별자 (A1, A2, B1, ...)
#   section     : 'skin_type' | 'sensitivity' | 'aging' | 'lifestyle'
#   text        : UI 에 표시될 한국어 질문
#   options     : 선택지 리스트. 각 옵션은:
#       label   : UI 에 표시될 텍스트
#       scores  : section 에 따라 다른 의미
#           skin_type   → {"건성": +3, "지성": +1, ...} (해당 타입 점수 가중)
#           sensitivity → {"sensitivity": +N}
#           aging       → {"aging": +N}
#           lifestyle   → {"flag_key": value}

QUESTIONS: List[Dict] = [
    # ===== Section A: 피부 타입 (3 questions) =====
    {
        "id": "A1",
        "section": "skin_type",
        "text": "세안 후 아무것도 바르지 않고 30분이 지나면 피부 상태가 어떤가요?",
        "options": [
            {"label": "매우 당기고 건조함", "scores": {"건성": 3}},
            {"label": "약간 당기는 느낌", "scores": {"건성": 1, "중성": 1}},
            {"label": "편안하고 적당히 촉촉함", "scores": {"중성": 3}},
            {"label": "T존(이마/코)만 번들거림", "scores": {"복합성": 3}},
            {"label": "전체적으로 번들거림", "scores": {"지성": 3}},
        ],
    },
    {
        "id": "A2",
        "section": "skin_type",
        "text": "T존(이마/코) 과 U존(볼/턱) 의 유분 차이가 큰가요?",
        "options": [
            {"label": "T존이 훨씬 더 번들거림", "scores": {"복합성": 3}},
            {"label": "T존이 약간 더 번들거림", "scores": {"복합성": 1}},
            {"label": "거의 같음", "scores": {"중성": 1}},
            {"label": "U존이 더 건조함", "scores": {"건성": 1, "복합성": 1}},
        ],
    },
    {
        "id": "A3",
        "section": "skin_type",
        "text": "모공 크기는 어떤 편인가요?",
        "options": [
            {"label": "거의 안 보임", "scores": {"건성": 2, "중성": 1}},
            {"label": "T존만 보임", "scores": {"복합성": 2}},
            {"label": "전체적으로 약간 보임", "scores": {"중성": 1, "지성": 1}},
            {"label": "전체적으로 두드러짐", "scores": {"지성": 3}},
        ],
    },
    # ===== Section B: 민감도 (3 questions — 화학/UV/환경 3가지 메커니즘 cover) =====
    {
        "id": "B1",
        "section": "sensitivity",
        "text": "새 화장품을 사용한 후 가려움/홍반/따끔거림이 얼마나 자주 발생하나요?",
        "options": [
            {"label": "거의 매번 발생", "scores": {"sensitivity": 4}},
            {"label": "자주 발생", "scores": {"sensitivity": 3}},
            {"label": "가끔 발생", "scores": {"sensitivity": 2}},
            {"label": "드물게", "scores": {"sensitivity": 1}},
            {"label": "거의 없음", "scores": {"sensitivity": 0}},
        ],
    },
    {
        "id": "B2",
        "section": "sensitivity",
        "text": "햇볕에 잠깐 노출되면 피부가 어떻게 반응하나요?",
        "options": [
            {"label": "쉽게 빨개지고 따끔거림", "scores": {"sensitivity": 3}},
            {"label": "빨개졌다가 그을림", "scores": {"sensitivity": 1}},
            {"label": "별 변화 없이 그을림", "scores": {"sensitivity": 0}},
            {"label": "거의 변화 없음", "scores": {"sensitivity": 0}},
        ],
    },
    {
        "id": "B3",
        "section": "sensitivity",
        "text": "계절 변화 (특히 환절기) 에 피부 트러블이 생기나요?",
        "options": [
            {"label": "항상 — 각질/홍반/뾰루지 다 발생", "scores": {"sensitivity": 3}},
            {"label": "자주 발생", "scores": {"sensitivity": 2}},
            {"label": "가끔 발생", "scores": {"sensitivity": 1}},
            {"label": "거의 없음", "scores": {"sensitivity": 0}},
        ],
    },
    # ===== Section C: 노화 (3 questions — 각각 sagging/wrinkle/pigment 헤드 직결) =====
    {
        "id": "C1",
        "section": "aging",
        "text": "거울로 볼 때 피부 탄력 (처짐 정도) 은 어떤가요?",
        "options": [
            {"label": "매우 탄력 있음", "scores": {"aging": 0}},
            {"label": "양호함", "scores": {"aging": 1}},
            {"label": "약간 처짐 느낌", "scores": {"aging": 2}},
            {"label": "확실히 처짐", "scores": {"aging": 3}},
            {"label": "심하게 처짐", "scores": {"aging": 4}},
        ],
    },
    {
        "id": "C2",
        "section": "aging",
        "text": "눈가 / 미간 / 입가의 주름은 어떤가요?",
        "options": [
            {"label": "거의 없음", "scores": {"aging": 0}},
            {"label": "표정 지을 때만 보임", "scores": {"aging": 1}},
            {"label": "무표정에도 약간 보임", "scores": {"aging": 2}},
            {"label": "무표정에도 뚜렷함", "scores": {"aging": 3}},
        ],
    },
    {
        "id": "C3",
        "section": "aging",
        "text": "기미 / 잡티 / 색소침착이 눈에 띄나요?",
        "options": [
            {"label": "거의 없음", "scores": {"aging": 0}},
            {"label": "한두 군데만 옅게", "scores": {"aging": 1}},
            {"label": "여러 군데 보임", "scores": {"aging": 2}},
            {"label": "전체적으로 뚜렷함", "scores": {"aging": 3}},
        ],
    },
    # ===== Section D: 라이프스타일 (1 question — 피부 영향 가장 직접적인 항목) =====
    {
        "id": "D1",
        "section": "lifestyle",
        "text": "자외선 차단제 사용 빈도는?",
        "options": [
            {"label": "매일 외출 전", "scores": {"sunscreen": "daily"}},
            {"label": "장시간 야외 활동 시", "scores": {"sunscreen": "occasional"}},
            {"label": "거의 사용 안 함", "scores": {"sunscreen": "rare"}},
        ],
    },
]


# ============================================================
# 채점 알고리즘
# ============================================================

SKIN_TYPES = ["건성", "지성", "복합성", "민감성", "중성"]


def score_answers(answers: Dict[str, int]) -> dict:
    """사용자 답변을 받아 최종 점수 산정.

    Args:
        answers: {question_id: option_index} dict. 모든 질문에 답해야 함.

    Returns:
        {
            "skin_type": str,           # 건성/지성/복합성/민감성/중성 중 하나
            "skin_type_scores": dict,   # 각 타입별 누적 점수 (디버깅/투명성)
            "sensitivity": int,         # 1~5
            "sensitivity_raw": int,     # 합산 raw score (max 10)
            "aging_score": int,         # 1~5
            "aging_raw": int,           # max 10
            "lifestyle_flags": dict,    # {"sunscreen": "daily"/"occasional"/"rare"}
            "incomplete": list,         # 답변 누락된 question_id 들 (있으면)
        }
    """
    # 누락 답변 체크
    answered_ids = set(answers.keys())
    expected_ids = {q["id"] for q in QUESTIONS}
    incomplete = sorted(expected_ids - answered_ids)

    skin_type_scores: Dict[str, int] = {t: 0 for t in SKIN_TYPES}
    sensitivity_raw = 0
    aging_raw = 0
    lifestyle_flags: Dict[str, str] = {}

    for q in QUESTIONS:
        qid = q["id"]
        if qid not in answers:
            continue
        opt_idx = answers[qid]
        if opt_idx < 0 or opt_idx >= len(q["options"]):
            continue
        chosen = q["options"][opt_idx]
        scores = chosen.get("scores", {})

        if q["section"] == "skin_type":
            for type_name, weight in scores.items():
                if type_name in skin_type_scores:
                    skin_type_scores[type_name] += int(weight)
        elif q["section"] == "sensitivity":
            sensitivity_raw += int(scores.get("sensitivity", 0))
        elif q["section"] == "aging":
            aging_raw += int(scores.get("aging", 0))
        elif q["section"] == "lifestyle":
            for k, v in scores.items():
                lifestyle_flags[k] = v

    # 민감성 자동 보정: sensitivity_raw 가 매우 높으면 skin_type="민감성"으로 격상
    # (민감성은 다른 타입 위에 덮어쓰는 라벨). 새 max=10 기준 6 이상 (~60%).
    skin_type = max(skin_type_scores.items(), key=lambda kv: kv[1])[0]
    if sensitivity_raw >= 6:
        skin_type = "민감성"

    # 1~5 정규화
    sensitivity_max = _max_section_score("sensitivity")
    aging_max = _max_section_score("aging")
    sensitivity = _normalize_to_5(sensitivity_raw, sensitivity_max)
    aging = _normalize_to_5(aging_raw, aging_max)

    return {
        "skin_type": skin_type,
        "skin_type_scores": skin_type_scores,
        "sensitivity": sensitivity,
        "sensitivity_raw": sensitivity_raw,
        "aging_score": aging,
        "aging_raw": aging_raw,
        "lifestyle_flags": lifestyle_flags,
        "incomplete": incomplete,
    }


def _max_section_score(section_key: str) -> int:
    """해당 섹션의 max possible score 계산 (정규화 분모용)."""
    total = 0
    for q in QUESTIONS:
        if q["section"] != section_key:
            continue
        max_in_q = max(
            (int(opt.get("scores", {}).get(section_key, 0)) for opt in q["options"]),
            default=0,
        )
        total += max_in_q
    return total


def _normalize_to_5(raw: int, max_score: int) -> int:
    """raw 점수를 1~5 정수로 정규화."""
    if max_score <= 0:
        return 1
    ratio = raw / max_score
    # 1=낮음, 5=매우 높음
    if ratio < 0.2:
        return 1
    if ratio < 0.4:
        return 2
    if ratio < 0.6:
        return 3
    if ratio < 0.8:
        return 4
    return 5


# ============================================================
# UI 용 helper
# ============================================================

def get_questions_for_ui() -> List[Dict]:
    """프론트엔드에 보낼 형태로 질문 리스트 반환 (scores 같은 내부값 제외)."""
    return [
        {
            "id": q["id"],
            "section": q["section"],
            "text": q["text"],
            "options": [{"label": opt["label"]} for opt in q["options"]],
        }
        for q in QUESTIONS
    ]


if __name__ == "__main__":
    # 간단 self-test
    sample = {q["id"]: 0 for q in QUESTIONS}
    result = score_answers(sample)
    print(f"질문 수: {len(QUESTIONS)}")
    print(f"sensitivity_max: {_max_section_score('sensitivity')}")
    print(f"aging_max: {_max_section_score('aging')}")
    print("Sample result (모든 질문 첫 번째 옵션):")
    for k, v in result.items():
        print(f"  {k}: {v}")
