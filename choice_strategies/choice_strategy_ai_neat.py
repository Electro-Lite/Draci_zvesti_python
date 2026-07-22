from choice_strategies.choice_strategy import PlayerChoiceStrategy

class PlayerChoiceStrategyNeat(PlayerChoiceStrategy):
    def __init__(self, _player):
        self.this_player    = _player
        self.info           = None
        self._turn_outputs  = None

    def begin_turn_choices(self):
        self._turn_outputs = self.this_player.net.activate(self.info.get_game_info())

    def end_turn_choices(self):
        self._turn_outputs = None

    def _get_outputs(self):
        if self._turn_outputs is None:
            self.begin_turn_choices()
        return self._turn_outputs

    def _get_bool_choice(self, output_index: int) -> bool:
        player = self.this_player
        choice = self._get_outputs()[output_index]
        if choice < 0 or choice > 1:
            player.fitness -= 1
        return choice >= 0.5

    def get_choice_pos(self) -> int:
            game_board  = self.info.game_board
            player      = self.this_player

            choice = self._get_outputs()[0] % 6
            choice = int(choice)
            if game_board.positions[choice] != None: # if failed to pick empty pos, return first empty
                player.fitness -=1
                for i in range(0, 6):
                    if game_board.positions[i] == None:
                        return i
            else:
                return choice
            raise Exception()

    def get_choice_card(self): # Card
        player = self.this_player
        choice = self._get_outputs()[1]
        if choice < 0 or choice >= len(player.hand.cards):
            player.fitness-=1
        choice = choice % len(player.hand.cards)
        choice = int(choice)
        Player_choice_card = player.hand.cards.pop(choice)
        return Player_choice_card

    def get_choice_use_ability(self) -> bool:
        return self._get_bool_choice(2)

    def get_choice_pass(self) -> bool:
        return self._get_bool_choice(3)

    def get_choice_ability_target(self) -> int:
        game_board  = self.info.game_board
        player      = self.this_player

        choice = self._get_outputs()[4] % 6
        choice = int(choice)
        return choice
