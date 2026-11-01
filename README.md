# Rating-project

Pet project for keeping personal ratings of movies, TV shows and music in one
SQLite database and rendering them as a static site.

- [TL;DR](#tldr)
- [Usage](#usage)
- [Commands](#commands)
- [Keeping the movie list in sync](#keeping-the-movie-list-in-sync)
- [How data is stored](#how-data-is-stored)
- [Supported services](#supported-services)
- [Features](#features)

## TL;DR

- SQLite + SQLAlchemy 2.0, schema versioned with Alembic.
- Movie ratings are imported from an IMDb CSV export; posters are downloaded
  once and served from `personal-site/images/movies`.
- `--sync` makes the CSV the authoritative movie list: rows missing from the
  file are deleted (with an automatic database backup).
- Music metadata (title, album, artist, rating, cover art) is read from audio
  tags with `mutagen`.
- `--create-html` renders a single static page with lazy-loaded posters.

## Usage

Create and activate a virtual environment, install dependencies, then run the CLI:

- macOS / Linux (bash/zsh):
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
python cli.py --help
```

- Windows (PowerShell):
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python cli.py --help
```

Notes:
- **Python version:** 3.11+
- To deactivate the venv: `deactivate`

Configure the paths and the OMDB key in `.env` (see below). All relative paths
are resolved against the project root, so the CLI works from any directory.

```ini
OMDB_API_KEY=your-key
OMDB_URL=https://www.omdbapi.com/
SITE_FOLDER=personal-site
DB_PATH=personal-site/ratings.db
```

## Commands

```bash
# create the database / apply migrations (never deletes data)
python cli.py --init

# import movie ratings from an IMDb CSV export (add/update only)
python cli.py --import-file data/imdb_ratings.csv

# same, but without network calls
python cli.py --import-file data/imdb_ratings.csv --no-posters

# import music metadata from a library folder
python cli.py --import-music "D:/Music"

# include tracks without a rating as well
python cli.py --import-music "D:/Music" --no-block-no-star-music

# one-time maintenance: move old poster BLOBs to files and fix stored paths
python cli.py --export-posters --dry-run
python cli.py --export-posters

# merge duplicate movies (same title + year), dry run first
python cli.py --dedupe --dry-run
python cli.py --dedupe

# delete poster files no movie references any more
python cli.py --prune-posters --dry-run
python cli.py --prune-posters

# generate the site (50 cards per section by default, 0 = all)
python cli.py --create-html
python cli.py --create-html --top-n 0
```

`--db-path`, `--site-folder` and `--html-path` override `.env` for a single run.

## Keeping the movie list in sync

When you edit the IMDb CSV (remove anime, games, episodes, …), import it with
`--sync`:

```bash
python cli.py --import-file data/imdb_ratings.csv --sync --dry-run   # plan only
python cli.py --import-file data/imdb_ratings.csv --sync             # apply
python cli.py --create-html --top-n 0                                # rebuild the site
```

What `--sync` does:

1. Rows from the CSV are inserted or updated (same logic as a normal import).
2. Movies whose `imdb_const` is **not** in the CSV are deleted.
3. Poster files of the deleted movies are removed if no other row uses them.
4. Before anything is deleted, the database is copied to
   `ratings.db.bak-<timestamp>` next to the original.

Safety rails:

- Without `--sync` nothing is ever deleted — the import stays additive.
- `--dry-run` prints every movie and poster that would be removed.
- A sync that would delete more than 50% of the movie table is refused; pass
  `--force` if that is really intended (protects against a truncated CSV).
- Only the `movies` table is touched. Music, its ratings and cover art are
  never affected.
- Rows without an `imdb_const` are never deleted automatically (they cannot be
  matched reliably).

`--init` is **not** a reset: it only applies migrations. To start from scratch
you would have to remove the database file, which also throws away music and
poster paths — use `--sync` instead.

## How data is stored

- `movies.poster_path` holds a path relative to the site folder, for example
  `images/movies/the-matrix-1999.jpg`. The file itself lives in
  `personal-site/images/movies/`.
- Legacy databases keep the raw image bytes in `movies.poster_blob`; run
  `--export-posters` once to turn them into files.
- Music cover art is resized to a 240 px webp and embedded into the page as a
  data URI, because many tracks share one album image.
- Ratings: movies are 0–10, music is 0–5 stars (the POPM value written by
  MusicBee is mapped to the nearest star value).
- Imports are idempotent: movies are matched by IMDb id and then by
  `title` + `year`, music by `title` + `artist` + `album`.

## Supported services

- Movies — IMDb CSV export (poster lookup through [OMDB](https://www.omdbapi.com/))
- Music files — MP3/FLAC/M4A/WAV/OGG tags (MusicBee POPM ratings, FLAC pictures, MP4 covers)
- Anime/Manga — **TBA** (Shikimori/MAL XML files are collected in `data/`)
- Steam games — **TBA** (Yamtrack CSV and Steam exports are collected in `data/`)

## Features

- [x] CLI
- [x] DB interface (SQLAlchemy 2.0)
- [x] Migrations (Alembic), including a repair path for half-initialized databases
- [x] Import movies from IMDb CSV
- [x] Sync the movie table with an edited CSV (backup + dry-run)
- [x] Download posters to `images/movies`
- [x] Import music metadata and cover art
- [x] Deduplicate movies by title + year
- [x] Clean up orphan poster files
- [x] Export a static HTML site
  - [x] Local poster files and lazy loading
  - [ ] Lazy loading for very large collections
- [ ] Import anime/manga (Shikimori XML/JSON)
- [ ] Import games (Yamtrack CSV, IGDB posters)
- [ ] Export to Markdown / JSON / IMDb CSV
- [ ] Logger, automated tests
