from __future__ import annotations

import shutil
import urllib.request
from pathlib import Path
from zipfile import BadZipFile, ZipFile

import pandas as pd

ARCHIVE_URL = "https://gdr.openei.org/files/1856/04_PRODUCTION_INJECTION_GENERATION.zip"
ARCHIVE_NAME = "04_PRODUCTION_INJECTION_GENERATION.zip"
TABLE_NAME = "production_injection_generation_reports_daily.csv"
SOURCE_URL = "https://catalog.data.gov/dataset/lightning-dock-geothermal-field-data-package-hidalgo-county-new-mexico"
LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/"


def download_archive(destination: Path) -> Path:
    """Download the public operations archive, retaining an existing non-empty copy."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.stat().st_size > 0:
        return destination

    temporary = destination.with_suffix(destination.suffix + ".part")
    request = urllib.request.Request(
        ARCHIVE_URL, headers={"User-Agent": "lightning-dock-monitor/0.1"}
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            with temporary.open("wb") as stream:
                shutil.copyfileobj(response, stream)
        if temporary.stat().st_size == 0:
            raise RuntimeError("The source server returned an empty archive.")
        temporary.replace(destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return destination


def inspect_archive(archive_path: Path) -> list[str]:
    """Return ZIP member names and sizes without extracting the archive."""
    try:
        with ZipFile(archive_path) as archive:
            return [
                f"{member.filename} ({member.file_size} bytes)"
                for member in archive.infolist()
                if not member.is_dir()
            ]
    except (OSError, BadZipFile) as exc:
        raise ValueError(f"Cannot read source ZIP archive: {archive_path}") from exc


def load_operations(archive_path: Path) -> tuple[pd.DataFrame, dict[str, str]]:
    """Load the operations CSV while preserving source rows and columns."""
    try:
        with ZipFile(archive_path) as archive:
            members = [name for name in archive.namelist() if not name.endswith("/")]
            csv_members = [
                name for name in members
                if name.lower().endswith(".csv") and TABLE_NAME in name.lower()
            ]
            if not csv_members:
                csv_members = [name for name in members if name.lower().endswith(".csv")]
            if len(csv_members) != 1:
                raise ValueError(
                    "Expected one operations CSV; found: " + ", ".join(csv_members or members)
                )
            pdf_members = [name for name in members if name.lower().endswith(".pdf")]
            with archive.open(csv_members[0]) as stream:
                frame = pd.read_csv(stream, encoding="utf-8-sig", low_memory=False)
    except (OSError, BadZipFile) as exc:
        raise ValueError(f"Cannot read source ZIP archive: {archive_path}") from exc

    required = {"date", "error", "net_to_grid_kw"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"Source table is missing required columns: {sorted(missing)}")
    return frame, {
        "table_member": csv_members[0],
        "guide_member": pdf_members[0] if pdf_members else "",
    }
