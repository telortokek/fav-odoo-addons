{
    'name': 'FAV POS Room Names',
    'version': '20.0.1.0.0',
    'category': 'Sales/Point of Sale',
    'summary': 'Show a room name on restaurant POS tables',
    'description': """
FAV rents rooms. Point of Sale restaurant mode uses those rooms as tables,
and Odoo only stores an integer table number. This module adds a room name
and shows it on the floor plan, the order header, the order list, and
customer and kitchen tickets. An empty name falls back to the table number.
    """,
    'author': 'FAV',
    'license': 'LGPL-3',
    'depends': [
        'pos_restaurant',
    ],
    'data': [
        'views/restaurant_table_views.xml',
        'views/pos_order_receipt_templates.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'fav_pos_room/static/src/**/*',
        ],
    },
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
}
