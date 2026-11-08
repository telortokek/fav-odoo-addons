def post_init_hook(env):
    """Fill blank room names on the FAV Setiabudi floor once, at install."""
    env['restaurant.table'].assign_setiabudi_room_names()
