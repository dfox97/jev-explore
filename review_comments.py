#!/usr/bin/env python3
"""Review changed Python comments with Jev; reports suggestions, never edits files."""

import argparse
import ast
import difflib
import getpass
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tokenize
from pathlib import Path

from choose import EXAMPLES, make_payload, parse_response, probability
from evaluate import EvaluationError, read_json, request_evaluation

PROTECTED = re.compile(
    r"#!|coding\s*[:=]|copyright|license|SPDX|\bnoqa\b|\bnosec\b|"
    r"\b(?:type|pyright|mypy|ruff|pylint|fmt|isort|pragma|coverage)\s*:|"
    r"\b(?:TODO|FIXME|HACK|XXX)\b",
    re.IGNORECASE,
)
MAX_FILE_BYTES = 1_000_000


def git(repo, *args):
    result = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, check=False
    )
    if result.returncode:
        raise EvaluationError(
            f"Git {args[0]} failed; check the repository and base revision."
        )
    return result.stdout


def decode_source(raw):
    if len(raw) > MAX_FILE_BYTES:
        raise EvaluationError("File exceeds the 1 MB review limit.")
    encoding, _ = tokenize.detect_encoding(io.BytesIO(raw).readline)
    return raw.decode(encoding)


def changed_lines(before, after):
    matcher = difflib.SequenceMatcher(
        a=before.splitlines(), b=after.splitlines(), autojunk=False
    )
    return {
        line
        for tag, _, _, start, end in matcher.get_opcodes()
        if tag in {"insert", "replace"}
        for line in range(start + 1, end + 1)
    }


def extract_comments(source, changed):
    tree = ast.parse(source)
    lines = source.splitlines()
    tokens = [
        token
        for token in tokenize.generate_tokens(io.StringIO(source).readline)
        if token.type == tokenize.COMMENT
    ]
    groups = []
    for token in tokens:
        standalone = not lines[token.start[0] - 1][: token.start[1]].strip()
        if (
            groups
            and standalone
            and groups[-1]["standalone"]
            and token.start[0] == groups[-1]["end_line"] + 1
            and token.start[1] == groups[-1]["column"]
        ):
            groups[-1]["comment"] += "\n" + token.string
            groups[-1]["end_line"] = token.end[0]
        else:
            groups.append(
                {
                    "line": token.start[0],
                    "end_line": token.end[0],
                    "column": token.start[1],
                    "standalone": standalone,
                    "comment": token.string,
                }
            )
    candidates, skipped = [], []
    for group in groups:
        if not changed.intersection(range(group["line"], group["end_line"] + 1)):
            continue
        if PROTECTED.search(group["comment"]):
            skipped.append(
                {**group, "reason": "Protected directive, notice, or tracking comment."}
            )
            continue
        start = max(1, group["line"] - 12)
        end = min(len(lines), group["end_line"] + 12)
        enclosing = [
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            and node.lineno <= group["line"] <= node.end_lineno
        ]
        if enclosing:
            node = min(enclosing, key=lambda n: n.end_lineno - n.lineno)
            start, end = min(start, node.lineno), max(end, node.end_lineno)
        candidates.append(
            {
                **group,
                "context_start_line": start,
                "context_end_line": end,
                "code": "\n".join(
                    f"{i}: {lines[i - 1]}" for i in range(start, end + 1)
                ),
            }
        )
    return candidates, skipped


def snapshots(repo, base, staged):
    root = Path(os.fsdecode(git(repo, "rev-parse", "--show-toplevel")).strip())
    revision = (
        git(root, "rev-parse", "--verify", "--end-of-options", f"{base}^{{commit}}")
        .decode()
        .strip()
    )
    base_paths = set(
        git(root, "ls-tree", "-r", "--name-only", "-z", revision).split(b"\0")
    )
    arguments = ["ls-files", "-z", "--cached"]
    if not staged:
        arguments += ["--others", "--exclude-standard"]
    paths = sorted(set(git(root, *arguments).split(b"\0")))
    for encoded in paths:
        if not encoded.endswith(b".py"):
            continue
        path = os.fsdecode(encoded)
        try:
            if staged:
                entry = git(root, "ls-files", "--stage", "--", path)
                if not entry.startswith(b"100"):
                    continue
                raw = git(root, "show", f":{path}")
            else:
                local = root / path
                if not local.is_file() or local.is_symlink():
                    continue
                if local.stat().st_size > MAX_FILE_BYTES:
                    raise EvaluationError("File exceeds the 1 MB review limit.")
                raw = local.read_bytes()
            old = (
                git(root, "show", f"{revision}:{path}")
                if encoded in base_paths
                else b""
            )
            if raw != old:
                yield path, decode_source(old), decode_source(raw), None
        except (EvaluationError, OSError, UnicodeError, SyntaxError) as exc:
            yield path, "", "", str(exc)


