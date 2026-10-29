/** @odoo-module */

import { RestaurantTable } from "@pos_restaurant/app/models/restaurant_table";
import { patch } from "@web/core/utils/patch";

patch(RestaurantTable.prototype, {
    getName() {
        const name = (this.room_name || "").trim();
        return name || String(this.table_number ?? "");
    },
});
