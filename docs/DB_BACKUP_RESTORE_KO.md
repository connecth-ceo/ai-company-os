# 데이터베이스 백업·복구 안내

이 문서는 AI Company OS V0.4의 PostgreSQL과 로컬 SQLite 데이터를 안전하게 백업·복구하는 절차다.

## 공통 안전 원칙

- 백업 파일에는 회사 지식과 개인정보가 포함될 수 있으므로 암호화된 저장소에 보관한다.
- `backups/`, `*.dump`, `*.backup`, SQLite 파일은 Git에 포함하지 않는다.
- 복구는 가능하면 별도 테스트 DB에서 먼저 실행한다.
- 복구 전에 API와 Worker를 중지해 새 데이터가 동시에 기록되지 않도록 한다.
- 백업 성공은 파일 생성만으로 판단하지 않고 실제 복구 시험으로 확인한다.

## Docker PostgreSQL 백업

프로젝트 루트에서 `backups` 폴더를 만들고 PostgreSQL custom-format dump를 생성한다.

```powershell
New-Item -ItemType Directory -Path .\backups -Force
docker compose exec -T db pg_dump -U ai_company -d ai_company -Fc > .\backups\ai_company.dump
Get-Item -LiteralPath .\backups\ai_company.dump
```

백업 중 API를 완전히 중지해야 하는 운영 환경이라면 먼저 web/worker 쓰기를 중단하고 실행한다.

## Docker PostgreSQL 복구 시험

운영 DB를 바로 덮어쓰지 않는다. 별도 DB를 생성해 백업을 검증한다.

```powershell
docker compose exec -T db createdb -U ai_company ai_company_restore_test
Get-Content -LiteralPath .\backups\ai_company.dump -AsByteStream -Raw |
  docker compose exec -T db pg_restore -U ai_company -d ai_company_restore_test --clean --if-exists
docker compose exec -T db psql -U ai_company -d ai_company_restore_test -c "SELECT COUNT(*) FROM tasks;"
```

검증이 끝난 테스트 DB는 이름을 다시 확인한 뒤에만 삭제한다.

```powershell
docker compose exec -T db dropdb -U ai_company ai_company_restore_test
```

운영 DB 복구가 필요하면 API와 Worker를 중지하고, 최신 백업 시각과 대상 DB 이름을 두 번 확인한 후 별도
복구 계획을 세운다. 운영 DB를 자동으로 삭제하는 스크립트는 제공하지 않는다.

## 로컬 SQLite 백업

배치 파일로 실행한 로컬 DB는 일반적으로 `ai_company_local.db`이다. 애플리케이션을 먼저 종료한 뒤 복사한다.

```powershell
New-Item -ItemType Directory -Path .\backups -Force
Copy-Item -LiteralPath .\ai_company_local.db -Destination .\backups\ai_company_local.db
```

복구할 때는 기존 파일을 바로 덮어쓰지 말고 먼저 별도 이름으로 보존한다.

```powershell
Move-Item -LiteralPath .\ai_company_local.db -Destination .\backups\ai_company_local.before-restore.db
Copy-Item -LiteralPath .\backups\ai_company_local.db -Destination .\ai_company_local.db
```

## 클라우드 PostgreSQL

- 배포 서비스의 자동 백업 보존 기간과 복구 지점을 확인한다.
- 서비스 제공자의 snapshot만 믿지 말고 정기적으로 암호화된 논리 백업을 별도 위치에 보관한다.
- 복구 시험은 운영 서비스와 분리된 임시 DB에서 수행한다.
- API key와 DB 접속 문자열을 명령 기록이나 문서에 직접 넣지 않는다.

## 권장 주기

| 대상 | 권장 주기 |
|---|---|
| 운영 PostgreSQL 논리 백업 | 매일 |
| 중요 배포 전 수동 백업 | 매 배포 전 |
| 외부 암호화 보관 | 매일 동기화 |
| 복구 시험 | 월 1회 및 중요 스키마 변경 전 |
| SQLite 로컬 백업 | 중요한 업무 전후 |

## 백업 점검표

- 백업 파일 크기가 0보다 크다.
- 백업 파일이 Git 상태에 나타나지 않는다.
- 별도 DB에서 schema와 주요 테이블을 조회할 수 있다.
- 복구 후 Task, Approval, AuditEvent 건수를 표본 확인했다.
- 백업 시각, 앱 버전, DB schema revision을 함께 기록했다.
- 복구 책임자와 복구에 필요한 접근 권한을 확인했다.
