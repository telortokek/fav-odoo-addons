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
