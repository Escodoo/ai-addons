Glue between `ai_oca_bridge_chatter_copilot` and `im_livechat`: it declares
livechat channels as customer conversations, so a chatter AI bridge keeps
answering the website visitor after an operator joins the conversation, and an
operator can take over at any time.

Closed conversations never trigger the assistant, and the handoff is not
recorded as a note because the visitor reads the channel itself.
