Glue between `ai_oca_bridge_chatter_copilot` and `mail_gateway`: it declares
gateway channels (Telegram, WhatsApp) as customer conversations, so a chatter
AI bridge keeps answering the external contact after a human joins the
conversation, and a human can take over at any time.

It also makes sure inbound webhook messages reach the assistant. Gateways
usually post them as the webhook user and leave the author empty, which
`ai_oca_bridge_chatter` reads as a message written by the bot itself and
therefore never answers.
