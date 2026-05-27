---
name: 버그 수정 (Bug fix)
about: API 오류 / 모델 로드 실패 / 응답 형식 이상 등
title: 'fix: '
labels: ['bug']
assignees: ''
---

## 증상

<!-- 무엇이 잘못 동작하는가 -->

재현:
1. ...
2. ...

기대: ...
실제: ...

## 영향 받는 엔드포인트

- `/api/...`

## 의심 원인

- main.py / questionnaire.py / narrative.py / AI 모델 ckpt / 의존성 등

## 로그 / 에러 메시지

```
[traceback or uvicorn output]
```

## 영향 범위

- [ ] FE 동작
- [ ] 시연 시연성
- [ ] 보안 / 데이터 노출
