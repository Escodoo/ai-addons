// Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
// License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import {Component, markup, useState} from "@odoo/owl";
import {browser} from "@web/core/browser/browser";
import {_t} from "@web/core/l10n/translation";
import {registry} from "@web/core/registry";
import {user} from "@web/core/user";
import {useService} from "@web/core/utils/hooks";

let assistantMessageSeq = 0;

const HISTORY_LIMIT = 10;
const STORAGE_KEY_PREFIX = "ai_agno_assistant.chat";

function nextAssistantMessageId() {
    assistantMessageSeq += 1;
    return `assistant-msg-${assistantMessageSeq}`;
}

function storageKey() {
    return `${STORAGE_KEY_PREFIX}.${user.userId || "anonymous"}`;
}

/**
 * Lightweight HTML cleanup for messages restored from localStorage.
 * Server responses are already sanitized; this covers tampered storage.
 */
function sanitizeStoredHtml(html) {
    const container = document.createElement("div");
    container.innerHTML = html || "";
    container
        .querySelectorAll("script,style,iframe,object,embed,link,meta")
        .forEach((el) => el.remove());
    for (const el of container.querySelectorAll("*")) {
        for (const attr of [...el.attributes]) {
            const name = attr.name.toLowerCase();
            if (
                name.startsWith("on") ||
                ((name === "href" || name === "src" || name === "xlink:href") &&
                    /^\s*javascript:/i.test(attr.value))
            ) {
                el.removeAttribute(attr.name);
            }
        }
    }
    return container.innerHTML;
}

function loadStoredMessages() {
    try {
        const raw = browser.localStorage.getItem(storageKey());
        if (!raw) {
            return [];
        }
        const parsed = JSON.parse(raw);
        if (!Array.isArray(parsed)) {
            return [];
        }
        const messages = [];
        for (const entry of parsed.slice(-HISTORY_LIMIT)) {
            if (!entry || typeof entry !== "object") {
                continue;
            }
            const role = entry.role;
            const text = typeof entry.text === "string" ? entry.text.trim() : "";
            if ((role !== "user" && role !== "assistant") || !text) {
                continue;
            }
            const isHtml = Boolean(entry.isHtml) && role === "assistant";
            const safeText = isHtml ? sanitizeStoredHtml(text) : text;
            if (!safeText) {
                continue;
            }
            messages.push({
                id: nextAssistantMessageId(),
                role,
                text: safeText,
                html: isHtml ? markup(safeText) : markup(""),
                isHtml,
            });
        }
        return messages;
    } catch {
        return [];
    }
}

function persistMessages(messages) {
    try {
        const payload = (messages || []).slice(-HISTORY_LIMIT).map((message) => ({
            role: message.role,
            text: message.text,
            isHtml: Boolean(message.isHtml),
        }));
        browser.localStorage.setItem(storageKey(), JSON.stringify(payload));
    } catch {
        // Quota / private mode: keep the in-memory conversation only.
    }
}

function clearStoredMessages() {
    try {
        browser.localStorage.removeItem(storageKey());
    } catch {
        // Ignore storage failures.
    }
}

