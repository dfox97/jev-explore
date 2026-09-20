import contextlib
import copy
import io
import json
import unittest
from unittest.mock import patch

import choose


class ChoiceTests(unittest.TestCase):
    def setUp(self):
        self.config = choose.read_json(choose.EXAMPLES / "feedback.json")
        self.response = {
            "model": "jev-test",
            "usage": {},
            "answers": {
                "decision": {
                    "type": "choice",
                    "choice": "bug_report",
                    "confidence": 0.9,
                    "probabilities": {
                        "bug_report": 0.94,
                        "feature_request": 0.04,
                        "praise": 0.02,
                    },
                },
                "applicable": {"type": "noul", "noul": 0.99},
            },
        }

    def test_both_examples_have_three_choices_and_independent_scope_check(self):
        for example in ["feedback", "game"]:
            config = choose.read_json(choose.EXAMPLES / f"{example}.json")
            for sample in config["samples"]:
                payload = choose.make_payload(config, sample)
                self.assertEqual(payload["state"]["input"], sample)
                self.assertEqual(len(payload["questions"]["decision"]["criteria"]), 3)
                self.assertEqual(payload["questions"]["applicable"]["type"], "noul")

    def test_out_of_scope_and_uncertainty_require_review(self):
        self.assertFalse(
            choose.parse_response(self.response, self.config, 0.5)["needs_review"]
        )
        self.response["answers"]["applicable"]["noul"] = 0.1
        result = choose.parse_response(self.response, self.config, 0.5)
        self.assertTrue(result["needs_review"])
        self.assertIn("Provisional choice", choose.display(result))
        self.response["answers"]["applicable"]["noul"] = 0.99
        self.response["answers"]["decision"]["confidence"] = 0.3
        self.assertTrue(
            choose.parse_response(self.response, self.config, 0.5)["needs_review"]
        )

    def test_rejects_invalid_answers(self):
        for key, value in [
            ("choice", []),
            ("choice", "other"),
            ("choice", "praise"),
            ("confidence", float("nan")),
            ("probabilities", {"bug_report": 1}),
            ("probabilities", {"bug_report": True, "feature_request": 0, "praise": 0}),
        ]:
            response = copy.deepcopy(self.response)
            response["answers"]["decision"][key] = value
            with self.assertRaises(choose.EvaluationError):
                choose.parse_response(response, self.config, 0.5)
        del self.response["answers"]["applicable"]
        with self.assertRaises(choose.EvaluationError):
            choose.parse_response(self.response, self.config, 0.5)

    def test_empty_and_oversize_inputs(self):
        for text in [" ", "\x00", "x" * 28_000]:
            with self.assertRaises(choose.EvaluationError):
                choose.make_payload(self.config, text)

    def test_dry_run_and_samples_never_use_key_or_network(self):
        for example in ["feedback", "game"]:
            with (
                patch.dict("os.environ", {}, clear=True),
                patch.object(choose, "request_evaluation") as request,
                patch("getpass.getpass") as prompt,
                contextlib.redirect_stdout(io.StringIO()) as output,
            ):
                self.assertEqual(
                    choose.main(
                        [example, "--sample", "1", "--dry-run", "--prompt-key"]
                    ),
                    0,
                )
                json.loads(output.getvalue())
                request.assert_not_called()
                prompt.assert_not_called()
            with (
                patch.object(choose, "request_evaluation") as request,
                contextlib.redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(choose.main([example, "--list-samples"]), 0)
                request.assert_not_called()

    def test_cli_json_with_mocked_service(self):
        with (
            patch.dict("os.environ", {"TYPESAFE_API_KEY": "test-key"}),
            patch.object(
                choose, "request_evaluation", return_value=self.response
            ) as request,
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            self.assertEqual(
                choose.main(["feedback", "--text", "Export crashes", "--json"]), 0
            )
        result = json.loads(output.getvalue())
        self.assertEqual(result["choice"], "bug_report")
        self.assertEqual(request.call_args.args[0]["state"]["input"], "Export crashes")
        self.assertNotIn("test-key", output.getvalue())

    def test_missing_key_and_api_errors(self):
        with (
            patch.dict("os.environ", {}, clear=True),
            contextlib.redirect_stderr(io.StringIO()) as error,
        ):
            self.assertEqual(choose.main(["feedback", "--sample", "1"]), 2)
            self.assertIn("TYPESAFE_API_KEY", error.getvalue())
        with (
            patch.dict("os.environ", {"TYPESAFE_API_KEY": "test"}),
            patch.object(
                choose,
                "request_evaluation",
                side_effect=choose.EvaluationError("Unavailable"),
            ),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            self.assertEqual(choose.main(["game", "--sample", "1"]), 2)

    def test_piped_input(self):
        with (
            patch("sys.stdin", io.StringIO("Please add dark mode\n")),
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            self.assertEqual(choose.main(["feedback", "--dry-run"]), 0)
        self.assertEqual(
            json.loads(output.getvalue())["request"]["state"]["input"],
            "Please add dark mode",
        )


if __name__ == "__main__":
    unittest.main()
