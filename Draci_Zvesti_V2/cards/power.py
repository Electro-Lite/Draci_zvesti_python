from enum import Enum

class Power(Enum):
    """Card/Deck rarity"""
    STARTER     = 0
    NORMAL      = 1
    LEGENDARY   = 2

    def __le__(self, other):
        if isinstance(other, Power):
            return self.value <= other.value
        return NotImplemented  # fallback if other type is incompatible