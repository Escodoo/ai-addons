/* Copyright 2026 - TODAY, Marcel Savegnago <marcel.savegnago@escodoo.com.br>
 * License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl). */

import {Thread} from "@mail/core/common/thread_model";
import {patch} from "@web/core/utils/patch";

patch(Thread.prototype, {
    setup() {
        super.setup();
        this.ai_bridge_paused = false;
        this.has_ai_bridge = false;
    },
});
