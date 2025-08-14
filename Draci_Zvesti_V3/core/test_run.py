from core.game_loop import run
from core.player import Player
from choice_strategies.choice_strategy_ai_random import ChoiceStrategyAIRandom as random_choice_strategy

# Test run block
player_1 = Player(1, random_choice_strategy)   
player_2 = Player(2, random_choice_strategy)

run(player_1, player_2)
