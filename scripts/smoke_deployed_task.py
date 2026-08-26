"""Submit and poll one task against a running API deployment."""

import argparse
import os
import time

import httpx


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("base_url")
    parser.add_argument("--api-key", default=os.getenv("APP_API_KEY"))
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--startup-timeout", type=int, default=180)
    parser.add_argument("--require-token-usage", action="store_true")
    args = parser.parse_args()
    if not args.api_key:
        parser.error("set APP_API_KEY or pass --api-key")

    headers = {"X-API-Key": args.api_key, "X-Tenant-ID": "owner"}
    base_url = args.base_url.rstrip("/")
    with httpx.Client(base_url=base_url, headers=headers, timeout=30) as client:
        startup_deadline = time.monotonic() + args.startup_timeout
        while True:
            try:
                ready = client.get("/ready")
                ready.raise_for_status()
                break
            except (httpx.HTTPError, httpx.InvalidURL):
                if time.monotonic() >= startup_deadline:
                    raise SystemExit("Deployment did not become ready before the timeout") from None
                time.sleep(2)
        print(f"Readiness: {ready.json()}")
        created = client.post(
            "/api/v1/tasks",
            json={"title": "Deployment smoke test", "request": "간단한 실행 준비 상태를 보고해줘."},
        )
        created.raise_for_status()
        task_id = created.json()["id"]
        dispatched = client.post(f"/api/v1/tasks/{task_id}/run")
        dispatched.raise_for_status()

        deadline = time.monotonic() + args.timeout
        while time.monotonic() < deadline:
            detail = client.get(f"/api/v1/tasks/{task_id}")
            detail.raise_for_status()
            body = detail.json()
            if body["status"] in {"completed", "failed"}:
                print(f"Task {task_id}: {body['status']}")
                if body["status"] != "completed":
                    raise SystemExit(body.get("error") or "Task failed")
                runs = body.get("runs") or []
                if not runs:
                    raise SystemExit("Task completed without a TaskRun")
                total_tokens = runs[-1].get("total_tokens", 0)
                print(f"Token total: {total_tokens}")
                if args.require_token_usage and total_tokens <= 0:
                    raise SystemExit("Task completed without real model token usage")
                return
            time.sleep(2)
    raise SystemExit("Timed out waiting for task completion")


if __name__ == "__main__":
    main()
