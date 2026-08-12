import {describe, expect, test} from "@odoo/hoot";
import {click, edit} from "@odoo/hoot-dom";
import {
    mockService,
    mountWithCleanup,
    patchWithCleanup,
} from "@web/../tests/web_test_helpers";
import {AiAssistantSystray} from "@ai_agno_assistant/assistant/assistant_systray";
import {animationFrame} from "@odoo/hoot-mock";
import {browser} from "@web/core/browser/browser";

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

function mockAssistantServices() {
    mockService("orm", {
        call: async () => ({
            body: "<p>Hello</p>",
            body_is_html: true,
            actions: [],
        }),
    });
    mockService("action", {
        doAction: async () => true,
        currentController: null,
    });
    mockService("notification", {
        add: () => true,
    });
}

async function openPanelAndAsk(question) {
    await click(".o_ai_assistant_systray a");
    await animationFrame();
    await click(".o_ai_assistant_input");
    await edit(question);
    await click("button[title='Send']");
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
    mockService("orm", {
        call: async () => ({
            body: "<p>Kept</p>",
            body_is_html: true,
            actions: [],
        }),
    });
    mockService("action", {
        doAction: async () => true,
        currentController: null,
    });
    mockService("notification", {
        add: () => true,
    });

    await mountWithCleanup(AiAssistantSystray);
    await openPanelAndAsk("Keep me");
    expect(".o_ai_assistant_panel").toHaveCount(1);

    await click("button[title='Close']");
    await animationFrame();
    expect(".o_ai_assistant_panel").toHaveCount(0);

    await click(".o_ai_assistant_systray a");
    await animationFrame();
    expect(".o_ai_assistant_panel").toHaveCount(1);
    expect(".o_ai_assistant_message").toHaveCount(2);
});
