from enum import Enum


MIN_DECK_SIZE = 10
MAX_DECK_SIZE = 12


class InfoType(Enum):
    INFO    = 0
    DEBUG   = 1
    DISPLAY = 2
class Config():
    ### print config ###
    print_info_enabled      = True
    print_debug_enabled     = True
    print_display_enabled   = True
    
    ### game config ###
    max_rounds = 10
    turn_count_limit = 50

    ### online lobby server ###
    # Cloudflare terminates TLS and proxies this secure WebSocket endpoint to
    # the local online relay. Use ws://127.0.0.1:47888/game for local testing.
    lobby_server_url = "wss://draci-zvesti.kluck.uk/game"
    lobby_server_port = 47888
