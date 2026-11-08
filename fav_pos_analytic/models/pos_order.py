from odoo import models


class PosOrder(models.Model):
    _inherit = 'pos.order'

    def _generate_pos_order_invoice(self):
        invoice = super()._generate_pos_order_invoice()
        configs = self.config_id
        if invoice and len(configs) == 1:
            configs._fav_tag_outlet_analytic(invoice)
        return invoice
