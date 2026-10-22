import logging

import psycopg2

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command

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

    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        for booking in self:
            if booking.date_end <= booking.date_start:
                raise ValidationError(self.env._('The booking end must be after the start.'))

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
        state='confirmed',
        amount_untaxed=0.0,
        amount_tax=0.0,
        amount_total=None,
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
            product = self._product_from_payload(product_id, product_code)
            vals = self._booking_vals(
                external_ref, partner_record, product, date_start, date_end,
                state, amount_untaxed, amount_tax, amount_total, note, company,
            )
            try:
                with self.env.cr.savepoint():
                    booking = self.create(vals)
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
                product_code, state, amount_untaxed, amount_tax, amount_total, note,
            )
        _logger.info(
            'FAV booking %s external_ref=%s created=%s state=%s',
            booking.name, external_ref, created, booking.state,
        )
        return booking._to_api_dict(created)

    def _update_existing(
        self, booking, date_start, date_end, partner_id, partner, product_id,
        product_code, state, amount_untaxed, amount_tax, amount_total, note,
    ):
        if booking.state in ('draft', 'confirmed'):
            partner_record = booking._partner_from_payload(partner_id, partner)
            product = booking._product_from_payload(product_id, product_code)
            booking.write({
                'partner_id': partner_record.id,
                'product_id': product.id,
                'date_start': booking._to_datetime(date_start, 'date_start'),
                'date_end': booking._to_datetime(date_end, 'date_end'),
                'amount_untaxed': amount_untaxed or 0.0,
                'amount_tax': amount_tax or 0.0,
                'amount_total': booking._amount_total(amount_untaxed, amount_tax, amount_total),
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
    ):
        return {
            'external_ref': external_ref,
            'partner_id': partner.id,
            'product_id': product.id,
            'date_start': self._to_datetime(date_start, 'date_start'),
            'date_end': self._to_datetime(date_end, 'date_end'),
            'state': state or 'draft',
            'amount_untaxed': amount_untaxed or 0.0,
            'amount_tax': amount_tax or 0.0,
            'amount_total': self._amount_total(amount_untaxed, amount_tax, amount_total),
            'note': note or False,
            'company_id': company.id,
            'currency_id': company.currency_id.id,
        }

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
            'date_start': fields.Datetime.to_string(self.date_start),
            'date_end': fields.Datetime.to_string(self.date_end),
            'amount_untaxed': self.amount_untaxed,
            'amount_tax': self.amount_tax,
            'amount_total': self.amount_total,
            'currency_id': self.currency_id.id,
            'pos_order_id': self.pos_order_id.id or False,
            'sale_order_id': self.sale_order_id.id or False,
            'created': created,
        }
