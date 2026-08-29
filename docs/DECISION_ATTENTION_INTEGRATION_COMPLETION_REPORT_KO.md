# 대표 결정 주의 큐 통합 완료 보고서

## 완료 범위

- `decision-readiness-v1`과 `decision-follow-through-v1` 결과를 결정 ID별로 결합
- 같은 결정을 하나의 `decision_governance:<decision_id>` 주의 항목으로 표현
- 근거 차단, 검토 필요, 실행 위험, 후속 미연결, 관찰 상태의 결정론적 AttentionLevel 변환
- 기존 `GET /api/v1/attention`, CEO Desk, Telegram 데일리 브리핑에 자동 반영
- `attention-rules-v2` 규칙 버전으로 변경
- tenant 격리와 검증·실행계획이 정상인 결정의 큐 제외 검증

## 수준 규칙

| 입력 신호 | AttentionLevel |
|---|---|
| readiness `blocked` | `critical` |
| readiness `review` 또는 follow-through `at_risk` | `decision` |
| follow-through `untracked` | `action` |
| readiness `watch` | `watch` |
| readiness `ready`이며 follow-through `planned/in_progress/complete` | 항목 없음 |

여러 신호가 동시에 있으면 가장 높은 수준을 사용합니다. 근거 상태와 후속 실행 상태는 evidence에 함께
보존되며 원본 Decision, ProvenanceRecord, Commitment를 변경하지 않습니다.

## 구조 결정

- 새 테이블과 migration을 만들지 않았습니다.
- 두 기존 계산 서비스를 다시 사용해 분류 규칙의 단일 기준을 유지합니다.
- 내부 통합 호출은 `limit=None`으로 전체 결과를 받아 API 표시 limit 때문에 결정이 누락되지 않게 했습니다.
- 외부 행동, OpenAI 호출, 자동 승인, 상태 전이는 추가하지 않았습니다.

## 검증 기준

- 미검증 근거와 후속 미연결이 함께 있는 결정은 하나의 `decision` 항목
- 검증 완료 근거와 미래 마감 후속 약속이 있는 결정은 주의 항목 없음
- 다른 tenant의 결정은 조회되지 않음
- 데일리 브리핑의 대표 확인 건수와 상위 주의 큐에 결정 신호 포함
