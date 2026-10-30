from lib.config import Config
from lib.create_html import main as create_html


def main(config: Config, top_n: int = 50) -> int:
    try:
        report = create_html(str(config.html_path), str(config.db_path), top_n)
    except Exception as exc:
        print(f"HTML generation failed: {exc}")
        return 1

    print(
        f"HTML written: {report['path']} "
        f"({report['movies']} movies, {report['music']} music, {report['bytes']} bytes)"
    )
    return 0
