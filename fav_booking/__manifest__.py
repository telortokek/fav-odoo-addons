{
    'name': 'FAV Booking',
    'version': '20.0.1.2.0',
    'category': 'Sales/Point of Sale',
    'summary': 'Rental bookings from the FAV website, linked to sales and POS',
    'description': """
FAV Booking stores rental-slot bookings inside Odoo.

The customer-facing booking website remains separate. It creates and confirms
bookings here, keyed by an external reference. Staff do not create or edit
bookings in Odoo. Opening the register opens today's bills on the tables.
    """,
    'author': 'FAV',
    'license': 'LGPL-3',
    'depends': [
        'mail',
        'sale',
        'fav_pos_room',
    ],
    'data': [
        'security/fav_booking_security.xml',
        'security/ir.access.csv',
        'data/ir_sequence_data.xml',
        'views/fav_room_views.xml',
        'views/fav_booking_views.xml',
        'views/pos_order_views.xml',
        'views/restaurant_floor_views.xml',
        'views/fav_booking_menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'fav_booking/static/src/schedule/**/*',
        ],
    },
    'installable': True,
    'application': True,
}
