# AI Company OS — 운영화 이후 실제 프로그램 가동 순서

운영화 코드, 자동 테스트, mock HTTP E2E, Docker 통합, 배포 정의는 완료됐다. 아래 단계는 사용자
자격증명 또는 클라우드 환경이 있어야 완료할 수 있는 실제 외부 연동 순서다.

## 지금 바로 가능한 것

프로젝트 폴더에서 `START_AI_COMPANY_MOCK.bat`을 더블클릭하면 비용 없이 CEO Desk가 열린다.
이 모드는 화면, 업무 배분, 회사 기억, 대표 결정, 지식 축적, 승인함을 실제로 저장하지만 AI 답변은
테스트용 문구를 사용한다.

## 1단계: 실제 OpenAI AI 팀 연결

1. https://platform.openai.com/api-keys 에서 API 키를 만든다.
2. 프로젝트의 `.env` 파일을 메모장으로 연다.
3. `OPENAI_API_KEY=` 뒤에 키를 붙여 넣는다. 키를 채팅에 보내거나 GitHub에 올리지 않는다.
4. `START_AI_COMPANY_REAL_AI.bat`을 더블클릭한다.
5. 브라우저의 CEO Desk에서 작은 첫 업무를 지시한다.
6. 첫 실행은 OpenAI API 비용이 발생할 수 있다.

별도 검증은 `.\.venv\Scripts\python.exe scripts\smoke_openai.py --confirm-cost`로 실행할 수 있다.

2026-08-26 실제 OpenAI 오케스트레이션을 실행해 출처 URL, 최종 보고서, 32,774 tokens를 확인했다.
Reviewer는 `REWORK`를 반환해 검수 통제 경계도 실제 확인됐다. 추가 비용 재실행은 수행하지 않았다.

## 2단계: 로컬 전체 운영 환경

2026-08-26에 Docker Desktop 4.88.1과 WSL 2.7.3 설치를 완료하고 다음 항목을 실제 검증했다.

- PostgreSQL과 Redis healthy
- Alembic schema `12738dc9272a`
- API healthy 및 `/ready` 성공
- Celery worker `pong`
- Compose mock 업무가 worker에서 완료

현재 서비스는 `http://localhost:8000`에서 사용할 수 있다. 다시 검증할 때는
`scripts/run_docker_integration.ps1`을 실행한다.

## 3단계: Telegram 연결

Telegram에서 BotFather로 bot token을 만들고 본인 chat ID를 확인한 뒤 `.env`의 다음 값을 채운다.

```text
TELEGRAM_ENABLED=true
TELEGRAM_BOT_TOKEN=
TELEGRAM_WEBHOOK_SECRET=
TELEGRAM_ALLOWED_CHAT_ID=
```

Telegram webhook에는 인터넷에서 접근할 수 있는 HTTPS 주소가 필요하므로 클라우드 배포 후 연결하는
것이 가장 간단하다. 자세한 명령은 `docs/SETUP_AND_OPERATIONS_KO.md`의 Telegram 항목에 있다.

## 4단계: 24시간 클라우드 배포

현재 GitHub 저장소와 Render 계정이 연결되지 않아 실제 배포는 수행하지 못했다.

1. GitHub에 새 비공개 저장소를 만든다.
2. 현재 프로젝트를 최초 commit 후 해당 저장소에 push한다.
3. Render에서 Blueprint 배포를 선택하고 GitHub 저장소를 연결한다.
4. Render secret 환경 변수에 `OPENAI_API_KEY`, `APP_API_KEY`, Telegram 값을 등록한다.
5. `render.yaml` 기준으로 web, worker, PostgreSQL, Redis를 생성한다.
6. `/ready`가 `ready`를 반환하는지 확인한다.
7. Render 주소로 Telegram webhook을 등록한다.

Render 리소스는 요금이 발생할 수 있으므로 계정과 비용 계획을 확인한 뒤 배포해야 한다.

## 현재 설정 때문에 남은 검증

| 항목 | 현재 상태 | 필요한 사용자 작업 |
|---|---|---|
| 실제 OpenAI 답변 | 검증 완료 | 없음 |
| Docker/PostgreSQL/Redis/Celery | 검증 완료 | 없음 |
| 실제 Telegram 송수신 | 미실행 | Bot token, chat ID, HTTPS 배포 주소 |
| 24시간 Render 운영 | 미실행 | GitHub/Render 계정 연결 및 비용 확인 |

비밀값은 Codex나 Claude 대화에 붙여 넣지 말고 `.env` 또는 클라우드 Secret 화면에 직접 입력한다.
단일 VPS를 사용할 경우 `deploy/compose.vps.yml`과 `docs/SETUP_AND_OPERATIONS_KO.md`의 VPS 절차를 따른다.
