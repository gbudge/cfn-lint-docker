# cfn-lint-docker

A small Python wrapper that runs [`cfn-lint`][cfn-lint] inside [Docker][docker] while behaving like the native CLI. It mounts your working directory, forwards arguments, preserves exit codes, and maps common AWS and cfn-lint config locations into the container.

## Why this exists

- Avoids installing Python dependencies and [`cfn-lint`][cfn-lint] locally.
- Keeps behavior close to the real [`cfn-lint`][cfn-lint] CLI.
- Works on Linux, macOS, and Windows with path normalization.

## Features

- Drop-in [`cfn-lint`][cfn-lint] command that runs in [Docker][docker].
- Mounts the current working directory at `/workspace`.
- Passes through common AWS and cfn-lint env vars and config files.
- Preserves exit codes, stdin/stdout/stderr, and TTY color output.
- Optional debug logging of the Docker command.

## Requirements

- [Docker][docker] in PATH.
- [Python 3][python] to run the wrapper.

## Installation

### Build the image

>[!NOTE]
>Skip this section, if you already have your own image.

The [Makefile][makefile] is the recommended way to build and install. If you do not have
[make][make] installed, use the fallback commands in each section.

The wrapper expects a local image named `cfn-lint:latest` by default. If you do
not already have your own `cfn-lint` image, run either `make build` or
`make build-wolfi` to create one.

Alpine-based image:

```sh
make build
```

Wolfi-based image:

```sh
make build-wolfi
```

If you do not have `make`, build directly:

```sh
docker build -f Dockerfile -t cfn-lint:latest .
```

### Install the wrapper

```sh
make install
```

If you do not have `make`, install directly:

```sh
install -m 755 src/cfn-lint.py ~/.local/bin/cfn-lint
```

This installs [`src/cfn-lint.py`][src-cfn-lint] to `~/.local/bin/cfn-lint` by default. Override
installation locations if needed:

```sh
make install PREFIX=/custom/prefix
make install BINDIR=/custom/bin
make install INSTALL_NAME=cfn-lint-docker
```

Windows (PowerShell) without `make`:

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\\bin" | Out-Null
Copy-Item src\\cfn-lint.py "$env:USERPROFILE\\bin\\cfn-lint.py"
Set-Content -Path "$env:USERPROFILE\\bin\\cfn-lint.cmd" -Value "@echo off\r\npy -3 \"%~dp0cfn-lint.py\" %*"
```

Ensure `%USERPROFILE%\\bin` is on your PATH, then run `cfn-lint` normally.

To remove it:

```sh
make uninstall
```

If you do not have `make`, remove directly:

```sh
rm -f ~/.local/bin/cfn-lint
```

Windows (PowerShell) without `make`:

```powershell
Remove-Item "$env:USERPROFILE\\bin\\cfn-lint.py" -ErrorAction SilentlyContinue
Remove-Item "$env:USERPROFILE\\bin\\cfn-lint.cmd" -ErrorAction SilentlyContinue
```

## Usage

Run it the same way you would run `cfn-lint`:

```sh
cfn-lint template.yaml
cfn-lint --template-file template.yaml
cfn-lint -t template.yaml
```

All arguments are forwarded directly to `cfn-lint` inside the container.

### Image selection

Use a different image tag by setting `CFNLINT_DOCKER_IMAGE`:

```sh
CFNLINT_DOCKER_IMAGE=myrepo/cfn-lint:1.2.3 cfn-lint template.yaml
```

### Debugging

To log the constructed Docker command to stderr:

```sh
CFNLINT_DOCKER_DEBUG=1 cfn-lint template.yaml
```

### Config and credentials

The wrapper mounts your working directory and your home directory, so local
config files and AWS credentials are available to the container. These variables
are passed through if set:

- `AWS_PROFILE`
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `AWS_SESSION_TOKEN`
- `AWS_DEFAULT_REGION`
- `AWS_REGION`
- `AWS_CONFIG_FILE`
- `AWS_SHARED_CREDENTIALS_FILE`
- `HTTP_PROXY`
- `HTTPS_PROXY`
- `NO_PROXY`
- `CFN_LINT_IGNORE_TEMPLATES_DIR`
- `CFN_LINT_CONFIG_FILE`

### Windows behavior

On Windows, absolute or relative Windows paths are mapped into container paths:

- Paths under the current working directory map to `/workspace/...`.
- Paths under the home directory map to `/cfnlint-home/...`.

This keeps config paths and template paths usable inside the container.

## Development

### Setup

```sh
make dev-setup
```

This creates a virtual environment, installs test requirements, and sets up
[pre-commit][pre-commit].

### Tests

```sh
make test
```

If you do not have `make`, run the steps directly:

```sh
pre-commit run --all-files
docker build . -f Dockerfile.wolfi -t cfn-lint:latest
python run_tests.py
```

This runs [pre-commit][pre-commit], builds the Wolfi image, and executes the test suite with
coverage. You can also run tests directly:

```sh
python run_tests.py
```

### Project layout

- [`src/cfn-lint.py`][src-cfn-lint]: wrapper implementation.
- [`Dockerfile`][dockerfile], [`Dockerfile.wolfi`][dockerfile-wolfi]: base images for [`cfn-lint`][cfn-lint].
- [`test/`][test-dir]: unit, system, and integration tests.
- [`Makefile`][makefile]: developer workflows and installation helpers.

## License

See [`LICENSE`][license].

<!-- markdown links -->
[cfn-lint]: https://github.com/aws-cloudformation/cfn-lint
[docker]: https://www.docker.com/
[python]: https://www.python.org/
[make]: https://www.gnu.org/software/make/
[pre-commit]: https://pre-commit.com/
[license]: LICENSE
[dockerfile]: Dockerfile
[dockerfile-wolfi]: Dockerfile.wolfi
[makefile]: Makefile
[src-cfn-lint]: src/cfn-lint.py
[test-dir]: test/
