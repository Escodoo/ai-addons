

# AI Odoo Addons
<!-- /!\ Non OCA Context : Set here the badge of your runbot / runboat instance. -->
[![Pre-commit Status](https://github.com/Escodoo/ai-addons/actions/workflows/pre-commit.yml/badge.svg?branch=18.0)](https://github.com/Escodoo/ai-addons/actions/workflows/pre-commit.yml?query=branch%3A18.0)
[![Build Status](https://github.com/Escodoo/ai-addons/actions/workflows/test.yml/badge.svg?branch=18.0)](https://github.com/Escodoo/ai-addons/actions/workflows/test.yml?query=branch%3A18.0)
[![codecov](https://codecov.io/gh/Escodoo/ai-addons/branch/18.0/graph/badge.svg)](https://codecov.io/gh/Escodoo/ai-addons)
<!-- /!\ Non OCA Context : Set here the badge of your translation instance. -->

<!-- /!\ do not modify above this line -->

AI Odoo Addons

<!-- /!\ do not modify below this line -->

<!-- prettier-ignore-start -->

[//]: # (addons)

Available addons
----------------
addon | version | maintainers | summary
--- | --- | --- | ---
[ai_agno_chatter_bots](ai_agno_chatter_bots/) | 18.0.1.3.0 | <a href='https://github.com/marcelsavegnago'><img src='https://github.com/marcelsavegnago.png' width='32' height='32' style='border-radius:50%;' alt='marcelsavegnago'/></a> | Provision Discuss chatter bots and AI bridges for Agno personas
[ai_agno_connector](ai_agno_connector/) | 18.0.1.3.0 | <a href='https://github.com/marcelsavegnago'><img src='https://github.com/marcelsavegnago.png' width='32' height='32' style='border-radius:50%;' alt='marcelsavegnago'/></a> | RPC gateway that runs AI agent queries with the identity of the requesting user, enforcing ACLs and record rules
[ai_agno_document_page_kb](ai_agno_document_page_kb/) | 18.0.1.6.2 | <a href='https://github.com/marcelsavegnago'><img src='https://github.com/marcelsavegnago.png' width='32' height='32' style='border-radius:50%;' alt='marcelsavegnago'/></a> | Sync document.page records to Agno knowledge bases via AI bridges
[ai_agno_llm_settings](ai_agno_llm_settings/) | 18.0.1.7.0 | <a href='https://github.com/marcelsavegnago'><img src='https://github.com/marcelsavegnago.png' width='32' height='32' style='border-radius:50%;' alt='marcelsavegnago'/></a> | Bring-your-own-key LLM and embedder settings for Agno (Ollama / OpenAI / Gemini)
[ai_agno_thread_bridge_base](ai_agno_thread_bridge_base/) | 18.0.1.1.2 | <a href='https://github.com/marcelsavegnago'><img src='https://github.com/marcelsavegnago.png' width='32' height='32' style='border-radius:50%;' alt='marcelsavegnago'/></a> | Base Agno thread bridges for Odoo base models (Partner Analysis)
[ai_agno_thread_bridge_crm](ai_agno_thread_bridge_crm/) | 18.0.1.0.2 | <a href='https://github.com/marcelsavegnago'><img src='https://github.com/marcelsavegnago.png' width='32' height='32' style='border-radius:50%;' alt='marcelsavegnago'/></a> | Agno thread bridge for CRM leads and opportunities
[ai_agno_thread_bridge_helpdesk_mgmt](ai_agno_thread_bridge_helpdesk_mgmt/) | 18.0.1.0.2 | <a href='https://github.com/marcelsavegnago'><img src='https://github.com/marcelsavegnago.png' width='32' height='32' style='border-radius:50%;' alt='marcelsavegnago'/></a> | Agno thread bridge for OCA helpdesk_mgmt tickets
[ai_oca_bridge_chatter_error_notify](ai_oca_bridge_chatter_error_notify/) | 18.0.1.0.0 | <a href='https://github.com/marcelsavegnago'><img src='https://github.com/marcelsavegnago.png' width='32' height='32' style='border-radius:50%;' alt='marcelsavegnago'/></a> | Post chatter bridge failures in the Discuss channel and clear the typing indicator
[ai_oca_bridge_provider](ai_oca_bridge_provider/) | 18.0.1.0.0 | <a href='https://github.com/marcelsavegnago'><img src='https://github.com/marcelsavegnago.png' width='32' height='32' style='border-radius:50%;' alt='marcelsavegnago'/></a> | Mark which AI runtime each AI bridge targets so integrations can scope their behaviour per bridge
[ai_oca_bridge_request_timeout](ai_oca_bridge_request_timeout/) | 18.0.1.0.0 | <a href='https://github.com/marcelsavegnago'><img src='https://github.com/marcelsavegnago.png' width='32' height='32' style='border-radius:50%;' alt='marcelsavegnago'/></a> | Configure the HTTP request timeout per AI bridge

[//]: # (end addons)

<!-- prettier-ignore-end -->

## Licenses

This repository is licensed under [AGPL-3.0](LICENSE).

However, each module can have a totally different license, as long as they adhere to Escodoo
policy. Consult each module's `__manifest__.py` file, which contains a `license` key
that explains its license.

----
<!-- /!\ Non OCA Context : Set here the full description of your organization. -->
