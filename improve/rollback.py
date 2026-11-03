"""Switch a stage back to an earlier prompt version (e.g. if a new rule made things worse).
   python -m improve.rollback --list
   python -m improve.rollback verifier verifier_v1"""
import json
import sys

from root import versions


def main(argv: list[str]) -> None:
    if not argv or argv[0] == "--list":
        print(json.dumps({"active": versions.active(), "available": versions.list_versions()}, indent=1))
        return
    if len(argv) != 2 or argv[0] not in ("splitter", "verifier") or argv[1] not in versions.list_versions()[argv[0]]:
        sys.exit("Unknown stage or version. Run with --list to see what exists.")
    versions.set_active(argv[0], argv[1])
    print(f"{argv[0]} is now {argv[1]}. Re-run the eval to score it.")


if __name__ == "__main__":
    main(sys.argv[1:])
