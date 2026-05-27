---
name: 기능 추가 (Feature)
about: 새 엔드포인트 / 자가진단 항목 / narrative 로직 등
title: 'feat: '
labels: ['feature']
assignees: ''
---

## 배경 / 동기

<!-- FE 요구 / AI 모델 변화 / 시연 시나리오 등 -->

## API 변경 / 추가

| Method | Path | 변경 종류 |
|---|---|---|
| GET / POST | `/api/...` | 신규 / 수정 |

## 요청 / 응답 schema

```python
# 요청
...

# 응답
{
    ...
}
```

## AI 모델 의존

- 호환 ckpt 버전: v3 / v5 / 둘 다
- 호출할 `DamdaInferenceModel` 메서드: `predict()` 등

## FE 영향

- 필요 FE 변경: ...

## 작업 체크리스트

- [ ] 코드 (main.py / 신규 모듈)
- [ ] Pydantic schema
- [ ] /docs 동작 확인
- [ ] curl 또는 httpie 수동 테스트
- [ ] FE 통합 테스트
- [ ] README 갱신

## 참고

- AI repo 관련 PR / Issue
- FE repo 관련 PR / Issue
