"""Delete poster files that no longer belong to any movie row."""
from __future__ import annotations

from lib.config import Config
from lib.posters import prune_orphan_posters


def main(config: Config, *, dry_run: bool = False) -> int:
    if not config.db_path.is_file():
        print(f"Database not found: {config.db_path}")
        return 2

    removed, count = prune_orphan_posters(
        config.db_path,
        config.site_folder,
        dry_run=dry_run,
    )

    prefix = "[dry-run] " if dry_run else ""
    for relative in removed:
        print(f"  - {relative}")
    verb = "to delete" if dry_run else "deleted"
    print(f"{prefix}Poster files {verb}: {count}")
    return 0
