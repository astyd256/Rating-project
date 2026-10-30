from pathlib import Path

from lib.config import Config
from lib.import_utils import import_movies_csv

ALLOWED_EXTENSIONS = {"csv"}


def main(
    file_path: str,
    config: Config,
    data_type: str = "movie",
    *,
    download_posters: bool = True,
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
        stats = import_movies_csv(path, config, download_posters=download_posters)
    except Exception as exc:
        print(f"Import failed: {exc}")
        return 1

    print(
        f"Movies: {stats.inserted} added, {stats.updated} updated, "
        f"{stats.unchanged} unchanged, {stats.skipped} skipped"
    )
    print(f"Posters downloaded: {stats.posters_downloaded}")
    return 0