export class AiAssistantSystray extends Component {
    static template = "ai_agno_assistant.Systray";
    static props = {};

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({
            panelOpen: false,
            loading: false,
            messages: loadStoredMessages(),
            draft: "",
        });
    }

    get canSend() {
        return Boolean(!this.state.loading && (this.state.draft || "").trim());
    }

    get canCopyBody() {
        return Boolean(!this.state.loading && this.state.messages.length);
    }

    get canClearChat() {
        return Boolean(!this.state.loading && this.state.messages.length);
    }

    _htmlToPlainText(html) {
        const container = document.createElement("div");
        container.innerHTML = html || "";
        const text = container.innerText || container.textContent || "";
        return text.replace(/\n{3,}/g, "\n\n").trim();
    }

    _appendMessage(role, content, {html = false} = {}) {
        const text = (content || "").trim();
        const message = {
            id: nextAssistantMessageId(),
            role,
            text,
            html: html ? markup(text) : markup(""),
            isHtml: Boolean(html),
        };
        this.state.messages = [...this.state.messages, message].slice(-HISTORY_LIMIT);
        persistMessages(this.state.messages);
        return message;
    }

    _buildHistoryPayload() {
        return this.state.messages.slice(-HISTORY_LIMIT).map((message) => ({
            role: message.role,
            content: message.isHtml
                ? this._htmlToPlainText(message.text)
                : message.text,
        }));
    }

    _buildUiContext() {
        const controller = this.action.currentController;
        const props = controller?.props || {};
        const currentAction = controller?.action || {};
        return {
            current_action: currentAction.xml_id || currentAction.name || false,
            current_model: props.resModel || currentAction.res_model || false,
            current_res_id: props.resId || false,
            company_id: user.context?.allowed_company_ids?.[0] || false,
        };
    }

    openPanel() {
        this.state.panelOpen = true;
    }

    closePanel() {
        this.state.panelOpen = false;
        this.state.loading = false;
        this.state.draft = "";
        // Keep messages so reopening restores the conversation.
    }

    clearChat() {
        if (!this.canClearChat) {
            return;
        }
        this.state.messages = [];
        this.state.draft = "";
        clearStoredMessages();
    }

    onDraftKeydown(ev) {
        if (ev.key === "Enter" && !ev.shiftKey) {
            ev.preventDefault();
            this.sendMessage();
        }
    }

    _messagePlainText(message) {
        if (!message) {
            return "";
        }
        return message.isHtml
            ? this._htmlToPlainText(message.text)
            : (message.text || "").trim();
    }

    async _copyTextToClipboard(text) {
        const value = (text || "").trim();
        if (!value) {
            return;
        }
        try {
            await browser.navigator.clipboard.writeText(value);
            this.notification.add(_t("Copied to clipboard."), {type: "success"});
        } catch {
            this.notification.add(_t("Could not copy to the clipboard."), {
                type: "danger",
            });
        }
    }

    async copyMessage(message) {
        await this._copyTextToClipboard(this._messagePlainText(message));
    }

    async copyBody() {
        if (!this.canCopyBody) {
            return;
        }
        const parts = this.state.messages.map((message) => {
            const label = message.role === "user" ? _t("You") : _t("AI");
            return `${label}:\n${this._messagePlainText(message)}`;
        });
        await this._copyTextToClipboard(parts.join("\n\n"));
    }

    async _applyAssistantActions(actions) {
        if (!Array.isArray(actions) || !actions.length) {
            return;
        }
        let applied = 0;
        for (const entry of actions) {
            const action = entry?.action;
            if (!action) {
                continue;
            }
            await this.action.doAction(action);
            applied += 1;
        }
        if (applied) {
            this.notification.add(_t("Opening the requested screen…"), {
                type: "info",
            });
        }
    }

    async sendMessage() {
        if (!this.canSend) {
            return;
        }
        const question = this.state.draft.trim();
        this.state.draft = "";
        this.state.panelOpen = true;
        this._appendMessage("user", question);
        this.state.loading = true;
        try {
            const history = this._buildHistoryPayload().slice(0, -1);
            const result = await this.orm.call("ai.assistant", "action_ai_chat", [
                question,
                history,
                this._buildUiContext(),
            ]);
            await this._applyAssistantActions(result?.actions);
            this._appendMessage(
                "assistant",
                result?.body || _t("No response was returned."),
                {html: true}
            );
        } catch (error) {
            this.notification.add(
                error.data?.message || error.message || _t("AI request failed."),
                {type: "danger"}
            );
        } finally {
            this.state.loading = false;
        }
    }
}

export const systrayItem = {
    Component: AiAssistantSystray,
    isDisplayed: () => user.hasGroup("ai_agno_assistant.group_system_ai_user"),
};

registry.category("systray").add("ai_agno_assistant.Systray", systrayItem, {
    sequence: 25,
});
