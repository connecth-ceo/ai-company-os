"""Run one paid, real OpenAI orchestration only after explicit CLI confirmation."""

import argparse
import asyncio
import re

from app.agents.orchestrator import orchestrate
from app.core.config import get_settings


async def run(request: str) -> None:
    settings = get_settings()
    if settings.ai_provider != "openai":
        raise SystemExit("Set AI_PROVIDER=openai before running this check")
    result = await orchestrate(request, settings)
    if result.total_tokens <= 0:
        raise RuntimeError("OpenAI run completed without token usage")
    if not result.research.strip() or not result.final_report.strip():
        raise RuntimeError("OpenAI run returned an empty artifact")
    if not re.search(r"https?://", result.research):
        raise RuntimeError("OpenAI research completed without a direct source URL")
    print("OpenAI orchestration: passed")
    print(f"Reviewer verdict: {result.verdict.value}")
    print(f"Token total: {result.total_tokens}")
    print(f"Report preview: {result.final_report[:500]}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm-cost", action="store_true")
    parser.add_argument(
        "--request",
        default="최근 AI 업무 자동화 시장의 핵심 변화 3가지를 출처와 함께 간단히 조사해줘.",
    )
    args = parser.parse_args()
    if not args.confirm_cost:
        raise SystemExit("This calls the paid OpenAI API. Re-run with --confirm-cost.")
    asyncio.run(run(args.request))


if __name__ == "__main__":
    main()
