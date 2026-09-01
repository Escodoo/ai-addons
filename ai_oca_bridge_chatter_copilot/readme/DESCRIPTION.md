`ai_oca_bridge_chatter` only lets a chatter AI bridge answer on its own in a
one-to-one conversation. As soon as a third member joins the channel, the bot
answers only when it is explicitly mentioned. Customer conversations coming
from a mail gateway (Telegram, WhatsApp) or from livechat never carry such a
mention, so adding a human to the conversation silently stops the assistant.

This module treats gateway and livechat channels as customer conversations
instead of internal group channels:

- the assistant answers the customer regardless of how many members the
  channel has;
- it answers only the customer of that conversation, so operators can talk in
  the channel without the bot replying to them;
- the customer side is determined by the role in the conversation, not by the
  contact record, so it keeps working after the gateway contact is linked to a
  partner or gets a portal user;
- a human can take over (copilot) and give the conversation back to the
  assistant at any time.
