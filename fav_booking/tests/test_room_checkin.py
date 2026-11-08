from odoo import Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase

from odoo.addons.fav_booking.tests.common import open_restaurant_session


class TestFavRoomCheckIn(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({'name': 'Walk-in Guest'})
        cls.product = cls.env['product.product'].create({
            'name': 'VIP Plus Hour',
            'type': 'service',
            'list_price': 150000,
            'available_in_pos': True,
            'sale_ok': True,
            'default_code': 'FAV-VIP-PLUS-HOUR',
        })
        cls.other_product = cls.env['product.product'].create({
            'name': 'Unmapped Hour',
            'type': 'service',
            'list_price': 100000,
            'sale_ok': True,
            'default_code': 'FAV-UNMAPPED',
        })
        cls.floor = cls.env['restaurant.floor'].create({'name': 'FAV Check-in Floor'})
        cls.table = cls.env['restaurant.table'].create({
            'floor_id': cls.floor.id,
            'table_number': 1,
            'room_name': 'VIP PLUS 1',
            'seats': 2,
        })
        cls.other_table = cls.env['restaurant.table'].create({
            'floor_id': cls.floor.id,
            'table_number': 2,
            'room_name': 'VIP PLUS 2',
            'seats': 2,
        })
        cls.room = cls.env['fav.room'].create({
            'name': 'VIP PLUS 1',
            'code': 'FAV-TEST-ROOM-1',
            'table_id': cls.table.id,
            'product_id': cls.product.id,
        })
        cls.other_room = cls.env['fav.room'].create({
            'name': 'VIP PLUS 2',
            'code': 'FAV-TEST-ROOM-2',
            'table_id': cls.other_table.id,
            'product_id': cls.product.id,
        })

    def _payload(self, **extra):
        values = {
            'external_ref': 'WEB-ROOM-1',
            'partner_id': self.partner.id,
            'room_code': 'FAV-TEST-ROOM-1',
            'date_start': '2026-10-20 02:00:00',
            'date_end': '2026-10-20 04:00:00',
            'state': 'confirmed',
            'amount_untaxed': 300000.0,
            'amount_tax': 0.0,
            'amount_total': 300000.0,
            'amount_down_payment': 50000.0,
        }
        values.update(extra)
        return values

    def test_amount_paid_alias_wins_over_amount_down_payment(self):
        payload = self._payload(
            external_ref='WEB-PAID-ALIAS',
            amount_down_payment=50000.0,
            amount_paid=80000.0,
        )
        result = self.env['fav.booking'].upsert_from_website(**payload)
        booking = self.env['fav.booking'].browse(result['id'])
        self.assertEqual(booking.amount_down_payment, 80000.0)
        self.assertEqual(result['amount_paid'], 80000.0)
        self.assertEqual(result['amount_down_payment'], 80000.0)
        legacy = self._payload(
            external_ref='WEB-PAID-LEGACY',
            amount_paid=None,
            date_start='2026-10-20 06:00:00',
            date_end='2026-10-20 08:00:00',
        )
        legacy_booking = self.env['fav.booking'].browse(
            self.env['fav.booking'].upsert_from_website(**legacy)['id']
        )
        self.assertEqual(legacy_booking.amount_down_payment, 50000.0)

    def test_room_code_sets_the_mapped_product(self):
        result = self.env['fav.booking'].upsert_from_website(**self._payload())
        booking = self.env['fav.booking'].browse(result['id'])
        self.assertEqual(booking.room_id, self.room)
        self.assertEqual(booking.product_id, self.product)
        self.assertEqual(result['room_code'], 'FAV-TEST-ROOM-1')
        self.assertEqual(booking.duration_hours, 2.0)
        self.assertEqual(booking.amount_down_payment, 50000.0)

    def test_product_code_still_matches_a_room_code(self):
        payload = self._payload(
            external_ref='WEB-ROOM-CODE', room_code=None, product_code='FAV-TEST-ROOM-1',
        )
        booking = self.env['fav.booking'].browse(
            self.env['fav.booking'].upsert_from_website(**payload)['id']
        )
        self.assertEqual(booking.room_id, self.room)
        self.assertEqual(booking.product_id, self.product)

    def test_unmapped_product_stays_without_a_room(self):
        payload = self._payload(
            external_ref='WEB-UNMAPPED',
            room_code=None,
            product_code='FAV-UNMAPPED',
        )
        booking = self.env['fav.booking'].browse(
            self.env['fav.booking'].upsert_from_website(**payload)['id']
        )
        self.assertFalse(booking.room_id)
        self.assertEqual(booking.product_id, self.other_product)

    def test_staff_cannot_create_bookings_directly(self):
        user = self.env['res.users'].create({
            'name': 'FAV Desk',
            'login': 'fav_desk_test',
            'group_ids': [Command.set([
                self.env.ref('base.group_user').id,
                self.env.ref('fav_booking.group_fav_booking_user').id,
            ])],
        })
        bookings = self.env['fav.booking'].with_user(user)
        with self.assertRaises(AccessError):
            bookings.create({
                'partner_id': self.partner.id,
                'product_id': self.product.id,
                'date_start': '2026-10-21 02:00:00',
                'date_end': '2026-10-21 04:00:00',
            })
        created = bookings.upsert_from_website(**self._payload(external_ref='WEB-STAFF-API'))
        self.assertTrue(created['created'])

    def test_overlap_is_rejected_unless_cancelled_or_touching(self):
        Booking = self.env['fav.booking']
        first = Booking.browse(Booking.upsert_from_website(**self._payload())['id'])
        with self.assertRaises(ValidationError):
            Booking.upsert_from_website(**self._payload(
                external_ref='WEB-OVERLAP',
                date_start='2026-10-20 03:00:00',
                date_end='2026-10-20 05:00:00',
            ))
        Booking.upsert_from_website(**self._payload(
            external_ref='WEB-NEXT',
            date_start='2026-10-20 04:00:00',
            date_end='2026-10-20 06:00:00',
        ))
        Booking.upsert_from_website(**self._payload(
            external_ref='WEB-OTHER-ROOM',
            room_code='FAV-TEST-ROOM-2',
            date_start='2026-10-20 02:00:00',
            date_end='2026-10-20 04:00:00',
        ))
        first.action_cancel()
        Booking.upsert_from_website(**self._payload(
            external_ref='WEB-AFTER-CANCEL',
            date_start='2026-10-20 02:30:00',
            date_end='2026-10-20 03:30:00',
        ))

    def test_check_in_opens_a_draft_bill_on_the_table(self):
        config, _session = open_restaurant_session(self.env, self.floor, name='FAV Check-in Register')
        booking = self.env['fav.booking'].browse(
            self.env['fav.booking'].upsert_from_website(**self._payload())['id']
        )
        booking.action_check_in()
        order = booking.pos_order_id
        self.assertEqual(booking.state, 'checked_in')
        self.assertEqual(order.state, 'draft')
        self.assertEqual(order.table_id, self.table)
        self.assertEqual(order.partner_id, self.partner)
        self.assertEqual(order.session_id.config_id, config)
        self.assertEqual(order.session_id.state, 'opened')
        self.assertEqual(order.fav_booking_id, booking)
        room_line = order.lines.filtered(lambda line: line.price_unit > 0)
        deposit_line = order.lines.filtered(lambda line: line.price_unit < 0)
        self.assertEqual(room_line.qty, 2.0)
        self.assertEqual(room_line.product_id, self.product)
        self.assertEqual(room_line.price_unit, 150000)
        self.assertEqual(deposit_line.full_product_name, 'Website payment')
        self.assertIn('Paid on website for', deposit_line.customer_note or '')
        self.assertFalse(deposit_line.tax_ids)
        self.assertEqual(deposit_line.price_unit, -50000)
        self.assertFalse(order.payment_ids)
        # Untaxed remainder is 2 × 150000 − 50000. Tax, if the product has any, sits on top.
        self.assertEqual(order.amount_total - order.amount_tax, 250000)
        loaded = self.env['pos.order'].search(
            self.env['pos.order']._load_pos_data_domain({'pos.config': config})
        )
        self.assertIn(order, loaded)

    def test_full_website_payment_nets_the_room_charge_to_zero(self):
        open_restaurant_session(self.env, self.floor, name='FAV Paid In Full Register')
        sample = self.env['fav.booking'].browse(
            self.env['fav.booking'].upsert_from_website(**self._payload(
                external_ref='WEB-CHARGE-SAMPLE',
                amount_paid=0,
            ))['id']
        )
        sample.action_check_in()
        room_charge = sample.pos_order_id.amount_total
        self.assertGreater(room_charge, 0)
        over = self.env['fav.booking'].browse(
            self.env['fav.booking'].upsert_from_website(**self._payload(
                external_ref='WEB-PAID-OVER',
                room_code='FAV-TEST-ROOM-2',
                date_start='2026-10-21 02:00:00',
                date_end='2026-10-21 04:00:00',
                amount_paid=room_charge + 1,
            ))['id']
        )
        with self.assertRaises(UserError) as error:
            over.action_check_in()
        self.assertIn('payment', str(error.exception).lower())
        self.assertIn('room charge', str(error.exception).lower())
        self.assertFalse(over.pos_order_id)
        self.assertFalse(self.env['pos.order'].search([
            ('table_id', '=', self.other_table.id),
            ('state', '=', 'draft'),
        ]))
        paid = self.env['fav.booking'].browse(
            self.env['fav.booking'].upsert_from_website(**self._payload(
                external_ref='WEB-PAID-FULL',
                room_code='FAV-TEST-ROOM-2',
                amount_paid=room_charge,
                amount_down_payment=1,
            ))['id']
        )
        paid.action_check_in()
        order = paid.pos_order_id
        credit = order.lines.filtered(lambda line: line.price_unit < 0)
        self.assertEqual(credit.full_product_name, 'Website payment')
        self.assertIn('Paid on website for', credit.customer_note or '')
        self.assertEqual(credit.price_unit, -room_charge)
        self.assertFalse(credit.tax_ids)
        self.assertEqual(order.amount_total, 0)
        self.assertFalse(order.payment_ids)

    def test_check_in_requires_an_open_session(self):
        booking = self.env['fav.booking'].browse(
            self.env['fav.booking'].upsert_from_website(**self._payload(external_ref='WEB-NO-SESSION'))['id']
        )
        with self.assertRaises(UserError):
            booking.action_check_in()
        self.assertEqual(booking.state, 'confirmed')
        self.assertFalse(booking.pos_order_id)

    def test_second_bill_on_a_busy_table_is_allowed(self):
        open_restaurant_session(self.env, self.floor, name='FAV Occupied Register')
        first = self.env['fav.booking'].browse(
            self.env['fav.booking'].upsert_from_website(**self._payload(external_ref='WEB-FIRST'))['id']
        )
        first.action_check_in()
        second = self.env['fav.booking'].browse(
            self.env['fav.booking'].upsert_from_website(**self._payload(
                external_ref='WEB-SECOND',
                date_start='2026-10-20 06:00:00',
                date_end='2026-10-20 08:00:00',
            ))['id']
        )
        second.action_check_in()
        self.assertEqual(second.state, 'checked_in')
        self.assertTrue(second.pos_order_id)
        self.assertNotEqual(second.pos_order_id, first.pos_order_id)
        note = ' '.join(second.message_ids.mapped('body'))
        self.assertIn('already has draft order', note)
