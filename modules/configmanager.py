from models import config, SessionManager


def get_config(module, key):
    """
    Get a config parameter
    :param module: Config Module
    :param key: Key to fetch
    :return: A list of matching config variables
    """
    session = SessionManager().session
    ret = []
    print("CM running: ")
    for result in session.query(config.Config).filter_by(module=module, key=key):
        ret.append(result.value)
    return ret or None


def set_config(module, key, value, overwrite=False):
    session = SessionManager().session
    if overwrite:
        res = session.update(config.Config).where(config.Config.module == module).\
            where(config.Config.key == key).values(value=value)
    else:
        conf = config.Config(module=module, key=key, value=value)
        session.add(conf)
        session.commit()
