import ctypes as ct
import sys
from threading import Timer
from unittest.mock import Mock

import pytest

from localphraser.models import _rename_directory


@pytest.mark.skipif(sys.platform != "win32", reason="Windows file sharing semantics")
def test_publication_waits_for_a_brief_open_child_file_handle(tmp_path):
    stage, destination = tmp_path / "stage", tmp_path / "installed"
    stage.mkdir()
    weights = stage / "weights.bin"
    weights.write_bytes(b"owned synthetic model")
    kernel = ct.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [
        ct.c_wchar_p,
        ct.c_uint,
        ct.c_uint,
        ct.c_void_p,
        ct.c_uint,
        ct.c_uint,
        ct.c_void_p,
    ]
    kernel.CreateFileW.restype = ct.c_void_p
    kernel.CloseHandle.argtypes = [ct.c_void_p]
    handle = kernel.CreateFileW(str(weights), 0x80000000, 1, None, 3, 0, None)
    assert handle not in (None, ct.c_void_p(-1).value)
    release = Timer(0.2, lambda: kernel.CloseHandle(handle))
    release.start()
    try:
        _rename_directory(stage, destination)
    finally:
        release.join()
    assert not stage.exists()
    assert (destination / "weights.bin").read_bytes() == b"owned synthetic model"


@pytest.mark.parametrize("winerror,attempts", [(5, 6), (32, 6), (33, 6), (None, 1)])
def test_publication_retry_is_bounded_and_does_not_change_permissions(
    monkeypatch, winerror, attempts
):
    error = PermissionError("synthetic refusal")
    error.winerror = winerror
    source = Mock()
    source.rename.side_effect = error
    sleep = Mock()
    monkeypatch.setattr("localphraser.models.time.sleep", sleep)
    with pytest.raises(PermissionError):
        _rename_directory(source, Mock())
    assert source.rename.call_count == attempts
    assert sum(call.args[0] for call in sleep.call_args_list) <= 1.55
