import importlib
import sys
from unittest.mock import MagicMock, patch

import pytest
from assertpy2 import assert_that


class TestImportGuard:
    def test_non_linux_raises(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(sys, "platform", "win32")
        assert_that(lambda: importlib.reload(importlib.import_module("seekbar._locate"))).raises(
            ImportError
        ).when_called_with().matches("Linux")


@pytest.mark.skipif(sys.platform != "linux", reason="Linux-only")
class TestLocateSearchStrategy:
    def test_calls_subprocess_search_with_plocate(self):
        from seekbar._locate import LocateSearchStrategy  # noqa: PLC0415 - deferred; module has platform guard

        mock_on_found = MagicMock()
        mock_interrupted = MagicMock(return_value=False)

        with patch("seekbar._locate.subprocess_search", return_value=7) as mock_search:
            strategy = LocateSearchStrategy("/usr/bin/plocate")
            count = strategy.execute("hosts", ["hosts"], mock_on_found, mock_interrupted)

        assert_that(count).is_equal_to(7)
        args = mock_search.call_args
        assert_that(args[0][0]).is_equal_to(["/usr/bin/plocate", "-i", "hosts"])

    def test_calls_subprocess_search_with_locate(self):
        from seekbar._locate import LocateSearchStrategy  # noqa: PLC0415 - deferred; module has platform guard

        mock_on_found = MagicMock()
        mock_interrupted = MagicMock(return_value=False)

        with patch("seekbar._locate.subprocess_search", return_value=3) as mock_search:
            strategy = LocateSearchStrategy("/usr/bin/locate")
            count = strategy.execute("hosts", ["hosts"], mock_on_found, mock_interrupted)

        assert_that(count).is_equal_to(3)
        args = mock_search.call_args
        assert_that(args[0][0]).is_equal_to(["/usr/bin/locate", "-i", "hosts"])
