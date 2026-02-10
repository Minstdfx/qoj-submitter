import argparse
import pathlib
import sys
import time
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
    parser.add_argument("-c", "--contest", default="", help="Contest id")
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
        print(
            "Submission information:\n"
            f"    filename: {filename}\n"
            f"    filesize: {args.filesize}\n"
            f"    contest: {contest}\n"
            f"    problem: {problem}\n"
            "    language: C++"
        )
        return
    prompt = (
        "Submission information:\n"
        f"    filename: {filename}\n"
        f"    filesize: {args.filesize}\n"
        f"    contest: {contest}\n"
        f"    problem: {problem}\n"
        "    language: C++\n"
        "Do you want to continue?[y/N]: "
    )
    resp = input(prompt).strip().lower()
    if resp != "y":
        print("aborted by user")
        sys.exit(3)


def wait_submission_result(base_url: str, request_id: str, total_timeout: float = 60.0) -> Tuple[str, str, str]:
    start = time.time()
    while time.time() - start < total_timeout:
        try:
            resp = requests.get(f"{base_url}/submission-result/{request_id}", params={"timeout": 10}, timeout=12)
        except requests.RequestException:
            time.sleep(1)
            continue
        if resp.status_code != 200:
            time.sleep(1)
            continue
        data = resp.json()
        if data.get("status") == "done":
            return data.get("sid", ""), data.get("stime", ""), data.get("surl", "")
        if data.get("status") == "unknown":
            break
        time.sleep(1)
    return "", "", ""


def main() -> None:
    args = parse_args()
    filename, payload = load_file(args.file)
    args.filesize = len(payload)
    problem = resolve_problem(args, filename)
    contest_id = args.contest
    confirm_or_abort(args, contest_id, problem, filename)
    base_url = args.server.rstrip('/')
    url = f"{base_url}/submit"
    data = {
        "problem_code": problem,
        "language": args.lang,
    }
    files = {"file": (filename, payload, "text/plain")}
    resp = requests.post(url, data=data, files=files, timeout=10)
    if resp.status_code != 200:
        print(f"server error: {resp.status_code} {resp.text}", file=sys.stderr)
        sys.exit(2)
    resp_data = resp.json()
    request_id = resp_data.get("request_id")
    sid, stime, surl = ("", "", "")
    if request_id:
        sid, stime, surl = wait_submission_result(base_url, request_id)
    if sid and stime and surl:
        print(f"Submission received: id = {sid}, time = {stime}")
        print(f"Check https://qoj.ac{surl} for the result.")
    else:
        print("Submission queued. Result not received.")


if __name__ == "__main__":
    main()
