import argparse
import pathlib
import sys
import time
from typing import Dict, Optional, Tuple

import requests


LANGUAGE_NAME_MAP: Dict[str, str] = {
    "c++": "C++26",
    "cpp": "C++26",
    "c": "C11",
    "java": "Java21",
    "jvav": "Java21",
    "python": "PyPy3",
    "pypy": "PyPy3",
    "py": "PyPy3",
    "kotlin": "Kotlin",
    "rust": "Rust",
}

EXTENSION_MAP: Dict[str, str] = {
    ".cpp": "C++26",
    ".cc": "C++26",
    ".c": "C11",
    ".java": "Java21",
    ".py": "PyPy3",
    ".kt": "Kotlin",
    ".kts": "Kotlin",
    ".rs": "Rust",
}

DEFAULT_LANGUAGE = "C++26"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send a code file to the submit bridge")
    parser.add_argument("file", type=pathlib.Path, help="Path to the source file")
    parser.add_argument(
        "-p",
        "--problem",
        help="Problem code (e.g. A). If omitted, derived from filename stem (must be single letter).",
    )
    parser.add_argument("-c", "--contest", default="", help="Contest id")
    parser.add_argument(
        "--lang",
        default=None,
        help=(
            "Language to submit. If omitted, infer from file extension. "
            "Supported: C++/cpp/c++ -> C++26; C/c -> C11; Java/java/jvav -> Java21; "
            "Python/python/pypy -> PyPy3; Kotlin/kotlin -> Kotlin; Rust/rust -> Rust."
        ),
    )
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


def resolve_language(lang_arg: Optional[str], path: pathlib.Path) -> str:
    if lang_arg:
        key = lang_arg.strip().lower()
        if key in LANGUAGE_NAME_MAP:
            return LANGUAGE_NAME_MAP[key]
        print(f"unrecognized language '{lang_arg}', defaulting to {DEFAULT_LANGUAGE}", file=sys.stderr)
    ext = path.suffix.lower()
    if ext in EXTENSION_MAP:
        return EXTENSION_MAP[ext]
    return DEFAULT_LANGUAGE


def confirm_or_abort(args: argparse.Namespace, contest: str, problem: str, filename: str, language: str) -> None:
    if args.yes:
        print(
            "Submission information:\n"
            f"    filename: {filename}\n"
            f"    filesize: {args.filesize}\n"
            f"    contest: {contest}\n"
            f"    problem: {problem}\n"
            f"    language: {language}"
        )
        return
    prompt = (
        "Submission information:\n"
        f"    filename: {filename}\n"
        f"    filesize: {args.filesize}\n"
        f"    contest: {contest}\n"
        f"    problem: {problem}\n"
        f"    language: {language}\n"
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
    language = resolve_language(args.lang, args.file)
    confirm_or_abort(args, contest_id, problem, filename, language)
    base_url = args.server.rstrip('/')
    url = f"{base_url}/submit"
    data = {
        "problem_code": problem,
        "language": language,
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
