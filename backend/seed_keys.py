import argparse
import getpass
import sys

from key_store import (
    KeyStoreError,
    get_pepper,
    import_access_keys,
    initialize_database,
    load_local_env,
    verify_admin_access_key,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Securely import a fixed access-key list from standard input."
    )
    parser.add_argument("--expected-count", type=int, default=100)
    args = parser.parse_args()

    load_local_env()
    initialize_database()
    get_pepper()
    verify_admin_access_key(getpass.getpass("Admin access key: "))

    imported = import_access_keys(sys.stdin.read().splitlines(), args.expected_count)
    print(f"Imported {imported} access keys. Plaintext keys were not stored in source code.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyStoreError as error:
        print(error.message, file=sys.stderr)
        raise SystemExit(error.status_code)
