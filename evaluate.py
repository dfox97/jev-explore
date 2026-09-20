#!/usr/bin/env python3
"""Evaluate documents using TypeSafe's HTTP API; Python 3.10+, no dependencies."""

import argparse
import csv
import getpass
import hashlib
import io
import json
import math
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ENDPOINT = "https://api.typesafe.ai/v1/systemone"
SUPPORTED = {".txt", ".md", ".markdown"}


class EvaluationError(Exception):
    pass


def number(value, low, high):
    return type(value) in (int, float) and math.isfinite(value) and low <= value <= high


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def validate_rubric(rubric):
    if not isinstance(rubric, dict):
        raise EvaluationError("Rubric must be a JSON object.")
    dimensions = rubric.get("dimensions")
    if not isinstance(dimensions, dict) or not dimensions:
        raise EvaluationError("Rubric needs a nonempty dimensions object.")
    if (
        not isinstance(rubric.get("model", "jev-latest"), str)
        or not rubric.get("model", "jev-latest").strip()
    ):
        raise EvaluationError("model must be a nonempty string.")
    if not number(rubric.get("review_below_confidence", 0.5), 0, 1):
        raise EvaluationError("review_below_confidence must be between 0 and 1.")
    for name, dimension in dimensions.items():
        if not name.strip() or not isinstance(dimension, dict):
            raise EvaluationError("Each dimension needs a name and an object.")
        levels = dimension.get("levels")
        if (
            not isinstance(levels, list)
            or not 2 <= len(levels) <= 10
            or not all(isinstance(x, str) and x.strip() for x in levels)
        ):
            raise EvaluationError(
                f"{name}: supply 2–10 nonempty level descriptions, ordered worst to best."
            )
        if (
            not isinstance(dimension.get("instructions"), str)
            or not dimension["instructions"].strip()
        ):
            raise EvaluationError(f"{name}: instructions are required.")
        if not number(dimension.get("weight", 1), 0, 1e6):
            raise EvaluationError(
                f"{name}: weight must be finite and between 0 and 1000000."
            )
    if sum(d.get("weight", 1) for d in dimensions.values()) == 0:
        raise EvaluationError("At least one dimension must have a positive weight.")
    return rubric


def documents(inputs):
    found = []
    for value in inputs:
        path = Path(value)
        if path.is_dir():
            found.extend(
                sorted(
                    p
                    for p in path.rglob("*")
                    if p.is_file() and p.suffix.lower() in SUPPORTED
                )
            )
        elif path.is_file() and path.suffix.lower() in SUPPORTED:
            found.append(path)
        else:
            raise EvaluationError(
                f"Not a supported document or directory: {path}. Use .txt or .md files."
            )
    unique = list(dict.fromkeys(p.resolve() for p in found))
    if not unique:
        raise EvaluationError("No supported documents found.")
    return unique


def payload_for(path, rubric):
    if path.stat().st_size > 1_000_000:
        raise EvaluationError(
            f"{path.name}: file exceeds the 1 MB input limit; split it explicitly."
        )
    content = path.read_text(encoding="utf-8")
    if not content.strip() or "\x00" in content:
        raise EvaluationError(f"{path.name}: expected nonempty UTF-8 text.")
    payload = {
        "model": rubric.get("model", "jev-latest"),
        "state": {
            "document": {"name": path.name, "text": content},
            "context": rubric.get("context", ""),
        },
        "questions": {
            name: {
                "type": "score",
                "instructions": d["instructions"],
                "criteria": d["levels"],
            }
            for name, d in rubric["dimensions"].items()
        },
    }
    # A conservative byte budget, not an exact tokenizer. Never silently truncate.
    if len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) > 28_000:
        raise EvaluationError(
            f"{path.name}: request exceeds the conservative 28000-byte budget; split the document or shorten the rubric."
        )
    return payload


def request_evaluation(payload, key, timeout=60):
    request = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            status = exc.code
            retry_after = exc.headers.get("Retry-After", "") if exc.headers else ""
            exc.close()
            if status in (429, 500, 502, 503, 504, 529) and attempt < 2:
                delay = float(retry_after) if retry_after.isdigit() else 2**attempt
                if delay > 60:
                    raise EvaluationError(
                        f"TypeSafe HTTP {status}: retry after {delay:g} seconds."
                    ) from None
                time.sleep(delay)
                continue
            hint = (
                "Check TYPESAFE_API_KEY (an OpenRouter key is not a TypeSafe key)."
                if status in (401, 403)
                else "Check the request, model, quota, and TypeSafe service status."
            )
            raise EvaluationError(f"TypeSafe HTTP {status}. {hint}") from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise EvaluationError(
                "TypeSafe connection failed or timed out; check your network and retry."
            ) from None
        except (ValueError, UnicodeError):
            raise EvaluationError("TypeSafe returned invalid JSON.") from None


