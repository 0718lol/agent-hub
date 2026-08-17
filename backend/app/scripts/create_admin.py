"""Create the first local administrator without storing a plaintext password."""

import argparse
import getpass

from app.core.accounts import AccountError, ensure_admin_account
from app.core.database import init_db


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", required=True)
    args = parser.parse_args()
    init_db()
    password = getpass.getpass("Password: ")
    confirmation = getpass.getpass("Confirm password: ")
    if password != confirmation:
        raise SystemExit("Passwords do not match")
    try:
        created = ensure_admin_account(args.username, password)
    except AccountError as exc:
        raise SystemExit(str(exc)) from exc
    print("Administrator created" if created else "Administrator already exists")


if __name__ == "__main__":
    main()
