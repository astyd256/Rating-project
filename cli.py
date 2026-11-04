import argparse
import sys

from commands.create_html import main as create_html
from commands.dedupe import main as dedupe
from commands.import_file import main as import_file
from commands.import_media import main as import_media
from commands.import_music import main as import_music
from commands.prune_posters import main as prune_posters
from lib.config import load_config
from lib.db.init import ensure_db


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Ratings CLI: import movies, music, games, anime and manga; build a static site.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python cli.py --init\n"
            "  python cli.py --import-file data/imdb_ratings.csv\n"
            "  python cli.py --import-file data/imdb_ratings.csv --sync --dry-run\n"
            "  python cli.py --import-file data/imdb_ratings.csv --sync\n"
            "  python cli.py --import-music \"D:/Music\"\n"
            "  python cli.py --import-games data/yamtrack.csv\n"
            "  python cli.py --import-anime data/animes.xml\n"
            "  python cli.py --import-manga data/mangas.xml\n"
            "  python cli.py --create-html --top-n 100\n"
        ),
    )

    parser.add_argument("--init", action="store_true", help="create the database and apply migrations")
    parser.add_argument("--import-file", metavar="CSV", help="import rated movies from an IMDb CSV export")
    parser.add_argument("--import-music", metavar="FOLDER", help="scan a music folder and import tags/cover art")
    parser.add_argument("--import-games", metavar="CSV", help="import rated games from a Yamtrack CSV export")
    parser.add_argument("--import-anime", metavar="XML", help="import rated anime from a MAL XML export")
    parser.add_argument("--import-manga", metavar="XML", help="import rated manga from a MAL XML export")
    parser.add_argument(
        "--dedupe",
        action="store_true",
        help="merge movies that are duplicate (same title and year)",
    )
    parser.add_argument(
        "--prune-posters",
        action="store_true",
        help="delete files in images/movies that no movie references",
    )
    parser.add_argument("--create-html", action="store_true", help="generate the static HTML site")

    parser.add_argument(
        "--sync",
        action="store_true",
        help="with --import-file: the CSV is the full list, delete movies missing from it",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="allow --sync to delete more than half of the movie table",
    )
    parser.add_argument(
        "--data-type",
        default="movie",
        help="type of data in --import-file (only 'movie' is supported)",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=30,
        help="max cards per section in the generated HTML (0 = all)",
    )
    parser.add_argument(
        "--include-manga-types",
        metavar="LIST",
        help=(
            "comma-separated MAL manga types to show, e.g. doujin,light_novel "
            "or 'all'; by default doujin and light_novel are hidden"
        ),
    )
    parser.add_argument(
        "--block-no-star-music",
        dest="block_no_star_music",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="skip tracks without a rating when importing music",
    )
    parser.add_argument(
        "--no-posters",
        action="store_true",
        help="do not download posters while importing media",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="show what --sync / --dedupe / --prune-posters would change",
    )

    parser.add_argument("--db-path", help="override DB_PATH from .env")
    parser.add_argument("--site-folder", help="override SITE_FOLDER from .env")
    parser.add_argument("--html-path", help="override the generated HTML path")
    return parser


def _configure_output() -> None:
    """Avoid crashes on Windows consoles that cannot encode a path/title."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass


def main(argv: list[str] | None = None) -> int:
    _configure_output()
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.sync and not args.import_file:
        parser.error("--sync requires --import-file")
    if args.dry_run and args.import_file and not args.sync:
        parser.error("--dry-run with --import-file requires --sync")

    selected = any(
        (
            args.init,
            args.import_file,
            args.import_music,
            args.import_games,
            args.import_anime,
            args.import_manga,
            args.dedupe,
            args.prune_posters,
            args.create_html,
        )
    )
    if not selected:
        parser.print_help()
        return 0

    config = load_config(
        db_path=args.db_path,
        site_folder=args.site_folder,
        html_path=args.html_path,
    )

    # One bootstrap for every action that needs a working schema.
    if (
        args.init
        or args.import_file
        or args.import_music
        or args.import_games
        or args.import_anime
        or args.import_manga
        or args.create_html
    ):
        ensure_db(config.db_path)

    if args.import_file:
        code = import_file(
            args.import_file,
            config,
            args.data_type,
            download_posters=not args.no_posters,
            sync=args.sync,
            dry_run=args.dry_run,
            force=args.force,
        )
        if code:
            return code

    if args.import_music:
        code = import_music(
            args.import_music,
            config,
            block_without_rating=args.block_no_star_music,
        )
        if code:
            return code

    if args.import_games:
        code = import_media(
            "games",
            args.import_games,
            config,
            download_posters=not args.no_posters,
        )
        if code:
            return code

    if args.import_anime:
        code = import_media(
            "anime",
            args.import_anime,
            config,
            download_posters=not args.no_posters,
        )
        if code:
            return code

    if args.import_manga:
        code = import_media(
            "manga",
            args.import_manga,
            config,
            download_posters=not args.no_posters,
        )
        if code:
            return code

    if args.dedupe:
        code = dedupe(config, dry_run=args.dry_run)
        if code:
            return code

    if args.prune_posters:
        code = prune_posters(config, dry_run=args.dry_run)
        if code:
            return code

    if args.create_html:
        include_manga_types = {
            value.strip().lower()
            for value in (args.include_manga_types or "").split(",")
            if value.strip()
        }
        code = create_html(
            config,
            args.top_n,
            include_manga_types=include_manga_types,
        )
        if code:
            return code

    return 0


if __name__ == "__main__":
    sys.exit(main())
