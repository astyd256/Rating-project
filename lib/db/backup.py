"""Database backups taken before destructive maintenance operations."""
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path


def backup_database(db_path: str | Path) -> Path:
    """Copy the SQLite file next to the original and return the backup path."""
    source = Path(db_path)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = source.with_name(f"{source.name}.bak-{stamp}")
    index = 2
    while target.exists():
        target = source.with_name(f"{source.name}.bak-{stamp}-{index}")
        index += 1
    shutil.copy2(source, target)
    return target
