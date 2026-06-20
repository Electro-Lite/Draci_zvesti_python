from pygame import *
from py_game.game import Game
from py_game.menu.options_menu import OptionsMenu
from py_game.menu.main_menu import MainMenu

g = Game()
def main_menu():
    g.playing = True
    g.curr_menu = MainMenu(g)
    g.curr_menu.display_menu()
    # g.game_loop()
if __name__ == '__main__':
    main_menu()