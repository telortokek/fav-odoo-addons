import logging

from odoo import models

_logger = logging.getLogger(__name__)


class PosSession(models.Model):
    _inherit = 'pos.session'

    def create(self, vals_list):
        sessions = super().create(vals_list)
        sessions.filtered(lambda session: session.state == 'opened')._fav_create_today_bills()
        return sessions

    def write(self, vals):
        opening = self.browse()
        if vals.get('state') == 'opened':
            opening = self.filtered(lambda session: session.state != 'opened')
        result = super().write(vals)
        if opening:
            opening.filtered(lambda session: session.state == 'opened')._fav_create_today_bills()
        return result

    def _fav_create_today_bills(self):
        """Open today's confirmed bookings on this register. Never raises."""
        Booking = self.env['fav.booking'].sudo()
        for session in self:
            config = session.config_id
            if not config.module_pos_restaurant or not config.floor_ids:
                continue
            today = Booking._local_today()
            bookings = Booking.search([
                ('state', '=', 'confirmed'),
                ('pos_order_id', '=', False),
                ('floor_id', 'in', config.floor_ids.ids),
            ])
            for booking in bookings:
                if booking._starts_on_local_day(today):
                    booking._try_create_bill(session=session)
                    _logger.info(
                        'FAV session %s considered booking %s for a bill',
                        session.id, booking.name,
                    )
