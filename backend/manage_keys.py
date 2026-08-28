import argparse
import getpass
import sys

from key_store import (
    KeyStoreError,
    generate_access_keys,
    get_pepper,
    initialize_database,
    key_counts,
    load_local_env,
    release_access_key,
    verify_admin_access_key,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Royal BetKing access-key administration")
    subparsers = parser.add_subparsers(dest="command", required=True)
    generate_parser = subparsers.add_parser("generate", help="Create one-time 9-digit access keys")
    generate_parser.add_argument("--count", type=int, default=100)
    release_parser = subparsers.add_parser("release", help="Allow a key to be activated on a new device")
    release_parser.add_argument("--key", required=True)
    subparsers.add_parser("status", help="Show key counts without exposing keys")
    args = parser.parse_args()

    load_local_env()
    initialize_database()
    get_pepper()
    verify_admin_access_key(getpass.getpass("Admin access key: "))

    if args.command == "generate":
        for label, access_key in generate_access_keys(args.count):
            print(f"{label}: {access_key}")
        return 0

    if args.command == "release":
        if release_access_key(args.key):
            print("Key released. It can now be activated on one new device.")
            return 0
        print("Key not found.")
        return 1

    print(key_counts())
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyStoreError as error:
        print(error.message, file=sys.stderr)
        raise SystemExit(error.status_code)
