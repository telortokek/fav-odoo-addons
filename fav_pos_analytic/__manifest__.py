{
    'name': 'FAV POS Outlet Analytic',
    'version': '20.0.1.0.0',
    'category': 'Sales/Point of Sale',
    'summary': 'Tag POS income and P&L lines with the outlet analytic account',
    'description': """
Each Point of Sale can store an outlet analytic account. When the session
closes, or when an order is invoiced, income and other profit-and-loss lines
receive that account at 100%. Receivable, bank, cash, and tax lines are left
untagged.
    """,
    'author': 'FAV',
    'license': 'LGPL-3',
    'depends': [
        'point_of_sale',
        'analytic',
    ],
    'data': [
        'views/pos_config_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'installable': True,
    'application': False,
}
