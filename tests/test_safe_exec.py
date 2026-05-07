"""Tests for the safe execution sandbox (app.core.safe_exec)."""
from __future__ import annotations

import builtins

import pytest

from app.core.safe_exec import (
    build_safe_builtins,
    safe_exec_code,
    validate_code_safety,
)


# ---------------------------------------------------------------------------
# validate_code_safety -- safe code passes
# ---------------------------------------------------------------------------

class TestValidateCodeSafetySafe:
    """Safe code that should pass validation."""

    @pytest.mark.parametrize("code", [
        "x = 1 + 2",
        "result = sum(range(10))",
        "data = [i**2 for i in range(5)]",
        "x = max(1, 2, 3)",
    ])
    def test_simple_expressions_pass(self, code: str) -> None:
        is_safe, error = validate_code_safety(code)
        assert is_safe is True
        assert error is None

    def test_pandas_operations_pass(self) -> None:
        code = "df['close'].mean()"
        is_safe, error = validate_code_safety(code)
        assert is_safe is True
        assert error is None

    @pytest.mark.parametrize("code", [
        "import numpy as np",
        "import pandas as pd",
        "import math",
        "import json",
        "import datetime",
        "import collections",
    ])
    def test_allowed_imports_pass(self, code: str) -> None:
        is_safe, error = validate_code_safety(code)
        assert is_safe is True
        assert error is None

    def test_multiline_safe_code_passes(self) -> None:
        code = (
            "import numpy as np\n"
            "arr = np.array([1, 2, 3])\n"
            "mean_val = arr.mean()\n"
        )
        is_safe, error = validate_code_safety(code)
        assert is_safe is True
        assert error is None


# ---------------------------------------------------------------------------
# validate_code_safety -- dangerous code rejected
# ---------------------------------------------------------------------------

class TestValidateCodeSafetyDangerous:
    """Dangerous code that must be rejected."""

    @pytest.mark.parametrize("code, fragment", [
        ("import os", "os"),
        ("import subprocess", "subprocess"),
        ("import sys", "sys"),
        ("import shutil", "shutil"),
        ("import socket", "socket"),
        ("import ctypes", "ctypes"),
        ("import pickle", "pickle"),
    ])
    def test_dangerous_imports_rejected(self, code: str, fragment: str) -> None:
        is_safe, error = validate_code_safety(code)
        assert is_safe is False
        assert error is not None
        assert fragment in error.lower() or "不允许" in error or "dangerous" in error.lower()

    def test_exec_call_rejected(self) -> None:
        is_safe, error = validate_code_safety("exec(\"print('hi')\")")
        assert is_safe is False
        assert error is not None

    def test_eval_call_rejected(self) -> None:
        is_safe, error = validate_code_safety('eval("1+1")')
        assert is_safe is False
        assert error is not None

    def test_dunder_import_rejected(self) -> None:
        is_safe, error = validate_code_safety("__import__('os')")
        assert is_safe is False
        assert error is not None

    def test_open_call_rejected(self) -> None:
        is_safe, error = validate_code_safety("open('/etc/passwd')")
        assert is_safe is False
        assert error is not None

    def test_os_system_rejected(self) -> None:
        is_safe, error = validate_code_safety("os.system('rm -rf /')")
        assert is_safe is False
        assert error is not None

    @pytest.mark.parametrize("code", [
        "os.popen('whoami')",
        "os.listdir('/')",
        "getattr(obj, '__class__')",
        "setattr(obj, 'x', 1)",
        "globals()",
        "breakpoint()",
    ])
    def test_other_dangerous_patterns_rejected(self, code: str) -> None:
        is_safe, error = validate_code_safety(code)
        assert is_safe is False
        assert error is not None

    def test_syntax_error_rejected(self) -> None:
        is_safe, error = validate_code_safety("def foo(:")
        assert is_safe is False
        assert error is not None


# ---------------------------------------------------------------------------
# build_safe_builtins
# ---------------------------------------------------------------------------

