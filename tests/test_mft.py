import sys

import pytest
from assertpy2 import assert_that

if sys.platform != "win32":
    pytest.skip("Windows-only tests", allow_module_level=True)

import ctypes
import ctypes.wintypes
import importlib
from unittest.mock import MagicMock

# noinspection PyProtectedMember
import seekbar._mft as mft_module

# noinspection PyProtectedMember
from seekbar._mft import (
    FILE_ATTRIBUTE_DIRECTORY,
    INVALID_HANDLE_VALUE,
    MftRecord,
    _UsnRecordV2,
    _stream_mft_batches,
    enumerate_mft,
    is_ntfs,
    resolve_path,
    stream_mft,
)


def _build_usn_record(file_ref, parent_ref, name, *, is_dir=False):
    name_bytes = name.encode("utf-16-le")
    name_offset = ctypes.sizeof(_UsnRecordV2)
    record_length = name_offset + len(name_bytes)
    padding = (8 - record_length % 8) % 8
    record_length += padding

    record_buffer = bytearray(record_length)
    record = _UsnRecordV2.from_buffer(record_buffer)
    record.RecordLength = record_length
    record.MajorVersion = 2
    record.FileReferenceNumber = file_ref
    record.ParentFileReferenceNumber = parent_ref
    record.FileAttributes = FILE_ATTRIBUTE_DIRECTORY if is_dir else 0
    record.FileNameLength = len(name_bytes)
    record.FileNameOffset = name_offset
    record_buffer[name_offset : name_offset + len(name_bytes)] = name_bytes
    return bytes(record_buffer)


class TestIsNtfs:
    def test_ntfs_returns_true(self, monkeypatch):
        mock_kernel = MagicMock()

        def fake_get_volume_info(_path, _a, _b, _c, _d, _e, filesystem_buffer, _f):
            ctypes.memmove(filesystem_buffer, ctypes.create_unicode_buffer("NTFS"), 10)
            return 1

        mock_kernel.GetVolumeInformationW = fake_get_volume_info
        monkeypatch.setattr("seekbar._mft.kernel32", mock_kernel)
        assert_that(is_ntfs("C:")).is_true()

    def test_fat32_returns_false(self, monkeypatch):
        mock_kernel = MagicMock()

        def fake_get_volume_info(_path, _a, _b, _c, _d, _e, filesystem_buffer, _f):
            ctypes.memmove(filesystem_buffer, ctypes.create_unicode_buffer("FAT32"), 12)
            return 1

        mock_kernel.GetVolumeInformationW = fake_get_volume_info
        monkeypatch.setattr("seekbar._mft.kernel32", mock_kernel)
        assert_that(is_ntfs("D:")).is_false()

    def test_failure_returns_false(self, monkeypatch):
        mock_kernel = MagicMock()
        mock_kernel.GetVolumeInformationW = MagicMock(return_value=0)
        monkeypatch.setattr("seekbar._mft.kernel32", mock_kernel)
        assert_that(is_ntfs("E:")).is_false()


class TestEnumerateMft:
    def test_access_denied(self, monkeypatch):
        mock_kernel = MagicMock()
        mock_kernel.CreateFileW = MagicMock(return_value=INVALID_HANDLE_VALUE)
        mock_kernel.CloseHandle = MagicMock()
        monkeypatch.setattr("seekbar._mft.kernel32", mock_kernel)
        monkeypatch.setattr(ctypes, "get_last_error", lambda: 5)

        assert_that(enumerate_mft).raises(OSError).when_called_with("C:").satisfies(
            lambda message: "Cannot open volume" in message
        )

    def test_empty_volume(self, monkeypatch):
        mock_kernel = MagicMock()
        mock_kernel.CreateFileW = MagicMock(return_value=42)
        mock_kernel.DeviceIoControl = MagicMock(return_value=0)
        mock_kernel.CloseHandle = MagicMock()
        monkeypatch.setattr("seekbar._mft.kernel32", mock_kernel)

        records, root_ref = enumerate_mft("C:")
        assert_that(records).is_empty()
        assert_that(root_ref).is_equal_to(5)
        mock_kernel.CloseHandle.assert_called_once_with(42)

    def test_parses_records(self, monkeypatch):
        record1 = _build_usn_record(10, 5, "hosts.txt", is_dir=False)
        record2 = _build_usn_record(11, 5, "docs", is_dir=True)
        next_ref_bytes = bytes(ctypes.c_ulonglong(99))
        data = next_ref_bytes + record1 + record2
        total_len = len(data)

        call_count = [0]

        def fake_device_io(_h, _c, _ib, _is, out_buf, _os, bytes_ret_ptr, _ov):
            if call_count[0] > 0:
                return 0
            call_count[0] += 1
            ctypes.memmove(out_buf, data, total_len)
            bytes_ret_ptr.contents.value = total_len
            return 1

        mock_kernel = MagicMock()
        mock_kernel.CreateFileW = MagicMock(return_value=42)
        mock_kernel.DeviceIoControl = fake_device_io
        mock_kernel.CloseHandle = MagicMock()
        monkeypatch.setattr("seekbar._mft.kernel32", mock_kernel)

        records, root_ref = enumerate_mft("C:")
        assert_that(root_ref).is_equal_to(5)
        assert_that(records).contains_key(10)
        assert_that(records[10]).is_equal_to((5, "hosts.txt", False))
        assert_that(records).contains_key(11)
        assert_that(records[11]).is_equal_to((5, "docs", True))


