import subprocess
import sys


def run(cmd):
    return subprocess.run(cmd).returncode


def main():
    test_dirs = ["test/unit", "test/system", "test/integration"]
    coverage_cmd = [
        sys.executable,
        "-m",
        "coverage",
        "run",
        "--source=src",
        "-m",
        "pytest",
    ]
    coverage_cmd.extend(test_dirs)

    if run([sys.executable, "-m", "coverage", "erase"]) != 0:
        return 1

    test_rc = run(coverage_cmd)
    if test_rc != 0:
        return test_rc

    report_rc = run([sys.executable, "-m", "coverage", "report", "-m"])
    return report_rc


if __name__ == "__main__":
    sys.exit(main())
