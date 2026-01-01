#!/usr/bin/env python
"""
cfn-lint: Docker wrapper for cfn-lint, intended as a drop-in replacement.

- Works on Linux, macOS, and Windows.
- Forwards all CLI arguments to cfn-lint inside the container.
- Propagates stdin/stdout/stderr and exit codes.
- Handles TTY detection for colored output.
- Normalizes Windows file paths for the Linux container and maps absolute
  paths under CWD/HOME into the mounted container paths.
- Optional debug logging of the docker command via CFNLINT_DOCKER_DEBUG.
"""

import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Set


def get_os_name() -> str:
    """
    Return the effective OS name for logic branches.
    Uses CFNLINT_DOCKER_OS as a test override when set.
    """
    override = os.environ.get("CFNLINT_DOCKER_OS")
    if override:
        return override
    return os.name


def looks_like_windows_path(arg: str) -> bool:
    """
    Heuristic: argument looks like a Windows filesystem path when:

    - Starts with a drive letter, colon, and slash or backslash, e.g. C:\\ or D:/.
    - Starts with .\\ or ..\\ for relative paths.
    - Exists on the local filesystem (handles 'subfolder\\file.yaml').

    We intentionally avoid IO-based existence checks UNLESS the pattern is ambiguous.
    """
    if not arg:
        return False

    # Drive letter path: C:\foo or C:/foo
    if re.match(r"^[a-zA-Z]:[\\/]", arg):
        return True

    # Explicit relative path: .\foo or ..\foo
    if arg.startswith(".\\") or arg.startswith("..\\"):
        return True

    # Simple relative path: templates\file.yaml
    # We check existence to distinguish paths from regexes (e.g. W\d+)
    if "\\" in arg and os.path.exists(arg):
        return True

    return False


def normalize_host_path(path: str) -> str:
    """
    Normalize host paths passed to docker -v on Windows.

    Docker CLI on Windows generally accepts both backslashes and forward slashes,
    but using forward slashes is more consistent and less error prone.
    """
    if get_os_name() != "nt":
        return path
    return path.replace("\\", "/")


def map_windows_path_to_container(
    arg: str,
    host_pwd_path: Optional[Path],
    home_path: Optional[Path],
) -> str:
    """
    For Windows:

    - If arg looks like a Windows path and is under CWD, map to /workspace/<rel>.
    - If under HOME, map to /cfnlint-home/<rel>.
    - Otherwise, just normalize backslashes to forward slashes.

    On non-Windows, returns arg as-is.
    """
    if get_os_name() != "nt":
        return arg

    if not looks_like_windows_path(arg):
        return arg

    # Try to resolve as a Path. If this fails, just do a simple slash normalization.
    # Note: .resolve() handles normalizing casing (e.g. c:\ vs C:\) on Windows,
    # which is crucial for the .relative_to() checks below.
    try:
        abs_path = Path(arg).resolve()
    except OSError:
        return arg.replace("\\", "/")

    # CWD mapping -> /workspace
    if host_pwd_path is not None:
        try:
            rel = abs_path.relative_to(host_pwd_path)
            return "/workspace/" + str(rel).replace("\\", "/")
        except ValueError:
            # Not under host_pwd_path
            pass

    # HOME mapping -> /cfnlint-home
    if home_path is not None:
        try:
            rel = abs_path.relative_to(home_path)
            return "/cfnlint-home/" + str(rel).replace("\\", "/")
        except ValueError:
            # Not under home_path
            pass

    # Fallback: just normalize slashes; path likely not reachable in container
    return arg.replace("\\", "/")


def normalize_arg(
    arg: str,
    host_pwd_path: Optional[Path],
    home_path: Optional[Path],
) -> str:
    """
    Normalize an argument that may be a Windows path into a path that makes sense
    inside the Linux container.

    Handles both:
      - simple path arguments: "C:\\foo\\bar.yaml"
      - option=value forms:   "--template-file=C:\\foo\\bar.yaml"
    """
    if get_os_name() != "nt":
        return arg

    # Handle --option=C:\path style
    if "=" in arg and arg.startswith("-"):
        key, value = arg.split("=", 1)
        mapped_value = map_windows_path_to_container(
            value, host_pwd_path=host_pwd_path, home_path=home_path
        )
        return f"{key}={mapped_value}"

    # Fallback: treat whole arg as a potential path
    return map_windows_path_to_container(arg, host_pwd_path, home_path)


def debug_enabled() -> bool:
    """
    Check CFNLINT_DOCKER_DEBUG to decide whether to log the docker command.

    Truthy values: 1, true, yes, on (case insensitive).
    """
    val = os.environ.get("CFNLINT_DOCKER_DEBUG")
    if val is None:
        return False
    return val.strip().lower() in ("1", "true", "yes", "on")


