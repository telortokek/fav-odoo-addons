from odoo import Command, fields
from odoo.tests import TransactionCase

from odoo.addons.fav_pos_room.hooks import post_init_hook
from odoo.addons.fav_pos_room.models.restaurant_table import SETIABUDI_ROOM_BY_NUMBER


class TestFavPosRoom(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.floor = cls.env['restaurant.floor'].create({'name': 'FAV Setiabudi'})
        cls.other_floor = cls.env['restaurant.floor'].create({'name': 'Other Floor'})

    def test_empty_name_falls_back_to_number(self):
        table = self.env['restaurant.table'].create({
            'floor_id': self.other_floor.id,
            'table_number': 4,
        })
        self.assertFalse(table.room_name)
        self.assertEqual(table._get_room_label(), '4')
        self.assertEqual(table.display_name, 'Other Floor, 4')
        table.room_name = '   '
        self.assertEqual(table._get_room_label(), '4')

    def test_room_name_is_the_label(self):
        table = self.env['restaurant.table'].create({
            'floor_id': self.other_floor.id,
            'table_number': 1,
            'room_name': '  VIP PLUS 1  ',
        })
        self.assertEqual(table._get_room_label(), 'VIP PLUS 1')
        self.assertEqual(table.display_name, 'Other Floor, VIP PLUS 1')

    def test_pos_load_includes_room_name(self):
        fields_to_load = self.env['restaurant.table']._load_pos_data_fields(self.env['pos.config'])
        self.assertIn('room_name', fields_to_load)
        self.assertIn('table_number', fields_to_load)

    def test_create_fills_setiabudi_and_keeps_a_given_name(self):
        named = self.env['restaurant.table'].create({
            'floor_id': self.floor.id,
            'table_number': 1,
            'room_name': 'Already named',
        })
        mapped = self.env['restaurant.table'].create({
            'floor_id': self.floor.id,
            'table_number': 6,
        })
        untouched = self.env['restaurant.table'].create({
            'floor_id': self.floor.id,
            'table_number': 11,
        })
        other = self.env['restaurant.table'].create({
            'floor_id': self.other_floor.id,
            'table_number': 1,
        })
        self.assertEqual(named.room_name, 'Already named')
        self.assertEqual(mapped.room_name, 'VVIP 1')
        self.assertFalse(untouched.room_name)
        self.assertFalse(other.room_name)

    def test_assign_does_not_overwrite_and_matches_by_number(self):
        tables = self.env['restaurant.table'].create([
            {'floor_id': self.floor.id, 'table_number': number, 'room_name': False}
            for number in range(1, 12)
        ])
        # create() already filled the mapped numbers. Clear them, then protect one.
        tables.write({'room_name': False})
        kept = tables.filtered(lambda table: table.table_number == 3)
        kept.room_name = 'Custom 3'
        blank = tables.filtered(lambda table: table.table_number == 8)
        blank.room_name = '   '

        updated = self.env['restaurant.table'].assign_setiabudi_room_names()

        self.assertEqual(kept.room_name, 'Custom 3')
        self.assertNotIn(kept, updated)
        by_number = {table.table_number: table.room_name for table in tables}
        for number, label in SETIABUDI_ROOM_BY_NUMBER.items():
            if number == 3:
                continue
            self.assertEqual(by_number[number], label)
        self.assertFalse(by_number[11])
        self.assertEqual(
            self.env['restaurant.table'].search_count([
                ('floor_id', '=', self.other_floor.id),
                ('room_name', '!=', False),
            ]),
            0,
        )

    def test_post_init_hook_leaves_existing_names(self):
        table = self.env['restaurant.table'].create({
            'floor_id': self.floor.id,
            'table_number': 10,
            'room_name': 'Keep me',
        })
        missing = self.env['restaurant.table'].create({
            'floor_id': self.floor.id,
            'table_number': 2,
            'room_name': 'temp',
        })
        missing.room_name = False
        post_init_hook(self.env)
        self.assertEqual(table.room_name, 'Keep me')
        self.assertEqual(missing.room_name, 'VIP PLUS 2')

    def test_floor_create_with_inline_tables(self):
        floor = self.env['restaurant.floor'].create({
            'name': 'FAV Setiabudi',
            'table_ids': [Command.create({'table_number': 9, 'seats': 2})],
        })
        self.assertEqual(floor.table_ids.room_name, 'DELUXE 2')

    def _receipt_values(self, extra):
        values = {
            'preset': False,
            'partner': False,
            'image': {'logo': False},
            'config': {'name': 'FAV', 'receipt_header': False},
            'conditions': {
                'display_vat': False,
                'module_pos_restaurant': True,
                'basic_receipt': False,
            },
            'order': {
                'tracking_number': '001',
                'pos_reference': 'Order 001',
                'customer_count': 2,
                'state': 'draft',
                'mobile': False,
            },
            'changes': {'data': [], 'title': 'NEW'},
            'extra_data': {
                'preset_time': False,
                'preset_datetime': False,
                'time': '12:00',
                'employee_name': False,
                'prefix': 'Order',
                'order_label': False,
                'reprint': False,
                'internal_note': False,
                'general_customer_note': False,
                'formated_date_order': '2026-10-16',
                'cashier_name': False,
                'floor_name': 'FAV Setiabudi',
                'table_name': '4',
                'room_name': False,
            },
        }
        values['extra_data'].update(extra)
        return values

    def test_receipts_use_room_name_without_table_prefix(self):
        named = self._receipt_values({
            'table_name': 'VIP PLUS 1',
            'room_name': 'VIP PLUS 1',
        })
        header = self.env['ir.qweb']._render('point_of_sale.pos_order_receipt_header', named)
        kitchen = self.env['ir.qweb']._render('point_of_sale.pos_order_change_receipt', named)
        self.assertIn('VIP PLUS 1', header)
        self.assertNotIn('Table VIP PLUS 1', header)
        self.assertIn('FAV Setiabudi - ', kitchen)
        self.assertIn('VIP PLUS 1', kitchen)
        self.assertNotIn('>T </span>', kitchen)
        self.assertNotIn('Table VIP PLUS 1', kitchen)

    def test_receipts_fall_back_to_the_number(self):
        numbered = self._receipt_values({})
        header = self.env['ir.qweb']._render('point_of_sale.pos_order_receipt_header', numbered)
        kitchen = self.env['ir.qweb']._render('point_of_sale.pos_order_change_receipt', numbered)
        self.assertIn('Table 4', header)
        self.assertIn('>T </span>', kitchen)
        self.assertIn('>4</span>', kitchen)

    def test_order_receipt_data_uses_the_room_label(self):
        config = self.env['pos.config'].create({
            'name': 'FAV Room POS',
            'module_pos_restaurant': True,
        })
        session = self.env['pos.session'].create({
            'config_id': config.id,
            'start_at': fields.Datetime.now(),
        })
        table = self.env['restaurant.table'].create({
            'floor_id': self.floor.id,
            'table_number': 10,
            'room_name': 'SUITE 1',
        })
        order = self.env['pos.order'].create({
            'session_id': session.id,
            'table_id': table.id,
            'amount_tax': 0,
            'amount_total': 0,
            'amount_paid': 0,
            'amount_return': 0,
        })
        data = {'extra_data': {}}
        order._set_pos_restaurant_receipt_common_data(data)
        self.assertEqual(data['extra_data']['table_name'], 'SUITE 1')
        self.assertEqual(data['extra_data']['room_name'], 'SUITE 1')
        self.assertEqual(data['extra_data']['floor_name'], 'FAV Setiabudi')

        bare = self.env['restaurant.table'].create({
            'floor_id': self.other_floor.id,
            'table_number': 2,
        })
        order.table_id = bare
        data = {'extra_data': {}}
        order._set_pos_restaurant_receipt_common_data(data)
        self.assertEqual(data['extra_data']['table_name'], '2')
        self.assertFalse(data['extra_data']['room_name'])
