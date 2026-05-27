<!--
첫 줄은 commit message 와 동일하게:
  <type>: <한국어 요약>
type: feat | fix | api | docs | refactor | chore | perf
-->

## 배경

<!-- 어떤 issue / FE 요구 / AI 변화에 대응하는 PR 인가 -->

## 변경 사항

### 엔드포인트

| Method | Path | 변경 |
|---|---|---|
| GET / POST | `/api/...` | 신규 / 수정 |

### 코드

- `main.py` — ...
- `questionnaire.py` — ...
- `narrative.py` — ...
- (기타 신규 모듈)

### Schema 변경

<!-- breaking change 있으면 명시 -->

## 검증 방법

```bash
# 서버 띄우고 curl
curl -X POST http://localhost:8000/api/predict \
  -F "image=@test.jpg" \
  -F "region=L_CHEEK" \
  -F "moisture=42.5"
```

## 보장 / 한계

- ✅ 기존 엔드포인트 호환 유지 (또는 breaking change 명시)
- ✅ 추론 latency 측정값: ___ ms
- ⚠ 동시성 처리 (concurrency) 검토 사항: ...

## FE 영향

- 필요 FE 변경: 있음/없음
- 필요 FE PR: #N

## 알려진 한계 / 후속 작업

- [ ] ...

## 참고

- 관련 Issue #N
- AI repo PR / Issue (모델 변경 시)
- FE repo PR (UI 변경 시)
