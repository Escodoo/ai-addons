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
} = {}) {
    mockService("orm", {
        call: async () => {
            if (error) {
                throw error;
            }
            return {
                body,
                body_is_html: bodyIsHtml,
                actions,
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

test("persists messages across remount and clears storage", async () => {
    const store = mockLocalStorage();
    mockAssistantServices();

    await mountWithCleanup(AiAssistantSystray);
    await openPanelAndAsk("Hi there");
    expect(".o_ai_assistant_message").toHaveCount(2);
    expect(
        Object.keys(store).some((key) => key.startsWith("ai_agno_assistant.chat"))
    ).toBe(true);

    await mountWithCleanup(AiAssistantSystray);
    await click(".o_ai_assistant_systray a");
    await animationFrame();
    expect(".o_ai_assistant_message").toHaveCount(2);

    await click("button[title='Clear conversation']");
    await animationFrame();
    expect(".o_ai_assistant_message").toHaveCount(0);
    expect(
        Object.keys(store).some((key) => key.startsWith("ai_agno_assistant.chat"))
    ).toBe(false);
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

test("applies sanitized assistant actions", async () => {
    mockLocalStorage();
    mockAssistantServices({
        body: "Opening",
        bodyIsHtml: false,
        actions: [
            {
                type: "open_record",
                action: {
                    type: "ir.actions.act_window",
                    res_model: "res.partner",
                    res_id: 1,
                },
            },
        ],
    });

    await mountWithCleanup(AiAssistantSystray);
    await openPanelAndAsk("Open partner");
    expect.verifySteps([
        "doAction:res.partner",
        "notify:Opening the requested screen…",
    ]);
});