class TestResolvePath:
    def test_simple_path(self):
        records = {10: (5, "hosts.txt", False)}
        cache: dict[int, str] = {}
        result = resolve_path(10, records, 5, "C:", cache)
        assert_that(result).is_equal_to("C:\\hosts.txt")
        assert_that(cache[10]).is_equal_to("C:\\hosts.txt")

    def test_nested_path(self):
        records = {
            10: (5, "Users", True),
            11: (10, "admin", True),
            12: (11, "hosts.txt", False),
        }
        cache: dict[int, str] = {}
        result = resolve_path(12, records, 5, "C:", cache)
        assert_that(result).is_equal_to("C:\\Users\\admin\\hosts.txt")

    def test_cached_path(self):
        records = {10: (5, "Users", True), 11: (10, "file.txt", False)}
        cache = {10: "C:\\Users"}
        result = resolve_path(11, records, 5, "C:", cache)
        assert_that(result).is_equal_to("C:\\Users\\file.txt")

    def test_orphaned_record(self):
        records = {10: (999, "orphan.txt", False)}
        cache: dict[int, str] = {}
        result = resolve_path(10, records, 5, "C:", cache)
        assert_that(result).is_empty()

    def test_cycle_detection(self):
        records = {10: (11, "a", False), 11: (10, "b", False)}
        cache: dict[int, str] = {}
        result = resolve_path(10, records, 5, "C:", cache)
        assert_that(result).is_empty()

    def test_already_cached(self):
        records: dict[int, tuple[int, str, bool]] = {}
        cache = {10: "C:\\cached\\file.txt"}
        result = resolve_path(10, records, 5, "C:", cache)
        assert_that(result).is_equal_to("C:\\cached\\file.txt")

    def test_drive_letter_trailing_backslash(self):
        records = {10: (5, "file.txt", False)}
        cache: dict[int, str] = {}
        result = resolve_path(10, records, 5, "C:\\", cache)
        assert_that(result).is_equal_to("C:\\file.txt")


class TestMftRecord:
    def test_fields(self):
        record = MftRecord(file_ref=10, parent_ref=5, name="hosts.txt", is_dir=False)
        assert_that(record.file_ref).is_equal_to(10)
        assert_that(record.parent_ref).is_equal_to(5)
        assert_that(record.name).is_equal_to("hosts.txt")
        assert_that(record.is_dir).is_false()

    def test_is_namedtuple(self):
        record = MftRecord(file_ref=1, parent_ref=2, name="dir", is_dir=True)
        assert_that(record).is_equal_to((1, 2, "dir", True))


class TestStreamMftBatches:
    def test_yields_batches(self, monkeypatch):
        record_data = _build_usn_record(10, 5, "file.txt", is_dir=False)
        next_ref_bytes = bytes(ctypes.c_ulonglong(99))
        data = next_ref_bytes + record_data
        total_len = len(data)

        call_count = [0]

        def fake_device_io(_h, _c, _ib, _is, out_buf, _os, bytes_ret_ptr, _ov):
            if call_count[0] >= 2:
                return 0
            call_count[0] += 1
            ctypes.memmove(out_buf, data, total_len)
            bytes_ret_ptr.contents.value = total_len
            return 1

        mock_kernel = MagicMock()
        mock_kernel.DeviceIoControl = fake_device_io
        monkeypatch.setattr("seekbar._mft.kernel32", mock_kernel)

        batches = list(_stream_mft_batches(42))
        assert_that(batches).is_length(2)
        assert_that(batches).all_satisfy(lambda batch: isinstance(batch, list))

    def test_empty_volume(self, monkeypatch):
        mock_kernel = MagicMock()
        mock_kernel.DeviceIoControl = MagicMock(return_value=0)
        monkeypatch.setattr("seekbar._mft.kernel32", mock_kernel)

        batches = list(_stream_mft_batches(42))
        assert_that(batches).is_empty()

    def test_record_fields_correct(self, monkeypatch):
        record_data = _build_usn_record(10, 5, "hosts.txt", is_dir=False)
        dir_data = _build_usn_record(11, 5, "docs", is_dir=True)
        next_ref_bytes = bytes(ctypes.c_ulonglong(99))
        data = next_ref_bytes + record_data + dir_data
        total_len = len(data)

        call_count = [0]

        def fake_device_io(_h, _c, _ib, _is, out_buf, _os, bytes_ret_ptr, _ov):
            if call_count[0] > 0:
                return 0
            call_count[0] += 1
            ctypes.memmove(out_buf, data, total_len)
            bytes_ret_ptr.contents.value = total_len
            return 1

        mock_kernel = MagicMock()
        mock_kernel.DeviceIoControl = fake_device_io
        monkeypatch.setattr("seekbar._mft.kernel32", mock_kernel)

        batches = list(_stream_mft_batches(42))
        assert_that(batches).is_length(1)
        batch = batches[0]
        assert_that(batch).is_length(2)

        assert_that(batch[0]).is_equal_to(MftRecord(file_ref=10, parent_ref=5, name="hosts.txt", is_dir=False))
        assert_that(batch[1]).is_equal_to(MftRecord(file_ref=11, parent_ref=5, name="docs", is_dir=True))


