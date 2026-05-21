import sys

import pytest

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
        assert is_ntfs("C:")

    def test_fat32_returns_false(self, monkeypatch):
        mock_kernel = MagicMock()

        def fake_get_volume_info(_path, _a, _b, _c, _d, _e, filesystem_buffer, _f):
            ctypes.memmove(filesystem_buffer, ctypes.create_unicode_buffer("FAT32"), 12)
            return 1

        mock_kernel.GetVolumeInformationW = fake_get_volume_info
        monkeypatch.setattr("seekbar._mft.kernel32", mock_kernel)
        assert not is_ntfs("D:")

    def test_failure_returns_false(self, monkeypatch):
        mock_kernel = MagicMock()
        mock_kernel.GetVolumeInformationW = MagicMock(return_value=0)
        monkeypatch.setattr("seekbar._mft.kernel32", mock_kernel)
        assert not is_ntfs("E:")


class TestEnumerateMft:
    def test_access_denied(self, monkeypatch):
        mock_kernel = MagicMock()
        mock_kernel.CreateFileW = MagicMock(return_value=INVALID_HANDLE_VALUE)
        mock_kernel.CloseHandle = MagicMock()
        monkeypatch.setattr("seekbar._mft.kernel32", mock_kernel)
        monkeypatch.setattr(ctypes, "get_last_error", lambda: 5)

        with pytest.raises(OSError, match="Cannot open volume"):
            enumerate_mft("C:")

    def test_empty_volume(self, monkeypatch):
        mock_kernel = MagicMock()
        mock_kernel.CreateFileW = MagicMock(return_value=42)
        mock_kernel.DeviceIoControl = MagicMock(return_value=0)
        mock_kernel.CloseHandle = MagicMock()
        monkeypatch.setattr("seekbar._mft.kernel32", mock_kernel)

        records, root_ref = enumerate_mft("C:")
        assert records == {}
        assert root_ref == 5
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
        assert root_ref == 5
        assert 10 in records
        assert records[10] == (5, "hosts.txt", False)
        assert 11 in records
        assert records[11] == (5, "docs", True)


class TestResolvePath:
    def test_simple_path(self):
        records = {10: (5, "hosts.txt", False)}
        cache: dict[int, str] = {}
        result = resolve_path(10, records, 5, "C:", cache)
        assert result == "C:\\hosts.txt"
        assert cache[10] == "C:\\hosts.txt"

    def test_nested_path(self):
        records = {
            10: (5, "Users", True),
            11: (10, "admin", True),
            12: (11, "hosts.txt", False),
        }
        cache: dict[int, str] = {}
        result = resolve_path(12, records, 5, "C:", cache)
        assert result == "C:\\Users\\admin\\hosts.txt"

    def test_cached_path(self):
        records = {10: (5, "Users", True), 11: (10, "file.txt", False)}
        cache = {10: "C:\\Users"}
        result = resolve_path(11, records, 5, "C:", cache)
        assert result == "C:\\Users\\file.txt"

    def test_orphaned_record(self):
        records = {10: (999, "orphan.txt", False)}
        cache: dict[int, str] = {}
        result = resolve_path(10, records, 5, "C:", cache)
        assert result == ""

    def test_cycle_detection(self):
        records = {10: (11, "a", False), 11: (10, "b", False)}
        cache: dict[int, str] = {}
        result = resolve_path(10, records, 5, "C:", cache)
        assert result == ""

    def test_already_cached(self):
        records: dict[int, tuple[int, str, bool]] = {}
        cache = {10: "C:\\cached\\file.txt"}
        result = resolve_path(10, records, 5, "C:", cache)
        assert result == "C:\\cached\\file.txt"

    def test_drive_letter_trailing_backslash(self):
        records = {10: (5, "file.txt", False)}
        cache: dict[int, str] = {}
        result = resolve_path(10, records, 5, "C:\\", cache)
        assert result == "C:\\file.txt"


class TestMftRecord:
    def test_fields(self):
        record = MftRecord(file_ref=10, parent_ref=5, name="hosts.txt", is_dir=False)
        assert record.file_ref == 10
        assert record.parent_ref == 5
        assert record.name == "hosts.txt"
        assert record.is_dir is False

    def test_is_namedtuple(self):
        record = MftRecord(file_ref=1, parent_ref=2, name="dir", is_dir=True)
        assert record == (1, 2, "dir", True)


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
        assert len(batches) == 2
        assert all(isinstance(batch, list) for batch in batches)

    def test_empty_volume(self, monkeypatch):
        mock_kernel = MagicMock()
        mock_kernel.DeviceIoControl = MagicMock(return_value=0)
        monkeypatch.setattr("seekbar._mft.kernel32", mock_kernel)

        batches = list(_stream_mft_batches(42))
        assert batches == []

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
        assert len(batches) == 1
        batch = batches[0]
        assert len(batch) == 2

        assert batch[0] == MftRecord(file_ref=10, parent_ref=5, name="hosts.txt", is_dir=False)
        assert batch[1] == MftRecord(file_ref=11, parent_ref=5, name="docs", is_dir=True)


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

        with pytest.raises(OSError, match="Cannot open volume"):
            list(stream_mft("C:"))


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
        assert root_ref == 5
        assert records[10] == (5, "hosts.txt", False)
        assert records[11] == (5, "docs", True)


class TestImportGuard:
    def test_non_windows_raises(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        with pytest.raises(ImportError, match="only available on Windows"):
            importlib.reload(mft_module)
