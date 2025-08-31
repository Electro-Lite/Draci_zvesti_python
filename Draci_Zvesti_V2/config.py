from enum import Enum
import core.player_type as player_type
PlayerType = player_type.PlayerType


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
    default_player_type = PlayerType.RND
