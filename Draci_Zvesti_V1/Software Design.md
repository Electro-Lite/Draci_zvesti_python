# Overview
I will use hybrid MVC
Game class will hold main game loop
it will have players with player strategy (interface, random, human, ai)
it will have display strategy (interface, web, pygame)

## Player decisions strategy
- Option 1) *sub strategy* - human will have sub strategies local and web, ai will have neat and rnd
- Option 2) **4 Choice strategies** - Player choice strategy for webPlayer, localPlayer, rnd, Neat
Game will run synchronously with game choice - aka, it will wait for response from choice.

## Display strategy
- we will have interface with methods like *render frame* which will take in game info and display it.
- Game must have *state machine, to pass to display strategy´s render frame method* what game.
	this is simplistic approach, we will also need some way to display animations, if this is not implemented, changes between states will not obviously display what happened to cause the new state. This is especially true for card abilities.

## Files
**core/**
	- game_loop.py
	- board.py
	- cards.py
	- player.py
	- abilities.py
	- dragons.py
**choice_strategies/**
	- choice_strategy.py
	- web_player.py
	- local_player.py
	- random_ai.py
	- neat_ai.py
**display_strategies/**
	- display_strategy.py
	- web_display.py
	- pygame_display.py
**neat/**
**pygame/**
**flask/**

## Dependencies
### Database
for card and deck storage
	sqlite3 - standard python package - single file local sql db
### Flask and Flask session
### pygame cu
### NEAT
### Type condtroll
### Enum
