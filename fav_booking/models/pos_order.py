from odoo import fields, models


class PosOrder(models.Model):
    _inherit = 'pos.order'

    fav_booking_id = fields.Many2one(
        'fav.booking',
        string='Booking',
        copy=False,
        index=True,
        ondelete='set null',
    )


class PosOrderLine(models.Model):
    _inherit = 'pos.order.line'

    fav_line_role = fields.Selection(
        selection=[
            ('room', 'Room'),
            ('payment', 'Website payment'),
        ],
        string='Booking Line',
        copy=False,
    )
