"""Unit tests for state reducers.

Created by @pytholic on 2026.04.16
"""

import pytest

from deep_research_agent.state import file_reducer


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        pytest.param(
            {"a.md": "content a"},
            {"b.md": "content b"},
            {"a.md": "content a", "b.md": "content b"},
            id="distinct_keys_merged",
        ),
        pytest.param(
            {"a.md": "old"},
            {"a.md": "new"},
            {"a.md": "new"},
            id="right_overwrites_left_on_conflict",
        ),
        pytest.param(
            None,
            {"b.md": "content b"},
            {"b.md": "content b"},
            id="left_none_returns_right",
        ),
        pytest.param(
            {"a.md": "content a"},
            None,
            {"a.md": "content a"},
            id="right_none_returns_left",
        ),
    ],
)
def test_file_reducer(
    left: dict[str, str] | None,
    right: dict[str, str] | None,
    expected: dict[str, str],
) -> None:
    assert file_reducer(left, right) == expected  # type: ignore[arg-type]
