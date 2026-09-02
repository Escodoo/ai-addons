Add the bot user (the user holding the chatter AI bridge) and the humans who
should follow the conversation to the members of the gateway. No further
configuration is needed.

Everything an operator writes in the conversation is delivered to the external
contact, so the first message pauses the assistant and hands the conversation
over. Use the **Resume AI** action in the conversation header to give it back.

A note records who paused or resumed the assistant. The gateway does not
forward notification messages, so the note stays between the operators.

Inbound messages are always treated as coming from the customer, even when the
webhook leaves the author empty or attributes the line to the bot user.
