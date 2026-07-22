Adds a **Provider** selection on AI bridges (`ai.bridge`) identifying which
AI runtime the bridge targets (default: `Generic`).

Integration modules extend the selection with their own value and gate their
`ai.bridge.execution` overrides (extra payload fields, identity signing,
timeouts) on it, so provider-specific behaviour never leaks into bridges of
other runtimes.
