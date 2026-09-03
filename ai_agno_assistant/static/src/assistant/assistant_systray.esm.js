// Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
// License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import {
    Component,
    markup,
    onMounted,
    onWillUnmount,
    useEffect,
    useRef,
    useState,
} from "@odoo/owl";
import {_t} from "@web/core/l10n/translation";
import {browser} from "@web/core/browser/browser";
import {ConfirmationDialog} from "@web/core/confirmation_dialog/confirmation_dialog";
import {registry} from "@web/core/registry";
import {useService} from "@web/core/utils/hooks";
import {user} from "@web/core/user";

let assistantMessageSeq = 0;

const HISTORY_LIMIT = 20;
const STORAGE_KEY_PREFIX = "ai_agno_assistant.chat";
const SESSION_KEY_PREFIX = "ai_agno_assistant.session";

const AUTO_NAV_TYPES = new Set([
    "open_action",
    "open_action_ref",
    "open_menu",
    "open_record",
    "open_last_draft",
]);

const SUGGESTIONS = [
    {label: _t("What needs attention?"), prompt: "What needs my attention today?"},
    {
        label: _t("Weekly briefing"),
        prompt: "Give me an executive briefing of this week.",
    },
    {label: _t("Explain this record"), prompt: "Explain the record I am looking at."},
    {label: _t("Prepare an RFQ"), prompt: "Help me prepare a draft RFQ."},
];

function nextAssistantMessageId() {
    assistantMessageSeq += 1;
    return `assistant-msg-${assistantMessageSeq}`;
}

function storageKey() {
    return `${STORAGE_KEY_PREFIX}.${user.userId || "anonymous"}`;
}

function sessionStorageKey() {
    return `${SESSION_KEY_PREFIX}.${user.userId || "anonymous"}`;
}

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
    container.querySelectorAll("a").forEach((el) => {
        const href = (el.getAttribute("href") || "").toLowerCase();
        if (
            href.includes("/web#") ||
            (href.includes("id=") && href.includes("model="))
        ) {
            el.remove();
        }
    });
    return container.innerHTML;
}

function buildMessage({role, text, isHtml = false, actions = []}) {
    const safeText = isHtml && role === "assistant" ? sanitizeStoredHtml(text) : text;
    return {
        id: nextAssistantMessageId(),
        role,
        text: safeText,
        html: isHtml ? markup(safeText) : markup(""),
        isHtml: Boolean(isHtml),
        actions: Array.isArray(actions) ? actions : [],
    };
}

function restoreStoredMessage(entry) {
    if (!entry || typeof entry !== "object") {
        return null;
    }
    const role = entry.role;
    const text = typeof entry.text === "string" ? entry.text.trim() : "";
    if ((role !== "user" && role !== "assistant") || !text) {
        return null;
    }
    const message = buildMessage({
        role,
        text,
        isHtml: Boolean(entry.isHtml) && role === "assistant",
        actions: entry.actions,
    });
    return message.text ? message : null;
}

function loadStoredMessages() {
    try {
        const raw = browser.localStorage.getItem(storageKey());
        const parsed = raw ? JSON.parse(raw) : null;
        if (!Array.isArray(parsed)) {
            return [];
        }
        return parsed.slice(-HISTORY_LIMIT).map(restoreStoredMessage).filter(Boolean);
    } catch {
        return [];
    }
}

function loadStoredSessionKey() {
    try {
        return browser.localStorage.getItem(sessionStorageKey()) || "";
    } catch {
        return "";
    }
}

function persistMessages(messages) {
    try {
        const payload = (messages || []).slice(-HISTORY_LIMIT).map((message) => ({
            role: message.role,
            text: message.text,
            isHtml: Boolean(message.isHtml),
            actions: message.actions || [],
        }));
        browser.localStorage.setItem(storageKey(), JSON.stringify(payload));
    } catch {
        // Quota / private mode: keep the in-memory conversation only.
    }
}