class TestStreamMft:
    def test_handle_closed_on_normal_exit(self, monkeypatch):
        mock_kernel = MagicMock()
        mock_kernel.CreateFileW = MagicMock(return_value=42)
        mock_kernel.DeviceIoControl = MagicMock(return_value=0)
        mock_kernel.CloseHandle = MagicMock()
        monkeypatch.setattr("seekbar._mft.kernel32", mock_kernel)

        list(stream_mft("C:"))
        mock_kernel.CloseHandle.assert_called_once_with(42)

    def test_handle_closed_on_early_break(self, monkeypatch):
        record_data = _build_usn_record(10, 5, "file.txt", is_dir=False)
        next_ref_bytes = bytes(ctypes.c_ulonglong(99))
        data = next_ref_bytes + record_data
        total_len = len(data)

        def fake_device_io(_h, _c, _ib, _is, out_buf, _os, bytes_ret_ptr, _ov):
            ctypes.memmove(out_buf, data, total_len)
            bytes_ret_ptr.contents.value = total_len
            return 1

        mock_kernel = MagicMock()
        mock_kernel.CreateFileW = MagicMock(return_value=42)
        mock_kernel.DeviceIoControl = fake_device_io
        mock_kernel.CloseHandle = MagicMock()
        monkeypatch.setattr("seekbar._mft.kernel32", mock_kernel)

        for _batch in stream_mft("C:"):
            break

        mock_kernel.CloseHandle.assert_called_once_with(42)

    def test_raises_on_invalid_handle(self, monkeypatch):
        mock_kernel = MagicMock()
        mock_kernel.CreateFileW = MagicMock(return_value=INVALID_HANDLE_VALUE)
        monkeypatch.setattr("seekbar._mft.kernel32", mock_kernel)
        monkeypatch.setattr(ctypes, "get_last_error", lambda: 5)

        assert_that(lambda: list(stream_mft("C:"))).raises(OSError).when_called_with().satisfies(
            lambda message: "Cannot open volume" in message
        )


class TestReadMftRefactored:
    def test_parses_records_same_as_before(self, monkeypatch):
        record1 = _build_usn_record(10, 5, "hosts.txt", is_dir=False)
        record2 = _build_usn_record(11, 5, "docs", is_dir=True)
        next_ref_bytes = bytes(ctypes.c_ulonglong(99))
        data = next_ref_bytes + record1 + record2
        total_len = len(data)

        call_count = [0]

        def fake_device_io(_h, _c, _ib, _is, out_buf, _os, bytes_ret_ptr, _ov):
            if call_count[0] > 0:
                return 0
            call_count[0] += 1
            ctypes.memmove(out_buf, data, total_len)
            bytes_ret_ptr.contents.value = total_len
            return 1

        mock_kernel = MagicMock()
        mock_kernel.CreateFileW = MagicMock(return_value=42)
        mock_kernel.DeviceIoControl = fake_device_io
        mock_kernel.CloseHandle = MagicMock()
        monkeypatch.setattr("seekbar._mft.kernel32", mock_kernel)

        records, root_ref = enumerate_mft("C:")
        assert_that(root_ref).is_equal_to(5)
        assert_that(records[10]).is_equal_to((5, "hosts.txt", False))
        assert_that(records[11]).is_equal_to((5, "docs", True))


class TestImportGuard:
    def test_non_windows_raises(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        assert_that(lambda: importlib.reload(mft_module)).raises(ImportError).when_called_with().satisfies(
            lambda message: "only available on Windows" in message
        )
