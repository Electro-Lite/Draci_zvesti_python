from config import Config,InfoType


class PrintTool:
    @staticmethod
    def tprint(*args, type: InfoType = InfoType.DEBUG , **kwargs):
        """
        Typed print
        Works like print(), print can be enabled or disabled in conf for each InfoType.
        """
        if (type == InfoType.INFO and Config.print_info_enabled):
            print(*args, **kwargs)
        elif (type == InfoType.DEBUG and Config.print_debug_enabled):
            print(*args, **kwargs)    
        elif (type == InfoType.DISPLAY and Config.print_display_enabled):
            print(*args, **kwargs)  
tprint = PrintTool.tprint

class MaxRoundsExceededError(Exception):
    """Raised when the maximum number of game rounds is exceeded."""
    pass