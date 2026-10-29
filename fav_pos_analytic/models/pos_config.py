from odoo import fields, models

# Profit-and-loss account types. Balance-sheet types (receivable, bank, cash,
# tax liabilities) are intentionally absent.
FAV_PNL_ACCOUNT_TYPES = (
    'income',
    'income_other',
    'expense',
    'expense_depreciation',
    'expense_direct_cost',
)
FAV_SKIP_DISPLAY_TYPES = (
    'payment_term',
    'tax',
    'line_section',
    'line_subsection',
    'line_note',
)


class PosConfig(models.Model):
    _inherit = 'pos.config'

    analytic_account_id = fields.Many2one(
        'account.analytic.account',
        string='Outlet analytic account',
        check_company=True,
        help='Applied at 100% to income, discount, and other profit-and-loss lines '
             'when this register closes a session or invoices an order. '
             'Receivable, bank, cash, and tax lines are not tagged.',
    )

    def _fav_outlet_analytic_distribution(self):
        self.ensure_one()
        if not self.analytic_account_id:
            return {}
        return {str(self.analytic_account_id.id): 100.0}

    def _fav_tag_outlet_analytic(self, moves):
        """Set the outlet distribution on P&L lines of ``moves``."""
        self.ensure_one()
        distribution = self._fav_outlet_analytic_distribution()
        if not distribution or not moves:
            return
        lines = moves.line_ids.filtered(lambda line: self._fav_line_takes_outlet_analytic(line))
        if lines:
            # Session and invoice moves are posted before this runs, including COGS
            # lines created during posting. The analytic inverse recreates analytic lines.
            lines.sudo().write({'analytic_distribution': distribution})

    def _fav_line_takes_outlet_analytic(self, line):
        if line.display_type in FAV_SKIP_DISPLAY_TYPES:
            return False
        return line.account_id.account_type in FAV_PNL_ACCOUNT_TYPES
