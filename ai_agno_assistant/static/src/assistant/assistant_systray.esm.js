// Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
// License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import {Component, markup, useState} from "@odoo/owl";
import {_t} from "@web/core/l10n/translation";
import {browser} from "@web/core/browser/browser";
import {registry} from "@web/core/registry";
import {user} from "@web/core/user";
import {useService} from "@web/core/utils/hooks";

let assistantMessageSeq = 0;

function nextAssistantMessageId() {
    assistantMessageSeq += 1;
    return `assistant-msg-${assistantMessageSeq}`;
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
            messages: [],
            draft: "",
        });
    }

    get canSend() {
        return Boolean(!this.state.loading && (this.state.draft || "").trim());
    }

    get canCopyBody() {
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
        this.state.messages = [...this.state.messages, message];
        return message;
    }

    _buildHistoryPayload() {
        return this.state.messages.slice(-10).map((message) => ({
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
        this.state.messages = [];
        this.state.draft = "";
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
