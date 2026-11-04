from lib.config import Config
from lib.create_html import main as create_html


def main(
    config: Config,
    top_n: int = 30,
    *,
    include_manga_types: set[str] | None = None,
) -> int:
    try:
        report = create_html(
            str(config.html_path),
            str(config.db_path),
            top_n,
            lastfm_user=config.lastfm_user,
            lastfm_api_key=config.lastfm_api_key,
            lastfm_refresh=config.lastfm_refresh_seconds,
            include_manga_types=include_manga_types,
        )
    except Exception as exc:
        print(f"HTML generation failed: {exc}")
        return 1

    print(
        f"HTML written: {report['path']} "
        f"({report['movies']} movies, {report['music']} music, "
        f"{report['games']} games, {report['anime']} anime, "
        f"{report['manga']} manga, {report['bytes']} bytes)"
    )
    if report.get("lastfm"):
        print("Last.fm widget: enabled")
    else:
        print("Last.fm widget: disabled (set LASTFM_USER and LASTFM_API_KEY in .env)")
    return 0
