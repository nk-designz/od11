DOMAIN = "od11"

DEFAULT_WS_PATH = "/ws"
DEFAULT_PROTOCOL_MAJOR = 0
DEFAULT_PROTOCOL_MINOR = 4
DEFAULT_NAME = "guest"
DEFAULT_UID = "uid-od11-ha"
DEFAULT_COLOR_INDEX = 0
DEFAULT_REALTIME = True

# Canonical source names for convenience services / matching
CANONICAL_SOURCES = {
    "airplay": 0,
    "spotify": 1,
    "playlist": 2,
    "linein": 3,
    "optical": 4,
    "bluetooth": 5,
}

SOURCE_ALIASES = {
    # Bluetooth
    "b": "bluetooth", "bt": "bluetooth", "blue": "bluetooth",
    # Optical
    "o": "optical", "opt": "optical",
    # Line in
    "l": "linein", "li": "linein", "line": "linein",
    # Spotify
    "s": "spotify", "sp": "spotify", "spot": "spotify",
    # AirPlay
    "a": "airplay", "ap": "airplay", "air": "airplay",
    # Playlist
    "p": "playlist", "pl": "playlist",
}
