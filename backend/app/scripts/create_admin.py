"""Create the first local administrator without storing a plaintext password."""

import argparse
import getpass

from app.core.accounts import create_account, get_account_by_username
from app.core.database import init_db


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", required=True)
    args = parser.parse_args()
    init_db()
    if get_account_by_username(args.username):
        print("Administrator already exists")
        return
    password = getpass.getpass("Password: ")
    confirmation = getpass.getpass("Confirm password: ")
    if password != confirmation:
        raise SystemExit("Passwords do not match")
    create_account(args.username, password, is_admin=True)
    print("Administrator created")


if __name__ == "__main__":
    main()
