import json

CONFIG_PATH = '/static/config/pico_config.json'

_defaults = {
    'hostname':     'picoctrl',
    'wifi_ssid':    '',
    'wifi_password': '',
    'admin_pass':   'hal9000',
    'viewer_pass':  'daisy',
}

_config = {}


def load():
    global _config
    try:
        with open(CONFIG_PATH, 'r') as f:
            _config = json.load(f)
        # Fill in any missing keys with defaults
        for k, v in _defaults.items():
            if k not in _config:
                _config[k] = v
        print(f"Config loaded: {_config}")
    except OSError:
        print("No config file — using defaults")
        _config = dict(_defaults)


def save():
    with open(CONFIG_PATH, 'w') as f:
        json.dump(_config, f)
    print(f"Config saved: {_config}")


def get(key, default=None):
    return _config.get(key, _defaults.get(key, default))


def set(key, value):
    _config[key] = value
    save()


def all():
    return dict(_config)


# Load on import
load()
