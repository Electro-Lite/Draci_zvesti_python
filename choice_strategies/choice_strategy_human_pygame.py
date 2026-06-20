from core.player import PlayerChoiceStrategy
from cards.card import Card
from enum import Enum
from time import sleep
from random import randint

class ChoiceType(Enum):
        NONE        = 0
        CARD        = 1
        POSITION    = 2
        PASS        = 3
        USE_ABILITY = 4
        TARGET      = 5



class PygameChoiceStrategy(PlayerChoiceStrategy):
    def __init__(self, _player):
        super().__init__(_player)
        self.choice      = None
        self.waiting_for = ChoiceType.NONE
        self.do_exit    = False

    def _wait_for_input(self, waiting_for:ChoiceType):
        self.waiting_for    = waiting_for
        while waiting_for != ChoiceType.NONE and self.choice == None:
            if self.do_exit:
                exit()
            else:
                sleep(0.2)
        self.waiting_for    = ChoiceType.NONE
        choice = self.choice
        self.choice         = None
        return choice

    def set_choice(self, choice_type:ChoiceType, choice_value):
        if self.waiting_for == choice_type:
            self.choice = choice_value
        else:
            raise ValueError()

    def get_choice_card(self) -> Card:
        # Blocks until Pygame sends a Card object
        card = self._wait_for_input(ChoiceType.CARD)

        pos = self.this_player.hand.cards.index(card)
        return self.this_player.hand.cards.pop(pos)

    def get_choice_pos(self) -> int:
        # Blocks until Pygame sends an int (0-5)
        return self._wait_for_input(ChoiceType.POSITION)
    
    def exit_thread(self):
        self.do_exit = True
    # def get_choice_pass(self) -> bool:
    #     # Blocks until Pygame sends a bool
    #     return self._wait_for_input(ChoiceType.PASS)

    # def get_choice_use_ability(self) -> bool:
    #     # Blocks until Pygame sends a bool
    #     return self._wait_for_input(ChoiceType.USE_ABILITY)
    
    # def get_choice_ability_target(self) -> int:
    #     # Blocks until Pygame sends an int target
    #     return self._wait_for_input(ChoiceType.TARGET)

    def get_choice_use_ability(self):
        return True

    def get_choice_pass(self):
        return False
    
    def get_choice_ability_target(self): #TODO should not select self (Nepotrebny_novic)
        game_board  = self.info.game_board
        start_pos = randint(0, 6) # 6 positions
        for i in range(0, 6):
            pos = ( start_pos + i ) % 6 
            if game_board.positions[pos] != None:
                return pos
    """
    def __init__(self, _player):
        super().__init__(_player)
        # We need the display strategy because it holds the input_queue
        self.display = None

    def _wait_for_input(self, input_type: str):
        with self.display.lock:
            self.display.waiting_for = input_type
            # Update prompt so the user knows what to do
            self.display.status_message = f"Please select: {input_type}"
        
        # --- BLOCKING CALL ---
        # The code stops here until Pygame puts something in the queue
        user_input = self.display.input_queue.get() 
        
        # Reset waiting state
        with self.display.lock:
            self.display.waiting_for = None
            
        return user_input

    def get_choice_card(self) -> Card:
        # Blocks until Pygame sends a Card object
        return self._wait_for_input("CARD")

    def get_choice_pos(self) -> int:
        # Blocks until Pygame sends an int (0-5)
        return self._wait_for_input("POSITION")

    def get_choice_pass(self) -> bool:
        # Blocks until Pygame sends a bool
        return self._wait_for_input("PASS_DECISION")

    def get_choice_use_ability(self) -> bool:
        # Blocks until Pygame sends a bool
        return self._wait_for_input("USE_ABILITY")
    
    def get_choice_ability_target(self) -> int:
        # Blocks until Pygame sends an int target
        return self._wait_for_input("TARGET")
    """