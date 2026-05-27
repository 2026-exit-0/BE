---
name: API 변경 (Breaking change)
about: 기존 엔드포인트의 schema / 동작 변경 (FE 영향 큰 작업)
title: 'api: '
labels: ['api', 'breaking']
assignees: ''
---

## 배경 / 동기

<!-- 왜 기존 API 를 바꿔야 하는가 -->

## 변경 전 → 후

| 항목 | Before | After |
|---|---|---|
| 엔드포인트 | `/api/...` | `/api/...` |
| 요청 형식 | ... | ... |
| 응답 형식 | ... | ... |

## Breaking change 영향

- [ ] FE 강제 갱신 필요
- [ ] 하위 호환 deprecation 기간 둘 것
- [ ] 즉시 swap (시연 환경 한정)

## 마이그레이션 가이드

<!-- FE 측에서 어떻게 갱신해야 하는지 -->

## 작업 체크리스트

- [ ] BE 변경 + 테스트
- [ ] /docs schema 검증
- [ ] FE 동시 PR 또는 사전 통보
- [ ] README 갱신
