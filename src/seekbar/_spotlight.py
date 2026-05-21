import sys
from typing import TYPE_CHECKING

if sys.platform != "darwin":  # pragma: no cover
    msg = "This module is only available on macOS"
    raise ImportError(msg)

from seekbar._subprocess_search import subprocess_search
from seekbar.search import _normalize

if TYPE_CHECKING:
    from collections.abc import Callable


class SpotlightSearchStrategy:
    # noinspection PyMethodMayBeStatic
    def execute(
        self,
        normalized_query: str,
        tokens: list[str],
        on_found: Callable[[str, int, int, bool], object],
        is_interrupted: Callable[[], bool],
    ) -> int:
        raw_query = _normalize(normalized_query)
        return subprocess_search(["mdfind", "-name", raw_query], normalized_query, tokens, on_found, is_interrupted)
