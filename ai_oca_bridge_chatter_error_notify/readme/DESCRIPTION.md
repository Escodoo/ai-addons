When a chatter AI bridge execution fails, users are left with a stuck typing
indicator and no feedback in the conversation.

This module posts the error in the Discuss channel as the bot user and clears
the typing indicator, extracting a short user-facing message from the bridge
HTTP body (JSON `detail` field when available). It works with any chatter
bridge, regardless of the AI runtime behind it.
