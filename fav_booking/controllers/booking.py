from odoo import http
from odoo.http import request


class FavBookingController(http.Controller):
    @http.route(
        '/fav/api/booking/upsert',
        type='json2',
        auth='bearer',
        bearer_scope='rpc',
        methods=['POST'],
        csrf=False,
        save_session=False,
    )
    def upsert_booking(
        self,
        external_ref=None,
        date_start=None,
        date_end=None,
        partner_id=None,
        partner=None,
        product_id=None,
        product_code=None,
        room_id=None,
        room_code=None,
        state='confirmed',
        amount_untaxed=0.0,
        amount_tax=0.0,
        amount_total=None,
        amount_down_payment=0.0,
        amount_paid=None,
        note=None,
        company_id=None,
    ):
        """Plain-JSON alias of ``fav.booking.upsert_from_website``.

        ``Authorization: Bearer <api-key>`` with scope ``rpc``.
        Send ``X-Odoo-Database`` when more than one database is served.
        """
        return request.env['fav.booking'].upsert_from_website(
            external_ref=external_ref,
            date_start=date_start,
            date_end=date_end,
            partner_id=partner_id,
            partner=partner,
            product_id=product_id,
            product_code=product_code,
            room_id=room_id,
            room_code=room_code,
            state=state,
            amount_untaxed=amount_untaxed,
            amount_tax=amount_tax,
            amount_total=amount_total,
            amount_down_payment=amount_down_payment,
            amount_paid=amount_paid,
            note=note,
            company_id=company_id,
        )
