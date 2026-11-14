from enum import StrEnum


class ChoiceType(StrEnum):
    NONE = "none"
    CARD = "card"
    POSITION = "position"
    PASS = "pass"
    USE_ABILITY = "use_ability"
    TARGET = "target"
    PLAY_OR_PASS = "play_or_pass"
    ABILITY_CARD = "ability_card"
    CONTINUE = "continue"
