#!/usr/bin/env python3

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[2]
SRC_PATH = ROOT / "src" / "cfn-lint.py"
FIXTURES_BIN = ROOT / "test" / "fixtures" / "bin"

# Get CFN_LINT_IMAGE from environment or use default
CFN_LINT_IMAGE = os.environ.setdefault("CFN_LINT_IMAGE", "cfn-lint:latest")


class TestWrapperIntegration(unittest.TestCase):
    def test_invokes_docker_stub_and_forwards_args(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "docker.json"

            env = os.environ.copy()
            env["PATH"] = f"{FIXTURES_BIN}{os.pathsep}{env.get('PATH', '')}"
            env["CFNLINT_DOCKER_TEST_OUTPUT"] = str(output_path)
            env["CFNLINT_DOCKER_TEST_RC"] = "0"

            proc = subprocess.run(
                [sys.executable, str(SRC_PATH), "test/fixtures/validation/good.yaml"],
                cwd=ROOT,
                env=env,
            )
            self.assertEqual(proc.returncode, 0)

            payload = json.loads(output_path.read_text())
            args = payload["args"]
            host_root = str(ROOT)
            if os.name == "nt":
                host_root = host_root.replace("\\", "/")
            expected_volume = f"{host_root}:/workspace"

            self.assertIn("run", args)
            self.assertIn(f"{CFN_LINT_IMAGE}", args)
            self.assertIn("test/fixtures/validation/good.yaml", args)
            self.assertIn("-w", args)
            self.assertIn("/workspace", args)
            self.assertIn(expected_volume, args)

    def test_exit_code_from_docker_is_propagated(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "docker.json"

            env = os.environ.copy()
            env["PATH"] = f"{FIXTURES_BIN}{os.pathsep}{env.get('PATH', '')}"
            env["CFNLINT_DOCKER_TEST_OUTPUT"] = str(output_path)
            env["CFNLINT_DOCKER_TEST_RC"] = "42"

            proc = subprocess.run(
                [sys.executable, str(SRC_PATH), "test/fixtures/validation/good.yaml"],
                cwd=ROOT,
                env=env,
            )
            self.assertEqual(proc.returncode, 42)

    def test_windows_override_sets_home_and_volume(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "docker.json"

            env = os.environ.copy()
            env["PATH"] = f"{FIXTURES_BIN}{os.pathsep}{env.get('PATH', '')}"
            env["CFNLINT_DOCKER_TEST_OUTPUT"] = str(output_path)
            env["CFNLINT_DOCKER_TEST_RC"] = "0"
            env["CFNLINT_DOCKER_OS"] = "nt"

            proc = subprocess.run(
                [sys.executable, str(SRC_PATH), "C:\\template.yaml"],
                cwd=ROOT,
                env=env,
            )
            self.assertEqual(proc.returncode, 0)

            payload = json.loads(output_path.read_text())
            args = payload["args"]
            host_root = str(ROOT).replace("\\", "/")
            expected_volume = f"{host_root}:/workspace"

            self.assertIn("HOME=/cfnlint-home", args)
            self.assertIn(expected_volume, args)
