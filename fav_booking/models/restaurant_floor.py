from odoo import api, fields, models
from odoo.exceptions import ValidationError


class RestaurantFloor(models.Model):
    _inherit = 'restaurant.floor'

    fav_schedule_start = fields.Float(
        string='Schedule Opens',
        default=9.0,
        help='Unused by the booking board. The board reads the system parameters '
             'fav_booking.schedule_start_hour and fav_booking.schedule_end_hour.',
    )
    fav_schedule_end = fields.Float(
        string='Schedule Closes',
        default=26.0,
        help='Unused by the booking board. Hours past 24 mean the next day.',
    )
    fav_schedule_slot = fields.Integer(
        string='Schedule Slot (minutes)',
        default=30,
        help='Unused by the booking board. Rows are fixed at 30 minutes.',
    )

    @api.constrains('fav_schedule_start', 'fav_schedule_end', 'fav_schedule_slot')
    def _check_fav_schedule_hours(self):
        for floor in self:
            if floor.fav_schedule_end <= floor.fav_schedule_start:
                raise ValidationError(self.env._(
                    'Schedule close for %(floor)s must be after it opens.',
                    floor=floor.display_name,
                ))
            if floor.fav_schedule_slot <= 0:
                raise ValidationError(self.env._(
                    'Schedule slot for %(floor)s must be a positive number of minutes.',
                    floor=floor.display_name,
                ))