function persistSessionKey(sessionKey) {
    try {
        if (sessionKey) {
            browser.localStorage.setItem(sessionStorageKey(), sessionKey);
        }
    } catch {
        // Ignore storage failures.
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
        this.dialog = useService("dialog");
        this.state = useState({
            panelOpen: false,
            loading: false,
            statusText: "",
            messages: loadStoredMessages(),
            draft: "",
            sessionKey: loadStoredSessionKey(),
            sessions: [],
        });
        this.panelBodyRef = useRef("panelBody");
        this.draftInputRef = useRef("draftInput");
        this.panelRef = useRef("panel");
        this._requestSeq = 0;
        this._elapsedTimer = null;
        this._onDocumentClick = this._onDocumentClick.bind(this);
        this._onDocumentKeydown = this._onDocumentKeydown.bind(this);
        useEffect(
            () => {
                const body = this.panelBodyRef.el;
                if (body) {
                    body.scrollTop = body.scrollHeight;
                }
            },
            () => [this.state.panelOpen, this.state.messages.length, this.state.loading]
        );
        useEffect(
            () => {
                const input = this.draftInputRef.el;
                if (this.state.panelOpen && input && !this.state.loading) {
                    input.focus();
                }
            },
            () => [this.state.panelOpen]
        );
        onMounted(() => {
            browser.addEventListener("click", this._onDocumentClick, true);
            browser.addEventListener("keydown", this._onDocumentKeydown, true);
        });
        onWillUnmount(() => {
            browser.removeEventListener("click", this._onDocumentClick, true);
            browser.removeEventListener("keydown", this._onDocumentKeydown, true);
            this._stopElapsed();
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

    get suggestions() {
        return SUGGESTIONS;
    }

    _htmlToPlainText(html) {
        const container = document.createElement("div");
        container.innerHTML = html || "";
        return this._nodeToMarkdown(container)
            .replace(/\n{3,}/g, "\n\n")
            .trim();
    }

    _nodeToMarkdown(node) {
        if (node.nodeType === Node.TEXT_NODE) {
            return (node.nodeValue || "").replace(/\s+/g, " ");
        }
        if (node.nodeType !== Node.ELEMENT_NODE) {
            return "";
        }
        const tag = node.tagName.toLowerCase();
        if (tag === "br") {
            return "\n";
        }
        const inner = Array.from(node.childNodes)
            .map((child) => this._nodeToMarkdown(child))
            .join("");
        if (tag === "b" || tag === "strong") {
            return inner.trim() ? `**${inner.trim()}**` : "";
        }
        if (tag === "i" || tag === "em") {
            return inner.trim() ? `*${inner.trim()}*` : "";
        }
        if (tag === "code") {
            return inner.trim() ? `\`${inner.trim()}\`` : "";
        }
        if (tag === "a") {
            const href = (node.getAttribute("href") || "").trim();
            const label = inner.trim() || href;
            if (href && /^(https?:|mailto:|\/)/i.test(href)) {
                return `[${label}](${href})`;
            }
            return label;
        }
        if (tag === "li") {
            const bullet = node.parentElement?.tagName === "OL" ? "1. " : "- ";
            return `${bullet}${inner.trim()}\n`;
        }
        if (tag === "tr") {
            const cellEls = Array.from(node.children).filter((child) =>
                ["TD", "TH"].includes(child.tagName)
            );
            const cells = cellEls.map((child) => this._nodeToMarkdown(child).trim());
            if (!cells.some(Boolean)) {
                return "";
            }
            const row = `| ${cells.join(" | ")} |`;
            const isHeader =
                cellEls.some((child) => child.tagName === "TH") ||
                node.parentElement?.tagName === "THEAD";
            if (isHeader) {
                return `${row}\n| ${cells.map(() => "---").join(" | ")} |\n`;
            }
            return `${row}\n`;
        }
        if (tag === "h1" || tag === "h2" || tag === "h3" || tag === "h4") {
            const level = Number(tag[1]);
            return `${"#".repeat(level)} ${inner.trim()}\n\n`;
        }
        if (tag === "blockquote") {
            return `> ${inner.trim()}\n\n`;
        }
        if (tag === "pre") {
            return `\`\`\`\n${inner.trim()}\n\`\`\`\n\n`;
        }
        if (["p", "div"].includes(tag)) {
            return `${inner.trim()}\n\n`;
        }
        if (tag === "ul" || tag === "ol" || tag === "table") {
            return `${inner.trim()}\n\n`;
        }
        return inner;
    }

    _appendMessage(role, content, extras = {}) {
        const message = buildMessage({
            role,
            text: (content || "").trim(),
            isHtml: extras.html,
            actions: extras.actions,
        });
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
            session_key: this.state.sessionKey || false,
        };
    }

    _onDocumentClick(ev) {
        if (!this.state.panelOpen) {
            return;
        }
        const root = this.el;
        if (root && !root.contains(ev.target)) {
            this.closePanel();
        }
    }

    _onDocumentKeydown(ev) {
        if (ev.key === "Escape" && this.state.panelOpen) {
            ev.preventDefault();
            if (this.state.loading) {
                this.cancelRequest();
            } else {
                this.closePanel();
            }
        }
    }

    onPanelClick() {
        // Keep clicks inside the floating panel from closing it.
    }

    togglePanel() {
        if (this.state.panelOpen) {
            this.closePanel();
        } else {
            this.openPanel();
        }
    }

    async openPanel() {
        this.state.panelOpen = true;
        this._refreshSessions();
    }

    closePanel() {
        this.state.panelOpen = false;
        this.state.draft = "";
        if (this.state.loading) {
            this.cancelRequest();
        }
    }

    cancelRequest() {
        this._requestSeq += 1;
        this._stopElapsed();
        this.state.loading = false;
        this.state.statusText = "";
    }

    _startElapsed() {
        this._stopElapsed();
        const started = Date.now();
        this.state.statusText = _t("Thinking…");
        this._elapsedTimer = browser.setInterval(() => {
            const seconds = Math.floor((Date.now() - started) / 1000);
            this.state.statusText = _t("Consulting Odoo… %ss", seconds);
        }, 1000);
    }

    _stopElapsed() {
        if (this._elapsedTimer) {
            browser.clearInterval(this._elapsedTimer);
            this._elapsedTimer = null;
        }
        this.state.statusText = "";
    }

    async _refreshSessions() {
        try {
            this.state.sessions = await this.orm.call(
                "ai.assistant",
                "action_ai_list_sessions",
                [8]
            );
        } catch {
            this.state.sessions = [];
        }
    }

    async onSelectSession(ev) {
        const key = ev.target.value;
        if (!key) {
            return;
        }
        await this.loadSession(key);
    }

    async loadSession(sessionKey) {
        try {
            const result = await this.orm.call(
                "ai.assistant",
                "action_ai_load_session",
                [sessionKey]
            );
            this.state.sessionKey = result?.session_key || sessionKey;
            persistSessionKey(this.state.sessionKey);
            const messages = (result?.messages || [])
                .map(restoreStoredMessage)
                .filter(Boolean);
            this.state.messages = messages;
            persistMessages(this.state.messages);
        } catch (error) {
            this.notification.add(
                error.data?.message ||
                    error.message ||
                    _t("Could not load the conversation."),
                {type: "danger"}
            );
        }
    }

    async startNewSession() {
        try {
            const result = await this.orm.call(
                "ai.assistant",
                "action_ai_new_session",
                []
            );
            this.state.sessionKey = result?.session_key || "";
            persistSessionKey(this.state.sessionKey);
            this.state.messages = [];
            this.state.draft = "";
            clearStoredMessages();
            await this._refreshSessions();
        } catch (error) {
            this.notification.add(
                error.data?.message ||
                    error.message ||
                    _t("Could not start a conversation."),
                {type: "danger"}
            );
        }
    }

    deleteConversation() {
        if (!this.canClearChat) {
            return;
        }
        this.dialog.add(ConfirmationDialog, {
            title: _t("Delete conversation"),
            body: _t("This conversation will be permanently deleted."),
            confirmLabel: _t("Delete"),
            confirm: () => this._deleteCurrentSession(),
        });
    }

    async _deleteCurrentSession() {
        const sessionKey = this.state.sessionKey;
        try {
            if (sessionKey) {
                await this.orm.call("ai.assistant", "action_ai_delete_session", [
                    sessionKey,
                ]);
            }
            this.state.messages = [];
            this.state.draft = "";
            clearStoredMessages();
            await this.startNewSession();
        } catch (error) {
            this.notification.add(
                error.data?.message ||
                    error.message ||
                    _t("Could not delete the conversation."),
                {type: "danger"}
            );
        }
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

    async _copyTextToClipboard(text, html = "") {
        const value = (text || "").trim();
        if (!value) {
            return;
        }
        try {
            const clipboard = browser.navigator.clipboard;
            const ClipboardItemClass =
                browser.ClipboardItem || globalThis.ClipboardItem;
            if (html && clipboard.write && ClipboardItemClass) {
                await clipboard.write([
                    new ClipboardItemClass({
                        "text/plain": new Blob([value], {type: "text/plain"}),
                        "text/html": new Blob([html], {type: "text/html"}),
                    }),
                ]);
            } else {
                await clipboard.writeText(value);
            }
            this.notification.add(_t("Copied to clipboard."), {type: "success"});
        } catch {
            try {
                await browser.navigator.clipboard.writeText(value);
                this.notification.add(_t("Copied to clipboard."), {type: "success"});
            } catch {
                this.notification.add(_t("Could not copy to the clipboard."), {
                    type: "danger",
                });
            }
        }
    }

    copyMessage(message) {
        const html = message?.isHtml ? message.text : "";
        return this._copyTextToClipboard(this._messagePlainText(message), html);
    }

    copyBody() {
        if (!this.canCopyBody) {
            return;
        }
        const parts = this.state.messages.map((message) => {
            const label = message.role === "user" ? _t("You") : _t("AI");
            return `${label}:\n${this._messagePlainText(message)}`;
        });
        const html = this.state.messages
            .map((message) => {
                const label = message.role === "user" ? _t("You") : _t("AI");
                const body = message.isHtml
                    ? message.text
                    : `<p>${this._escapeHtml(message.text)}</p>`;
                return `<p><b>${this._escapeHtml(label)}:</b></p>${body}`;
            })
            .join("");
        return this._copyTextToClipboard(parts.join("\n\n"), html);
    }

    _escapeHtml(value) {
        return (value || "")
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;");
    }

    actionLabel(entry) {
        return entry?.label || entry?.name || _t("Open");
    }

    _exportTitle(message) {
        const text = this._messagePlainText(message);
        const heading = text.match(/^#+\s+(.+)$/m);
        return ((heading && heading[1]) || "Assistant briefing").trim().slice(0, 80);
    }

    _exportFilename(title, suffix) {
        const cleaned =
            (title || "assistant-briefing")
                .replace(/[^A-Za-z0-9._-]+/g, "-")
                .replace(/^[-._]+|[-._]+$/g, "") || "assistant-briefing";
        const name = cleaned.slice(0, 80);
        return name.toLowerCase().endsWith(suffix) ? name : `${name}${suffix}`;
    }

    _downloadBlob(filename, blob) {
        const href = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = href;
        link.download = filename;
        link.rel = "noopener";
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(href);
    }

    _base64ToUint8Array(value) {
        const binary = atob(value || "");
        const bytes = new Uint8Array(binary.length);
        for (let index = 0; index < binary.length; index += 1) {
            bytes[index] = binary.charCodeAt(index);
        }
        return bytes;
    }

    exportMessageMarkdown(message) {
        const text = this._messagePlainText(message);
        if (!text) {
            this.notification.add(_t("Nothing to export."), {type: "warning"});
            return;
        }
        const filename = this._exportFilename(this._exportTitle(message), ".md");
        this._downloadBlob(
            filename,
            new Blob([`${text}\n`], {type: "text/markdown;charset=utf-8"})
        );
    }

    async exportMessagePdf(message) {
        const content = message?.isHtml
            ? message.text
            : this._messagePlainText(message);
        if (!(content || "").trim()) {
            this.notification.add(_t("Nothing to export."), {type: "warning"});
            return;
        }
        try {
            const result = await this.orm.call(
                "ai.assistant",
                "action_ai_export_message",
                [content, this._exportTitle(message), "pdf"]
            );
            if (!result?.datas) {
                this.notification.add(_t("Could not export the message."), {
                    type: "danger",
                });
                return;
            }
            this._downloadBlob(
                result.filename ||
                    this._exportFilename(this._exportTitle(message), ".pdf"),
                new Blob([this._base64ToUint8Array(result.datas)], {
                    type: result.mimetype || "application/pdf",
                })
            );
        } catch (error) {
            this.notification.add(
                error.data?.message ||
                    error.message ||
                    _t("Could not export the message."),
                {type: "danger"}
            );
        }
    }

    isAutoNavigable(entry) {
        return AUTO_NAV_TYPES.has(entry?.type) && Boolean(entry?.action);
    }

    async runChipAction(entry) {
        if (entry?.type === "confirm_pending") {
            return;
        }
        if (!entry?.action) {
            return;
        }
        await this.action.doAction(entry.action);
        this.state.panelOpen = true;
        this.notification.add(_t("Opening the requested screen…"), {type: "info"});
    }

    async _autoRunNavigation(actions) {
        const entry = (actions || []).find((item) => this.isAutoNavigable(item));
        if (!entry) {
            return;
        }
        await this.runChipAction(entry);
    }

    async confirmPending(accepted) {
        this.state.loading = true;
        try {
            const result = await this.orm.call(
                "ai.assistant",
                "action_ai_execute_pending",
                [accepted]
            );
            if (result?.error) {
                this.notification.add(result.detail || result.error, {type: "warning"});
                return;
            }
            if (result?.cancelled) {
                this._appendMessage(
                    "assistant",
                    _t("The pending action was cancelled."),
                    {
                        html: false,
                    }
                );
                return;
            }
            const actions = [];
            if (result?.open_record) {
                const sanitized = {
                    type: "open_record",
                    model: result.open_record.model,
                    res_id: result.open_record.res_id,
                    label: result.name,
                    action: {
                        type: "ir.actions.act_window",
                        res_model: result.open_record.model,
                        res_id: result.open_record.res_id,
                        view_mode: "form",
                        views: [[false, "form"]],
                        target: "current",
                    },
                };
                actions.push(sanitized);
            }
            this._appendMessage(
                "assistant",
                result?.name
                    ? _t("%s is now %s.", result.name, result.state || "confirmed")
                    : _t("The action completed."),
                {html: false, actions}
            );
        } catch (error) {
            this.notification.add(
                error.data?.message ||
                    error.message ||
                    _t("Could not confirm the action."),
                {type: "danger"}
            );
        } finally {
            this.state.loading = false;
        }
    }

    useSuggestion(prompt) {
        this.state.draft = prompt;
        this.sendMessage();
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
        const seq = (this._requestSeq += 1);
        this._startElapsed();
        try {
            const history = this._buildHistoryPayload().slice(0, -1);
            const result = await this.orm.call("ai.assistant", "action_ai_chat", [
                question,
                history,
                this._buildUiContext(),
            ]);
            if (seq !== this._requestSeq) {
                return;
            }
            if (result?.session_key) {
                this.state.sessionKey = result.session_key;
                persistSessionKey(this.state.sessionKey);
            }
            this._appendMessage(
                "assistant",
                result?.body || _t("No response was returned."),
                {
                    html: Boolean(result?.body_is_html),
                    actions: result?.actions || [],
                }
            );
            await this._autoRunNavigation(result?.actions);
            await this._refreshSessions();
        } catch (error) {
            if (seq !== this._requestSeq) {
                return;
            }
            this.notification.add(
                error.data?.message || error.message || _t("AI request failed."),
                {type: "danger"}
            );
        } finally {
            if (seq === this._requestSeq) {
                this._stopElapsed();
                this.state.loading = false;
            }
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
