# 약속·후속조치 관리

## 목적

Task는 AI 팀이 수행하는 업무를 기록하고, Commitment는 **누가 무엇을 언제까지 하기로 했는지**를
기록합니다. 회신 약속, 대표 후속조치, 외부 확인, 회의에서 나온 실행 항목을 Task와 구분해 추적할 수
있습니다.

## 저장 정보

- 약속 내용과 담당 유형(person/agent/team), 담당자 식별자
- 마감시각과 상태(open/in_progress/completed/cancelled)
- 생성 출처(manual/decision/task/meeting/external)와 출처 식별자·provenance
- 관련 Project, Task, Decision
- 향후 알림에 사용할 reminder_policy
- 완료시각과 생성·수정시각

기한 초과 여부는 open 또는 in_progress 상태이며 due_at이 현재시각보다 과거인지 조회할 때 계산합니다.
단순히 시간이 지났다는 이유로 원본 상태를 자동 변경하지 않으므로 감사 이력이 왜곡되지 않습니다.

## 상태 규칙

| 현재 상태 | 허용하는 다음 상태 |
| --- | --- |
| open | in_progress, completed, cancelled |
| in_progress | open, completed, cancelled |
| completed | 없음 |
| cancelled | 없음 |

완료·취소 기록은 종료 이력입니다. 잘못 기록했다면 기존 기록을 삭제하거나 되살리지 않고 새 Commitment를
만듭니다. completed_at은 completed 상태에만 존재하도록 데이터베이스에서도 검사합니다.

## 연결과 회사 격리

- Project, Task, Decision 연결은 같은 tenant의 실제 기록인지 확인합니다.
- Project와 Task를 함께 연결하면 Task가 해당 Project에 속하는지 확인합니다.
- decision 출처는 관련 Decision을, task 출처는 관련 Task를 반드시 가리켜야 합니다.
- meeting/external 출처는 원문을 찾을 수 있는 source_id가 필요합니다.
- manual 출처에는 임의 source_id를 숨겨 넣을 수 없습니다.

## CEO Desk 사용법

1. **약속·후속조치** 영역에서 **새 약속 기록**을 누릅니다.
2. 약속 내용, 담당자, 마감일을 입력합니다.
3. 대표 결정에서 나온 약속이면 **관련 대표 결정**을 선택합니다.
4. 저장 후 **시작**, **완료**, **취소**로 상태를 변경합니다.
5. 기한을 넘긴 미완료 약속은 주황색과 **기한 초과** 표시로 강조됩니다.

## 데일리 브리핑

Telegram `/briefing`에는 지연된 약속 수, 24시간 내 마감 수, 확인이 필요한 약속 최대 5건이 표시됩니다.
데이터베이스 조회만 사용하므로 OpenAI 호출 비용이 없습니다. 현재 단계는 요청형 브리핑이며 07:00 KST
예약 발송과 중복 알림 억제는 다음 Proactive Intelligence 단계입니다.

## API

- 생성: `POST /api/v1/commitments`
- 목록: `GET /api/v1/commitments`
- 상세: `GET /api/v1/commitments/{commitment_id}`
- 상태 변경: `POST /api/v1/commitments/{commitment_id}/transition`
- 기한 초과만: `GET /api/v1/commitments?overdue_only=true`
- 상태·담당자·Project·Task·Decision·마감 범위 필터 지원

## 안전 경계

- 생성과 모든 상태 변경을 AuditEvent에 기록합니다.
- Commitment는 약속을 **추적**하며 이메일 전송, 결제, 삭제, 배포 같은 외부 행동을 실행하지 않습니다.
- 자연어·회의록에서 약속을 자동 확정하지 않습니다. 추후 추출 기능도 사람 검토를 거친 후보 방식으로
  연결해야 합니다.
- 생성·조회·전환·브리핑은 OpenAI를 호출하지 않습니다.

## 배포 후 무비용 점검

Render에서 APP_API_KEY 값을 복사한 뒤 저장소 루트의 `SMOKE_COMMITMENT_TRACKING.bat`을 실행합니다.
검사는 `[SMOKE]` 약속 두 건을 만들고 기한 초과 판별, 시작·완료·취소 전환을 확인한 뒤 두 기록을 모두
종료 상태로 정리합니다. OpenAI 업무는 실행하지 않습니다.
