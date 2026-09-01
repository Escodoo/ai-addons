/* Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
 * License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl). */

import {_t} from "@web/core/l10n/translation";
import {threadActionsRegistry} from "@mail/core/common/thread_actions";

const CUSTOMER_CHANNEL_TYPES = ["gateway", "livechat"];

function hasAiBridge(component) {
    const thread = component.thread;
    if (!thread || thread.model !== "discuss.channel") {
        return false;
    }
    if (component.props.chatWindow && !component.props.chatWindow.isOpen) {
        return false;
    }
    return (
        CUSTOMER_CHANNEL_TYPES.includes(thread.channel_type) &&
        Boolean(thread.has_ai_bridge)
    );
}

async function setAiBridgePaused(component, paused) {
    const thread = component.thread;
    await component.env.services.orm.call(
        "discuss.channel",
        paused ? "action_ai_bridge_pause" : "action_ai_bridge_resume",
        [[thread.id]]
    );
    thread.ai_bridge_paused = paused;
}

threadActionsRegistry
    .add("ai-bridge-pause", {
        condition(component) {
            return hasAiBridge(component) && !component.thread.ai_bridge_paused;
        },
        icon: "fa fa-fw fa-pause",
        iconLarge: "fa fa-fw fa-lg fa-pause",
        name: _t("Pause AI"),
        open(component) {
            setAiBridgePaused(component, true);
        },
        sequence: 16,
    })
    .add("ai-bridge-resume", {
        condition(component) {
            return hasAiBridge(component) && Boolean(component.thread.ai_bridge_paused);
        },
        icon: "fa fa-fw fa-play",
        iconLarge: "fa fa-fw fa-lg fa-play",
        name: _t("Resume AI"),
        open(component) {
            setAiBridgePaused(component, false);
        },
        sequence: 16,
    });
