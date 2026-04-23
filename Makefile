.PHONY: install ui ui-stop lint format typecheck test

install:
	uv sync

ui:
	uv run fastapi run src/deep_research_agent/ui/server.py --port 8080

ui-stop:
	@pgrep -f "deep_research_agent.ui.server" | xargs kill 2>/dev/null && echo "Server stopped." || echo "Server not running."

lint:
	uv run ruff check --fix src/

format:
	uv run ruff format src/

typecheck:
	uv run pyright src/

test:
	uv run pytest
