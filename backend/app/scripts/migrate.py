"""Run the complete database migration and seed step once."""

from app.core.database import init_db


def main() -> int:
    init_db()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
