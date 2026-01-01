#!/usr/bin/env python3

import unittest
import sys
import os
import importlib.util
from unittest.mock import patch, MagicMock
from pathlib import Path

# Helper to import
SRC_PATH = Path(__file__).parents[2] / "src" / "cfn-lint.py"

# Get CFN_LINT_IMAGE from environment or use default
CFN_LINT_IMAGE = os.environ.setdefault("CFN_LINT_IMAGE", "cfn-lint:latest")

def load_module():
    spec = importlib.util.spec_from_file_location("cfn_lint_wrapper", SRC_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load module from {SRC_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["cfn_lint_wrapper"] = module
    spec.loader.exec_module(module)
    return module

class TestSystemCLI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfn_lint = load_module()
        cls.fixtures_dir = Path(__file__).parents[2] / "test" / "fixtures" / "validation"

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_all_fixtures_command_structure(self, mock_run, mock_which):
        """
        Verify that for every fixture file, we construct a valid docker command.
        """
        mock_which.return_value = "/usr/bin/docker"
        mock_run.return_value.returncode = 0

        # Iterate over all files in fixtures
        for fixture_file in self.fixtures_dir.iterdir():
            if not fixture_file.is_file():
                continue

            file_name = fixture_file.name
            # Skip log files
            if file_name.endswith(".log"):
                continue

            # Reset mock
            mock_run.reset_mock()

            # Run main with the file argument
            with patch("sys.argv", ["cfn-lint", str(fixture_file)]):
                # We mock getcwd to be the root of the repo so fixtures are relative or absolute
                # Actually, main() mounts getcwd().
                # Let's mock getcwd to be the parent of fixtures dir for variety
                cwd = str(self.fixtures_dir.parent)
                with patch("os.getcwd", return_value=cwd):
                     ret = self.cfn_lint.main()

            # Check return code
            self.assertEqual(ret, 0)

            # Check command
            args, _ = mock_run.call_args
            cmd = args[0]

            # Basics
            self.assertEqual(cmd[0], "/usr/bin/docker")
            self.assertIn(f"{CFN_LINT_IMAGE}", cmd)

            # Check that the file argument was passed
            # Since we passed an absolute path (fixture_file is absolute),
            # and it is under cwd (fixtures_dir.parent), it shouldn't be touched on Linux
            # unless we are testing windows logic.
            # On Linux (which this test runs on), normalize_arg does nothing.
            self.assertIn(str(fixture_file), cmd)

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_exit_code_propagation(self, mock_run, mock_which):
        mock_which.return_value = "/usr/bin/docker"

        # Simulate cfn-lint finding errors (exit code 2 usually, or 4, etc)
        mock_run.return_value.returncode = 2

        with patch("sys.argv", ["cfn-lint", "bad.yaml"]):
            ret = self.cfn_lint.main()
            self.assertEqual(ret, 2)

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_keyboard_interrupt(self, mock_run, mock_which):
        mock_which.return_value = "/usr/bin/docker"
        mock_run.side_effect = KeyboardInterrupt

        with patch("sys.argv", ["cfn-lint"]):
            ret = self.cfn_lint.main()
            self.assertEqual(ret, 130)

if __name__ == '__main__':
    unittest.main()
