from pathlib import Path

from lib.config import Config
from lib.import_movies import import_movies_csv

ALLOWED_EXTENSIONS = {"csv"}


def main(
    file_path: str,
    config: Config,
    data_type: str = "movie",
    *,
    download_posters: bool = True,
    sync: bool = False,
    dry_run: bool = False,
    force: bool = False,
) -> int:
    path = Path(file_path)
    if not path.is_file():
        print(f"File not found: {path}")
        return 2

    if data_type != "movie":
        print(f"Unsupported data type: {data_type} (only 'movie' is supported)")
        return 3

    extension = path.suffix.lstrip(".").lower()
    if extension not in ALLOWED_EXTENSIONS:
        print(
            f"Unsupported file extension: {extension or '<none>'}. "
            "Export your ratings from IMDb as CSV."
        )
        return 3

    try:
        stats = import_movies_csv(
            path,
            config,
            download_posters=download_posters,
            sync=sync,
            dry_run=dry_run,
            force=force,
        )
    except RuntimeError as exc:
        print(exc)
        return 1
    except Exception as exc:
        print(f"Import failed: {exc}")
        return 1

    mode = " [dry-run]" if dry_run else ""
    deleted_label = "to delete" if dry_run else "deleted"
    if dry_run:
        print(
            f"Movies{mode}: {stats.csv_rows} rows in CSV, "
            f"{stats.deleted} {deleted_label}"
        )
    else:
        print(
            f"Movies{mode}: {stats.inserted} added, {stats.updated} updated, "
            f"{stats.unchanged} unchanged, "
            f"{stats.deleted} {deleted_label}"
        )

    if stats.deleted_titles:
        for label in stats.deleted_titles:
            print(f"  - {label}")

    if stats.backup_path:
        print(f"Backup: {stats.backup_path}")

    print(f"Posters downloaded: {stats.posters_downloaded}")
    if sync:
        poster_label = "to delete" if dry_run else "deleted"
        print(f"Poster files {poster_label}: {stats.posters_deleted}")
        if dry_run and stats.poster_files:
            for relative in stats.poster_files:
                print(f"  - {relative}")

    return 0
