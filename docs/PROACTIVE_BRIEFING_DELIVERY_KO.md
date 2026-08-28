# 자동 데일리 브리핑 전달 운영 안내

## 목적

AI Company OS가 매일 오전 7시(Asia/Seoul)에 CEO의 Telegram으로 상태 브리핑을 먼저 보낸다.
브리핑은 데이터베이스의 업무·승인·약속·대표 주의 큐만 읽으므로 OpenAI를 호출하지 않는다.

## 동작 방식

1. Worker의 경량 스케줄러가 5분마다 전송 가능 여부를 확인한다.
2. 기본 전송 시각은 매일 `07:00 KST`다.
3. Worker 재시작 등으로 07:00을 놓쳐도 기본 3시간 이내에는 한 번 따라잡아 전송한다.
4. `22:00-07:00`에는 메시지를 보내지 않는다.
5. 회사·날짜·채널별 고유키로 같은 날의 브리핑은 한 번만 전송한다.
6. 전송 실패 시 5분부터 지수 간격으로 최대 3번 시도한다.
7. 전송 중 Worker가 중단되어 성공 여부가 불명확하면 10분 후 `uncertain`으로 격리하고 자동 재발송하지 않는다.

## 기록과 확인

- `GET /api/v1/briefing-schedule`: 활성 상태, 시각, 조용한 시간, 재시도 정책, 최근 전송을 확인한다.
- `GET /api/v1/briefing-deliveries`: 회사별 전송 성공·실패 이력을 확인한다.
- CEO Desk의 대표 주의 큐 오른쪽 배지에서 자동 브리핑 활성 상태를 확인한다.
- 감사 이벤트에는 `briefing.delivery.sent` 또는 `briefing.delivery.failed`가 남는다.

Telegram chat ID는 전달 기록에 보존되지만 API 응답과 감사 이벤트에는 노출하지 않는다. 브리핑 본문도
데이터베이스에 중복 저장하지 않고 SHA-256 해시만 남긴다.

## 설정

```dotenv
BRIEFING_ENABLED=true
BRIEFING_TIMEZONE=Asia/Seoul
BRIEFING_HOUR=7
BRIEFING_MINUTE=0
BRIEFING_CATCHUP_HOURS=3
BRIEFING_QUIET_START_HOUR=22
BRIEFING_QUIET_END_HOUR=7
BRIEFING_MAX_ATTEMPTS=3
BRIEFING_RETRY_SECONDS=300
BRIEFING_DELIVERY_LEASE_SECONDS=600
```

`TELEGRAM_ENABLED=false`이면 `BRIEFING_ENABLED=true`여도 전송하지 않는다. 따라서 Telegram 연결을 끄면
자동 브리핑도 함께 안전하게 멈춘다.

## 안전 경계

- 브리핑 생성은 읽기 전용이며 새 업무, 승인, 결제, 게시, 배포를 만들지 않는다.
- 자동 전송 과정에서 OpenAI를 호출하지 않는다.
- 이미 성공한 날짜는 재시도하지 않는다.
- 전송 성공 여부가 불명확한 기록은 자동 재시도하지 않아 중복 메시지 위험을 우선 차단한다.
- 실패 원문이나 비밀값 대신 제한된 실패 코드만 저장한다.
- 여러 Worker가 동시에 확인해도 DB의 원자적 claim과 고유키로 중복 발송을 막는다.
