import pygame

from py_game.game import Game
from py_game.menu.main_menu import MainMenu


def main():
    game = Game()
    game.curr_menu = MainMenu(game)
    game.curr_menu.display_menu()
    pygame.quit()


if __name__ == "__main__":
    main()
