from odoo import Command, fields


def open_restaurant_session(env, floor, name='FAV Test Register'):
    """Open a restaurant POS session on ``floor`` and return ``(config, session)``."""
    config = env['pos.config'].create({
        'name': name,
        'module_pos_restaurant': True,
        'floor_ids': [Command.link(floor.id)],
    })
    session = env['pos.session'].create({
        'config_id': config.id,
        'start_at': fields.Datetime.now(),
    })
    if session.state != 'opened':
        session.state = 'opened'
    return config, session
