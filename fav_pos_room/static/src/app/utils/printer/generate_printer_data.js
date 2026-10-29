/** @odoo-module */

import { GeneratePrinterData } from "@point_of_sale/app/utils/printer/generate_printer_data";
import { patch } from "@web/core/utils/patch";

patch(GeneratePrinterData.prototype, {
    get commonExtraData() {
        const extraData = super.commonExtraData;
        if (this.config.module_pos_restaurant) {
            const table = this.order.table_id;
            const roomName = (table?.room_name || "").trim();
            extraData.room_name = roomName || false;
            extraData.table_name = roomName || (table ? String(table.table_number) : false);
            extraData.floor_name = table?.floor_id?.name || false;
        }
        return extraData;
    },
});
