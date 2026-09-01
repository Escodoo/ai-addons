Add the bot user (the user holding the chatter AI bridge) and the humans who
should follow the conversation to the gateway members, or let operators join
the livechat conversation as usual. No further configuration is needed.

Joining a conversation does not stop the assistant, so a human can simply
watch it work.

## Taking over the conversation

The assistant is paused automatically as soon as an internal user writes a
message in the conversation from Odoo. From that point on the human is
responsible for the answers.

Use the **Resume AI** action in the conversation header to give the
conversation back to the assistant. The **Pause AI** action pauses it without
sending anything to the customer, which is useful before taking over.

On a gateway conversation a note records who paused or resumed the assistant.
The note is never forwarded to the external service. Livechat conversations get
no such note, because the visitor reads the channel itself and the note would
be shown to them; there the header action reflects the current state instead.

While the assistant is paused:

- incoming customer messages are still received and stored as usual;
- no AI bridge execution is created for the conversation;
- everything the human writes is delivered to the customer through the
  gateway or livechat, as usual.

## Notes

Messages the assistant would consider are only the ones coming from the
customer of that conversation. Portal users, partners without a user and
guests are all treated as the customer side. Inbound gateway posts (Telegram,
WhatsApp) are always the customer, even when the webhook leaves the author
empty or attributes the line to the bot user.

Livechat conversations that are already closed never trigger the assistant.

This module does not coordinate with the native livechat chatbot scripts. Use
either the chatbot script or the AI bridge bot on a given livechat channel,
not both.
