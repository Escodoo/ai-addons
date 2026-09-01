Add the bot user (the user holding the chatter AI bridge) and the humans who
should follow the conversation to the members of the conversation. No further
configuration is needed.

Joining a conversation does not stop the assistant, so a human can simply
watch it work.

## Taking over the conversation

The assistant is paused automatically as soon as an internal user writes a
message in the conversation from Odoo. From that point on the human is
responsible for the answers.

Use the **Resume AI** action in the conversation header to give the
conversation back to the assistant. The **Pause AI** action pauses it without
sending anything to the customer, which is useful before taking over.

A note records who paused or resumed the assistant. Channel types whose
customer reads the channel itself, such as livechat, get no note so the
handoff is not disclosed; there the header action reflects the current state
instead.

While the assistant is paused:

- incoming customer messages are still received and stored as usual;
- no AI bridge execution is created for the conversation;
- everything the human writes is delivered to the customer as usual.

## Notes

Messages the assistant would consider are only the ones coming from the
customer of that conversation. Portal users, partners without a user and
guests are all treated as the customer side.