def summarize(response, rubric):
    if not isinstance(response, dict) or not isinstance(response.get("answers"), dict):
        raise EvaluationError("TypeSafe response is missing answers.")
    dimensions = {}
    weighted = total_weight = 0
    review = False
    for name, d in rubric["dimensions"].items():
        answer = response["answers"].get(name)
        maximum = len(d["levels"]) - 1
        if (
            not isinstance(answer, dict)
            or answer.get("type") != "score"
            or not number(answer.get("score"), 0, maximum)
            or not number(answer.get("confidence"), 0, 1)
        ):
            raise EvaluationError(f"Invalid or missing score answer for {name}.")
        probabilities = answer.get("probabilities")
        if (
            not isinstance(probabilities, dict)
            or set(probabilities) != {str(i) for i in range(maximum + 1)}
            or not all(number(p, 0, 1) for p in probabilities.values())
            or not math.isclose(sum(probabilities.values()), 1, abs_tol=0.02)
        ):
            raise EvaluationError(f"Invalid probability distribution for {name}.")
        normalized = 100 * answer["score"] / maximum
        needs_review = answer["confidence"] < rubric.get("review_below_confidence", 0.5)
        dimensions[name] = {
            **answer,
            "score_percent": normalized,
            "weight": d.get("weight", 1),
            "needs_review": needs_review,
        }
        weighted += normalized * d.get("weight", 1)
        total_weight += d.get("weight", 1)
        review |= needs_review
    return {
        "model": response.get("model"),
        "usage": response.get("usage"),
        "dimensions": dimensions,
        "composite_percent": weighted / total_weight,
        "needs_review": review,
    }


def render(report, format):
    if format == "json":
        return json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "document",
            "dimension",
            "score_percent",
            "confidence",
            "composite_percent",
            "needs_review",
            "error",
        ]
    )
    for result in report["results"]:
        if "error" in result:
            writer.writerow([result["document"], "", "", "", "", "", result["error"]])
        else:
            for name, d in result["dimensions"].items():
                writer.writerow(
                    [
                        result["document"],
                        name,
                        d["score_percent"],
                        d["confidence"],
                        result["composite_percent"],
                        d["needs_review"],
                        "",
                    ]
                )
    return output.getvalue()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "documents", nargs="+", help="UTF-8 .txt/.md files or directories (recursive)"
    )
    parser.add_argument(
        "--rubric", required=True, help="JSON rubric with dimensions and ordered levels"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print exact request bodies without API calls or keys",
    )
    parser.add_argument(
        "--prompt-key",
        action="store_true",
        help="Prompt for a hidden TypeSafe key; never save it",
    )
    parser.add_argument("--format", choices=["json", "csv"], default="json")
    parser.add_argument(
        "--output", type=Path, help="Write a new report file (refuses to overwrite)"
    )
    args = parser.parse_args(argv)
    try:
        rubric = validate_rubric(read_json(args.rubric))
        paths = documents(args.documents)
        if args.output and args.output.exists():
            raise EvaluationError(f"Output already exists: {args.output}")
        # Validate all inputs before making any billable requests.
        prepared = [(p, payload_for(p, rubric)) for p in paths]
        if args.dry_run:
            text = (
                json.dumps(
                    {"endpoint": ENDPOINT, "requests": [p for _, p in prepared]},
                    indent=2,
                    ensure_ascii=False,
                )
                + "\n"
            )
            failed = False
        else:
            key = (
                getpass.getpass("TypeSafe API key (not saved): ")
                if args.prompt_key
                else os.environ.get("TYPESAFE_API_KEY", "")
            )
            if not key.strip():
                raise EvaluationError(
                    "Set TYPESAFE_API_KEY or use --prompt-key. Use --dry-run without a key."
                )
            results = []
            for path, payload in prepared:
                print(f"Evaluating {path.name}…", file=sys.stderr)
                result = {
                    "document": str(path),
                    "sha256": hashlib.sha256(
                        payload["state"]["document"]["text"].encode()
                    ).hexdigest(),
                }
                try:
                    result.update(
                        summarize(request_evaluation(payload, key.strip()), rubric)
                    )
                except EvaluationError as exc:
                    result["error"] = str(exc)
                results.append(result)
            failed = any("error" in r for r in results)
            text = render({"rubric": rubric, "results": results}, args.format)
        if args.output:
            with args.output.open("x", encoding="utf-8", newline="") as output:
                output.write(text)
        else:
            sys.stdout.write(text)
        return 1 if failed else 0
    except (EvaluationError, OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
