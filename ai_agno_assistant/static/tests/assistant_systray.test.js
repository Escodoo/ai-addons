import {animationFrame, tick} from "@odoo/hoot-mock";
import {click, edit, press} from "@odoo/hoot-dom";
import {describe, expect, test} from "@odoo/hoot";
import {
    mockService,
    mountWithCleanup,
    patchWithCleanup,
} from "@web/../tests/web_test_helpers";
import {AiAssistantSystray} from "@ai_agno_assistant/assistant/assistant_systray.esm";
import {browser} from "@web/core/browser/browser";
import {defineMailModels} from "@mail/../tests/mail_test_helpers";

defineMailModels();
describe.current.tags("desktop");

function mockLocalStorage() {
    const store = {};
    patchWithCleanup(browser, {
        localStorage: {
            getItem(key) {
                return Object.prototype.hasOwnProperty.call(store, key)
                    ? store[key]
                    : null;
            },
            setItem(key, value) {
                store[key] = String(value);
            },
            removeItem(key) {
                delete store[key];
            },
        },
    });
    return store;
}

function mockAssistantServices({
    body = "<p>Hello</p>",
    bodyIsHtml = true,
    actions = [],
    error = null,
    sessions = [],
    confirmDelete = true,
    exportResult = null,
} = {}) {
    let sessionList = [...sessions];
    mockService("orm", {
        call: async (model, method, args) => {
            if (method === "action_ai_list_sessions") {
                return sessionList;
            }
            if (method === "action_ai_new_session") {
                return {session_key: "session-new", messages: []};
            }
            if (method === "action_ai_load_session") {
                return {session_key: "session-test-key", messages: []};
            }
            if (method === "action_ai_delete_session") {
                const key = args?.[0];
                sessionList = sessionList.filter((item) => item.session_key !== key);
                expect.step(`delete:${key}`);
                return {deleted: true, session_key: key};
            }
            if (method === "action_ai_execute_pending") {
                return {ok: true, name: "SO001", state: "sale"};
            }
            if (method === "action_ai_export_message") {
                expect.step(`export:${args?.[2] || "markdown"}`);
                return (
                    exportResult || {
                        filename: "assistant-briefing.pdf",
                        mimetype: "application/pdf",
                        datas: btoa("%PDF-1.4"),
                    }
                );
            }
            if (error) {
                throw error;
            }
            return {
                body,
                body_is_html: bodyIsHtml,
                actions,
                artifacts: [],
                session_key: "session-test-key",
            };
        },
    });
    mockService("action", {
        doAction: async (action) => {
            expect.step(`doAction:${action?.res_model || action?.type || "unknown"}`);
            return true;
        },
        currentController: null,
    });
    mockService("notification", {
        add: (message) => {
            expect.step(`notify:${message}`);
            return true;
        },
    });
    mockService("dialog", {
        add: (_component, props) => {
            if (confirmDelete) {
                props.confirm?.();
            }
            return true;
        },
    });
}

async function openPanelAndAsk(question) {
    await click(".o_ai_assistant_systray a");
    await animationFrame();
    await click(".o_ai_assistant_input");
    await edit(question, {confirm: false});
    await press("Enter");
    await tick();
    await animationFrame();
}

test("persists messages across remount and deletes the conversation", async () => {
    const store = mockLocalStorage();
    mockAssistantServices({
        sessions: [
            {id: 1, session_key: "session-test-key", name: "Hi there"},
            {id: 2, session_key: "session-other", name: "Other chat"},
        ],
    });

    await mountWithCleanup(AiAssistantSystray);
    await openPanelAndAsk("Hi there");
    expect(".o_ai_assistant_message").toHaveCount(2);
    expect(
        Object.keys(store).some((key) => key.startsWith("ai_agno_assistant.chat"))
    ).toBe(true);
    expect(".o_ai_assistant_sessions option").toHaveCount(3);

    await mountWithCleanup(AiAssistantSystray);
    await click(".o_ai_assistant_systray a");
    await animationFrame();
    expect(".o_ai_assistant_message").toHaveCount(2);

    await click("button[title='Delete conversation']");
    await tick();
    await animationFrame();
    expect(".o_ai_assistant_message").toHaveCount(0);
    expect(
        Object.keys(store).some((key) => key.startsWith("ai_agno_assistant.chat"))
    ).toBe(false);
    expect.verifySteps(["delete:session-test-key"]);
    expect(".o_ai_assistant_sessions option[value='session-test-key']").toHaveCount(0);
    expect(".o_ai_assistant_sessions option[value='session-other']").toHaveCount(1);
});

test("closing the panel keeps the conversation", async () => {
    mockLocalStorage();
    mockAssistantServices({body: "<p>Kept</p>"});

    await mountWithCleanup(AiAssistantSystray);
    await openPanelAndAsk("Keep me");
    expect(".o_ai_assistant_panel").toHaveCount(1);
    expect(".o_ai_assistant_message").toHaveCount(2);

    await click("button[title='Close']");
    await animationFrame();
    expect(".o_ai_assistant_panel").toHaveCount(0);

    await click(".o_ai_assistant_systray a");
    await animationFrame();
    expect(".o_ai_assistant_panel").toHaveCount(1);
    expect(".o_ai_assistant_message").toHaveCount(2);
});