def log_docker_command(args: List[str]) -> None:
    """
    Log the docker command to stderr only.
    Uses shlex.join when available, falls back to a simple join.
    """
    try:
        cmd_str = shlex.join(args)
    except AttributeError:
        # Python < 3.8 fallback (unlikely, but harmless)
        cmd_str = " ".join(args)
    sys.stderr.write(f"[cfn-lint docker debug] {cmd_str}\n")


def main() -> int:
    # 1. Ensure docker is available
    docker_exe = shutil.which("docker")
    if docker_exe is None:
        sys.stderr.write("cfn-lint wrapper error: 'docker' not found in PATH\n")
        return 127

    # 2. Resolve image (env overrides default)
    image = os.environ.get(
        "CFNLINT_DOCKER_IMAGE", "cfn-lint:latest"
    )

    # 3. Base docker args
    docker_args: List[str] = [docker_exe, "run", "--rm", "-i"]

    # TTY support (colours, progress, etc.)
    if sys.stdout.isatty():
        docker_args.append("-t")

    # POSIX user mapping (avoid on Windows to prevent gid/uid issues)
    if get_os_name() == "posix":
        try:
            uid = os.getuid()
            gid = os.getgid()
            docker_args.extend(["-u", f"{uid}:{gid}"])
        except AttributeError:
            # Very old/non-standard POSIX; ignore
            pass

    # 4. Mount working directory -> /workspace (consistent inside container)
    host_pwd = os.getcwd()
    host_pwd_mnt = normalize_host_path(host_pwd)
    container_pwd = "/workspace"
    docker_args.extend(["-v", f"{host_pwd_mnt}:{container_pwd}", "-w", container_pwd])

    # Prepare Path objects for mapping args later
    try:
        host_pwd_path: Optional[Path] = Path(host_pwd).resolve()
    except OSError:
        host_pwd_path = None

    # 5. Mount HOME and override HOME inside container so cfn-lint sees host config
    #    (e.g. ~/.cfnlintrc or ~/.aws/config)
    try:
        home_str: Optional[str] = str(Path.home())
    except Exception:
        home_str = None

    if home_str:
        if get_os_name() == "nt":
            # On Windows: mount HOME to /cfnlint-home, set HOME=/cfnlint-home
            home_mnt = normalize_host_path(home_str)
            docker_args.extend(
                ["-v", f"{home_mnt}:/cfnlint-home", "-e", "HOME=/cfnlint-home"]
            )
        else:
            # On POSIX: mount HOME at same path, keep HOME value (fully transparent)
            docker_args.extend(["-v", f"{home_str}:{home_str}", "-e", "HOME"])

        try:
            home_path: Optional[Path] = Path(home_str).resolve()
        except OSError:
            home_path = None
    else:
        home_path = None

    # 6. Pass through relevant env vars (value from host)
    passthrough_env_vars = [
        # AWS Identity
        "AWS_PROFILE",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "AWS_DEFAULT_REGION",
        "AWS_REGION",
        # AWS Config Locations
        "AWS_CONFIG_FILE",
        "AWS_SHARED_CREDENTIALS_FILE",
        # Network / Proxy
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "NO_PROXY",
        # Tool Config
        "CFN_LINT_IGNORE_TEMPLATES_DIR",
        "CFN_LINT_CONFIG_FILE",
    ]

    # Env vars whose values are paths we may want to map on Windows
    path_env_vars: Set[str] = {
        "AWS_CONFIG_FILE",
        "AWS_SHARED_CREDENTIALS_FILE",
        "CFN_LINT_CONFIG_FILE",
        "CFN_LINT_IGNORE_TEMPLATES_DIR",
    }

    for var in passthrough_env_vars:
        if var not in os.environ:
            continue

        if get_os_name() == "nt" and var in path_env_vars:
            # Map Windows path values into container paths
            original_value = os.environ[var]
            mapped_value = map_windows_path_to_container(
                original_value, host_pwd_path=host_pwd_path, home_path=home_path
            )
            docker_args.extend(["-e", f"{var}={mapped_value}"])
        else:
            # Simple pass-through of host value
            docker_args.extend(["-e", var])

    # 7. Image and underlying command (cfn-lint)
    docker_args.append(image)

    # Forward user arguments, normalizing paths if on Windows
    user_args = [
        normalize_arg(arg, host_pwd_path=host_pwd_path, home_path=home_path)
        for arg in sys.argv[1:]
    ]
    docker_args.extend(user_args)

    # Optional debug logging to stderr
    if debug_enabled():
        log_docker_command(docker_args)

    # 8. Execute docker, preserving stdin/stdout/stderr and exit code
    try:
        completed = subprocess.run(docker_args)
        return completed.returncode
    except KeyboardInterrupt:
        # Preserve Ctrl+C semantics
        return 130
    except OSError as exc:
        sys.stderr.write(f"cfn-lint wrapper error: failed to run docker: {exc}\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
