<!--
첫 줄은 commit message 와 동일하게:
  <type>: <한국어 요약>
type: feat | fix | api | docs | refactor | chore | perf
-->

## 배경 / 동기

<!-- 어떤 사용자 시나리오 / FE 요구사항 / AI 모델 변화에 따른 작업인가 -->

## API 변경 / 추가 범위

<!-- 영향 받는 / 신설할 엔드포인트 -->

| Method | Path | 변경 종류 |
|---|---|---|
| GET / POST | `/api/...` | 신규 / 수정 / 삭제 |

## 요청 / 응답 schema

```python
# 요청 (Pydantic / FormData)
class XxxRequest(BaseModel):
    field_a: str
    field_b: int

# 응답
{
    "result": ...,
    "meta": {...}
}
```

## AI 모델 의존

<!-- ckpt 경로 / config 버전 / sensor_dim / 회귀-분류 헤드 변화 등 -->

- 필요 ckpt 버전: v3 / v5 / 둘 다 호환
- 영향 받는 infer.py 메서드: `predict()`, `predict_batch()` 등

## FE 영향

<!-- FE 어떤 컴포넌트가 이 변경에 맞춰 갱신 필요한가 -->

## 성능 / 안정성 영향

- 추론 latency 변화 예상: ms 단위
- 메모리 사용 변화: MB 단위
- 동시 요청 처리 (concurrency)

## 작업 체크리스트

- [ ] API 코드 변경 (`main.py` / 신규 모듈)
- [ ] Pydantic schema 정의
- [ ] /docs (Swagger) 동작 확인
- [ ] curl 또는 httpie 로 수동 테스트
- [ ] FE 와 통합 테스트
- [ ] README 갱신

## 참고

- 관련 AI Issue / PR (모델 변경)
- 관련 FE Issue / PR (UI 변경)
- FastAPI 문서: https://fastapi.tiangolo.com