def collect(sources, config, model):
    prepared, skipped, errors = [], [], []
    for path, before, after, error in sources:
        if error:
            errors.append({"path": path, "error": error})
            continue
        try:
            comments, protected = extract_comments(after, changed_lines(before, after))
            skipped.extend({"path": path, **item} for item in protected)
            for comment in comments:
                metadata = {
                    "path": path,
                    **comment,
                    "source_sha256": hashlib.sha256(after.encode()).hexdigest(),
                }
                try:
                    payload = make_payload(config, "comment review", model)
                    payload["state"]["input"] = {**metadata, "policy": config["policy"]}
                    serialized = json.dumps(
                        payload, ensure_ascii=False, sort_keys=True
                    ).encode()
                    if len(serialized) > 28_000:
                        raise EvaluationError(
                            "Comment and context exceed the 28000-byte request budget."
                        )
                    prepared.append(
                        (
                            {
                                **metadata,
                                "request_sha256": hashlib.sha256(
                                    serialized
                                ).hexdigest(),
                            },
                            payload,
                        )
                    )
                except EvaluationError as exc:
                    errors.append(
                        {"path": path, "line": comment["line"], "error": str(exc)}
                    )
        except (SyntaxError, tokenize.TokenError, IndentationError) as exc:
            errors.append({"path": path, "error": f"Cannot parse Python: {exc}"})
    return prepared, skipped, errors


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument(
        "--base", default="HEAD", help="Compare against this commit (default HEAD)"
    )
    parser.add_argument(
        "--staged",
        action="store_true",
        help="Review index contents instead of working files",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Review the bundled sample instead of Git changes",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print requests without a key or network calls",
    )
    parser.add_argument("--prompt-key", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--model", default="jev-latest")
    parser.add_argument("--review-below-confidence", type=probability, default=0.8)
    args = parser.parse_args(argv)
    try:
        if not args.model.strip():
            raise EvaluationError("Model cannot be empty.")
        config = read_json(EXAMPLES / "comment_policy.json")
        sources = (
            [
                (
                    "comments_demo.py",
                    "",
                    (EXAMPLES / "comments_demo.txt").read_text(),
                    None,
                )
            ]
            if args.demo
            else snapshots(args.repo, args.base, args.staged)
        )
        prepared, skipped, errors = collect(sources, config, args.model)
        report = {
            "results": [],
            "skipped": skipped,
            "errors": errors,
            "review_below_confidence": args.review_below_confidence,
            "applicability_threshold": 0.8,
        }
        if args.dry_run:
            report["requests"] = [payload for _, payload in prepared]
        elif prepared:
            key = (
                getpass.getpass("TypeSafe API key (not saved): ")
                if args.prompt_key
                else os.environ.get("TYPESAFE_API_KEY", "")
            )
            if not key.strip():
                raise EvaluationError(
                    "Set TYPESAFE_API_KEY or use --prompt-key; --dry-run needs no key."
                )
            for metadata, payload in prepared:
                try:
                    result = parse_response(
                        request_evaluation(payload, key.strip()),
                        config,
                        args.review_below_confidence,
                    )
                    report["results"].append({**metadata, **result})
                except EvaluationError as exc:
                    errors.append(
                        {
                            "path": metadata["path"],
                            "line": metadata["line"],
                            "error": str(exc),
                        }
                    )
        if args.json or args.dry_run:
            print(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False))
        else:
            for result in report["results"]:
                decision = "review" if result["needs_review"] else result["choice"]
                print(
                    f"{result['path']}:{result['line']}: {decision} (Jev: {result['choice']}, confidence {result['confidence']:.0%})"
                )
            print(
                f"{len(report['results'])} reviewed; {len(skipped)} protected; {len(errors)} errors. No files changed."
            )
            for error in errors:
                print(f"{error['path']}: {error['error']}", file=sys.stderr)
        return 1 if errors else 0
    except (EvaluationError, OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