test("the systray icon toggles the panel", async () => {
    mockLocalStorage();
    mockAssistantServices();

    await mountWithCleanup(AiAssistantSystray);
    await click(".o_ai_assistant_systray a");
    await animationFrame();
    expect(".o_ai_assistant_panel").toHaveCount(1);
    await click(".o_ai_assistant_systray a");
    await animationFrame();
    expect(".o_ai_assistant_panel").toHaveCount(0);
});

test("opening the panel focuses the composer", async () => {
    mockLocalStorage();
    mockAssistantServices();

    const assistant = await mountWithCleanup(AiAssistantSystray);
    expect(".o_ai_assistant_panel").toHaveCount(0);

    await click(".o_ai_assistant_systray a");
    await animationFrame();
    expect(".o_ai_assistant_panel").toHaveCount(1);
    expect(".o_ai_assistant_panel").toHaveAttribute("aria-label", "System assistant");
    expect(document.activeElement).toBe(assistant.draftInputRef.el);
});

test("the chat body auto-scrolls to the latest message", async () => {
    mockLocalStorage();
    mockAssistantServices();

    const assistant = await mountWithCleanup(AiAssistantSystray);
    assistant.openPanel();
    await animationFrame();

    const body = assistant.panelBodyRef.el;
    body.style.maxHeight = "96px";
    for (let index = 0; index < 12; index++) {
        assistant._appendMessage("assistant", `Answer ${index}`);
    }
    await animationFrame();

    expect(body.scrollTop).toBeGreaterThan(0);
    expect(body.scrollHeight - body.clientHeight - body.scrollTop).toBeLessThan(2);
});

test("renders plain text when body_is_html is false", async () => {
    mockLocalStorage();
    mockAssistantServices({
        body: "<b>not html</b>",
        bodyIsHtml: false,
    });

    await mountWithCleanup(AiAssistantSystray);
    await openPanelAndAsk("Plain please");
    expect(".o_ai_assistant_content").toHaveCount(2);
    expect(".o_ai_assistant_message_assistant .o_ai_assistant_content").toHaveText(
        "<b>not html</b>"
    );
});

test("notifies when the RPC fails", async () => {
    mockLocalStorage();
    mockAssistantServices({
        error: {message: "AI request failed.", data: {message: "Bridge down"}},
    });

    await mountWithCleanup(AiAssistantSystray);
    await openPanelAndAsk("Fail me");
    expect.verifySteps(["notify:Bridge down"]);
});

test("auto-opens the first navigation action and keeps the chip", async () => {
    mockLocalStorage();
    mockAssistantServices({
        body: "Opening",
        bodyIsHtml: false,
        actions: [
            {
                type: "open_action",
                label: "Open RFQs",
                action: {
                    type: "ir.actions.act_window",
                    res_model: "purchase.order",
                },
            },
        ],
    });

    await mountWithCleanup(AiAssistantSystray);
    await openPanelAndAsk("Open RFQs");
    expect.verifySteps([
        "doAction:purchase.order",
        "notify:Opening the requested screen…",
    ]);
    expect(".o_ai_assistant_message_action").toHaveCount(1);
    expect(".o_ai_assistant_panel").toHaveCount(1);
});

test("does not navigate when a draft is only prepared", async () => {
    mockLocalStorage();
    mockAssistantServices({
        body: "The ticket is ready. Should I open it?",
        bodyIsHtml: false,
        actions: [],
    });

    await mountWithCleanup(AiAssistantSystray);
    await openPanelAndAsk("Create a ticket");
    expect.verifySteps([]);
    expect(".o_ai_assistant_panel").toHaveCount(1);
    expect(".o_ai_assistant_message_action").toHaveCount(0);
});

test("auto-opens a record action after the user accepts", async () => {
    mockLocalStorage();
    mockAssistantServices({
        body: "The ticket is ready.",
        bodyIsHtml: false,
        actions: [
            {
                type: "open_record",
                model: "helpdesk.ticket",
                res_id: 11,
                name: "Notebook problem - freezing",
                label: "Open ticket",
                action: {
                    type: "ir.actions.act_window",
                    res_model: "helpdesk.ticket",
                    res_id: 11,
                },
            },
        ],
    });

    await mountWithCleanup(AiAssistantSystray);
    await openPanelAndAsk("yes");
    expect.verifySteps([
        "doAction:helpdesk.ticket",
        "notify:Opening the requested screen…",
    ]);
    expect(".o_ai_assistant_message_action").toHaveCount(1);
    expect(".o_ai_assistant_panel").toHaveCount(1);
});

