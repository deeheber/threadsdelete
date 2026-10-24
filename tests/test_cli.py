import contextlib
import io
import os
import unittest
from unittest import mock

import main


class HelpTests(unittest.TestCase):
    def test_help_needs_no_credentials(self) -> None:
        out = io.StringIO()
        with (
            mock.patch.dict(os.environ, {}, clear=True),
            contextlib.redirect_stdout(out),
            self.assertRaises(SystemExit) as raised,
        ):
            main.main(["--help"])
        self.assertEqual(raised.exception.code, 0)
        self.assertIn("usage:", out.getvalue())


if __name__ == "__main__":
    unittest.main()
