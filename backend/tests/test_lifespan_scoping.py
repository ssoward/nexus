"""Regression guard for the lifespan shutdown UnboundLocalError.

The app lifespan assigns module-level task handles (e.g. ``_tls_task``,
``_watchdog_task``) only inside conditional startup branches, then reads them
during shutdown. If such a name is assigned without a matching ``global``
declaration, Python treats it as a function-local for the whole function and
the shutdown read raises ``UnboundLocalError`` whenever the startup branch did
not run (e.g. TLS auto-renewal disabled). The test suite builds the app
without the lifespan, so this is the only coverage of that scoping invariant.
"""

import ast
import pathlib


def test_lifespan_assigned_module_tasks_are_declared_global():
    main_py = pathlib.Path(__file__).resolve().parent.parent / "app" / "main.py"
    tree = ast.parse(main_py.read_text())

    lifespan = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "lifespan"
    )

    declared_global = set()
    assigned = set()
    for node in ast.walk(lifespan):
        if isinstance(node, ast.Global):
            declared_global.update(node.names)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            assigned.add(node.id)

    # Module-level task handles read during shutdown.
    task_vars = {"_tls_task", "_watchdog_task"}
    for var in task_vars & assigned:
        assert var in declared_global, (
            f"{var} is assigned in lifespan() but not declared global; "
            "reading it during shutdown will raise UnboundLocalError when the "
            "startup branch that assigns it does not run."
        )
