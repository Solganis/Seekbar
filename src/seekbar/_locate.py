import sys
from typing import TYPE_CHECKING

if sys.platform != "linux":  # pragma: no cover
    msg = "This module is only available on Linux"
    raise ImportError(msg)

from seekbar._subprocess_search import subprocess_search
from seekbar.search import _normalize

if TYPE_CHECKING:
    from collections.abc import Callable


class LocateSearchStrategy:
    def __init__(self, command: str) -> None:
        self._command = command

    def execute(
        self,
        normalized_query: str,
        tokens: list[str],
        on_found: Callable[[str, int, int, bool], object],
        is_interrupted: Callable[[], bool],
    ) -> int:
        raw_query = _normalize(normalized_query)
        return subprocess_search([self._command, "-i", raw_query], normalized_query, tokens, on_found, is_interrupted)
