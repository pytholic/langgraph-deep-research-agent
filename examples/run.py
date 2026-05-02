"""Run the deep research agent from the command line.

Usage:
    uv run python examples/run.py
    uv run python examples/run.py "Your research query here"

Created by @pytholic on 2026.04.16
"""

import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

# Allow importing from examples/
sys.path.insert(0, str(Path(__file__).parent))

load_dotenv(override=True)

from utils import stream_agent  # noqa: E402

from deep_research_agent.agent import create_deep_research_agent  # noqa: E402

DEFAULT_QUERY = "Find the most recent material on LLM agents evaluation using arxiv and tavily search. Then output you findings in a structured markdown format. Keep it as detailed and accurate as possible."


async def main() -> None:
    """Run the research agent with an optional query argument."""
    query = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_QUERY

    agent = create_deep_research_agent()
    await stream_agent(agent, {"messages": [{"role": "user", "content": query}]})


if __name__ == "__main__":
    asyncio.run(main())
