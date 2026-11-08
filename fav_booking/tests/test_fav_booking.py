from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase

from odoo.addons.fav_booking.tests.common import open_restaurant_session


class TestFavBooking(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({'name': 'Walk-in Guest'})
        cls.product = cls.env['product.product'].create({
            'name': 'Court Hour',
            'type': 'service',
            'list_price': 150000,
            'default_code': 'FAV-TEST-COURT',
        })
        cls.payload = {
            'external_ref': 'WEB-1001',
            'partner_id': cls.partner.id,
            'product_code': 'FAV-TEST-COURT',
            'date_start': '2026-10-20 02:00:00',
            'date_end': '2026-10-20 04:00:00',
            'state': 'confirmed',
            'amount_untaxed': 150000.0,
            'amount_tax': 0.0,
            'amount_total': 150000.0,
            'note': 'Online',
        }

    def test_upsert_is_idempotent(self):
        Booking = self.env['fav.booking']
        first = Booking.upsert_from_website(**self.payload)
        second = Booking.upsert_from_website(**self.payload)
        self.assertTrue(first['created'])
        self.assertFalse(second['created'])
        self.assertEqual(first['id'], second['id'])
        self.assertEqual(first['state'], 'confirmed')
        self.assertEqual(Booking.search_count([('external_ref', '=', 'WEB-1001')]), 1)
        booking = Booking.browse(first['id'])
        self.assertNotEqual(booking.name, 'New')
        self.assertTrue(booking.name.startswith('BK'))

    def test_upsert_creates_partner_by_email(self):
        payload = dict(self.payload, external_ref='WEB-1002', partner_id=None, partner={
            'name': 'Ayu',
            'email': 'ayu@example.com',
            'phone': '081234',
        })
        result = self.env['fav.booking'].upsert_from_website(**payload)
        booking = self.env['fav.booking'].browse(result['id'])
        self.assertEqual(booking.partner_id.email, 'ayu@example.com')
        again = dict(payload, external_ref='WEB-1003')
        other = self.env['fav.booking'].upsert_from_website(**again)
        self.assertEqual(
            self.env['fav.booking'].browse(other['id']).partner_id,
            booking.partner_id,
        )

    def test_stale_confirm_does_not_rewind_check_in(self):
        self.product.available_in_pos = True
        floor = self.env['restaurant.floor'].create({'name': 'FAV Stale Floor'})
        table = self.env['restaurant.table'].create({
            'floor_id': floor.id,
            'table_number': 1,
            'room_name': 'Court 1',
        })
        self.env['fav.room'].create({
            'name': 'Court 1',
            'code': 'FAV-TEST-COURT',
            'table_id': table.id,
            'product_id': self.product.id,
        })
        open_restaurant_session(self.env, floor, name='FAV Stale Register')
        result = self.env['fav.booking'].upsert_from_website(**self.payload)
        booking = self.env['fav.booking'].browse(result['id'])
        self.assertTrue(booking.room_id)
        booking.action_check_in()
        replay = self.env['fav.booking'].upsert_from_website(**self.payload)
        self.assertEqual(replay['id'], booking.id)
        self.assertEqual(booking.state, 'checked_in')
        self.assertFalse(replay['created'])
        self.assertTrue(booking.pos_order_id)

    def test_end_before_start_is_rejected(self):
        payload = dict(self.payload, external_ref='WEB-BAD', date_end='2026-10-20 01:00:00')
        with self.assertRaises(ValidationError):
            self.env['fav.booking'].upsert_from_website(**payload)

    def test_missing_external_ref(self):
        payload = dict(self.payload, external_ref='  ')
        with self.assertRaises(UserError):
            self.env['fav.booking'].upsert_from_website(**payload)

    def test_illegal_button_transition(self):
        result = self.env['fav.booking'].upsert_from_website(**self.payload)
        booking = self.env['fav.booking'].browse(result['id'])
        with self.assertRaises(UserError):
            booking.action_done()

    def test_create_sale_order_links_product(self):
        result = self.env['fav.booking'].upsert_from_website(**self.payload)
        booking = self.env['fav.booking'].browse(result['id'])
        booking.action_create_sale_order()
        self.assertTrue(booking.sale_order_id)
        self.assertEqual(booking.sale_order_id.partner_id, self.partner)
        self.assertEqual(booking.sale_order_id.order_line.product_id, self.product)
        action = booking.action_create_sale_order()
        self.assertEqual(action['res_id'], booking.sale_order_id.id)
        self.assertEqual(
            self.env['sale.order'].search_count([('origin', '=', booking.name)]),
            1,
        )
