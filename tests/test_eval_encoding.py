"""Regression tests for the Windows agent-browser eval encoding fix.

Two stacked bugs in scripts/acquire_url.py acquisition:
  1. JS passed as a raw CLI arg was mangled by the npm .ps1/.cmd shim (quotes /
     metacharacters) -> `SyntaxError: Unexpected end of input`. Fixed by base64
     encoding the eval source (`agent-browser eval -b`).
  2. agent-browser JSON-encodes the eval RESULT; our JS wraps payloads in
     JSON.stringify(...), so results arrive double-encoded. The parser only
     unwrapped one layer -> returned a string instead of dict/list. Fixed by
     `_unwrap_eval`.

These tests pin both fixes without needing a live browser.
"""
import base64
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import acquire_url as cb  # noqa: E402


class TestEvalArgsBase64(unittest.TestCase):
    def test_roundtrip(self):
        src = 'JSON.stringify({a:1, b:"x", c:(1>0)})'
        args = cb._eval_args(src)
        self.assertEqual(args[0], "eval")
        self.assertEqual(args[1], "-b")
        self.assertEqual(base64.b64decode(args[2]).decode("utf-8"), src)

    def test_b64_has_no_shell_metacharacters(self):
        # The whole point: base64 must be free of chars the shim mangles.
        args = cb._eval_args('a>b && c|d ("q") {z}')
        for ch in "<>&|(){}\"'":
            self.assertNotIn(ch, args[2])


class TestUnwrapEval(unittest.TestCase):
    def test_double_encoded_object(self):
        self.assertEqual(cb._unwrap_eval('{"heading":"X"}'), {"heading": "X"})

    def test_double_encoded_list(self):
        self.assertEqual(cb._unwrap_eval("[1, 2, 3]"), [1, 2, 3])

    def test_double_encoded_string(self):
        self.assertEqual(cb._unwrap_eval('"<html>x</html>"'), "<html>x</html>")

    def test_plain_non_json_string_kept(self):
        self.assertEqual(cb._unwrap_eval("AWDMods"), "AWDMods")

    def test_already_decoded_dict_unchanged(self):
        self.assertEqual(cb._unwrap_eval({"a": 1}), {"a": 1})

    def test_none_unchanged(self):
        self.assertIsNone(cb._unwrap_eval(None))


class TestFullParseChain(unittest.TestCase):
    def test_double_encoded_object_stdout_to_dict(self):
        # Exactly what agent-browser emits for JSON.stringify(obj) on Windows.
        stdout = '"{\\"heading\\":\\"Performance\\",\\"scene\\":\\"Above\\"}"\n'
        obj = cb._unwrap_eval(cb._parse_trailing_json(stdout))
        self.assertIsInstance(obj, dict)
        self.assertEqual(obj.get("heading"), "Performance")

    def test_double_encoded_html_stdout_to_string(self):
        stdout = '"\\"<html>x</html>\\""\n'
        self.assertEqual(cb._parse_eval_json_string(stdout), "<html>x</html>")


if __name__ == "__main__":
    unittest.main()
