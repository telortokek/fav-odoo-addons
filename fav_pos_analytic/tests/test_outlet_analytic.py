import uuid

from odoo import Command, fields
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestFavPosOutletAnalytic(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.group_ids += cls.env.ref('point_of_sale.group_pos_manager')
        cls._ensure_chart()
        cls.suffix = uuid.uuid4().hex[:6]
        cls.plan = cls.env['account.analytic.plan'].create({
            'name': f'Outlet {cls.suffix}',
        })
        cls.outlet = cls.env['account.analytic.account'].create({
            'name': f'FAV Setiabudi {cls.suffix}',
            'code': f'S{cls.suffix[:4].upper()}',
            'plan_id': cls.plan.id,
        })
        cls.income_account = cls._create_account('FAV POS Income', 'income')
        cls.discount_account = cls._create_account('FAV POS Discount', 'income')
        cls.cogs_account = cls._create_account('FAV POS COGS', 'expense_direct_cost')
        cls.tax_account = cls._create_account('FAV POS Tax', 'liability_current')
        cls.tax = cls.env['account.tax'].create({
            'name': f'FAV 10% {cls.suffix}',
            'amount_type': 'percent',
            'amount': 10,
            'type_tax_use': 'sale',
            'invoice_repartition_line_ids': [
                Command.create({'repartition_type': 'base'}),
                Command.create({
                    'repartition_type': 'tax',
                    'account_id': cls.tax_account.id,
                }),
            ],
            'refund_repartition_line_ids': [
                Command.create({'repartition_type': 'base'}),
                Command.create({
                    'repartition_type': 'tax',
                    'account_id': cls.tax_account.id,
                }),
            ],
        })
        cls.revenue_product = cls._create_product(
            'FAV Analytic Room Hour', 100, cls.income_account, cls.tax,
        )
        cls.discount_product = cls._create_product(
            'FAV Analytic Discount', -25, cls.discount_account, cls.env['account.tax'],
        )
        cls.cogs_product = cls._create_product(
            'FAV Analytic COGS', 40, cls.cogs_account, cls.env['account.tax'],
        )
        cls.cash_journal = cls.env['account.journal'].create({
            'name': f'FAV Analytic Cash {cls.suffix}',
            'type': 'cash',
            'code': cls._free_journal_code(),
            'company_id': cls.env.company.id,
            'profit_account_id': cls.income_account.id,
            'loss_account_id': cls.cogs_account.id,
        })
        cls.cash_pm = cls.env['pos.payment.method'].create({
            'name': f'FAV Analytic Cash {cls.suffix}',
            'type': 'cash',
            'journal_id': cls.cash_journal.id,
        })
        cls.config = cls.env['pos.config'].create({
            'name': f'FAV Analytic Register {cls.suffix}',
            'payment_method_ids': [Command.set([cls.cash_pm.id])],
            'analytic_account_id': cls.outlet.id,
        })

    @classmethod
    def _ensure_chart(cls):
        company = cls.env.company
        income = cls.env['account.account'].search([
            ('account_type', '=', 'income'),
            ('company_ids', 'in', company.ids),
        ], limit=1)
        if not income:
            if not company.country_id:
                company.country_id = cls.env.ref('base.us')
            cls.env['account.chart.template'].try_loading('generic_coa', company)
        if not company.account_fiscal_country_id:
            company.account_fiscal_country_id = company.country_id or cls.env.ref('base.us')

    @classmethod
    def _create_account(cls, name, account_type):
        return cls.env['account.account'].create({
            'name': f'{name} {cls.suffix}',
            'code': cls._free_account_code(),
            'account_type': account_type,
        })

    @classmethod
    def _free_account_code(cls):
        Account = cls.env['account.account']
        for _attempt in range(20):
            code = f'9{uuid.uuid4().hex[:5]}'
            if not Account.search([('code', '=', code)], limit=1):
                return code
        raise AssertionError('no free account code')

    @classmethod
    def _free_journal_code(cls):
        Journal = cls.env['account.journal']
        company = cls.env.company
        for _attempt in range(20):
            code = uuid.uuid4().hex[:5].upper()
            if not Journal.search([
                ('code', '=', code),
                ('company_id', '=', company.id),
            ], limit=1):
                return code
        raise AssertionError('no free journal code')

    @classmethod
    def _create_product(cls, name, price, account, tax):
        return cls.env['product.product'].create({
            'name': f'{name} {cls.suffix}',
            'type': 'service',
            'list_price': price,
            'available_in_pos': True,
            'sale_ok': True,
            'taxes_id': [Command.set(tax.ids)],
            'property_account_income_id': account.id,
        })

    def _open_session(self):
        self.config.open_ui()
        session = self.config.current_session_id
        session.set_opening_control(0, '')
        self.assertEqual(session.state, 'opened')
        return session

    def _create_draft_order(self, products, partner=None, to_invoice=False):
        extra = {}
        if partner:
            extra['partner_id'] = partner.id
        if to_invoice:
            extra['to_invoice'] = True
        order_vals = {
            'amount_total': 0,
            'amount_paid': 0,
            'amount_tax': 0,
            'amount_return': 0,
            'state': 'draft',
            'date_order': fields.Datetime.to_string(fields.Datetime.now()),
            'company_id': self.env.company.id,
            'session_id': self.config.current_session_id.id,
            'lines': [Command.create({
                'qty': 1,
                'product_id': product.id,
                'price_unit': product.lst_price,
                'price_subtotal': product.lst_price,
                'tax_ids': [Command.set(product.taxes_id.ids)],
                'price_subtotal_incl': 0,
            }) for product in products],
            **extra,
        }
        data = self.env['pos.order'].sync_from_ui([order_vals])
        return self.env['pos.order'].browse(data['pos.order'][0]['id'])

    def _pay(self, order):
        order._compute_prices()
        order.add_payment({
            'pos_order_id': order.id,
            'amount': order.amount_total,
            'payment_method_id': self.cash_pm.id,
        })
        order.with_context(generate_pdf=False)._process_saved_order(False)
        self.assertEqual(order.state, 'paid')
        return order

    def _close(self, session):
        closing = session.get_closing_control_data()
        counted = closing['default_cash_details']['payment_amount']
        result = session.close_session_from_ui({self.cash_pm.id: counted})
        self.assertTrue(result['status'], result)
        self.assertEqual(session.state, 'closed')

    def _assert_tagged(self, lines):
        self.assertTrue(lines)
        expected_key = str(self.outlet.id)
        # Odoo stores the account on a plan column, not on analytic line account_id
        # (that field is only the project plan).
        column = self.plan._column_name()
        for line in lines:
            distribution = line.analytic_distribution or {}
            self.assertIn(expected_key, distribution)
            self.assertAlmostEqual(distribution[expected_key], 100.0)
            analytic_lines = line.analytic_line_ids
            self.assertTrue(analytic_lines)
            self.assertEqual(analytic_lines.mapped(column), self.outlet)

    def _assert_untagged(self, lines):
        expected_key = str(self.outlet.id)
        column = self.plan._column_name()
        for line in lines:
            distribution = line.analytic_distribution or {}
            self.assertNotIn(expected_key, distribution)
            self.assertFalse(line.analytic_line_ids.filtered(
                lambda analytic: analytic[column] == self.outlet,
            ))

    def test_close_session_tags_revenue_and_pnl_lines(self):
        session = self._open_session()
        order = self._create_draft_order([
            self.revenue_product,
            self.discount_product,
            self.cogs_product,
        ])
        self._pay(order)
        self._close(session)

        move = session.sale_move_ids
        self.assertEqual(len(move), 1)
        self.assertEqual(move.state, 'posted')
        income = move.line_ids.filtered(
            lambda line: line.account_id.account_type == 'income' and line.display_type == 'product',
        )
        cogs = move.line_ids.filtered(
            lambda line: line.account_id.account_type == 'expense_direct_cost',
        )
        tax = move.line_ids.filtered(lambda line: line.display_type == 'tax')
        receivable = move.line_ids.filtered(
            lambda line: line.display_type == 'payment_term'
            or line.account_id.account_type in ('asset_receivable', 'asset_cash'),
        )
        self.assertGreaterEqual(len(income), 2)
        self._assert_tagged(income)
        self._assert_tagged(cogs)
        self._assert_untagged(tax)
        self._assert_untagged(receivable)

    def test_pos_invoice_lines_carry_the_outlet(self):
        self._open_session()
        partner = self.env['res.partner'].create({'name': f'FAV Guest {self.suffix}'})
        order = self._create_draft_order(
            [self.revenue_product, self.discount_product, self.cogs_product],
            partner=partner,
            to_invoice=True,
        )
        self._pay(order)
        invoice = order.account_move
        self.assertEqual(invoice.state, 'posted')
        self.assertNotEqual(invoice, order.session_id.sale_move_ids)
        product_lines = invoice.line_ids.filtered(lambda line: line.display_type == 'product')
        income = product_lines.filtered(lambda line: line.account_id.account_type == 'income')
        cogs = product_lines.filtered(
            lambda line: line.account_id.account_type == 'expense_direct_cost',
        )
        tax = invoice.line_ids.filtered(lambda line: line.display_type == 'tax')
        receivable = invoice.line_ids.filtered(lambda line: line.display_type == 'payment_term')
        self._assert_tagged(income)
        self._assert_tagged(cogs)
        self._assert_untagged(tax)
        self._assert_untagged(receivable)

    def test_room_shows_the_register_outlet(self):
        if 'fav.room' not in self.env or 'floor_ids' not in self.config._fields:
            self.skipTest('fav.room is not installed')
        floor = self.env['restaurant.floor'].create({'name': f'FAV Analytic Floor {self.suffix}'})
        self.config.floor_ids = [Command.link(floor.id)]
        table = self.env['restaurant.table'].create({
            'floor_id': floor.id,
            'table_number': 1,
        })
        room = self.env['fav.room'].create({
            'name': f'Analytic Room {self.suffix}',
            'code': f'FAV-AN-{self.suffix}',
            'table_id': table.id,
            'product_id': self.revenue_product.id,
        })
        self.assertEqual(room.outlet_analytic_account_id, self.outlet)

    def test_register_without_an_outlet_is_left_untagged(self):
        self.config.analytic_account_id = False
        session = self._open_session()
        order = self._create_draft_order([self.revenue_product])
        self._pay(order)
        self._close(session)
        income = session.sale_move_ids.line_ids.filtered(
            lambda line: line.account_id.account_type == 'income',
        )
        self.assertTrue(income)
        self._assert_untagged(income)
