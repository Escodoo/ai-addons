# Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""Declarative registry of typed methods exposed on /agno/rpc."""

AGNO_TOOLS = {}


def agno_tool(model="ai.assistant", *, args=(), description=""):
    """Register an ORM helper as an Agno-callable tool."""

    def decorator(func):
        AGNO_TOOLS.setdefault(model, {})[func.__name__] = {
            "method": func.__name__,
            "args": list(args),
            "description": description
            or (func.__doc__ or "").strip().split("\n", maxsplit=1)[0],
        }
        return func

    return decorator


def get_tools_catalog():
    catalog = []
    for model, methods in AGNO_TOOLS.items():
        for spec in methods.values():
            catalog.append({"model": model, **spec})
    return catalog


def allowed_methods_for(model):
    return frozenset(AGNO_TOOLS.get(model, {}))
