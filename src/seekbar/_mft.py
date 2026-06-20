import ctypes
import ctypes.wintypes
import sys
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from collections.abc import Iterator

if sys.platform != "win32":  # pragma: no cover
    msg = "This module is only available on Windows"
    raise ImportError(msg)

GENERIC_READ = 0x80000000
OPEN_EXISTING = 3
FILE_SHARE_READ = 1
FILE_SHARE_WRITE = 2
FSCTL_ENUM_USN_DATA = 0x000900B3
FILE_ATTRIBUTE_DIRECTORY = 0x10
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
_BUF_SIZE = 64 * 1024
_MFT_ROOT_REF = 5
_REF_MASK = 0x0000FFFFFFFFFFFF


class _MftEnumDataV0(ctypes.Structure):
    _fields_ = [
        ("StartFileReferenceNumber", ctypes.c_ulonglong),
        ("LowUsn", ctypes.c_longlong),
        ("HighUsn", ctypes.c_longlong),
    ]


class _UsnRecordV2(ctypes.Structure):
    _fields_ = [
        ("RecordLength", ctypes.wintypes.DWORD),
        ("MajorVersion", ctypes.wintypes.WORD),
        ("MinorVersion", ctypes.wintypes.WORD),
        ("FileReferenceNumber", ctypes.c_ulonglong),
        ("ParentFileReferenceNumber", ctypes.c_ulonglong),
        ("Usn", ctypes.c_longlong),
        ("TimeStamp", ctypes.c_longlong),
        ("Reason", ctypes.wintypes.DWORD),
        ("SourceInfo", ctypes.wintypes.DWORD),
        ("SecurityId", ctypes.wintypes.DWORD),
        ("FileAttributes", ctypes.wintypes.DWORD),
        ("FileNameLength", ctypes.wintypes.WORD),
        ("FileNameOffset", ctypes.wintypes.WORD),
    ]


kernel32 = ctypes.windll.kernel32


class MftRecord(NamedTuple):
    file_ref: int
    parent_ref: int
    name: str
    is_dir: bool


# noinspection PyUnresolvedReferences
def is_ntfs(drive_letter: str) -> bool:
    filesystem_name = ctypes.create_unicode_buffer(256)
    result = kernel32.GetVolumeInformationW(
        f"{drive_letter.rstrip(chr(92))}\\",
        None,
        0,
        None,
        None,
        None,
        filesystem_name,
        256,
    )
    if not result:
        return False
    return filesystem_name.value == "NTFS"


# noinspection PyUnresolvedReferences
def enumerate_mft(drive_letter: str) -> tuple[dict[int, tuple[int, str, bool]], int]:
    volume_path = f"\\\\.\\{drive_letter.rstrip(chr(92))}"
    handle = kernel32.CreateFileW(
        volume_path,
        GENERIC_READ,
        FILE_SHARE_READ | FILE_SHARE_WRITE,
        None,
        OPEN_EXISTING,
        0,
        None,
    )
    if handle == INVALID_HANDLE_VALUE:
        error_code = ctypes.get_last_error()
        error_msg = f"Cannot open volume {volume_path} (error {error_code}, admin required?)"
        raise OSError(error_msg)

    try:
        return _read_mft(handle)
    finally:
        kernel32.CloseHandle(handle)


# noinspection PyUnresolvedReferences
def _stream_mft_batches(handle: int) -> Iterator[list[MftRecord]]:
    enum_data = _MftEnumDataV0()
    enum_data.StartFileReferenceNumber = 0
    enum_data.LowUsn = 0
    enum_data.HighUsn = 0x7FFFFFFFFFFFFFFF

    read_buffer = ctypes.create_string_buffer(_BUF_SIZE)
    bytes_returned = ctypes.wintypes.DWORD()
    bytes_returned_ptr = ctypes.pointer(bytes_returned)

    while kernel32.DeviceIoControl(
        handle,
        FSCTL_ENUM_USN_DATA,
        ctypes.byref(enum_data),
        ctypes.sizeof(enum_data),
        read_buffer,
        _BUF_SIZE,
        bytes_returned_ptr,
        None,
    ):
        batch: list[MftRecord] = []
        next_ref = ctypes.c_ulonglong.from_buffer_copy(read_buffer, 0).value
        offset = 8
        while offset < bytes_returned.value:
            record = _UsnRecordV2.from_buffer_copy(read_buffer, offset)
            name_start = offset + record.FileNameOffset
            name_end = name_start + record.FileNameLength
            name = bytes(read_buffer[name_start:name_end]).decode("utf-16-le")

            batch.append(
                MftRecord(
                    file_ref=record.FileReferenceNumber & _REF_MASK,
                    parent_ref=record.ParentFileReferenceNumber & _REF_MASK,
                    name=name,
                    is_dir=bool(record.FileAttributes & FILE_ATTRIBUTE_DIRECTORY),
                )
            )
            offset += record.RecordLength

        enum_data.StartFileReferenceNumber = next_ref
        yield batch


def _read_mft(handle: int) -> tuple[dict[int, tuple[int, str, bool]], int]:
    records: dict[int, tuple[int, str, bool]] = {}
    for batch in _stream_mft_batches(handle):
        for mft_record in batch:
            records[mft_record.file_ref] = (mft_record.parent_ref, mft_record.name, mft_record.is_dir)
    return records, _MFT_ROOT_REF


# noinspection PyUnresolvedReferences
def stream_mft(drive_letter: str) -> Iterator[list[MftRecord]]:
    volume_path = f"\\\\.\\{drive_letter.rstrip(chr(92))}"
    handle = kernel32.CreateFileW(
        volume_path,
        GENERIC_READ,
        FILE_SHARE_READ | FILE_SHARE_WRITE,
        None,
        OPEN_EXISTING,
        0,
        None,
    )
    if handle == INVALID_HANDLE_VALUE:
        error_code = ctypes.get_last_error()
        error_msg = f"Cannot open volume {volume_path} (error {error_code}, admin required?)"
        raise OSError(error_msg)

    try:
        yield from _stream_mft_batches(handle)
    finally:
        kernel32.CloseHandle(handle)


def resolve_path(
    ref: int,
    records: dict[int, tuple[int, str, bool]],
    root_ref: int,
    drive_letter: str,
    cache: dict[int, str],
) -> str:
    if ref in cache:
        return cache[ref]

    chain: list[int] = []
    names: list[str] = []
    current = ref
    seen: set[int] = set()

    while current != root_ref and current in records:
        if current in cache:
            break
        if current in seen:
            return ""
        seen.add(current)
        parent, name, _ = records[current]
        chain.append(current)
        names.append(name)
        current = parent

    if current != root_ref and current not in cache and current not in records:
        return ""

    # Cache every ref walked, not just the requested one, so sibling lookups
    # reuse already-resolved ancestor paths instead of re-walking the chain.
    path = cache[current] if current in cache else drive_letter.rstrip("\\")
    for index in range(len(names) - 1, -1, -1):
        path = path + "\\" + names[index]
        cache[chain[index]] = path
    return path
