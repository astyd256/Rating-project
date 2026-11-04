from lib.config import Config
from lib.import_music_metadata import import_music_folder


def main(
    folder_path: str,
    config: Config,
    *,
    block_without_rating: bool = True,
) -> int:
    print("Scanning music metadata...")
    try:
        stats = import_music_folder(
            folder_path,
            str(config.db_path),
            config.site_folder,
            block_without_rating=block_without_rating,
        )
    except FileNotFoundError as exc:
        print(exc)
        return 2
    except Exception as exc:
        print(f"Music import failed: {exc}")
        return 1

    print(
        f"Music: {stats.added} added, {stats.updated} updated, "
        f"{stats.errors} errors"
    )
    return 0
