# Build a folder, retaining dynamically linked Qt libraries for LGPL replacement.
from PyInstaller.utils.hooks import collect_all, copy_metadata
from pathlib import Path
import os
import sys
import importlib.util
import importlib.metadata
import runpy

# Ignore unrelated tools on the developer's PATH. In particular, a Poppler ICU DLL
# can shadow Windows' ICU and break Qt even though source execution works.
windows_root = Path(os.environ.get("SystemRoot", "C:/Windows"))
os.environ["PATH"] = os.pathsep.join([
    str(Path(sys.executable).parent), sys.base_prefix,
    str(windows_root / "System32"), str(windows_root),
])

project = Path(SPECPATH).parent

datas, binaries, hiddenimports = [], [], []
for package in ("faster_whisper", "ctranslate2", "uiautomation"):
    package_datas, package_binaries, package_imports = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_imports
for package in (
    "PySide6-Essentials", "faster-whisper", "huggingface-hub", "sounddevice", "numpy", "uiautomation",
):
    datas += copy_metadata(package, recursive=True)
if importlib.util.find_spec("llama_cpp") is not None:
    package_datas, package_binaries, package_imports = collect_all("llama_cpp")
    datas += package_datas + copy_metadata("llama-cpp-python", recursive=True)
    binaries += package_binaries
    hiddenimports += package_imports
# Some wheels store notices outside dist-info, beyond copy_metadata's scope.
metadata_directories = [Path(source) for source, _ in datas
                        if Path(source).is_dir() and str(source).endswith(".dist-info")]
bootloader = importlib.metadata.distribution("pyinstaller")
metadata_directories += [Path(bootloader.locate_file(record)).parent
                         for record in bootloader.files if str(record).endswith(".dist-info/METADATA")]
collect_notices = runpy.run_path(str(project / "scripts" / "bundle_inventory.py"))["collect_notices"]
datas += collect_notices(metadata_directories)
datas += [(str(project / "packaging" / "licenses"), "third_party/supplemental")]
datas += [(str(Path(sys.base_prefix) / "LICENSE.txt"), "third_party/python")]
datas += [(str(project / "LICENSE"), "."), (str(project / "THIRD_PARTY_NOTICES.md"), ".")]
a = Analysis([str(project / "packaging" / "entry.py")], pathex=[str(project / "src")], binaries=binaries,
             datas=datas, hiddenimports=hiddenimports,
             excludes=["tkinter", "pytest", "mypy", "ruff"])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="LocalPhraser",
          debug=False, strip=False, upx=False, console=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="LocalPhraser")
