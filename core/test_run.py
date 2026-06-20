from core.game_loop         import run
from core.player            import Player
from utils.database_utils   import DBUtil
from choice_strategies.choice_strategy_ai_random import ChoiceStrategyAIRandom
from choice_strategies.choice_strategy_human_CLI import ChoiceStrategyCLI 
from display_strategies.display_strategy_none import DisplayStrategyNone
from display_strategies.display_strategy_CLI import DisplayStrategyCLI

# Test run block
player_1 = Player(1, DBUtil().load_deck("Starter Blue_1"), ChoiceStrategyCLI)
player_2 = Player(2, DBUtil().load_deck("Starter Blue_1"), ChoiceStrategyAIRandom)
def foo(): 
    run(player_1, player_2, DisplayStrategyCLI)
