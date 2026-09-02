Add the bot user (the user holding the chatter AI bridge) to the operators of
the livechat channel. No further configuration is needed.

Everything an operator writes is read by the visitor, so the first message
pauses the assistant and hands the conversation over. Use the **Resume AI**
action in the conversation header to give it back; the action reflects the
current state, since no note is posted in the conversation.

This module does not coordinate with the native livechat chatbot scripts. Use
either the chatbot script or the AI bridge bot on a given livechat channel, not
both.
