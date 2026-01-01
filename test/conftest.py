#!/usr/bin/env python3

import importlib.util
import sys
from pathlib import Path
import pytest

# Helper to import the source file which has a hyphen
SRC_PATH = Path(__file__).parents[1] / "src" / "cfn-lint.py"

def load_module():
    spec = importlib.util.spec_from_file_location("cfn_lint_wrapper", SRC_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load spec for {SRC_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["cfn_lint_wrapper"] = module
    spec.loader.exec_module(module)
    return module

@pytest.fixture(scope="session")
def cfn_lint():
    return load_module()
