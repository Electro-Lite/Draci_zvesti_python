from enum import StrEnum


class BattlePhase(StrEnum):
    REVEAL = "reveal"
    DRAGON_ABILITY = "dragon_ability"
    DRAGON_REVEAL_ABILITY = "dragon_reveal_ability"
    DRAGON_MOVE_ABILITY = "dragon_move_ability"
    VERSUS = "versus"
    IMPACT = "impact"
    STALEMATE = "stalemate"
    CARD_DEFEATED = "card_defeated"
    DRAGON_DEFEATED = "dragon_defeated"
    DRAGON_SURVIVED = "dragon_survived"
    FANATIC_TIEBREAK = "fanatic_tiebreak"


FINAL_BATTLE_PHASES = frozenset(
    {BattlePhase.DRAGON_DEFEATED, BattlePhase.DRAGON_SURVIVED, BattlePhase.FANATIC_TIEBREAK}
)
