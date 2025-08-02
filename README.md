# NEAT Card Game (Dračí Zvěsti)

This is a card game experiment built in Python, where AI agents learn to play using NEAT (NeuroEvolution of Augmenting Topologies). The long-term goal is to develop a **neuroevolution-based tool for optimizing card decks in collectible card games (CCGs).**

The system is designed around two interconnected AI components:
- One acts as the **game-playing agent**, learning how to play effectively.
- The other serves as the **deck optimizer**, learning how to construct competitive decks through evolutionary strategies.

---

## Current Status

**Project is under development.** Here's where things currently stand:

- In process of complete refactor. Refer to previous versions for runnable example.

---

## Dependencies

This project uses the following libraries/modules:

```python
from flask import Flask, render_template
from multiprocessing import Process, Pipe
import time
import neat
import os
from time import time, ctime
import pickle
import game  # custom game logic
import winsound
import sys
