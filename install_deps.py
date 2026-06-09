"""Install all dependencies: pip, npm, and ripgrep."""
import subprocess
import sys
import zipfile
import urllib.request
from pathlib import Path

RG_VERSION = "15.1.0"
RG_FILENAME = f"ripgrep-{RG_VERSION}-x86_64-pc-windows-msvc.zip"
RG_URL = f"https://github.com/BurntSushi/ripgrep/releases/download/{RG_VERSION}/{RG_FILENAME}"

PROJECT = Path(__file__).resolve().parent
DEST_DEV = PROJECT / "agentcore" / "rg.exe"
DEST_BUILD = PROJECT / "build" / "agentcore" / "rg.exe"


def run(cmd: list[str], cwd: str | None = None) -> int:
    print(f"  {' '.join(cmd)}")
    p = subprocess.run(cmd, cwd=cwd)
    return p.returncode


def install_backend() -> int:
    print("\n" + "=" * 40)
    print("Installing backend dependencies...")
    print("=" * 40)
    return run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])


def install_frontend() -> int:
    print("\n" + "=" * 40)
    print("Installing frontend dependencies...")
    print("=" * 40)
    ui_dir = str(PROJECT / "ui")
    npm = "npm.cmd" if sys.platform == "win32" else "npm"
    return run([npm, "install"], cwd=ui_dir)


def install_ripgrep() -> int:
    print("\n" + "=" * 40)
    print("Downloading ripgrep (rg.exe)...")
    print("=" * 40)

    tmp = PROJECT / "build" / "ripgrep_dl"
    tmp.mkdir(parents=True, exist_ok=True)
    zip_path = tmp / RG_FILENAME

    print(f"  {RG_URL}")
    try:
        urllib.request.urlretrieve(RG_URL, zip_path)
    except Exception as e:
        print(f"  Download failed: {e}")
        print("  Download manually from https://github.com/BurntSushi/ripgrep/releases")
        return 1

    print("  Extracting...")
    extract_dir = tmp / "extracted"
    if extract_dir.exists():
        import shutil
        shutil.rmtree(extract_dir)
    extract_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(extract_dir)

    rg_exe = None
    for f in extract_dir.rglob("rg.exe"):
        rg_exe = f
        break
    if not rg_exe:
        print("  Error: rg.exe not found in archive")
        return 1

    DEST_DEV.parent.mkdir(parents=True, exist_ok=True)
    DEST_BUILD.parent.mkdir(parents=True, exist_ok=True)
    import shutil
    shutil.copy2(rg_exe, DEST_DEV)
    print(f"  -> {DEST_DEV}")
    shutil.copy2(rg_exe, DEST_BUILD)
    print(f"  -> {DEST_BUILD}")

    shutil.rmtree(tmp)
    print("  Done.")
    return 0


def main() -> int:
    print("AI Code Agent — Dependency Installer\n")

    for step, fn in [("Backend", install_backend),
                      ("Frontend", install_frontend),
                      ("Ripgrep", install_ripgrep)]:
        ret = fn()
        if ret != 0:
            print(f"\n{step} install failed!")
            return ret

    print("\n" + "=" * 40)
    print("All dependencies installed successfully!")
    print("=" * 40)
    return 0


if __name__ == "__main__":
    sys.exit(main())
