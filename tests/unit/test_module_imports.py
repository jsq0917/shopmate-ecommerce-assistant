"""Regression: bare imports of RAG modules must not depend on import order.

History: ``safety.output_guard`` used to import the answer guards from
``rag.policy_qa``, closing the cycle ``policy_qa -> retrieval -> repositories ->
models -> safety -> output_guard -> policy_qa``. In a fresh interpreter a bare
``import shopmate_ecommerce_assistant.rag.policy_qa`` then failed with
``ImportError: cannot import name ... (partially initialized module)``; it only
worked when something else happened to import ``safety`` first, which is exactly
the kind of landmine a new script or deployment tool steps on. The guards now
live in ``rag.answer_guards``; these tests keep that true by exercising the
previously-failing imports in fresh subprocesses, unaffected by whatever the
surrounding pytest process already imported.
"""

from __future__ import annotations

import subprocess
import sys

#: Modules that historically formed (or sat on) the cycle. Each must import cleanly
#: on its own in a fresh interpreter.
_CYCLE_MODULES = (
    "shopmate_ecommerce_assistant.rag.policy_qa",
    "shopmate_ecommerce_assistant.rag.answer_guards",
    "shopmate_ecommerce_assistant.safety.output_guard",
    "shopmate_ecommerce_assistant.main",
)

#: Importing output_guard must not even *transitively* pull in policy_qa — that edge
#: is what closed the cycle, so it is checked structurally via ``sys.modules``.
_GUARD_GRAPH_CHECK = (
    "import sys\n"
    "import shopmate_ecommerce_assistant.safety.output_guard\n"
    "assert 'shopmate_ecommerce_assistant.rag.policy_qa' not in sys.modules, (\n"
    "    'output_guard transitively imports policy_qa again — the cycle is back')\n"
)


def _run(code: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_cycle_modules_import_alone_in_a_fresh_interpreter() -> None:
    for module in _CYCLE_MODULES:
        completed = _run(f"import {module}")
        assert completed.returncode == 0, (
            f"bare `import {module}` failed in a fresh interpreter "
            f"(import-order cycle regression?):\n{completed.stderr}"
        )


def test_output_guard_does_not_import_policy_qa_anymore() -> None:
    completed = _run(_GUARD_GRAPH_CHECK)
    assert completed.returncode == 0, completed.stderr
