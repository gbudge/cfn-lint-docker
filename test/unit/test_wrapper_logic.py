#!/usr/bin/env python3
import os
import sys
import unittest
import importlib.util
import runpy
from unittest.mock import patch
from pathlib import Path
from io import StringIO

# Helper to import the source file which has a hyphen
SRC_PATH = Path(__file__).parents[2] / "src" / "cfn-lint.py"

# Get CFN_LINT_IMAGE from environment or use default
CFN_LINT_IMAGE = os.environ.setdefault("CFN_LINT_IMAGE", "cfn-lint:latest")

def load_module():
    spec = importlib.util.spec_from_file_location("cfn_lint_wrapper", SRC_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load module spec from {SRC_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["cfn_lint_wrapper"] = module
    spec.loader.exec_module(module)
    return module

class TestWindowsPathLogic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfn_lint = load_module()

    def test_looks_like_windows_path(self):
        # Drive letters
        self.assertTrue(self.cfn_lint.looks_like_windows_path("C:\\Users"))
        self.assertTrue(self.cfn_lint.looks_like_windows_path("D:/Users"))
        self.assertTrue(self.cfn_lint.looks_like_windows_path("c:\\foo"))

        # Relative paths
        self.assertTrue(self.cfn_lint.looks_like_windows_path(".\\foo"))
        self.assertTrue(self.cfn_lint.looks_like_windows_path("..\\bar"))

        # Not windows paths
        self.assertFalse(self.cfn_lint.looks_like_windows_path("/usr/bin"))
        self.assertFalse(self.cfn_lint.looks_like_windows_path("foo/bar"))
        self.assertFalse(self.cfn_lint.looks_like_windows_path("-t"))
        self.assertFalse(self.cfn_lint.looks_like_windows_path("--template"))
        self.assertFalse(self.cfn_lint.looks_like_windows_path(""))

    def test_looks_like_windows_path_existence_check(self):
        with patch("os.path.exists") as mock_exists:
            mock_exists.return_value = True
            self.assertTrue(self.cfn_lint.looks_like_windows_path("subfolder\\file.yaml"))

            mock_exists.return_value = False
            self.assertFalse(self.cfn_lint.looks_like_windows_path("regex\\d+"))

    def test_normalize_host_path(self):
        with patch.object(self.cfn_lint, "get_os_name", return_value="posix"):
            self.assertEqual(self.cfn_lint.normalize_host_path("C:\\foo"), "C:\\foo")

        with patch.object(self.cfn_lint, "get_os_name", return_value="nt"):
            self.assertEqual(self.cfn_lint.normalize_host_path("C:\\foo\\bar"), "C:/foo/bar")

    def test_get_os_name_override(self):
        with patch.dict(os.environ, {"CFNLINT_DOCKER_OS": "nt"}):
            self.assertEqual(self.cfn_lint.get_os_name(), "nt")

    def test_map_windows_path_to_container(self):
        host_pwd = Path("C:/Users/User/Project")
        home = Path("C:/Users/User")

        with patch.object(self.cfn_lint, "get_os_name", return_value="nt"):
            # We must mock Path inside the module because Path() checks os.name
            with patch.object(self.cfn_lint, "Path") as mock_path_cls:
                # Setup the mock path to raise OSError on resolve so we hit the fallback
                mock_instance = mock_path_cls.return_value
                mock_instance.resolve.side_effect = OSError("Mock error")

                # Simple slash replacement if lookup fails/mocks not perfect
                self.assertEqual(self.cfn_lint.map_windows_path_to_container("C:\\Random", None, None), "C:/Random")

    def test_map_windows_path_non_windows(self):
        with patch.object(self.cfn_lint, "get_os_name", return_value="posix"):
            self.assertEqual(
                self.cfn_lint.map_windows_path_to_container("C:\\Random", None, None),
                "C:\\Random",
            )

    def test_map_windows_path_logic_mocked(self):
        with patch.object(self.cfn_lint, "get_os_name", return_value="nt"), \
             patch.object(self.cfn_lint, "looks_like_windows_path", return_value=True):

            # We need to mock Path inside the module to avoid WindowsPath instantiation on Linux
            with patch.object(self.cfn_lint, "Path") as mock_path_cls:

                # We need to mock the behavior of .resolve() and .relative_to()
                # This is complex because we want to test the logic.
                # Let's create a FakePath class that mimics what we need.

                class FakePath:
                    def __init__(self, path_str):
                        self.path_str = str(path_str).replace("\\", "/")

                    def resolve(self):
                        return self

                    def relative_to(self, other):
                        # Simple string-based relative check for testing
                        other_str = str(other).replace("\\", "/")
                        if self.path_str.startswith(other_str):
                            rel = self.path_str[len(other_str):].lstrip("/")
                            return FakePath(rel)
                        raise ValueError("Not relative")

                    def __str__(self):
                        return self.path_str

                mock_path_cls.side_effect = FakePath

                # Define host paths as objects that match our FakePath logic (strings or FakePaths)
                host_pwd = FakePath("/mnt/c/Project")
                home = FakePath("/mnt/c/Users/Me")

                # 1. Under CWD
                arg = "/mnt/c/Project/subdir/file.yaml"
                res = self.cfn_lint.map_windows_path_to_container(arg, host_pwd, home)
                self.assertEqual(res, "/workspace/subdir/file.yaml")

                # 2. Under HOME
                arg = "/mnt/c/Users/Me/.config"
                res = self.cfn_lint.map_windows_path_to_container(arg, host_pwd, home)
                self.assertEqual(res, "/cfnlint-home/.config")

                # 3. Elsewhere
                arg = "/mnt/d/Other"
                res = self.cfn_lint.map_windows_path_to_container(arg, host_pwd, home)
                self.assertEqual(res, "/mnt/d/Other")

class TestArgNormalization(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfn_lint = load_module()

    def test_normalize_arg_posix(self):
        with patch.object(self.cfn_lint, "get_os_name", return_value="posix"):
            self.assertEqual(self.cfn_lint.normalize_arg("foo", None, None), "foo")
            self.assertEqual(self.cfn_lint.normalize_arg("C:\\foo", None, None), "C:\\foo")

    def test_normalize_arg_windows(self):
        with patch.object(self.cfn_lint, "get_os_name", return_value="nt"), \
             patch.object(self.cfn_lint, "map_windows_path_to_container", return_value="/mapped/path"):

            # Since we patch os.name='nt', we might need to be careful if normalize_arg uses Path?
            # normalize_arg calls map_windows_path_to_container, but doesn't use Path directly itself.
            # checks: if os.name != "nt": return arg
            # Then splits '='.
            # Then calls map_windows_path_to_container.

            self.assertEqual(self.cfn_lint.normalize_arg("C:\\foo", None, None), "/mapped/path")
            self.assertEqual(self.cfn_lint.normalize_arg("--file=C:\\foo", None, None), "--file=/mapped/path")

class TestMainExecution(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfn_lint = load_module()

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_main_no_docker(self, mock_run, mock_which):
        mock_which.return_value = None

        err_out = StringIO()
        with patch("sys.stderr", err_out):
            ret = self.cfn_lint.main()
            self.assertEqual(ret, 127)
            self.assertIn("docker' not found", err_out.getvalue())

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_main_basic_run(self, mock_run, mock_which):
        mock_which.return_value = "/usr/bin/docker"
        mock_run.return_value.returncode = 0

        with patch("sys.argv", ["cfn-lint", "template.yaml"]):
            with patch("os.getcwd", return_value="/home/user/project"):
                with patch("pathlib.Path.home", return_value=Path("/home/user")):
                    ret = self.cfn_lint.main()
                    self.assertEqual(ret, 0)

        args, _ = mock_run.call_args
        cmd_list = args[0]
        self.assertEqual(cmd_list[0], "/usr/bin/docker")
        self.assertIn("run", cmd_list)
        self.assertIn("/workspace", cmd_list)
        self.assertIn(f"{CFN_LINT_IMAGE}", cmd_list)
        self.assertIn("template.yaml", cmd_list)

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_main_tty_flag(self, mock_run, mock_which):
        mock_which.return_value = "/usr/bin/docker"
        mock_run.return_value.returncode = 0

        with patch("sys.stdout.isatty", return_value=True):
            self.cfn_lint.main()

        args, _ = mock_run.call_args
        cmd_list = args[0]
        self.assertIn("-t", cmd_list)

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_main_getuid_attribute_error(self, mock_run, mock_which):
        mock_which.return_value = "/usr/bin/docker"
        mock_run.return_value.returncode = 0

        with patch.object(self.cfn_lint, "get_os_name", return_value="posix"):
            with patch("os.getuid", side_effect=AttributeError):
                self.cfn_lint.main()

        args, _ = mock_run.call_args
        cmd_list = args[0]
        self.assertNotIn("-u", cmd_list)

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_debug_enabled(self, mock_run, mock_which):
        mock_which.return_value = "/bin/docker"
        mock_run.return_value.returncode = 0

        with patch.dict(os.environ, {"CFNLINT_DOCKER_DEBUG": "true"}):
            with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
                with patch("sys.argv", ["cfn-lint"]):
                    self.cfn_lint.main()
                    self.assertIn("[cfn-lint docker debug]", mock_stderr.getvalue())

    def test_debug_check(self):
        with patch.dict(os.environ, {"CFNLINT_DOCKER_DEBUG": "1"}):
            self.assertTrue(self.cfn_lint.debug_enabled())
        with patch.dict(os.environ, {"CFNLINT_DOCKER_DEBUG": "False"}):
            self.assertFalse(self.cfn_lint.debug_enabled())
        with patch.dict(os.environ, {}, clear=True):
             self.assertFalse(self.cfn_lint.debug_enabled())

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_main_windows_execution(self, mock_run, mock_which):
        """Test main() execution flow when get_os_name returns nt."""
        mock_which.return_value = "docker.exe"
        mock_run.return_value.returncode = 0

        # Create path before patching get_os_name
        home_path_obj = Path("C:\\Users\\Me")

        with patch.object(self.cfn_lint, "get_os_name", return_value="nt"):
            with patch("sys.argv", ["cfn-lint", "C:\\template.yaml"]):
                # Mock getcwd and home
                with patch("os.getcwd", return_value="C:\\Project"):
                    # We need to mock Path inside module again
                    with patch.object(self.cfn_lint, "Path") as mock_path_cls:
                        # Configure Path.home() on the mock class
                        mock_path_cls.home.return_value = home_path_obj

                        # Mock Path behavior
                        class FakePath:
                            def __init__(self, p): self.p = str(p).replace("\\", "/")
                            def resolve(self): return self
                            def __str__(self): return self.p
                            def relative_to(self, o): return self # simplistic
                        mock_path_cls.side_effect = FakePath

                        ret = self.cfn_lint.main()
                        self.assertEqual(ret, 0)

        args, _ = mock_run.call_args
        cmd_list = args[0]
        # Check windows specific args
        # Check environment variable setting
        self.assertIn("HOME=/cfnlint-home", cmd_list)
        # Check volume mount
        # normalize_host_path("C:\Users\Me") -> "C:/Users/Me"
        self.assertIn("C:/Users/Me:/cfnlint-home", cmd_list)

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_main_env_var_mapping_windows(self, mock_run, mock_which):
        mock_which.return_value = "docker"
        mock_run.return_value.returncode = 0

        env = {
            "AWS_CONFIG_FILE": "C:\\Users\\Me\\.aws\\config",
            "CFN_LINT_CONFIG_FILE": "C:\\Project\\.cfnlintrc"
        }

        # Create path before patching get_os_name
        home_path_obj = Path("C:\\Users\\Me")

        with patch.object(self.cfn_lint, "get_os_name", return_value="nt"), patch.dict(os.environ, env):
             with patch("os.getcwd", return_value="C:\\Project"):
                with patch.object(self.cfn_lint, "Path") as mock_path_cls:
                    mock_path_cls.home.return_value = home_path_obj

                    class FakePath:
                        def __init__(self, p): self.p = str(p).replace("\\", "/")
                        def resolve(self): return self
                        def __str__(self): return self.p
                        def relative_to(self, o):
                            # If under project, return rel
                            if "Project" in self.p and "Project" in str(o):
                                return FakePath(self.p.split("Project/")[-1])
                            # If under home
                            if "Users/Me" in self.p and "Users/Me" in str(o):
                                return FakePath(self.p.split("Users/Me/")[-1])
                            raise ValueError("Not relative")
                    mock_path_cls.side_effect = FakePath

                    self.cfn_lint.main()

        args, _ = mock_run.call_args
        cmd_list = args[0]
        # Check mapped env vars
        # AWS_CONFIG_FILE should be mapped to home
        # CFN_LINT_CONFIG_FILE should be mapped to workspace

        # We need to find the args in the list
        aws_conf = next(x for x in cmd_list if x.startswith("AWS_CONFIG_FILE="))
        self.assertIn("/cfnlint-home/.aws/config", aws_conf)

        cfn_conf = next(x for x in cmd_list if x.startswith("CFN_LINT_CONFIG_FILE="))
        self.assertIn("/workspace/.cfnlintrc", cfn_conf)

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_main_subprocess_oserror(self, mock_run, mock_which):
        mock_which.return_value = "docker"
        mock_run.side_effect = OSError("Docker failed")

        with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
            ret = self.cfn_lint.main()
            self.assertEqual(ret, 1)
            self.assertIn("failed to run docker", mock_stderr.getvalue())

    def test_log_docker_command_fallback(self):
        # Mock shlex to raise AttributeError
        with patch("shlex.join", side_effect=AttributeError):
             with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
                 self.cfn_lint.log_docker_command(["echo", "hello"])
                 self.assertIn("echo hello", mock_stderr.getvalue())

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_main_oserror_resolving_paths(self, mock_run, mock_which):
        # Trigger OSError during path resolution in main
        mock_which.return_value = "docker"
        mock_run.return_value.returncode = 0

        with patch.object(self.cfn_lint, "Path") as mock_path_cls:
            mock_instance = mock_path_cls.return_value
            mock_instance.resolve.side_effect = OSError("Disk error")

            # This covers the try/except blocks for host_pwd_path and home_path
            ret = self.cfn_lint.main()
            self.assertEqual(ret, 0)

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_main_no_home(self, mock_run, mock_which):
        # Cover the "else: home_path = None" if home_str is missing or Exception
        mock_which.return_value = "docker"
        mock_run.return_value.returncode = 0

        with patch("pathlib.Path.home", side_effect=Exception("No home")):
             ret = self.cfn_lint.main()
             self.assertEqual(ret, 0)

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_main_guard_execution(self, mock_run, mock_which):
        mock_which.return_value = "/usr/bin/docker"
        mock_run.return_value.returncode = 0

        with patch("sys.argv", ["cfn-lint"]):
            with patch.dict(os.environ, {"CFNLINT_DOCKER_OS": "posix"}):
                with self.assertRaises(SystemExit) as ctx:
                    runpy.run_path(str(SRC_PATH), run_name="__main__")
        self.assertEqual(ctx.exception.code, 0)


if __name__ == '__main__':
    unittest.main()
