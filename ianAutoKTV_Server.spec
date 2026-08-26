# PyInstaller build specification for OpenKTV-AI v1.0.0.
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

project_dir = Path(SPECPATH)
datas = []
binaries = []

datas += collect_data_files("spleeter")
datas.append((str(project_dir / ".venv" / "Lib" / "site-packages" / "setuptools" / "_vendor" / "jaraco" / "text" / "Lorem ipsum.txt"), "setuptools/_vendor/jaraco/text"))
hiddenimports = collect_submodules("spleeter")
hiddenimports += ["engineio.async_drivers.threading"]

a = Analysis(
    [str(project_dir / "main.py")],
    pathex=[str(project_dir)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hooksconfig={},
    runtime_hooks=[str(project_dir / "pyinstaller_runtime_hook.py")],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    name="ianAutoKTV_Server",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="ianAutoKTV_Server",
)