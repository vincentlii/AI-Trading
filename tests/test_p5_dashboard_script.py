import sys
import unittest
from pathlib import Path

from scripts.check_p5_dashboard import DEFAULT_APP_PATH, parse_args, _streamlit_command


class P5DashboardScriptTests(unittest.TestCase):
    def test_parse_args_uses_safe_local_defaults(self):
        args = parse_args([])

        self.assertEqual(Path(args.app), DEFAULT_APP_PATH)
        self.assertEqual(args.host, "localhost")
        self.assertEqual(args.port, 8501)
        self.assertEqual(args.timeout, 60.0)
        self.assertFalse(args.keep_running)

    def test_streamlit_command_uses_current_python_and_headless_server(self):
        command = _streamlit_command(Path("app.py"), 8502)

        self.assertEqual(command[0], sys.executable)
        self.assertIn("streamlit", command)
        self.assertIn("app.py", command)
        self.assertIn("--server.headless=true", command)
        self.assertIn("--server.port=8502", command)
        self.assertIn("--browser.gatherUsageStats=false", command)


if __name__ == "__main__":
    unittest.main()
