/** @odoo-module */

import { TicketScreen } from "@point_of_sale/app/screens/ticket_screen/ticket_screen";
import { patch } from "@web/core/utils/patch";

patch(TicketScreen.prototype, {
    getTableTag(order) {
        const table = order.table_id;
        if (!table) {
            return "";
        }
        return table.getName();
    },
    _getSearchFields() {
        const fields = super._getSearchFields(...arguments);
        if (this.pos.config.module_pos_restaurant && fields.REFERENCE) {
            fields.REFERENCE.modelFields.push("table_id.room_name");
        }
        return fields;
    },
});