class TestBuildSafeBuiltins:
    """Verify the restricted builtins dict."""

    @pytest.fixture()
    def safe_builtins(self) -> dict:
        return build_safe_builtins()

    def test_returns_dict(self, safe_builtins: dict) -> None:
        assert isinstance(safe_builtins, dict)

    @pytest.mark.parametrize("name", [
        "len", "range", "print", "abs", "min", "max", "sum",
        "int", "float", "str", "bool", "list", "dict", "set",
        "enumerate", "zip", "map", "filter", "sorted", "reversed",
        "round", "pow", "divmod", "isinstance", "callable",
    ])
    def test_contains_expected_safe_builtins(self, safe_builtins: dict, name: str) -> None:
        assert name in safe_builtins, f"Expected safe builtin '{name}' missing"
        assert safe_builtins[name] is getattr(builtins, name)

    @pytest.mark.parametrize("name", [
        "exec", "eval", "compile", "__import__",
        "open", "globals", "vars", "dir",
        "breakpoint", "input", "exit", "quit",
    ])
    def test_does_not_contain_dangerous_builtins(self, safe_builtins: dict, name: str) -> None:
        if name == "__import__":
            # __import__ is present but replaced with a restricted version
            assert safe_builtins["__import__"] is not builtins.__import__
        else:
            assert name not in safe_builtins, f"Dangerous builtin '{name}' should not be present"

    def test_custom_import_is_restricted(self, safe_builtins: dict) -> None:
        """The injected __import__ should reject non-whitelisted modules."""
        restricted_import = safe_builtins["__import__"]
        with pytest.raises(ImportError, match="not allowed"):
            restricted_import("os")
        with pytest.raises(ImportError, match="not allowed"):
            restricted_import("subprocess")

    def test_custom_import_allows_whitelisted(self, safe_builtins: dict) -> None:
        """Whitelisted modules should import without error."""
        restricted_import = safe_builtins["__import__"]
        math_mod = restricted_import("math")
        assert math_mod.__name__ == "math"

    def test_extra_allowed_merged(self) -> None:
        extra = {"type", "hash"}
        sb = build_safe_builtins(extra_allowed=extra)
        assert "type" in sb
        assert "hash" in sb


# ---------------------------------------------------------------------------
# safe_exec_code
# ---------------------------------------------------------------------------

class TestSafeExecCode:
    """Execute code inside the sandbox."""

    def test_simple_code_success(self) -> None:
        env: dict = {}
        result = safe_exec_code("x = 42", exec_globals=env, timeout=5)
        assert result["success"] is True
        assert result["error"] is None

    def test_result_dict_contains_variables(self) -> None:
        env: dict = {}
        safe_exec_code("x = 10\ny = 20", exec_globals=env, timeout=5)
        assert env.get("x") == 10
        assert env.get("y") == 20

    def test_code_can_use_print(self, capsys: pytest.CaptureFixture) -> None:
        env: dict = {"__builtins__": build_safe_builtins()}
        result = safe_exec_code("print('hello')", exec_globals=env, timeout=5)
        assert result["success"] is True
        captured = capsys.readouterr()
        assert "hello" in captured.out

    def test_timeout_on_infinite_loop(self) -> None:
        env: dict = {"__builtins__": build_safe_builtins()}
        result = safe_exec_code(
            "while True: pass",
            exec_globals=env,
            timeout=1,
        )
        assert result["success"] is False
        assert result["error"] is not None
        assert "超时" in result["error"] or "timed out" in result["error"].lower()

    def test_runtime_error_caught(self) -> None:
        env: dict = {"__builtins__": build_safe_builtins()}
        result = safe_exec_code("1 / 0", exec_globals=env, timeout=5)
        assert result["success"] is False
        assert result["error"] is not None
        assert "ZeroDivisionError" in result["error"]

    def test_syntax_error_caught(self) -> None:
        env: dict = {}
        result = safe_exec_code("def foo(:", exec_globals=env, timeout=5)
        assert result["success"] is False
        assert result["error"] is not None

    def test_exec_locals_independent_of_globals(self) -> None:
        globals_env: dict = {}
        locals_env: dict = {}
        result = safe_exec_code(
            "local_var = 99",
            exec_globals=globals_env,
            exec_locals=locals_env,
            timeout=5,
        )
        assert result["success"] is True
        assert locals_env.get("local_var") == 99
        assert "local_var" not in globals_env
