import contextlib
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

import evaluate as app

ROOT = Path(__file__).resolve().parents[1]


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.rubric = app.read_json(ROOT / "examples/rubric.json")
        self.response = {"model": "jev-test", "usage": {"input_tokens": 10, "output_tokens": 5}, "answers": {
            "clarity": {"type": "score", "score": 3, "confidence": 1, "probabilities": {"0": 0, "1": 0, "2": 0, "3": 1}},
            "actionability": {"type": "score", "score": 1.5, "confidence": 0.4, "probabilities": {"0": 0, "1": 0.5, "2": 0.5, "3": 0}},
        }}

    def test_batch_and_weights(self):
        payload = app.payload_for(ROOT / "examples/document.md", self.rubric)
        self.assertEqual(set(payload["questions"]), {"clarity", "actionability"})
        self.assertNotIn("weight", payload["questions"]["clarity"])
        self.rubric["dimensions"]["clarity"]["weight"] = 3
        report = app.summarize(self.response, self.rubric)
        self.assertEqual(report["composite_percent"], 87.5)
        self.assertTrue(report["needs_review"])

    def test_reject_invalid_rubrics(self):
        for value in [-1, float("nan"), True, "1"]:
            rubric = copy.deepcopy(self.rubric)
            rubric["dimensions"]["clarity"]["weight"] = value
            with self.assertRaises(app.EvaluationError):
                app.validate_rubric(rubric)

    def test_reject_bad_answers(self):
        for value in [float("nan"), True, -1, 4]:
            response = copy.deepcopy(self.response)
            response["answers"]["clarity"]["score"] = value
            with self.assertRaises(app.EvaluationError):
                app.summarize(response, self.rubric)
        del self.response["answers"]["clarity"]
        with self.assertRaises(app.EvaluationError):
            app.summarize(self.response, self.rubric)

    def test_dry_run_needs_no_key_or_network(self):
        with patch.dict("os.environ", {}, clear=True), patch("urllib.request.urlopen") as network, contextlib.redirect_stdout(io.StringIO()) as output:
            code = app.main([str(ROOT / "examples/document.md"), "--rubric", str(ROOT / "examples/rubric.json"), "--dry-run"])
        self.assertEqual(code, 0)
        self.assertEqual(len(json.loads(output.getvalue())["requests"]), 1)
        network.assert_not_called()

    def test_retry_and_authorization(self):
        response = io.BytesIO(json.dumps(self.response).encode())
        error = HTTPError(app.ENDPOINT, 429, "limited", {"Retry-After": "2"}, None)
        with patch("urllib.request.urlopen", side_effect=[error, response]) as network, patch("time.sleep") as sleep:
            result = app.request_evaluation({"state": "test"}, "test-key")
        self.assertEqual(result["model"], "jev-test")
        self.assertEqual(network.call_count, 2)
        self.assertEqual(network.call_args.args[0].get_header("Authorization"), "Bearer test-key")
        sleep.assert_called_once_with(2)

    def test_auth_error_does_not_expose_key(self):
        error = HTTPError(app.ENDPOINT, 401, "secret-key", {}, None)
        with patch("urllib.request.urlopen", side_effect=error), self.assertRaises(app.EvaluationError) as caught:
            app.request_evaluation({}, "secret-key")
        self.assertNotIn("secret-key", str(caught.exception))

    def test_partial_failure_preserves_success(self):
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first.txt"
            second = Path(directory) / "second.txt"
            first.write_text("first")
            second.write_text("second")
            with patch.dict("os.environ", {"TYPESAFE_API_KEY": "test"}), patch.object(app, "request_evaluation", side_effect=[app.EvaluationError("unavailable"), self.response]), contextlib.redirect_stdout(io.StringIO()) as output, contextlib.redirect_stderr(io.StringIO()):
                code = app.main([directory, "--rubric", str(ROOT / "examples/rubric.json")])
            results = json.loads(output.getvalue())["results"]
        self.assertEqual(code, 1)
        self.assertIn("error", results[0])
        self.assertEqual(results[1]["composite_percent"], 75)

    def test_input_limits_and_deduplication(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "doc.txt"
            path.write_text("x" * 30_000)
            self.assertEqual(app.documents([directory, str(path)]), [path.resolve()])
            with self.assertRaises(app.EvaluationError):
                app.payload_for(path, self.rubric)
            path.write_text("")
            with self.assertRaises(app.EvaluationError):
                app.payload_for(path, self.rubric)

    def test_csv_is_parseable(self):
        result = {"document": "a,b.md", **app.summarize(self.response, self.rubric)}
        rows = list(app.csv.DictReader(io.StringIO(app.render({"results": [result]}, "csv"))))
        self.assertEqual(rows[0]["document"], "a,b.md")
        self.assertEqual(len(rows), 2)


if __name__ == "__main__":
    unittest.main()
