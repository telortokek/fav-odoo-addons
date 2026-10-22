/** @odoo-module */

import { PosOrder } from "@point_of_sale/app/models/pos_order";
import { patch } from "@web/core/utils/patch";

patch(PosOrder.prototype, {
    getName() {
        if (this.config?.module_pos_restaurant && this.getTable() && !this.isDirectSale) {
            const table = this.getTable();
            const childTables = this.models["restaurant.table"].filter((child) => {
                if (child.floor_id && child.floor_id.id === table.floor_id?.id) {
                    return table.isParent(child);
                }
                return false;
            });
            let name = table.getName();
            for (const child of childTables) {
                name += ` & ${child.getName()}`;
            }
            return `${name} - ${this.tracking_number}`;
        }
        return super.getName(...arguments);
    },
});
