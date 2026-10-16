import hashlib
import random
from dataclasses import dataclass, field
from typing import Optional

from .                                      import game_info as gi
from .                                      import player as p
from config                                 import Config
from core.board                             import Board
# from utils.print_tool                       import *
from display_strategies.display_strategy    import DisplayStrategy
from cards.mana                             import ManaColor
from core.enums.game_state                  import GameState

Player      = p.Player
GameInfo    = gi.GameInfo


@dataclass(frozen=True)
class GameResult:
    player_1_score: int
    player_2_score: int
    winner_id: Optional[int]
    rounds: int
    starting_player_id: int
    seed: Optional[int]
    player_1_card_plays: dict[str, int] = field(default_factory=dict)
    player_2_card_plays: dict[str, int] = field(default_factory=dict)
    player_1_active_ability_uses: dict[str, int] = field(default_factory=dict)
    player_2_active_ability_uses: dict[str, int] = field(default_factory=dict)


def _derived_seed(seed: int, namespace: str) -> int:
    digest = hashlib.sha256(f"{seed}:{namespace}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def _shuffle_deck(deck, seed: Optional[int], namespace: str) -> None:
    if seed is None:
        random.shuffle(deck.cards)
        return
    # Canonicalizing first gives identical compositions the same draw order,
    # even when their generated database IDs or construction order differ.
    deck.cards.sort(key=lambda card: str(card.id))
    composition = ",".join(str(card.id) for card in deck.cards)
    random.Random(_derived_seed(seed, f"{namespace}:{composition}")).shuffle(deck.cards)


def run(
        player_1: Player,
        player_2: Player,
        display_strategy_class: DisplayStrategy = DisplayStrategy,
        board=None,
        seed: Optional[int] = None,
        starting_player_id: Optional[int] = None,
) -> GameResult:
    """run game for players of given type, random if not set"""
    if seed is not None:
        random.seed(_derived_seed(seed, "environment"))
    if board is None:
        board = Board()

    ### Init Game ###
    current_round = 0
    """run game for players of given type, random if not set"""
    ### Init Game ###
    current_round = 0
    run           = True

    # Give each player their own perspective of the game
    info_p1 = GameInfo(board, _opposing_player = player_2)
    info_p2 = GameInfo(board, _opposing_player = player_1)

    display_strategy = display_strategy_class(player_1, player_2, board)

    # Assign unique info objects
    player_1.choice_strategy.info = info_p1  # Info is only needed by neat.
    player_2.choice_strategy.info = info_p2

    player_1.choice_strategy.display    = display_strategy_class  # Info is only needed by pygame.
    player_2.choice_strategy.display    = display_strategy_class

    # player_1.deck=decks_lib.get_base_blue_deck()    # Will be handled by db later
    # player_2.deck=decks_lib.get_base_blue_deck()

    _shuffle_deck(player_1.deck, seed, "deck")
    _shuffle_deck(player_2.deck, seed, "deck")

    player_1.draw_hand()
    player_2.draw_hand()

    player_1.hand.sort()
    player_2.hand.sort()

    if starting_player_id is None:
        player_on_turn = random_player(player_1, player_2)
    elif starting_player_id == player_1.id:
        player_on_turn = player_1
    elif starting_player_id == player_2.id:
        player_on_turn = player_2
    else:
        raise ValueError(f"Unknown starting player id: {starting_player_id}")
    first_player_id = player_on_turn.id
    winner = None
    ### Game loop ###
    while run:  ### ROUNDS
        board.game_state = GameState.PREP
        current_round += 1
        board.round    = current_round # for pygame
        display_strategy.display_round(current_round)
        ### Prepare new Round ###
        run_turns = True
        dragon_slain_by = None
        player_1.passed = False
        player_2.passed = False

        if current_round != 1:
            board.clear_round(player_1, player_2)
            player_1.draw_cards(3)
            player_2.draw_cards(3)
        player_1.hand.sort()
        player_2.hand.sort()

        # reveal mana
        board.cycle_mana()
        display_strategy.display_mana()
        display_strategy.display_status()
        ### TODO update game info ###
        while run_turns:  ### TURNS
            board.game_state = GameState.PLAY
            # sleep(2) #TODO remove
            board.player_on_turn = player_on_turn

            # KEEP GAME INFO UPDATED WITH CURRENT TURN
            info_p1.player_on_turn = player_on_turn
            info_p2.player_on_turn = player_on_turn

            display_strategy.display_player_on_turn(player_on_turn)
            display_strategy.display_board()

            choice_strategy = player_on_turn.choice_strategy
            if hasattr(choice_strategy, "begin_turn_choices"):
                choice_strategy.begin_turn_choices()
            try:
                # pass?
                Player_choice_pass = (
                    choice_strategy.get_choice_pass()
                    if not player_on_turn.passed and player_on_turn.hand.cards
                    else True
                )
                if Player_choice_pass or len(player_on_turn.hand.cards) <= 0:
                    player_on_turn.passed = True

                if not player_on_turn.passed:
                    if  display_strategy.this_player == player_on_turn:
                        display_strategy.display_hand()

                    play_card(
                        player_on_turn,
                        choice_strategy,
                        board,
                        display_strategy,
                    )
                    ### evaluate ability ###
                    board.recalculate(do_display=False)  # TODO remove do_display, it is responsibility of player strategy
                    display_strategy.display_board()
            finally:
                if hasattr(choice_strategy, "end_turn_choices"):
                    choice_strategy.end_turn_choices()

            ### check for round end condition ###
            # is board full
            if board.get_card_count() >= 6:  # end player actions, goto finish round
                run_turns = False  # Run turns is for inner loop, each round has many turns
                dragon_slain_by = battle_dragon(board, display_strategy)
            # have both players passed
            elif player_1.passed and player_2.passed:  # end player actions, goto finish round
                run_turns = False
                dragon_slain_by = battle_dragon(board, display_strategy)

            if run_turns:
                player_on_turn = player_2 if player_on_turn == player_1 else player_1

        ### handle result ###
        if dragon_slain_by == player_1:
            player_1.score += 1
        elif dragon_slain_by == player_2:
            player_2.score += 1

        if player_1.score >= 2 or player_2.score >= 2:
            winner = get_winner(player_1, player_2)
            display_strategy.display_game_result(winner)
            run = False  # end match
            board.winner        = winner # for pygame, #TODO move to display strategy pygame

        if player_1.get_card_count() + player_2.get_card_count() <= 0:
            winner = get_winner(player_1, player_2)
            display_strategy.display_game_result(winner)
            run = False  # end match
            board.winner        = winner # for pygame, #TODO move to display strategy pygame
        board.game_running = run # for pygame, #TODO move to display strategy pygame

        ### clean-up board ###
        board.clear_round(player_1=player_1, player_2=player_2)
        if current_round > Config.max_rounds: # Terminate too long games
            winner = get_winner(player_1, player_2)
            display_strategy.display_game_result(winner)
            board.winner        = winner # for pygame, #TODO move to display strategy pygame
            run = False
            # raise IndexError(f"Exceeded max number of game rounds: {current_round}")
    return GameResult(
        player_1_score=player_1.score,
        player_2_score=player_2.score,
        winner_id=winner.id if winner is not None else None,
        rounds=current_round,
        starting_player_id=first_player_id,
        seed=seed,
        player_1_card_plays=dict(player_1.card_plays),
        player_2_card_plays=dict(player_2.card_plays),
        player_1_active_ability_uses=dict(player_1.active_ability_uses),
        player_2_active_ability_uses=dict(player_2.active_ability_uses),
    )


def play_card(player, choice_strategy, board, display_strategy):
    """Stage a card visibly, then resolve its optional ability choices."""
    card = choice_strategy.get_choice_card()
    position = choice_strategy.get_choice_pos()
    card.owner = player
    board.stage_card(card, position)
    display_strategy.display_board()

    use_ability = choice_strategy.get_choice_use_ability()
    requires_target = bool(
        use_ability
        and getattr(card.ability, "requires_target", False)
    )
    target = (
        choice_strategy.get_choice_ability_target()
        if requires_target
        else None
    )
    board.resolve_staged_card(card, use_ability, target)
    player.record_card_play(card, use_ability)
    display_strategy.display_choice(card, position, use_ability, target)
    return card


def battle_dragon(board: Board, display_strategy: DisplayStrategy) -> Player:  # returns winner or None if dragon survived
    board.game_state = GameState.BATTLE
    dragon = board.dragons.pop()
    dragon_name = str(getattr(dragon, "name", "Dragon"))
    board.dragon = dragon
    board.dragon_position = None
    display_strategy.dragon = dragon
    board.battle_event = {
        "phase": "reveal",
        "card": None,
        "slot": None,
        "message": f"{dragon_name} enters the battle",
    }
    display_strategy.display_dragon()
    winning_card = None
    winning_slot = None
    # Dispatch reveal hooks; each ability owns its effect and presentation event.
    for slot, card in enumerate(board.positions):
        ability = getattr(card, "ability", None) if card else None
        if ability and getattr(ability, "is_onDragonReveal", False):
            ability.apply_onDragonReveal(card, board, dragon)
            display_strategy.display_dragon()
            if dragon.slain_by is not None:
                winning_card = card
                winning_slot = slot
                break
    ### activate dragon ability ###
    if dragon.hp > 0 and dragon.ability.is_active:
        dragon.ability.activate(dragon, board)
        board.battle_event = {
            "phase": "dragon_ability",
            "card": None,
            "slot": None,
            "message": str(getattr(dragon.ability, "name", "Dragon ability")),
        }
        display_strategy.display_dragon()
    ### recalculate board ###
    board.recalculate()
    display_strategy.display_board()
    ### battle positions ###
    for x in range(0, 6):
        if dragon.slain_by:
            break
        card = board.positions[x]
        if card is None:
            continue
        board.dragon_position = x - 1
        card_name = str(getattr(card, "name", "Card"))
        # A zero-damage stalemate belongs to the defending dragon. Without this
        # guard malformed or heavily debuffed content could stall every UI and
        # LAN match forever.
        if card.dmg <= 0 and dragon.dmg <= 0:
            board.battle_event = {
                "phase": "stalemate",
                "card": card,
                "slot": x,
                "message": "Neither fighter can deal damage; the dragon advances",
            }
            display_strategy.display_dragon_vs_card()
            board.remove_card(card)
            if dragon.hp <= 0:
                dragon.slain_by = card.owner
                winning_card = card
                winning_slot = x
                break
            board.recalculate(False)
            board.battle_event = {
                "phase": "card_defeated",
                "card": card,
                "slot": x,
                "message": f"{card_name} leaves the battle; board effects recalculate",
            }
            display_strategy.display_dragon_vs_card()
            continue
        while card.hp > 0 and dragon.hp > 0:
            board.battle_event = {
                "phase": "versus",
                "card": card,
                "slot": x,
                "message": f"{card_name} challenges {dragon_name}",
            }
            display_strategy.display_dragon_vs_card()
            dragon.hp -= card.dmg
            card.hp   -= dragon.dmg
            board.battle_event = {
                "phase": "impact",
                "card": card,
                "slot": x,
                "card_damage": dragon.dmg,
                "dragon_damage": card.dmg,
                "message": f"{card_name} and {dragon_name} exchange blows",
            }
            display_strategy.display_dragon_vs_card()

        ### evaluate results ###
        # if slain
        if dragon.hp <= 0:  # if dragon defeated
            dragon.slain_by = card.owner
            winning_card = card
            winning_slot = x
            break
        board.remove_card(card)
        if dragon.hp <= 0:
            dragon.slain_by = card.owner
            winning_card = card
            winning_slot = x
            break
        board.recalculate(False)
        board.battle_event = {
            "phase": "card_defeated",
            "card": card,
            "slot": x,
            "message": f"{card_name} was defeated; board effects recalculate",
        }
        display_strategy.display_dragon_vs_card()
    board.battle_event = {
        "phase": "dragon_defeated" if dragon.slain_by is not None else "dragon_survived",
        "card": winning_card,
        "slot": winning_slot,
        "point_for": dragon.slain_by,
        "message": (
            f"{dragon_name} was defeated — Player {getattr(dragon.slain_by, 'id', '?')} earns the point"
            if dragon.slain_by is not None
            else f"{dragon_name} survived the round"
        ),
    }
    display_strategy.display_battle_result()
    # else put dragon to bottom#
    # TODO restore dragon is tmp solution, convert dragon to card of type Dragon !!!
    if dragon.slain_by == None:
        dragon.restore()
        board.dragons.insert(0, dragon)
    board.dragon = None
    board.dragon_position = None
    board.battle_event = None
    return dragon.slain_by


def get_winner(player_1, player_2):
    if player_1.score > player_2.score:
        winner = player_1
    elif player_2.score > player_1.score:
        winner = player_2
    else:
        winner = None
    return winner


def random_player(player_1, player_2):
    if random.randint(1, 2) == 1:
        player_on_turn = player_1
    else:
        player_on_turn = player_2
    return player_on_turn
