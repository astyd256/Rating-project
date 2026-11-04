from lib.config import Config
from lib.import_games import import_games_csv
from lib.import_mal import import_mal_xml


def main(
    kind: str,
    path: str,
    config: Config,
    *,
    download_posters: bool = True,
) -> int:
    try:
        if kind == "games":
            stats = import_games_csv(path, config, download_posters=download_posters)
        elif kind in {"anime", "manga"}:
            stats = import_mal_xml(
                path,
                config,
                kind,
                download_posters=download_posters,
            )
        else:
            print(f"Unsupported import kind: {kind}")
            return 3
    except FileNotFoundError:
        print(f"File not found: {path}")
        return 2
    except Exception as exc:
        print(f"{kind.title()} import failed: {exc}")
        return 1

    print(
        f"{kind.title()}: {stats.added} added, {stats.updated} updated, "
        f"{stats.posters} posters"
    )
    return 0
