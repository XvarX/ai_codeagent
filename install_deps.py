"""Download ripgrep and place it for dev + build modes."""
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


def main():
    tmp = Path(sys.prefix) / "tmp" / "ripgrep_dl"
    tmp.mkdir(parents=True, exist_ok=True)
    zip_path = tmp / RG_FILENAME

    print(f"Downloading {RG_URL} ...")
    try:
        urllib.request.urlretrieve(RG_URL, zip_path)
    except Exception as e:
        print(f"Download failed: {e}")
        print("Please download ripgrep manually from:")
        print("  https://github.com/BurntSushi/ripgrep/releases")
        return 1

    print("Extracting...")
    extract_dir = tmp / "extracted"
    if extract_dir.exists():
        import shutil
        shutil.rmtree(extract_dir)
    extract_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(extract_dir)

    # Find rg.exe
    rg_exe = None
    for f in extract_dir.rglob("rg.exe"):
        rg_exe = f
        break
    if not rg_exe:
        print("Error: rg.exe not found in archive")
        return 1

    DEST_DEV.parent.mkdir(parents=True, exist_ok=True)
    DEST_BUILD.parent.mkdir(parents=True, exist_ok=True)

    import shutil
    shutil.copy2(rg_exe, DEST_DEV)
    print(f"  -> {DEST_DEV}")
    shutil.copy2(rg_exe, DEST_BUILD)
    print(f"  -> {DEST_BUILD}")

    # Cleanup
    shutil.rmtree(tmp)
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
