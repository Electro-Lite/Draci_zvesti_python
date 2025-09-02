# NEAT Card Game (Dračí Zvěsti) V2

This is a card game experiment built in Python, where AI agents learn to play using NEAT (NeuroEvolution of Augmenting Topologies). The long-term goal is to develop a **neuroevolution-based tool for optimizing card decks in collectible card games (CCGs).**

The system is designed around two interconnected AI components:
- One acts as the **game-playing agent**, learning how to play effectively.
- The other serves as the **deck optimizer**, learning how to construct competitive decks through evolutionary strategies.

---

## Current Status

**Project is under development.** Here's where things currently stand:

- In process of complete refactor.
- Game logic implemented
- Simple temporary UI to create cards and decks.
- neat ai deck trainer - train ai to use given deck against it self
- CLI display strategy - View running game in CLI

---

## How to run
In powershell navigate to folder Draci_ZvestiV2 and from there run:
- python -m core.test_run
  This will run game in CLI between two players both making random decisions.
- python -m neat_ai.train_deck <deck_id>
  This will start ai training for given deck and test it afterwards on 10000 games vs random choice player.
- python -m cards.cards.card_builder_GUI
  This will create a tkinter interface for defining cards.
- python -m cards.cards.deck_builder_GUI
  This will create tkinter interface for building decks

## Dependencies

This project uses the following libraries/modules:

```python
neat - pip3 install neat-python
