1. Install this module (and its dependencies: `ai_oca_bridge_document_page`,
   `document_page_tag`, `agno_connector`).
2. Configure each bridge auth token (see CONFIGURE).
3. Create or edit a Knowledge page with `type=content` and tag it according to
   the audience of the content:

   | Tag          | Intended content                                      |
   | ------------ | ----------------------------------------------------- |
   | `processes`  | Internal SOPs (ops agent only)                        |
   | `legal`      | Contracts / compliance notes (ops and sales agents)   |
   | `support`    | Customer helpdesk FAQs and manuals                    |
   | `commercial` | Sales playbooks and commercial policies               |
   | `public`     | Content safe for anonymous website / livechat visitors|

4. On create, write or unlink, the matching bridge runs. Check
   *Settings → Technical → AI Bridge Executions* for a successful call.

Synced content is indexed in Agno under the stable name `document.page:{id}`.
Pages that do not match the bridge domain (`type=content` + tag) are ignored.

Editorial rule: never put internal SOPs on `public` or `support`.
