Adds a **Request Timeout** field on AI bridges (`ai.bridge`).

The upstream bridge hardcodes a 30s HTTP timeout, which LLM-backed endpoints
routinely exceed. This module lets each bridge configure its own timeout,
leaving bridges without a value on the default behaviour.
