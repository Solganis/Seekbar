import importlib
import sys
from unittest.mock import MagicMock, patch

import pytest


class TestImportGuard:
    def test_non_darwin_raises(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(sys, "platform", "win32")
        with pytest.raises(ImportError, match="macOS"):
            importlib.reload(importlib.import_module("seekbar._spotlight"))


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS-only")
class TestSpotlightSearchStrategy:
    def test_calls_subprocess_search(self):
        from seekbar._spotlight import SpotlightSearchStrategy  # noqa: PLC0415 - deferred; module has platform guard

        mock_on_found = MagicMock()
        mock_interrupted = MagicMock(return_value=False)

        with patch("seekbar._spotlight.subprocess_search", return_value=5) as mock_search:
            strategy = SpotlightSearchStrategy()
            count = strategy.execute("hosts", ["hosts"], mock_on_found, mock_interrupted)

        assert count == 5
        args = mock_search.call_args
        assert args[0][0] == ["mdfind", "-name", "hosts"]
