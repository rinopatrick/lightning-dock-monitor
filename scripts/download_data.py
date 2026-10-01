from __future__ import annotations
import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
from lightning_dock.io import download_archive, inspect_archive

def main() -> None:
    destination = PROJECT_ROOT / "data" / "raw" / "04_PRODUCTION_INJECTION_GENERATION.zip"
    archive = download_archive(destination)
    print(f"Archive saved at: {archive}")
    for member in inspect_archive(archive):
        print(member)

if __name__ == "__main__":
    main()
