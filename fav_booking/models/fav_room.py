from odoo import api, fields, models
from odoo.exceptions import ValidationError


class FavRoom(models.Model):
    _name = 'fav.room'
    _description = 'FAV Room'
    _order = 'sequence, room_type, name, id'

    _code_company_uniq = models.Constraint(
        'UNIQUE(code, company_id)',
        'A room with this code already exists for this company.',
    )
    _table_uniq = models.Constraint(
        'UNIQUE(table_id)',
        'This POS table is already linked to a room.',
    )

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    room_type = fields.Char(
        string='Room Type',
        help='Groups columns on the day schedule, for example VIP PLUS or SUITE.',
    )
    floor_id = fields.Many2one(
        'restaurant.floor',
        string='Outlet',
        related='table_id.floor_id',
        store=True,
        index=True,
    )
    outlet_analytic_account_id = fields.Many2one(
        'account.analytic.account',
        string='Outlet analytic account',
        compute='_compute_outlet_analytic_account_id',
        help='Analytic account of a Point of Sale linked to this outlet, '
             'when FAV POS Outlet Analytic is installed.',
    )
    code = fields.Char(
        string='Room Code',
        required=True,
        index=True,
        help='Identifier the booking website sends as room_code, or as product_code.',
    )
    table_id = fields.Many2one(
        'restaurant.table',
        string='POS Table',
        required=True,
        ondelete='restrict',
        index=True,
    )
    table_room_name = fields.Char(
        string='POS Room Name',
        related='table_id.room_name',
        help='Name shown on the floor plan. Set it on the POS table.',
    )
    product_id = fields.Many2one(
        'product.product',
        string='Room Product',
        required=True,
        ondelete='restrict',
        domain="[('sale_ok', '=', True), ('available_in_pos', '=', True)]",
        help='Sold by the hour on the POS bill. Price lives on the product, not on the room.',
    )
    company_id = fields.Many2one(
        'res.company',
        required=True,
        index=True,
        default=lambda self: self.env.company,
    )
    active = fields.Boolean(default=True)

    @api.constrains('product_id', 'company_id')
    def _check_product(self):
        for room in self:
            product = room.product_id
            if not product.available_in_pos or not product.sale_ok:
                raise ValidationError(self.env._(
                    'Room %(room)s needs a POS-available product that can be sold.',
                    room=room.display_name,
                ))
            if product.company_id and product.company_id != room.company_id:
                raise ValidationError(self.env._(
                    'Room %(room)s and its product must belong to the same company.',
                    room=room.display_name,
                ))

    @api.depends('floor_id')
    def _compute_outlet_analytic_account_id(self):
        Analytic = self.env['account.analytic.account']
        configs = self.env['pos.config']
        has_field = 'analytic_account_id' in configs._fields
        for room in self:
            account = Analytic.browse()
            if has_field and room.floor_id:
                linked = room.floor_id.pos_config_ids.filtered('analytic_account_id').sorted('id')
                account = linked[:1].analytic_account_id
            room.outlet_analytic_account_id = account

    @api.depends('name', 'code')
    def _compute_display_name(self):
        for room in self:
            if room.code:
                room.display_name = f'{room.name} ({room.code})'
            else:
                room.display_name = room.name or ''
