{
    'name': 'FAV Booking',
    'version': '20.0.1.0.0',
    'category': 'Sales/Point of Sale',
    'summary': 'Rental bookings from the FAV website, linked to sales and POS',
    'description': """
FAV Booking stores rental-slot bookings inside Odoo.

The customer-facing booking website remains separate. It creates and confirms
bookings here, keyed by an external reference. Cashiers then attach food and
beverage lines on a Point of Sale order and link that order to the booking.
    """,
    'author': 'FAV',
    'license': 'LGPL-3',
    'depends': [
        'mail',
        'sale',
        'point_of_sale',
    ],
    'data': [
        'security/fav_booking_security.xml',
        'security/ir.access.csv',
        'data/ir_sequence_data.xml',
        'views/fav_booking_views.xml',
        'views/fav_booking_menus.xml',
    ],
    'installable': True,
    'application': True,
}