test("shows empty-state suggestions and confirm chips", async () => {
    mockLocalStorage();
    mockAssistantServices({
        body: "Confirm SO001?",
        bodyIsHtml: false,
        actions: [{type: "confirm_pending", label: "Confirm SO001"}],
    });

    await mountWithCleanup(AiAssistantSystray);
    await click(".o_ai_assistant_systray a");
    await animationFrame();
    expect(".o_ai_assistant_suggestion").toHaveCount(4);

    await click(".o_ai_assistant_input");
    await edit("Confirm SO001", {confirm: false});
    await press("Enter");
    await tick();
    await animationFrame();
    expect(".o_ai_assistant_message_action").toHaveCount(1);
    await click(".o_ai_assistant_message_action");
    await animationFrame();
    expect(".o_ai_assistant_message").toHaveCount(3);
});

test("exports the assistant message as markdown without storing a file", async () => {
    mockLocalStorage();
    mockAssistantServices({
        body: "<h2>Weekly briefing</h2><p>Sales were stable.</p>",
    });
    const downloads = [];
    patchWithCleanup(AiAssistantSystray.prototype, {
        _downloadBlob(filename, blob) {
            downloads.push({filename, type: blob.type});
        },
    });

    await mountWithCleanup(AiAssistantSystray);
    await openPanelAndAsk("Briefing please");
    expect(".o_ai_assistant_artifact").toHaveCount(0);
    expect(".o_ai_assistant_message_export_md").toHaveCount(1);
    await click(".o_ai_assistant_message_export_md");
    await animationFrame();
    expect(downloads).toHaveLength(1);
    expect(downloads[0].filename).toBe("Weekly-briefing.md");
    expect(downloads[0].type).toMatch(/markdown/);
});

test("exports the assistant message as an ephemeral PDF", async () => {
    mockLocalStorage();
    mockAssistantServices({
        body: "<h2>Weekly briefing</h2><p>Sales were stable.</p>",
    });
    const downloads = [];
    patchWithCleanup(AiAssistantSystray.prototype, {
        _downloadBlob(filename, blob) {
            downloads.push({filename, type: blob.type});
        },
    });

    await mountWithCleanup(AiAssistantSystray);
    await openPanelAndAsk("Briefing please");
    expect(".o_ai_assistant_message_export_pdf").toHaveCount(1);
    await click(".o_ai_assistant_message_export_pdf");
    await tick();
    await animationFrame();
    expect.verifySteps(["export:pdf"]);
    expect(downloads).toHaveLength(1);
    expect(downloads[0].filename).toBe("assistant-briefing.pdf");
    expect(downloads[0].type).toBe("application/pdf");
});

test("strips backend record links from stored HTML", async () => {
    mockLocalStorage();
    mockAssistantServices({
        body:
            '<p>Created</p><p><a href="/web#id=8&amp;model=helpdesk.ticket">' +
            "Open HT00008</a></p>",
        bodyIsHtml: true,
        actions: [],
    });

    await mountWithCleanup(AiAssistantSystray);
    await openPanelAndAsk("Create a ticket");
    expect.verifySteps([]);
    expect(".o_ai_assistant_message_assistant a").toHaveCount(0);
    expect(".o_ai_assistant_message_action").toHaveCount(0);
});

test("copy keeps paragraphs and list line breaks", async () => {
    mockLocalStorage();
    mockAssistantServices();

    const assistant = await mountWithCleanup(AiAssistantSystray);
    const text = assistant._htmlToPlainText(
        "<p>Encontrei o chamado mais antigo registrado no sistema:</p>" +
            "<ul>" +
            "<li><b>Ticket:</b> HT00005 - Some products missing</li>" +
            "<li><b>Criação:</b> 02/09/2026 15:53</li>" +
            "<li><b>Cliente:</b> Azure Interior</li>" +
            "</ul>" +
            "<p>Vou abrir este ticket para você.</p>"
    );
    expect(text).toBe(
        "Encontrei o chamado mais antigo registrado no sistema:\n\n" +
            "- **Ticket:** HT00005 - Some products missing\n" +
            "- **Criação:** 02/09/2026 15:53\n" +
            "- **Cliente:** Azure Interior\n\n" +
            "Vou abrir este ticket para você."
    );
});

test("copy keeps a blank line after a table", async () => {
    mockLocalStorage();
    mockAssistantServices();

    const assistant = await mountWithCleanup(AiAssistantSystray);
    const text = assistant._htmlToPlainText(
        "<p>Você está visualizando um ticket de helpdesk:</p>" +
            "<table><thead><tr><th>Campo</th><th>Valor</th></tr></thead>" +
            "<tbody><tr><td>Número do Ticket</td><td>HT00010</td></tr>" +
            "<tr><td>Assunto</td><td>Teclado #9</td></tr></tbody></table>" +
            "<p>Este ticket parece ser uma solicitação de suporte.</p>"
    );
    expect(text).toBe(
        "Você está visualizando um ticket de helpdesk:\n\n" +
            "| Campo | Valor |\n" +
            "| --- | --- |\n" +
            "| Número do Ticket | HT00010 |\n" +
            "| Assunto | Teclado #9 |\n\n" +
            "Este ticket parece ser uma solicitação de suporte."
    );
});
