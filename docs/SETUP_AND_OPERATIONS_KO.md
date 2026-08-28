# AI Company OS 설정·실행·검증 안내서

현재 버전은 V0.4 제어 흐름과 Phase 1 Runtime/Registry 경계를 유지한 운영화 버전입니다. CEO Desk에서 기억과 대표 결정을 저장하면 이후 업무에 자동 반영되며,
외부 발송·결제·삭제·게시·배포처럼 실제 영향이 있는 요청은 바로 실행하지 않고 승인함에 등록됩니다.
승인 결정은 현재 감사 가능한 기록으로만 남고 실제 외부 행동은 자동 실행하지 않습니다.

이 문서는 코드 수정 없이 실제 AI, Telegram, Docker, 클라우드를 연결하는 순서다.

## 1. 이미 검증된 범위

- API, CEO Desk, 업무·기억·의사결정·지식·승인·감사 이벤트 저장
- mock 에이전트 실행, Reviewer PASS, 실행 결과와 지식 저장
- API 키 인증, 회사별 데이터 분리, idempotency key
- 시간 제한, inline/Celery 재시도 구조, 토큰 사용량 필드
- Telegram webhook 비밀 헤더와 허용 chat ID 검사
- Alembic upgrade → downgrade → upgrade 왕복
- 로컬 HTTP 서버에서 업무 생성 → 실행 → 완료 → 감사 이벤트 저장
- Render Blueprint 문법 파싱
- production 설정의 PostgreSQL/worker/인증/비밀값/CORS 강제 검사
- Docker 이미지 비-root 실행, Celery late acknowledgement와 worker-loss 재처리 설정
- Caddy 자동 HTTPS 기반 VPS Compose 구성
- Docker Desktop/WSL 2에서 PostgreSQL, Redis, migration, API, Celery worker 통합 실행
- 실제 Compose 스택에서 mock 업무 생성 → Celery 처리 → 완료 저장
- 데스크톱 CEO Desk 렌더링과 브라우저 콘솔 오류 0건 확인

## 2. 아직 외부 설정 때문에 실행하지 못한 범위

| 항목 | 이유 | 완료 판단 기준 |
|---|---|---|
| 실제 OpenAI 응답 | `OPENAI_API_KEY` 없음 | 업무 완료 후 `total_tokens`가 0보다 크고 조사 결과에 실제 출처가 있음 |
| Telegram 실수신·회신 | bot token과 chat ID 없음 | Telegram 메시지가 업무가 되고 완료 보고가 돌아옴 |
| Render 24시간 배포 | Render/GitHub 계정 연결 권한 없음 | 공개 HTTPS URL의 `/ready`가 `ready` 반환 |
| Render Blueprint 원격 검증 | Render 인증 정보 없음 | Render Blueprint 생성 화면에서 오류 없이 리소스 미리보기 표시 |

## 3. OpenAI 실제 AI 연결

