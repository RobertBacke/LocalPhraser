"""Query build/license strings from a trusted Windows build in a disposable process."""

import ctypes
import json
import os
import sys
from contextlib import ExitStack
from pathlib import Path


def probe(folder: Path) -> list[dict]:
    if os.name != "nt":
        raise RuntimeError("This probe requires Windows.")
    folder = folder.resolve()
    internal = folder / "_internal"
    libraries = sorted(internal.rglob("*.dll"))
    if any(path.is_symlink() or not path.resolve().is_relative_to(folder) for path in libraries):
        raise ValueError("Untrusted library path.")
    reports = []
    with ExitStack() as directories:
        for directory in sorted({path.parent for path in libraries}):
            directories.enter_context(os.add_dll_directory(str(directory)))
        for path in libraries:
            prefix = path.name.split("-", 1)[0]
            if prefix not in ("avcodec", "avformat", "avutil"):
                continue
            library = ctypes.CDLL(str(path))
            strings = {}
            for suffix in ("configuration", "license"):
                function = getattr(library, prefix + "_" + suffix)
                function.argtypes = []
                function.restype = ctypes.c_char_p
                strings[suffix] = function().decode("utf-8")
            version = getattr(library, prefix + "_version")
            version.argtypes = []
            version.restype = ctypes.c_uint
            encoded = version()
            reports.append(
                {
                    "path": path.relative_to(folder).as_posix(),
                    "version": [encoded >> 16, (encoded >> 8) & 255, encoded & 255],
                    **strings,
                }
            )
    return reports


if __name__ == "__main__":
    print(json.dumps(probe(Path(sys.argv[1])), ensure_ascii=False))
