# 대표 주의 큐

## 목적

Attention Queue는 대표가 지금 확인해야 할 예외를 기존 운영 데이터에서 결정론적으로 계산합니다. LLM을
호출하거나 새 업무를 실행하지 않으며, Task의 입력 우선순위와도 분리됩니다.

## 탐지 규칙 v1

| 종류 | 조건 | 수준 |
|---|---|---|
| 지연 약속 | 미완료 Commitment가 마감 초과 | 24시간 미만 `action`, 24시간 이상 `decision`, 72시간 이상 `critical` |
| 장기 실행 | Task `running` 상태가 설정된 시간 이상 유지 | 기준 이상 `action`, 기준 2배 이상 `critical` |
| 업무 실패 | Task가 `failed` | 실패 1회 `watch`, 2회 `decision`, 3회 이상 `critical` |
| 승인 적체 | Approval이 `pending` | 기본 `decision`, `critical` 위험 또는 72시간 이상 대기 시 `critical` |

기본 설정은 `ATTENTION_TASK_STALE_SECONDS=1200`,
`ATTENTION_COMMITMENT_DECISION_HOURS=24`, `ATTENTION_COMMITMENT_CRITICAL_HOURS=72`,
`ATTENTION_APPROVAL_CRITICAL_HOURS=72`입니다. 심각도 순, 발생 후 경과시간 순으로 정렬합니다.

## API

- `GET /api/v1/attention`
- 최소 수준: `?min_level=decision`
- 종류: `?kind=overdue_commitment`
- 개수 제한: `?limit=20`

응답에는 규칙 버전, 생성시각, 수준별 건수와 항목이 포함됩니다. 각 항목의 ID는
`종류:원본 리소스 ID`로 결정되므로 같은 원인에서 중복 항목이 생기지 않습니다.

## CEO Desk와 Telegram

CEO Desk의 **대표 주의 큐**는 최대 8건을 표시하고 `decision`과 `critical` 건수를 상단 지표에
반영합니다. Telegram `/briefing`도 상위 5건과 권장 확인 행동을 보여줍니다. 둘 다 데이터 조회만 하므로
OpenAI 비용이 없습니다.

## 안전 경계

- 주의 항목은 계산 결과이며 별도 실행 명령이 아닙니다.
- 재시도, 승인, 외부 발송, 결제, 삭제, 배포를 자동 수행하지 않습니다.
- 회사 ID가 같은 원본만 조회하므로 다른 회사의 상태가 섞이지 않습니다.
- 사람의 확인/결정 없이 상태를 바꾸지 않습니다.
- 알림 예약, 중복 알림 억제, 확인 완료(acknowledge) 이력은 후속 Proactive Intelligence 단계입니다.

## 운영 점검

배포 후 프로젝트 폴더의 `SMOKE_ATTENTION_QUEUE.bat`을 실행합니다. Render에서 복사한
`APP_API_KEY`를 클립보드로 읽고, `[SMOKE]` 지연 약속과 승인 요청을 하나씩 생성해 심각도·필터를 확인한
뒤 각각 취소·거절로 닫습니다. OpenAI 업무는 실행하지 않습니다.