1. [OpenAI API Platform](https://platform.openai.com/)에 로그인한다.
2. API Keys 화면에서 이 프로젝트 전용 key를 만든다. Admin key가 아니라 일반 project key를 사용한다.
3. 결제 설정과 월 사용 한도를 확인한다. ChatGPT 구독과 API 사용료는 별도일 수 있다.
4. 로컬 `.env`에서 아래 두 값만 바꾼다.

```dotenv
AI_PROVIDER=openai
OPENAI_API_KEY=발급받은_키
OPENAI_MODEL=gpt-5.6-luna
OPENAI_TRACING_ENABLED=false
OPENAI_STORE_RESPONSES=false
```

5. 서비스를 다시 시작하고 CEO Desk에서 작은 테스트 업무를 한 건 맡긴다.
6. 업무 상세의 `total_tokens`가 0보다 큰지, Research 결과에 출처가 있는지 확인한다.

작은 유료 smoke test만 따로 실행하려면 다음 명령을 사용한다. `--confirm-cost` 없이는 호출하지 않는다.

```powershell
.\.venv\Scripts\python.exe scripts\smoke_openai.py --confirm-cost
```

키를 README, 채팅, Git commit, 화면 캡처에 넣지 않는다. 애플리케이션은 `.env` 또는 배포 환경에서 읽은
`OPENAI_API_KEY`를 로그나 일반 환경 변수로 다시 출력하지 않고 Agents SDK에 직접 전달한다.

회사 맥락이 trace dashboard로 추가 전송되지 않도록 SDK tracing은 기본적으로 꺼져 있다. 운영 관찰을 위해
trace가 필요하고 데이터 취급 범위를 검토한 뒤에만 `OPENAI_TRACING_ENABLED=true`로 바꾼다.
Responses API의 별도 응답 저장도 기본적으로 끈다. 대시보드 보관이 명시적으로 필요하고 회사 데이터 취급
범위를 검토한 뒤에만 `OPENAI_STORE_RESPONSES=true`로 바꾼다.

## 4. Windows에서 Docker로 전체 실행

현재 PC에는 Docker Desktop 4.88.1과 WSL 2.7.3이 설치되어 있고 통합 검증이 완료됐다.
[Docker Desktop Windows 설치 안내](https://docs.docker.com/desktop/setup/install/windows-install/)는
재설치나 다른 PC 설정 시 참고한다.

설치 후:

1. 시작 메뉴에서 Docker Desktop을 실행한다.
2. 화면 왼쪽 아래 상태가 Engine running이 될 때까지 기다린다.
3. 프로젝트 PowerShell에서 `scripts/run_docker_integration.ps1`을 실행한다.
4. 마지막에 `Docker integration verified successfully.`가 표시되는지 확인한다.

직접 확인하려면 프로젝트 폴더의 PowerShell에서 다음을 실행한다.

```powershell
docker version
docker compose up -d --build
docker compose ps
docker compose exec api python scripts/verify_runtime.py
```

브라우저에서 `http://localhost:8000`을 연다. 중지는 해당 PowerShell에서 `Ctrl+C`, 서비스 제거는
`docker compose down`이다. 데이터까지 지우는 `docker compose down -v`는 PostgreSQL 데이터를
삭제하므로 초기화가 확실히 필요할 때만 사용한다.

## 5. CEO Desk 사용

1. 브라우저에서 서비스 URL을 연다.
2. 오른쪽 아래 `설정`을 누른다.
3. `API 키`에는 서버의 `APP_API_KEY`, 회사 ID에는 기본값 `owner`를 넣는다.
4. 새 업무 지시에 자연어로 요청하고 `업무 맡기기`를 누른다.
5. 최근 업무에서 상태와 결과를 확인한다.
6. 위험 행동이 생성되면 대표 승인함에서 승인 또는 거절한다.

로컬 `.env`의 `AUTH_ENABLED=false` 상태에서는 API 키를 비워도 된다. 클라우드 production에서는
인증을 끌 수 없도록 막아 두었다.

## 6. Telegram 연결

### 6.1 Bot token 만들기

1. Telegram에서 인증 표시가 있는 `@BotFather`를 연다.
2. `/newbot`을 보내고 표시 이름과 `bot`으로 끝나는 사용자 이름을 정한다.
3. BotFather가 준 token을 안전한 비밀번호 관리자에 저장한다.
4. 만든 bot 채팅을 열고 `/start`를 한 번 보낸다.

### 6.2 본인 chat ID 확인

Webhook을 설정하기 전에 PowerShell에서 실행한다. token 값은 명령 기록에 남기지 않기 위해
보안 입력으로 받는다.

```powershell
$secretToken = Read-Host "Telegram bot token" -AsSecureString
$telegramToken = [System.Net.NetworkCredential]::new('', $secretToken).Password
$updates = Invoke-RestMethod "https://api.telegram.org/bot$telegramToken/getUpdates"
$updates.result | ForEach-Object { $_.message.chat | Select-Object id, username, first_name }
```

표시되는 `id`가 `TELEGRAM_ALLOWED_CHAT_ID`다. 아무것도 나오지 않으면 bot에게 일반 메시지를 하나
보낸 뒤 다시 실행한다.

### 6.3 서버 환경 변수

```dotenv
TELEGRAM_ENABLED=true
TELEGRAM_BOT_TOKEN=BotFather가_준_token
TELEGRAM_ALLOWED_CHAT_ID=위에서_확인한_숫자
TELEGRAM_WEBHOOK_SECRET=영문숫자_밑줄_하이픈으로_만든_긴_임의값
PUBLIC_BASE_URL=https://배포된_서비스_주소
```

Webhook secret은 16~256자의 영문 대소문자, 숫자, `_`, `-`만 사용한다. 서버는 Telegram이 보내는
`X-Telegram-Bot-Api-Secret-Token` 헤더와 이 값을 고정 시간 비교한다.

Render의 일반 자동 생성값에는 `+`, `/`, `=` 같은 문자가 포함될 수 있어 Telegram이 거절할 수 있다.
따라서 `TELEGRAM_WEBHOOK_SECRET`은 Blueprint의 `sync: false` 입력란에 직접 넣고, 위 허용 문자만
포함하는 값을 사용한다. API와 worker는 같은 값을 공유해야 한다.

### 6.4 Webhook 등록

환경 변수가 들어간 컴퓨터에서 다음을 실행한다.

```powershell
.\.venv\Scripts\python.exe scripts\configure_telegram.py
```

성공하면 bot에게 업무 문장을 보낸다. 즉시 접수 ID가 오고, 작업 완료 후 비서실장 보고가 돌아와야 한다.
`/status`는 최근 5개 업무 상태를 보여준다.

## 7. GitHub에 올리기

Render가 코드를 가져가려면 온라인 Git 저장소가 필요하다.

1. GitHub에서 private repository를 새로 만든다.
2. README, `.gitignore`, license 자동 생성 옵션은 선택하지 않는다.
3. 이 프로젝트는 이미 Git 저장소로 초기화되어 있다. Git 사용자 이름·이메일을 설정한 뒤 첫 commit을 만든다.
4. GitHub 화면의 기존 저장소 올리기 안내에 따라 remote를 연결하고 `main` branch를 push한다.

`.env`, `work`, `outputs`, 데이터베이스 파일은 `.gitignore`에 포함되어 있다. push 전에
`git status`에서 `.env`가 보이지 않는지 반드시 확인한다. GitHub Desktop을 사용하는 것도 안전한 방법이다.

## 8. Render에 24시간 배포

`render.yaml`은 web API, worker, PostgreSQL, Key Value(Redis 호환), DB migration, health check를
한 번에 정의한다. background worker에는 free plan을 사용할 수 없으므로 생성 전 Render가 보여주는
월 예상 비용을 반드시 확인한다.

1. [Render Dashboard](https://dashboard.render.com/)에 로그인한다.
2. `New` → `Blueprint`를 선택한다.
3. GitHub를 연결하고 위 private repository를 선택한다.
4. Render가 `render.yaml`을 읽어 4개 리소스(API, worker, DB, queue)를 보여주는지 확인한다.
5. `OPENAI_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_CHAT_ID`,
   `TELEGRAM_WEBHOOK_SECRET`, `PUBLIC_BASE_URL`, `TELEGRAM_ENABLED` 입력란을 채운다. Telegram을
   나중에 쓸 경우 빈 값으로 둘 수 있는지 화면에서 확인하고, 허용하지 않으면 임시 생성 후 서비스의
   Environment 화면에서 추가한다.
6. 예상 비용을 확인한 뒤 Apply 한다.
7. 배포 완료 후 web service URL을 열고 `/ready`가 `{"status":"ready"}`인지 확인한다.
8. web service의 Environment 탭에서 자동 생성된 `APP_API_KEY`를 확인해 CEO Desk 설정에 넣는다.
9. `PUBLIC_BASE_URL`이 실제 배포 URL인지 확인하고 Telegram webhook을 등록한다.
10. Telegram을 실제 사용할 때만 `TELEGRAM_ENABLED=true`로 바꾼다. 그 전에는 `false`를 유지한다.
11. `BRIEFING_ENABLED=true` 상태에서 Telegram이 활성화되면 매일 07:00 KST 자동 브리핑이 시작된다.
    시간을 바꾸기 전에는 `docs/PROACTIVE_BRIEFING_DELIVERY_KO.md`의 quiet hours 규칙을 확인한다.

Render는 `sync: false`로 선언된 secret을 최초 Blueprint 생성 중 입력받고, DB/queue 연결 주소는
Blueprint가 자동 연결한다. `/ready`는 실제 DB 연결까지 확인하므로 배포 health check로 사용된다.
Web 서비스의 Telegram 값을 Blueprint 생성 후 수동으로 바꾸면 worker의 `fromService` 참조가 즉시
재주입되지 않을 수 있다. 이 경우 worker Environment에도 같은 값을 저장하고 재배포하거나, 값을 보존한
상태에서 Blueprint를 다시 동기화한 뒤 worker의 `BOT_OK`, 허용 chat ID, 활성값을 확인한다.
Worker는 Celery 작업 실행과 5분 주기의 브리핑 스케줄 확인을 한 프로세스에서 수행한다. 자동 브리핑은
기존 Worker를 사용하므로 별도 Render 서비스나 추가 월정액 리소스를 만들지 않는다.

## 9. 단일 VPS에 배포

`deploy/compose.vps.yml`은 API, Celery worker, PostgreSQL, Redis, migration, Caddy HTTPS를 한 서버에
구성한다. Ubuntu 계열 VPS에 Docker Engine과 Compose plugin을 설치하고, 도메인의 A/AAAA 레코드를 VPS로
연결한 뒤 방화벽에서 80/443만 공개한다. PostgreSQL과 Redis는 외부 포트를 열지 않는다.

```powershell
Copy-Item deploy/.env.vps.example deploy/.env.vps
# 비밀값과 도메인을 deploy/.env.vps에 직접 입력
docker compose --env-file deploy/.env.vps -f deploy/compose.vps.yml config
docker compose --env-file deploy/.env.vps -f deploy/compose.vps.yml up -d --build
docker compose --env-file deploy/.env.vps -f deploy/compose.vps.yml ps
```

배포 후에는 로컬에서 다음 smoke test로 `/ready` 확인, 업무 생성, Celery 처리, 결과 저장을 한 번에 확인한다.

```powershell
$secretValue = Read-Host "APP_API_KEY" -AsSecureString
$env:APP_API_KEY = [System.Net.NetworkCredential]::new('', $secretValue).Password
.\.venv\Scripts\python.exe scripts\smoke_deployed_task.py https://도메인 --require-token-usage
Remove-Item Env:APP_API_KEY
```

운영 업데이트 전에는 `docs/DB_BACKUP_RESTORE_KO.md`에 따라 DB를 백업한다. `down -v`는 운영 데이터
볼륨을 삭제하므로 사용하지 않는다.

## 10. 실제 운영 전 최종 체크리스트

- CEO Desk에 API 키 없이 접근하면 업무 API가 401을 반환한다.
- 같은 idempotency key로 업무를 두 번 보내도 하나만 생성된다.
- 업무가 `dispatched → running → completed`로 이동한다.
- 실제 AI 업무의 `total_tokens`가 기록된다.
- Research 출처를 직접 열어 핵심 사실 두세 개를 표본 검증한다.
- 승인 요청은 CEO가 결정하기 전 외부 행동을 실행하지 않는다.
- 허용되지 않은 Telegram chat ID는 403을 받는다.
- Render API와 worker 로그에 반복 오류가 없다.
- PostgreSQL 백업 및 Render 비용 알림을 켠다.
- `APP_API_KEY`, OpenAI key, Telegram token을 비밀번호 관리자에 보관한다.

## 11. 문제가 생겼을 때 Codex에 전달할 정보

비밀값은 보내지 말고 아래만 전달한다.

- 어느 단계에서 실패했는지
- 화면에 나온 오류 문구
- `/health`와 `/ready` 응답(`/ready`의 database와 redis가 모두 ready인지)
- task ID와 task 상태
- Render에서 실패한 서비스 이름(API/worker/DB/queue)
- 오류 발생 시각과 시간대
