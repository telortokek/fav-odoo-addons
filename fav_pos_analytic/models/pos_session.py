from odoo import models


class PosSession(models.Model):
    _inherit = 'pos.session'

    def _create_session_account_move(self, orders):
        move = super()._create_session_account_move(orders)
        # After post, so COGS lines created during posting are included.
        if move:
            self.config_id._fav_tag_outlet_analytic(move)
        return move
