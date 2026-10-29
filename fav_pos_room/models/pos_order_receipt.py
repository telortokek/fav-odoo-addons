from odoo import models


class PosOrderReceipt(models.AbstractModel):
    _inherit = 'pos.order.receipt'

    def _set_pos_restaurant_receipt_common_data(self, data):
        super()._set_pos_restaurant_receipt_common_data(data)
        if not self.config_id.module_pos_restaurant or not self.table_id:
            return
        table = self.table_id
        data['extra_data']['table_name'] = table._get_room_label()
        data['extra_data']['room_name'] = (table.room_name or '').strip() or False
