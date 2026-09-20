#!/usr/bin/env python3
"""Three-option TypeSafe examples: feedback sorting and game action selection."""
import argparse
import getpass
import json
import math
import os
from pathlib import Path
import sys

from evaluate import ENDPOINT, EvaluationError, number, read_json, request_evaluation

EXAMPLES = Path(__file__).resolve().parent / "examples"


def make_payload(config, text, model="jev-latest"):
    if not text.strip() or "\x00" in text:
        raise EvaluationError("Supply nonempty text without NUL characters.")
    payload = {"model": model, "state": {"input": text}, "questions": {
        "decision": {"type": "choice", "instructions": config["instructions"], "criteria": config["criteria"]},
        "applicable": {"type": "noul", "instructions": config["applicable"]},
    }}
    if len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) > 28_000:
        raise EvaluationError("Input exceeds the conservative 28000-byte request budget; shorten it.")
    return payload


def parse_response(response, config, threshold):
    if not isinstance(response, dict) or not isinstance(response.get("answers"), dict):
        raise EvaluationError("TypeSafe response is missing answers.")
    answer = response["answers"].get("decision")
    applicable = response["answers"].get("applicable")
    options = config["criteria"]
    if (not isinstance(answer, dict) or answer.get("type") != "choice"
            or not isinstance(answer.get("choice"), str) or answer["choice"] not in options
            or not number(answer.get("confidence"), 0, 1)):
        raise EvaluationError("TypeSafe returned an invalid choice answer.")
    probabilities = answer.get("probabilities")
    if (not isinstance(probabilities, dict) or set(probabilities) != set(options)
            or not all(number(p, 0, 1) for p in probabilities.values())
            or not math.isclose(sum(probabilities.values()), 1, abs_tol=0.02)
            or probabilities[answer["choice"]] < max(probabilities.values()) - 1e-6):
        raise EvaluationError("TypeSafe returned an invalid choice distribution.")
    if not isinstance(applicable, dict) or applicable.get("type") != "noul" or not number(applicable.get("noul"), 0, 1):
        raise EvaluationError("TypeSafe returned an invalid applicability answer.")
    reasons = []
    if applicable["noul"] < 0.8:
        reasons.append("Input may be outside this example's scope or missing necessary facts.")
    if answer["confidence"] < threshold:
        reasons.append("The choice confidence is below the review threshold.")
    return {"model": response.get("model"), "usage": response.get("usage"),
            "choice": answer["choice"], "probabilities": probabilities, "confidence": answer["confidence"],
            "applicable_probability": applicable["noul"], "needs_review": bool(reasons), "review_reasons": reasons}


def display(result):
    label = "Provisional choice" if result["needs_review"] else "Choice"
    lines = [f"{label}: {result['choice'].replace('_', ' ').title()}", f"Confidence: {result['confidence']:.1%}", "Probabilities:"]
    for name, probability in result["probabilities"].items():
        lines.append(f"  {name.replace('_', ' ').title():18} {probability:6.1%}")
    lines.append(f"Input fits example: {result['applicable_probability']:.1%}")
    for reason in result["review_reasons"]:
        lines.append(f"Review: {reason}")
    return "\n".join(lines)


def probability(value):
    try:
        parsed = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError("Expected a number from 0 to 1.") from None
    if not number(parsed, 0, 1):
        raise argparse.ArgumentTypeError("Expected a finite number from 0 to 1.")
    return parsed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("example", choices=["feedback", "game"])
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--text", help="Feedback or a game situation; prompts if omitted")
    source.add_argument("--sample", type=int, choices=[1, 2, 3], help="Use a built-in sample")
    parser.add_argument("--list-samples", action="store_true", help="Print sample inputs without API calls")
    parser.add_argument("--dry-run", action="store_true", help="Print the request without using a key")
    parser.add_argument("--prompt-key", action="store_true", help="Enter a hidden TypeSafe key without saving it")
    parser.add_argument("--json", action="store_true", help="Print structured results")
    parser.add_argument("--model", default="jev-latest")
    parser.add_argument("--review-below-confidence", type=probability, default=0.5)
    args = parser.parse_args(argv)
    try:
        config = read_json(EXAMPLES / f"{args.example}.json")
        if args.list_samples:
            for index, sample in enumerate(config["samples"], 1):
                print(f"{index}. {sample}")
            return 0
        if not args.model.strip():
            raise EvaluationError("Model cannot be empty.")
        text = config["samples"][args.sample - 1] if args.sample else args.text
        if text is None:
            if sys.stdin.isatty():
                print(f"{config['title']} — enter your input: ", end="", file=sys.stderr, flush=True)
            text = sys.stdin.readline(28_001).rstrip("\n")
        payload = make_payload(config, text, args.model)
        if args.dry_run:
            print(json.dumps({"endpoint": ENDPOINT, "request": payload}, indent=2, ensure_ascii=False))
            return 0
        key = getpass.getpass("TypeSafe API key (not saved): ") if args.prompt_key else os.environ.get("TYPESAFE_API_KEY", "")
        if not key.strip():
            raise EvaluationError("Set TYPESAFE_API_KEY or use --prompt-key. Use --dry-run without a key.")
        result = parse_response(request_evaluation(payload, key.strip()), config, args.review_below_confidence)
        result.update({"example": args.example, "input": text, "review_below_confidence": args.review_below_confidence, "applicability_threshold": 0.8})
        print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) if args.json else display(result))
        return 0
    except (EvaluationError, OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\nCancelled.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
