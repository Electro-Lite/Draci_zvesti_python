from cards.card_type    import CardType
from typing             import TYPE_CHECKING

if TYPE_CHECKING:
    from cards.card                 import Card
    from cards.mana                 import ManaColor
    from cards.power                import Power
    from core.board                 import Board
    from core.player                import Player
    from cards.ability.abilities    import Ability

class Card:
    def __init__(
        self,
        owner:"Player"      = None,
        id                  = 0,
        name:str            = "",
        power:"Power"       = None,
        color:"ManaColor"   = None,
        color_buf           = [0, 0], #[dmg, hp]
        hp:int              = 0,
        dmg:int             = 0,
        ability:"Ability" = None,
        image:str           = None, #path to image
        type:CardType       = CardType.PLAYER
    ) -> None:
        self.init_args = [id, name, power, color,
                          color_buf if color_buf is not None else [0, 0],
                          hp, dmg, ability, image, type]

        self.owner      = owner
        self.id         = id  # database given
        self.name       = name
        self.power      = power
        self.color      = color
        self.color_buf  = color_buf if color_buf is not None else [0, 0]
        self.hp         = hp
        self.dmg        = dmg
        self.ability    = ability
        self.image      = image
        self.type       = type #dragon/player
    def __str__(self):
        return self.name
    def restore(self):
        """Restore the object to its initial state from init_args."""
        (self.id,
         self.name,
         self.power,
         self.color,
         self.color_buf,
         self.hp,
         self.dmg,
         self.ability,
         self.image,
         self.type) = self.init_args.copy() #ensures you don’t accidentally mutate the original list when restoring
        
    def get_neat_ids(self):
        neat_ids  = []
        # power
        neat_ids += self.power.value
        # color
        neat_ids += self.color.value
        # color buf
        neat_ids.extend(self.color_buf)
        # hp
        neat_ids += self.hp
        # dmg
        neat_ids += self.dmg
        # ability
        neat_ids += self.ability.id
        return neat_ids
