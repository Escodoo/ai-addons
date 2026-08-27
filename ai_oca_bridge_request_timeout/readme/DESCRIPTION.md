Adds a **Request Timeout** field on AI bridges (`ai.bridge`).

The upstream bridge hardcodes a 30s HTTP timeout, which LLM-backed endpoints
routinely exceed. This module lets each bridge configure its own timeout,
leaving bridges without a value on the default behaviour.

The field is injected through `_execute_kwargs`. A local `_execute` replica
remains until OCA `ai_oca_bridge` pops `timeout` from those kwargs instead of
hardcoding `timeout=30` (which would raise `TypeError`). After that upstream
change lands (OCA/ai#107), the replica can be deleted.
