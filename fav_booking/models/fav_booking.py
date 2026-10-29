import logging

import psycopg2

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command
from odoo.tools import float_round

_logger = logging.getLogger(__name__)

# Linear progress of a booking. Cancelled is a side exit from the open states.
_STATE_RANK = {
    'draft': 0,
    'confirmed': 1,
    'checked_in': 2,
    'done': 3,
    'cancelled': -1,
}
_NEXT_STATES = {
    'draft': {'confirmed', 'cancelled'},
    'confirmed': {'checked_in', 'cancelled'},
    'checked_in': {'done', 'cancelled'},
    'done': set(),
    'cancelled': {'draft'},
}


class FavBooking(models.Model):
    _name = 'fav.booking'
    _description = 'FAV Booking'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_start desc, id desc'

    _external_ref_company_uniq = models.Constraint(
        'UNIQUE(external_ref, company_id)',
        'A booking with this external reference already exists for this company.',
    )
    _date_start_idx = models.Index('(date_start DESC, id DESC)')

    name = fields.Char(
        string='Number',
        required=True,
        copy=False,
        readonly=True,
        default='New',
        index='trigram',
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Customer',
        required=True,
        tracking=True,
        index=True,
        check_company=True,
        ondelete='restrict',
    )
    product_id = fields.Many2one(
        'product.product',
        string='Resource',
        required=True,
        tracking=True,
        check_company=True,
        ondelete='restrict',
        domain="[('sale_ok', '=', True)]",
        help='Rentable unit or slot, sold as a product.',
    )
    date_start = fields.Datetime(string='Start', required=True, tracking=True, index=True)
    date_end = fields.Datetime(string='End', required=True, tracking=True)
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('confirmed', 'Confirmed'),
            ('checked_in', 'Checked In'),
            ('done', 'Done'),
            ('cancelled', 'Cancelled'),
        ],
        string='Status',
        required=True,
        default='draft',
        copy=False,
        tracking=True,
        index=True,
    )
    external_ref = fields.Char(
        string='External Reference',
        copy=False,
        index=True,
        help='Idempotency key sent by the booking website.',
    )
    pos_order_id = fields.Many2one(
        'pos.order',
        string='POS Order',
        copy=False,
        index=True,
        check_company=True,
        ondelete='set null',
        help='Point of Sale order where the cashier adds food and beverages.',
    )
    sale_order_id = fields.Many2one(
        'sale.order',
        string='Sales Order',
        copy=False,
        index=True,
        check_company=True,
        ondelete='set null',
    )
    amount_untaxed = fields.Monetary(string='Untaxed Amount', tracking=True)
    amount_tax = fields.Monetary(string='Taxes', tracking=True)
    amount_total = fields.Monetary(string='Total', tracking=True)
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        required=True,
        default=lambda self: self.env.company.currency_id,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        index=True,
        default=lambda self: self.env.company,
    )
    note = fields.Text()
    room_id = fields.Many2one(
        'fav.room',
        string='Room',
        tracking=True,
        index=True,
        ondelete='restrict',
        check_company=True,
    )
    amount_down_payment = fields.Monetary(
        string='Payment',
        tracking=True,
        help='Amount already paid on the website. '
             'Check-in adds it as a negative line on the open POS bill, '
             'not as cash taken in the register.',
    )
    duration_hours = fields.Float(
        string='Hours',
        compute='_compute_duration_hours',
        digits=(16, 2),
    )

    @api.depends('date_start', 'date_end')
    def _compute_duration_hours(self):
        for booking in self:
            if booking.date_start and booking.date_end:
                booking.duration_hours = booking._booked_hours()
            else:
                booking.duration_hours = 0.0

    def _booked_hours(self):
        self.ensure_one()
        if not self.date_start or not self.date_end or self.date_end <= self.date_start:
            return 0.0
        hours = (self.date_end - self.date_start).total_seconds() / 3600.0
        return float_round(hours, precision_rounding=0.01)

    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        for booking in self:
            if booking.date_end <= booking.date_start:
                raise ValidationError(self.env._('The booking end must be after the start.'))

    @api.constrains('room_id', 'date_start', 'date_end', 'state')
    def _check_room_overlap(self):
        for booking in self:
            if not booking.room_id or booking.state == 'cancelled':
                continue
            if not booking.date_start or not booking.date_end:
                continue
            # Serialize overlapping writes for this room.
            self.env.cr.execute(
                'SELECT id FROM fav_room WHERE id = %s FOR UPDATE',
                (booking.room_id.id,),
            )
            overlap = self.search([
                ('id', '!=', booking.id),
                ('room_id', '=', booking.room_id.id),
                ('state', '!=', 'cancelled'),
                ('date_start', '<', booking.date_end),
                ('date_end', '>', booking.date_start),
            ], limit=1)
            if overlap:
                raise ValidationError(self.env._(
                    'Booking %(name)s overlaps %(other)s in %(room)s.',
                    name=booking.display_name,
                    other=overlap.display_name,
                    room=booking.room_id.display_name,
                ))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals.get('name') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('fav.booking') or 'New'
            if vals.get('external_ref'):
                vals['external_ref'] = vals['external_ref'].strip() or False
        return super().create(vals_list)

    def action_confirm(self):
        self._change_state('confirmed')

    def action_check_in(self):
        """Open a draft POS bill on the room's table, then mark the booking checked in."""
        for booking in self:
            if 'checked_in' not in _NEXT_STATES[booking.state]:
                raise UserError(self.env._(
                    'Cannot move booking %(name)s from %(current)s to %(new)s.',
                    name=booking.display_name,
                    current=booking.state,
                    new='checked_in',
                ))
            booking._create_check_in_pos_order()
        self._change_state('checked_in')

    def action_done(self):
        self._change_state('done')

    def action_cancel(self):
        self._change_state('cancelled')

    def action_draft(self):
        self._change_state('draft')

    def action_create_sale_order(self):
        """Create a draft sales order for the rental product and link it."""
        self.ensure_one()
        if self.sale_order_id:
            return self.action_open_sale_order()
        price = self.amount_untaxed or self.amount_total
        order = self.env['sale.order'].create({
            'partner_id': self.partner_id.id,
            'company_id': self.company_id.id,
            'origin': self.name,
            'client_order_ref': self.external_ref or False,
            'order_line': [Command.create({
                'product_id': self.product_id.id,
                'product_uom_qty': 1.0,
            })],
        })
        if price:
            order.order_line.write({'price_unit': price})
        self.sale_order_id = order
        return self.action_open_sale_order()

    def action_open_sale_order(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Sales Order'),
            'res_model': 'sale.order',
            'view_mode': 'form',
            'res_id': self.sale_order_id.id,
        }

    def action_open_pos_order(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('POS Order'),
            'res_model': 'pos.order',
            'view_mode': 'form',
            'res_id': self.pos_order_id.id,
        }

    def _change_state(self, new_state):
        for booking in self:
            allowed = _NEXT_STATES[booking.state]
            if new_state not in allowed:
                raise UserError(self.env._(
                    'Cannot move booking %(name)s from %(current)s to %(new)s.',
                    name=booking.display_name,
                    current=booking.state,
                    new=new_state,
                ))
        self.write({'state': new_state})

    @api.model
    def upsert_from_website(
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
        """Create or replay a booking identified by ``external_ref``.

        A second call with the same reference returns the existing booking.
        While the booking is draft or confirmed, customer, resource, schedule
        and amounts are updated. Later states keep those fields. A requested
        status is applied only when it is a legal next step; a stale earlier
        status is ignored so website retries stay successful.

        Authenticate with a bearer API key of scope ``rpc`` (see the module
        README). The user needs FAV Booking access. Creating a customer also
        needs Contact Creation (Settings / partner manager).
        """
        self.check_access('write')
        amount_down_payment = self._website_payment_amount(amount_paid, amount_down_payment)
        external_ref = (external_ref or '').strip()
        if not external_ref:
            raise UserError(self.env._('external_ref is required.'))
        self._check_state_name(state)

        company = self._company_from_payload(company_id)
        booking = self.search([
            ('external_ref', '=', external_ref),
            ('company_id', '=', company.id),
        ], limit=1)
        created = False
        if not booking:
            partner_record = self._partner_from_payload(partner_id, partner)
            room, product = self._room_and_product_from_payload(
                room_id, room_code, product_id, product_code, company,
            )
            vals = self._booking_vals(
                external_ref, partner_record, product, date_start, date_end,
                state, amount_untaxed, amount_tax, amount_total, note, company,
                room, amount_down_payment,
            )
            try:
                with self.env.cr.savepoint():
                    # Staff have no create right. The website method is the only creator.
                    booking = self.sudo().create(vals)
                    created = True
            except psycopg2.errors.UniqueViolation:
                booking = self.search([
                    ('external_ref', '=', external_ref),
                    ('company_id', '=', company.id),
                ], limit=1)
                if not booking:
                    raise
        if not created:
            self._update_existing(
                booking, date_start, date_end, partner_id, partner, product_id,
                product_code, room_id, room_code, state, amount_untaxed, amount_tax,
                amount_total, amount_down_payment, note,
            )
        _logger.info(
            'FAV booking %s external_ref=%s created=%s state=%s',
            booking.name, external_ref, created, booking.state,
        )
        return booking._to_api_dict(created)

    def _update_existing(
        self, booking, date_start, date_end, partner_id, partner, product_id,
        product_code, room_id, room_code, state, amount_untaxed, amount_tax,
        amount_total, amount_down_payment, note,
    ):
        if booking.state in ('draft', 'confirmed'):
            partner_record = booking._partner_from_payload(partner_id, partner)
            room, product = booking._room_and_product_from_payload(
                room_id, room_code, product_id, product_code, booking.company_id,
            )
            booking.write({
                'partner_id': partner_record.id,
                'product_id': product.id,
                'room_id': room.id,
                'date_start': booking._to_datetime(date_start, 'date_start'),
                'date_end': booking._to_datetime(date_end, 'date_end'),
                'amount_untaxed': amount_untaxed or 0.0,
                'amount_tax': amount_tax or 0.0,
                'amount_total': booking._amount_total(amount_untaxed, amount_tax, amount_total),
                'amount_down_payment': amount_down_payment or 0.0,
                'note': note or False,
            })
        booking._apply_requested_state(state)

    def _apply_requested_state(self, requested):
        self.ensure_one()
        if not requested or requested == self.state:
            return
        self._check_state_name(requested)
        if requested in _NEXT_STATES[self.state]:
            self.write({'state': requested})
            return
        current_rank = _STATE_RANK[self.state]
        requested_rank = _STATE_RANK[requested]
        # Stale retry of an earlier status, or a replay after cancel.
        if requested_rank < current_rank or self.state == 'cancelled' or requested == 'cancelled':
            return
        raise UserError(self.env._(
            'Cannot move booking %(name)s from %(current)s to %(new)s.',
            name=self.display_name,
            current=self.state,
            new=requested,
        ))

    @api.model
    def _booking_vals(
        self, external_ref, partner, product, date_start, date_end, state,
        amount_untaxed, amount_tax, amount_total, note, company,
        room, amount_down_payment,
    ):
        return {
            'external_ref': external_ref,
            'partner_id': partner.id,
            'product_id': product.id,
            'room_id': room.id,
            'date_start': self._to_datetime(date_start, 'date_start'),
            'date_end': self._to_datetime(date_end, 'date_end'),
            'state': state or 'draft',
            'amount_untaxed': amount_untaxed or 0.0,
            'amount_tax': amount_tax or 0.0,
            'amount_total': self._amount_total(amount_untaxed, amount_tax, amount_total),
            'amount_down_payment': amount_down_payment or 0.0,
            'note': note or False,
            'company_id': company.id,
            'currency_id': company.currency_id.id,
        }

    @api.model
    def _website_payment_amount(self, amount_paid, amount_down_payment):
        """Prefer ``amount_paid`` when the caller sent it, including zero."""
        if amount_paid is not None:
            return amount_paid or 0.0
        return amount_down_payment or 0.0

    @api.model
    def _amount_total(self, amount_untaxed, amount_tax, amount_total):
        if amount_total is None:
            return (amount_untaxed or 0.0) + (amount_tax or 0.0)
        return amount_total

    @api.model
    def _check_state_name(self, state):
        if state and state not in _STATE_RANK:
            raise UserError(self.env._('Unknown booking status: %s', state))

    @api.model
    def _company_from_payload(self, company_id):
        if not company_id:
            return self.env.company
        company = self.env['res.company'].browse(int(company_id)).exists()
        if not company:
            raise UserError(self.env._('Unknown company.'))
        company.check_access('read')
        return company

    @api.model
    def _partner_from_payload(self, partner_id, partner):
        if partner_id:
            record = self.env['res.partner'].browse(int(partner_id)).exists()
            if not record:
                raise UserError(self.env._('Unknown customer.'))
            record.check_access('read')
            return record
        if isinstance(partner, dict):
            email = (partner.get('email') or '').strip()
            name = (partner.get('name') or '').strip() or email
            if not name:
                raise UserError(self.env._('Customer name or email is required.'))
            if email:
                found = self.env['res.partner'].search([('email', '=ilike', email)], limit=1)
                if found:
                    return found
            return self.env['res.partner'].create({
                'name': name,
                'email': email or False,
                'phone': partner.get('phone') or False,
            })
        raise UserError(self.env._('partner_id or partner is required.'))

    @api.model
    def _product_from_payload(self, product_id, product_code):
        product = self.env['product.product']
        if product_id:
            product = product.browse(int(product_id)).exists()
        elif product_code:
            products = product.search([('default_code', '=', product_code)])
            if len(products) > 1:
                raise UserError(self.env._(
                    'Internal reference %s matches more than one product.',
                    product_code,
                ))
            product = products
        else:
            raise UserError(self.env._('product_id or product_code is required.'))
        if not product:
            raise UserError(self.env._('Unknown resource product.'))
        product.check_access('read')
        return product

    @api.model
    def _room_and_product_from_payload(self, room_id, room_code, product_id, product_code, company):
        """Resolve a website room identifier without dropping the old product payload.

        ``room_id`` and ``room_code`` win. ``product_code`` is also tried as a
        room code so existing callers that send the room's code as the product
        reference keep working. When nothing matches a room, the product is
        resolved exactly as before and the booking has no room.
        """
        room = self.env['fav.room']
        if room_id:
            room = room.browse(int(room_id)).exists()
            if not room or room.company_id != company:
                raise UserError(self.env._('Unknown room.'))
        else:
            code = (room_code or '').strip()
            if code:
                room = self.env['fav.room'].search([
                    ('code', '=', code),
                    ('company_id', '=', company.id),
                ], limit=1)
                if not room:
                    raise UserError(self.env._('Unknown room code: %s', code))
            elif product_code:
                room = self.env['fav.room'].search([
                    ('code', '=', product_code),
                    ('company_id', '=', company.id),
                ], limit=1)
        if room:
            room.check_access('read')
            if product_id and int(product_id) != room.product_id.id:
                raise UserError(self.env._(
                    'Product does not match room %s.',
                    room.display_name,
                ))
            return room, room.product_id
        product = self._product_from_payload(product_id, product_code)
        mapped = self.env['fav.room'].search([
            ('product_id', '=', product.id),
            ('company_id', '=', company.id),
        ])
        if len(mapped) == 1:
            room = mapped
        return room, product

    def _create_check_in_pos_order(self):
        """Create the draft bill for this booking on its POS table.

        The room line quantity is the booked hours at the product's POS price.
        Money already paid on the website is a second line with a negative unit
        price, no taxes, and ``price_type`` ``manual``. It reduces the amount
        still due. It is not a ``pos.payment``, so the register's counted cash
        does not include money the website already collected.
        """
        self.ensure_one()
        if not self.room_id:
            raise UserError(self.env._(
                'Booking %(name)s has no room, so it cannot be checked in on a table.',
                name=self.display_name,
            ))
        room = self.room_id
        table = room.table_id
        if not table or not table.floor_id:
            raise UserError(self.env._(
                'Room %(room)s is not placed on a POS floor.',
                room=room.display_name,
            ))
        if not room.product_id.available_in_pos:
            raise UserError(self.env._(
                'Room %(room)s has a product that is not available in the Point of Sale.',
                room=room.display_name,
            ))
        hours = self._booked_hours()
        if hours <= 0:
            raise UserError(self.env._(
                'Booking %(name)s does not cover a positive number of hours.',
                name=self.display_name,
            ))

        session = self._open_session_for_table(table)
        PosOrder = self.env['pos.order'].sudo()
        existing = PosOrder.search([
            ('table_id', '=', table.id),
            ('state', '=', 'draft'),
            ('session_id.state', '!=', 'closed'),
        ], limit=1)
        if existing:
            label = (table.room_name or '').strip() or str(table.table_number)
            raise UserError(self.env._(
                'Table %(table)s already has open order %(order)s.',
                table=label,
                order=existing.pos_reference or existing.name,
            ))

        product = room.product_id
        price = self._hourly_price(session.config_id, product, hours)
        website_payment = self.amount_down_payment or 0.0
        if self.currency_id.compare_amounts(website_payment, 0) < 0:
            raise UserError(self.env._('The payment cannot be negative.'))

        taxes = product.taxes_id.filtered_domain(
            self.env['account.tax']._check_company_domain(self.company_id)
        )
        order = PosOrder.create({
            'session_id': session.id,
            'partner_id': self.partner_id.id,
            'table_id': table.id,
            'customer_count': 1,
            'fav_booking_id': self.id,
            'amount_tax': 0.0,
            'amount_total': 0.0,
            'amount_paid': 0.0,
            'amount_return': 0.0,
            'lines': [Command.create(self._pos_line_vals(
                product, hours, price, taxes, product.display_name, False,
            ))],
        })
        self._recompute_pos_amounts(order)
        if self.currency_id.compare_amounts(website_payment, 0) > 0:
            if self.currency_id.compare_amounts(website_payment, order.amount_total) > 0:
                order.unlink()
                raise UserError(self.env._(
                    'The payment is higher than the room charge on the bill.',
                ))
            # No taxes: this is cash already collected, not another sale of the room.
            self.env['pos.order.line'].sudo().create(self._pos_line_vals(
                product, 1.0, -website_payment, self.env['account.tax'],
                self.env._('Website payment'),
                self.env._('Paid on website for %s', self.name),
            ) | {'order_id': order.id})
            self._recompute_pos_amounts(order)
        self.pos_order_id = order
        self._notify_open_pos_order(session, order)
        return order

    def _recompute_pos_amounts(self, order):
        for line in order.lines:
            line._onchange_amount_line_all()
        order._compute_prices()

    def _pos_line_vals(self, product, qty, price_unit, taxes, full_name, customer_note):
        return {
            'product_id': product.id,
            'qty': qty,
            'price_unit': price_unit,
            'price_type': 'manual',
            'price_subtotal': 0.0,
            'price_subtotal_incl': 0.0,
            'tax_ids': [Command.set(taxes.ids)],
            'full_product_name': full_name,
            'customer_note': customer_note or False,
        }

    def _hourly_price(self, config, product, hours):
        self.ensure_one()
        pricelist = config.pricelist_id
        if pricelist:
            return pricelist._get_product_price(
                product, hours, currency=self.currency_id, uom=product.uom_id,
            )
        return product.lst_price

    def _open_session_for_table(self, table):
        self.ensure_one()
        configs = table.floor_id.pos_config_ids.filtered(
            lambda config: config.company_id == self.company_id
        )
        sessions = self.env['pos.session'].sudo().search([
            ('config_id', 'in', configs.ids),
            ('state', '=', 'opened'),
        ])
        floor_name = table.floor_id.name
        if not sessions:
            raise UserError(self.env._(
                'No open POS session for floor %(floor)s. Open that register, then check in again.',
                floor=floor_name,
            ))
        if len(sessions) > 1:
            names = ', '.join(sessions.mapped('config_id.name'))
            raise UserError(self.env._(
                'Several POS sessions are open for floor %(floor)s: %(names)s. '
                'Close the extra registers first.',
                floor=floor_name,
                names=names,
            ))
        return sessions

    def _notify_open_pos_order(self, session, order):
        """Ask open POS clients to load this bill. A reload loads it anyway."""
        config = session.config_id
        if not config.current_session_id:
            return
        config.sudo()._notify_synchronisation(session.id, 0, {
            'pos.order': order.ids,
            'pos.order.line': order.lines.ids,
        })

    @api.model
    def _to_datetime(self, value, label):
        if not value:
            raise UserError(self.env._('%s is required.', label))
        try:
            parsed = fields.Datetime.to_datetime(value)
        except (TypeError, ValueError) as error:
            raise UserError(self.env._('%s is not a valid UTC datetime.', label)) from error
        if not parsed:
            raise UserError(self.env._('%s is required.', label))
        return parsed

    def _to_api_dict(self, created):
        self.ensure_one()
        return {
            'id': self.id,
            'name': self.name,
            'state': self.state,
            'external_ref': self.external_ref,
            'partner_id': self.partner_id.id,
            'product_id': self.product_id.id,
            'room_id': self.room_id.id or False,
            'room_code': self.room_id.code or False,
            'date_start': fields.Datetime.to_string(self.date_start),
            'date_end': fields.Datetime.to_string(self.date_end),
            'amount_untaxed': self.amount_untaxed,
            'amount_tax': self.amount_tax,
            'amount_total': self.amount_total,
            'amount_down_payment': self.amount_down_payment,
            'amount_paid': self.amount_down_payment,
            'currency_id': self.currency_id.id,
            'pos_order_id': self.pos_order_id.id or False,
            'sale_order_id': self.sale_order_id.id or False,
            'created': created,
        }
