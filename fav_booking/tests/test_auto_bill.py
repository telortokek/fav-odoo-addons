from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from odoo import fields
from odoo.tests import TransactionCase

from odoo.addons.fav_booking.tests.common import open_restaurant_session


class TestFavAutoBill(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.tz = 'Asia/Jakarta'
        cls.partner = cls.env['res.partner'].create({'name': 'Schedule Guest'})
        cls.product = cls.env['product.product'].create({
            'name': 'Schedule Hour',
            'type': 'service',
            'list_price': 100000,
            'available_in_pos': True,
            'sale_ok': True,
            'default_code': 'FAV-SCHED-HOUR',
        })
        cls.setiabudi = cls.env['restaurant.floor'].create({'name': 'FAV Setiabudi'})
        cls.tenun = cls.env['restaurant.floor'].create({'name': 'FAV Rental Tenun'})
        cls.vip = cls._room(cls.setiabudi, 1, 'VIP PLUS 1', 'FAV-AUTO-VIP', 'VIP PLUS', 1)
        cls.vvip = cls._room(cls.setiabudi, 2, 'VVIP 1', 'FAV-AUTO-VVIP', 'VVIP', 2)
        cls.tenun_room = cls._room(cls.tenun, 1, 'TENUN 1', 'FAV-AUTO-TENUN', 'Suite', 1)

    @classmethod
    def _room(cls, floor, number, name, code, room_type, sequence):
        table = cls.env['restaurant.table'].create({
            'floor_id': floor.id,
            'table_number': number,
            'room_name': name,
            'seats': 2,
        })
        return cls.env['fav.room'].create({
            'name': name,
            'code': code,
            'room_type': room_type,
            'sequence': sequence,
            'table_id': table.id,
            'product_id': cls.product.id,
        })

    def _at(self, day_offset, hour, minute=0):
        tz = ZoneInfo('Asia/Jakarta')
        day = datetime.now(tz).date() + timedelta(days=day_offset)
        local = datetime(day.year, day.month, day.day, hour, minute, tzinfo=tz)
        utc = local.astimezone(ZoneInfo('UTC')).replace(tzinfo=None)
        return fields.Datetime.to_string(utc)

    def _book(self, ref, room_code, start_hour, end_hour, day_offset=0, **extra):
        values = {
            'external_ref': ref,
            'partner_id': self.partner.id,
            'room_code': room_code,
            'date_start': self._at(day_offset, start_hour),
            'date_end': self._at(day_offset, end_hour),
            'state': 'confirmed',
            'amount_paid': 0,
        }
        values.update(extra)
        if end_hour < start_hour:
            values['date_end'] = self._at(day_offset + 1, end_hour)
        result = self.env['fav.booking'].upsert_from_website(**values)
        return self.env['fav.booking'].browse(result['id'])

    def test_opening_the_register_bills_today_only(self):
        today = self._book('WEB-TODAY', 'FAV-AUTO-VIP', 10, 12)
        tomorrow = self._book('WEB-TOMORROW', 'FAV-AUTO-VVIP', 10, 12, day_offset=1)
        _config, session = open_restaurant_session(self.env, self.setiabudi, name='FAV Today Register')
        self.assertEqual(session.state, 'opened')
        self.assertEqual(today.state, 'checked_in')
        self.assertEqual(today.pos_order_id.table_id, self.vip.table_id)
        self.assertEqual(today.pos_order_id.lines.filtered(lambda line: line.fav_line_role == 'room').qty, 2)
        self.assertEqual(tomorrow.state, 'confirmed')
        self.assertFalse(tomorrow.pos_order_id)

    def test_upsert_today_while_open_creates_the_bill(self):
        open_restaurant_session(self.env, self.setiabudi, name='FAV Live Register')
        booking = self._book('WEB-LIVE', 'FAV-AUTO-VIP', 13, 15)
        self.assertEqual(booking.state, 'checked_in')
        self.assertEqual(booking.pos_order_id.state, 'draft')
        self.assertEqual(booking.pos_order_id.partner_id, self.partner)

    def test_reschedule_updates_an_untouched_bill_and_cancel_removes_it(self):
        booking = self._book('WEB-MOVE', 'FAV-AUTO-VIP', 10, 12)
        open_restaurant_session(self.env, self.setiabudi, name='FAV Move Register')
        room_line = booking.pos_order_id.lines.filtered(lambda line: line.fav_line_role == 'room')
        self.assertEqual(room_line.qty, 2)
        self.env['fav.booking'].upsert_from_website(
            external_ref='WEB-MOVE',
            partner_id=self.partner.id,
            room_code='FAV-AUTO-VIP',
            date_start=booking.date_start,
            date_end=self._at(0, 13),
            state='confirmed',
        )
        self.assertEqual(room_line.qty, 3)
        order = booking.pos_order_id
        self.env['pos.order.line'].sudo().create({
            'order_id': order.id,
            'product_id': self.product.id,
            'qty': 1,
            'price_unit': 1000,
            'price_subtotal': 1000,
            'price_subtotal_incl': 1000,
        })
        self.env['fav.booking'].upsert_from_website(
            external_ref='WEB-MOVE',
            partner_id=self.partner.id,
            room_code='FAV-AUTO-VIP',
            date_start=booking.date_start,
            date_end=self._at(0, 16),
            state='confirmed',
        )
        self.assertEqual(room_line.qty, 3)
        self.assertIn('extra lines', ' '.join(booking.message_ids.mapped('body')))

    def test_cancel_removes_an_untouched_bill(self):
        booking = self._book('WEB-CANCEL', 'FAV-AUTO-VVIP', 16, 18)
        open_restaurant_session(self.env, self.setiabudi, name='FAV Cancel Register')
        order = booking.pos_order_id
        self.env['fav.booking'].upsert_from_website(
            external_ref='WEB-CANCEL',
            partner_id=self.partner.id,
            room_code='FAV-AUTO-VVIP',
            date_start=booking.date_start,
            date_end=booking.date_end,
            state='cancelled',
        )
        self.assertEqual(booking.state, 'cancelled')
        self.assertFalse(booking.pos_order_id)
        self.assertEqual(order.state, 'cancel')

    def test_a_bad_payment_does_not_stop_session_open(self):
        booking = self._book('WEB-HUGE', 'FAV-AUTO-VIP', 11, 12, amount_paid=10**12)
        _config, session = open_restaurant_session(self.env, self.setiabudi, name='FAV Huge Register')
        self.assertEqual(session.state, 'opened')
        self.assertEqual(booking.state, 'confirmed')
        self.assertFalse(booking.pos_order_id)
        self.assertIn('Could not open a POS bill', ' '.join(booking.message_ids.mapped('body')))

    def test_schedule_columns_follow_the_outlet(self):
        self._book('WEB-GRID', 'FAV-AUTO-VIP', 10, 12)
        self._book('WEB-TENUN', 'FAV-AUTO-TENUN', 11, 13)
        data = self.env['fav.booking'].get_schedule(floor_id=self.setiabudi.id)
        self.assertEqual(data['floor_id'], self.setiabudi.id)
        self.assertEqual(data['open_hour'], 9.0)
        self.assertEqual(data['close_hour'], 26.0)
        self.assertEqual(data['slot_minutes'], 30)
        names = [room['name'] for group in data['groups'] for room in group['rooms']]
        self.assertEqual(names, ['VIP PLUS 1', 'VVIP 1'])
        self.assertEqual(data['groups'][0]['type'], 'VIP PLUS')
        block = next(item for item in data['bookings'] if item['name'].startswith('BK'))
        vip_block = next(item for item in data['bookings'] if item['room_id'] == self.vip.id)
        self.assertEqual(vip_block['start_minute'], 60)
        self.assertEqual(vip_block['end_minute'], 180)
        self.assertEqual(vip_block['partner'], 'Schedule Guest')
        self.assertTrue(any(floor['name'] == 'FAV Rental Tenun' for floor in data['floors']))
        tenun = self.env['fav.booking'].get_schedule(floor_id=self.tenun.id)
        tenun_names = [room['name'] for group in tenun['groups'] for room in group['rooms']]
        self.assertEqual(tenun_names, ['TENUN 1'])
        self.assertEqual(len(tenun['bookings']), 1)
        self.assertNotEqual(block['room_id'], self.tenun_room.id)
