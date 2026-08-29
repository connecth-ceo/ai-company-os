# 대표 주의 큐

## 목적

Attention Queue는 대표가 지금 확인해야 할 예외를 기존 운영 데이터에서 결정론적으로 계산합니다. LLM을
호출하거나 새 업무를 실행하지 않으며, Task의 입력 우선순위와도 분리됩니다.

## 탐지 규칙 v3

| 종류 | 조건 | 수준 |
|---|---|---|
| 지연 약속 | 미완료 Commitment가 마감 초과 | 24시간 미만 `action`, 24시간 이상 `decision`, 72시간 이상 `critical` |
| 장기 실행 | Task `running` 상태가 설정된 시간 이상 유지 | 기준 이상 `action`, 기준 2배 이상 `critical` |
| 업무 실패 | Task가 `failed` | 실패 1회 `watch`, 2회 `decision`, 3회 이상 `critical` |
| 승인 적체 | Approval이 `pending` | 기본 `decision`, `critical` 위험 또는 72시간 이상 대기 시 `critical` |
| 결정 거버넌스 | Decision readiness와 follow-through를 결정 ID별로 통합 | 근거·기한 차단 `critical`, 검토 필요·후속 위험 `decision`, 후속 미연결 `action`, 관찰 신호 `watch` |

기본 설정은 `ATTENTION_TASK_STALE_SECONDS=1200`,
`ATTENTION_COMMITMENT_DECISION_HOURS=24`, `ATTENTION_COMMITMENT_CRITICAL_HOURS=72`,
`ATTENTION_APPROVAL_CRITICAL_HOURS=72`입니다. 심각도 순, 발생 후 경과시간 순으로 정렬합니다.

## API

- `GET /api/v1/attention`
- 최소 수준: `?min_level=decision`
- 종류: `?kind=overdue_commitment`
- 결정 거버넌스만: `?kind=decision_governance`
- 미확인 신호만: `?include_acknowledged=false`
- 개수 제한: `?limit=20`

응답에는 규칙 버전, 생성시각, 수준별 건수와 항목이 포함됩니다. 각 항목의 ID는
`종류:원본 리소스 ID`로 결정되므로 같은 원인에서 중복 항목이 생기지 않습니다. 결정 거버넌스는
`decision_governance:<decision_id>` 하나에 근거 신뢰도와 후속 실행 상태를 함께 담아 같은 결정을 두 번
올리지 않습니다. 검증 완료 근거와 유효한 후속 약속을 모두 가진 결정은 주의 큐에서 제외됩니다.

각 항목에는 현재 신호의 `fingerprint`와 `acknowledged` 상태가 포함됩니다. 지문은 초 단위 경과 카운터를
제외하고 수준, 원본, 탐지 시각, 안정적인 근거를 해시합니다. 따라서 같은 신호를 다시 조회해도 확인 상태가
유지되지만 심각도 상승이나 근거 변경은 새 지문이 되어 자동으로 재등장합니다.

확인은 `POST /api/v1/attention/{attention_id}/acknowledgements`로 기록합니다. 요청에는 화면에서 받은
`expected_fingerprint`, `acknowledged_by`, 선택 메모, `idempotency_key`가 필요합니다. 오래된 화면의 지문은
409로 거절하며, 이력은 `GET /api/v1/attention/acknowledgements`에서 회사별로 조회합니다.

## CEO Desk와 Telegram

CEO Desk의 **대표 주의 큐**는 최대 8건을 표시하고 미확인 `decision`과 `critical` 건수를 상단 지표에
반영합니다. 대표는 항목별 **확인 처리**를 누를 수 있으며 확인된 항목은 원본 상태를 바꾸지 않고 흐리게
표시됩니다. Telegram `/briefing`은 미확인 상위 5건만 보여 같은 신호의 반복 보고를 줄입니다. 둘 다
OpenAI 비용이 없습니다.

## 안전 경계

- 주의 항목은 계산 결과이며 별도 실행 명령이 아닙니다.
- 재시도, 승인, 외부 발송, 결제, 삭제, 배포를 자동 수행하지 않습니다.
- 회사 ID가 같은 원본만 조회하므로 다른 회사의 상태가 섞이지 않습니다.
- 확인 처리는 원본 Task, Approval, Commitment, Decision 상태를 바꾸거나 해결된 것으로 간주하지 않습니다.
- 확인 기록은 append-only이며, 동일 요청 재전송은 멱등 처리하고 오래된 지문은 거절합니다.

## 운영 점검

배포 후 프로젝트 폴더의 `SMOKE_ATTENTION_QUEUE.bat`을 실행합니다. Render에서 복사한
`APP_API_KEY`를 클립보드로 읽고, `[SMOKE]` 지연 약속과 승인 요청을 하나씩 생성해 심각도·필터를 확인한
뒤 각각 취소·거절로 닫습니다. OpenAI 업무는 실행하지 않습니다.
