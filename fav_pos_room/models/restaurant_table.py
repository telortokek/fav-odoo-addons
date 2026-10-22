from odoo import api, fields, models

# Matched by floor name and table number. Record ids differ per database.
SETIABUDI_FLOOR_NAME = 'FAV Setiabudi'
SETIABUDI_ROOM_BY_NUMBER = {
    1: 'VIP PLUS 1',
    2: 'VIP PLUS 2',
    3: 'VIP PLUS 3',
    4: 'VIP PLUS 4',
    5: 'VIP PLUS 5',
    6: 'VVIP 1',
    7: 'VVIP 2',
    8: 'DELUXE 1',
    9: 'DELUXE 2',
    10: 'SUITE 1',
}


class RestaurantTable(models.Model):
    _inherit = 'restaurant.table'

    room_name = fields.Char(
        string='Room Name',
        help='Shown on the floor plan, order header, order list, and tickets. '
             'Leave empty to show the table number. Reload the Point of Sale after changing it.',
    )

    def _get_room_label(self):
        self.ensure_one()
        name = (self.room_name or '').strip()
        if name:
            return name
        return str(self.table_number)

    @api.depends('room_name', 'table_number', 'floor_id')
    def _compute_display_name(self):
        for table in self:
            label = table._get_room_label()
            if table.floor_id:
                table.display_name = f"{table.floor_id.name}, {label}"
            else:
                table.display_name = label

    @api.model
    def _load_pos_data_fields(self, config):
        return super()._load_pos_data_fields(config) + ['room_name']

    @api.model_create_multi
    def create(self, vals_list):
        floor_ids = {vals['floor_id'] for vals in vals_list if vals.get('floor_id')}
        floor_names = {
            floor.id: floor.name
            for floor in self.env['restaurant.floor'].browse(list(floor_ids))
        }
        for vals in vals_list:
            if (vals.get('room_name') or '').strip():
                continue
            label = self._setiabudi_label(floor_names.get(vals.get('floor_id')), vals.get('table_number'))
            if label:
                vals['room_name'] = label
        return super().create(vals_list)

    @api.model
    def _setiabudi_label(self, floor_name, table_number):
        if floor_name != SETIABUDI_FLOOR_NAME:
            return False
        return SETIABUDI_ROOM_BY_NUMBER.get(table_number) or False

    @api.model
    def assign_setiabudi_room_names(self):
        """Fill blank room names on every floor named FAV Setiabudi.

        Existing names are kept. Tables are matched by number, not by id.
        """
        floors = self.env['restaurant.floor'].search([('name', '=', SETIABUDI_FLOOR_NAME)])
        updated = self.browse()
        for table in floors.table_ids:
            if (table.room_name or '').strip():
                continue
            label = SETIABUDI_ROOM_BY_NUMBER.get(table.table_number)
            if not label:
                continue
            table.room_name = label
            updated |= table
        return updated
