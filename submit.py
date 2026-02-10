import argparse
import pathlib
import sys
from typing import Tuple

import requests


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send a code file to the submit bridge")
    parser.add_argument("file", type=pathlib.Path, help="Path to the source file")
    parser.add_argument(
        "-p",
        "--problem",
        help="Problem code (e.g. A). If omitted, derived from filename stem (must be single letter).",
    )
    parser.add_argument("--lang", default="cpp17", help="Language key expected by QOJ")
    parser.add_argument(
        "--server", default="http://127.0.0.1:8000", help="Submit bridge base URL"
    )
    parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Skip confirmation prompt and submit immediately",
    )
    return parser.parse_args()


def load_file(path: pathlib.Path) -> Tuple[str, bytes]:
    if not path.exists():
        print(f"file not found: {path}", file=sys.stderr)
        sys.exit(1)
    return path.name, path.read_bytes()


def resolve_problem(args: argparse.Namespace, filename: str) -> str:
    if args.problem:
        return args.problem
    stem = pathlib.Path(filename).stem
    if len(stem) == 1 and stem.isalpha():
        return stem.upper()
    print("problem code not provided and could not infer a single-letter code from filename", file=sys.stderr)
    sys.exit(1)


def confirm_or_abort(args: argparse.Namespace, contest: str, problem: str, filename: str) -> None:
    if args.yes:
        return
    prompt = f"Submit {filename} to problem {problem}? [y/N]: "
    resp = input(prompt).strip().lower()
    if resp != "y":
        print("aborted by user")
        sys.exit(3)


def main() -> None:
    args = parse_args()
    filename, payload = load_file(args.file)
    problem = resolve_problem(args, filename)
    confirm_or_abort(args, "", problem, filename)
    url = f"{args.server.rstrip('/')}/submit"
    data = {
        "problem_code": problem,
        "language": args.lang,
    }
    files = {"file": (filename, payload, "text/plain")}
    resp = requests.post(url, data=data, files=files, timeout=10)
    if resp.status_code != 200:
        print(f"server error: {resp.status_code} {resp.text}", file=sys.stderr)
        sys.exit(2)
    print(resp.json())


if __name__ == "__main__":
    main()
