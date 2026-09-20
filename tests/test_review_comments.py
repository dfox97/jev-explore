import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import review_comments as review


class CommentReviewTests(unittest.TestCase):
    def test_token_comments_only_and_protected_blocks(self):
        source = (
            '"""A docstring # not a comment."""\n'
            'value = "# not a comment"\n'
            "# Useful context\n# More context\nvalue += 1  # Inline comment\n"
            "# noqa: E501\n# Explanation of directive\nvalue = 2\n"
        )
        comments, skipped = review.extract_comments(source, set(range(1, 9)))
        self.assertEqual(len(comments), 2)
        self.assertEqual(comments[0]["end_line"], 4)
        self.assertEqual(comments[1]["comment"], "# Inline comment")
        self.assertEqual(len(skipped), 1)

    def test_deleted_and_unchanged_comments_not_reviewed(self):
        before = "# Remove from source\nx = 1\n# Unchanged\ny = 2\n"
        after = "x = 1\n# Unchanged\ny = 2\n"
        comments, _ = review.extract_comments(
            after, review.changed_lines(before, after)
        )
        self.assertEqual(comments, [])

    def test_full_enclosing_function_context(self):
        source = (
            "def large():\n"
            + "    value = 1\n" * 30
            + "    # Explain this\n    return value\n"
        )
        comments, _ = review.extract_comments(source, {32})
        self.assertIn("1: def large():", comments[0]["code"])
        self.assertIn("33:     return value", comments[0]["code"])

    def test_demo_dry_run_no_network_or_key(self):
        with (
            patch.object(review, "request_evaluation") as request,
            patch("getpass.getpass") as key,
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            self.assertEqual(review.main(["--demo", "--dry-run", "--prompt-key"]), 0)
        report = json.loads(output.getvalue())
        self.assertEqual(len(report["requests"]), 3)
        self.assertEqual(len(report["skipped"]), 2)
        self.assertIsInstance(report["requests"][0]["state"]["input"], dict)
        request.assert_not_called()
        key.assert_not_called()

    def test_parse_failures_reported_not_silently_passed(self):
        config = review.read_json(review.EXAMPLES / "comment_policy.json")
        prepared, _, errors = review.collect(
            [("bad.py", "", "def broken(\n", None)], config, "jev-latest"
        )
        self.assertFalse(prepared)
        self.assertEqual(len(errors), 1)

    def test_source_hash_changes_with_context(self):
        config = review.read_json(review.EXAMPLES / "comment_policy.json")
        first, _, _ = review.collect(
            [("x.py", "", "# reason\nx = 1\n", None)], config, "jev-latest"
        )
        second, _, _ = review.collect(
            [("x.py", "", "# reason\nx = 2\n", None)], config, "jev-latest"
        )
        self.assertNotEqual(
            first[0][0]["request_sha256"], second[0][0]["request_sha256"]
        )

    def test_mock_decision_and_no_edits(self):
        response = {
            "answers": {
                "decision": {
                    "type": "choice",
                    "choice": "remove",
                    "confidence": 0.95,
                    "probabilities": {"keep": 0.01, "shorten": 0.02, "remove": 0.97},
                },
                "applicable": {"type": "noul", "noul": 0.99},
            },
            "model": "jev-test",
        }
        before = (review.EXAMPLES / "comments_demo.txt").read_bytes()
        with (
            patch.dict("os.environ", {"TYPESAFE_API_KEY": "test"}),
            patch.object(review, "request_evaluation", return_value=response),
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            self.assertEqual(review.main(["--demo", "--json"]), 0)
        self.assertEqual(
            json.loads(output.getvalue())["results"][0]["choice"], "remove"
        )
        self.assertEqual(before, (review.EXAMPLES / "comments_demo.txt").read_bytes())

    def test_git_worktree_index_untracked_and_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)

            def git(*args):
                subprocess.run(
                    ["git", "-C", directory, *args], check=True, capture_output=True
                )

            git("init")
            (repo / ".gitignore").write_text("ignored.py\n")
            path = repo / "space name.py"
            path.write_text("# Original\nx = 1\n")
            git("add", ".")
            git(
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@example.com",
                "commit",
                "-m",
                "base",
            )
            path.write_text("# Staged\nx = 1\n")
            git("add", ".")
            path.write_text("# Working\nx = 1\n")
            (repo / "new.py").write_text("# New\nx = 2\n")
            (repo / "ignored.py").write_text("# Ignored\nx = 3\n")
            (repo / "linked.py").symlink_to(path)
            working = {
                p: after for p, _, after, _ in review.snapshots(repo, "HEAD", False)
            }
            staged = {
                p: after for p, _, after, _ in review.snapshots(repo, "HEAD", True)
            }
            self.assertEqual(set(working), {"space name.py", "new.py"})
            self.assertIn("# Working", working["space name.py"])
            self.assertEqual(set(staged), {"space name.py"})
            self.assertIn("# Staged", staged["space name.py"])


if __name__ == "__main__":
    unittest.main()
