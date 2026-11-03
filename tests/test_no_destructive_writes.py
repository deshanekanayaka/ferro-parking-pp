"""Regression test for the CLAUDE.md rule: nothing under src/ may delete a
file or a directory, and nothing may touch data/runs except to create it."""
import ast
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src" / "ferro_parking"

FORBIDDEN_CALLS = {
    ("shutil", "rmtree"),
    ("os", "remove"),
    ("os", "rmdir"),
    ("os", "unlink"),
    ("os", "removedirs"),
}
FORBIDDEN_ATTRS = {"rmtree", "unlink", "rmdir"}


def _call_names(node: ast.Call):
    """Return (module, attr) for `module.attr(...)`, or (None, attr) for `x.attr(...)`."""
    func = node.func
    if isinstance(func, ast.Attribute):
        if isinstance(func.value, ast.Name):
            return func.value.id, func.attr
        return None, func.attr
    return None, None


def test_no_destructive_calls_under_src():
    violations = []
    for path in SRC.rglob("*.py"):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            module, attr = _call_names(node)
            if (module, attr) in FORBIDDEN_CALLS or attr in FORBIDDEN_ATTRS:
                violations.append(f"{path.relative_to(SRC.parent.parent)}:{node.lineno} {module}.{attr}()")
    assert not violations, "Destructive delete call(s) found:\n" + "\n".join(violations)
