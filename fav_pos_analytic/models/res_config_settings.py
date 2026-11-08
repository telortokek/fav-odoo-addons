from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    pos_analytic_account_id = fields.Many2one(
        related='pos_config_id.analytic_account_id',
        readonly=False,
        string='Outlet analytic account',
    )
