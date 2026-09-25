"""Generate deterministic UI screenshots for visual layout review.

Outputs are intentionally written outside source control by default. This is a
developer review tool, not part of the interactive application flow.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame as pg

from py_game.deck_editor import DeckBuilderMenu
from py_game.game import Game
from py_game.menu.basic_play_menu import BasicPlayMenu
from py_game.menu.deck_menu import DeckMenu
from py_game.menu.lan_menu import LanMenu
from py_game.menu.main_menu import MainMenu
from py_game.menu.options_menu import OptionsMenu
from py_game.menu.training_menu import TrainingMenu
from py_game.network.lobby import HostLobbyController
from py_game.training_service import (
    MatchupInsight,
    TrainingInsights,
    TrainingJob,
    TrainingKind,
    TrainingRunSummary,
    TrainingTelemetry,
)


REVIEW_SIZES = ((640, 480), (800, 600), (1024, 768), (1280, 720), (1600, 900), (1920, 1080))


def _save(game: Game, output: Path, name: str, size: tuple[int, int]) -> None:
    game.window.blit(game.display, (0, 0))
    path = output / f"{name}-{size[0]}x{size[1]}.png"
    pg.image.save(game.display, path)


def _main(game, output, size):
    menu = MainMenu(game)
    menu.refresh_layout()
    menu.build_menu_buttons(list(menu.ITEMS), 0, top_ratio=0.25, bottom_ratio=0.91, width_ratio=0.46)
    menu.draw_background()
    menu.draw_title("Dračí zvěsti", "Build a deck, challenge a rival, and face the dragons")
    menu.draw_buttons()
    _save(game, output, "main", size)


def _local(game, output, size):
    menu = BasicPlayMenu(game)
    menu.refresh_layout()
    labels = [
        f"Player 1: {menu._controller(1).value}",
        "Player 1 deck: Select deck",
        f"Player 1 model: {menu._model_label(1)}",
        f"Player 2: {menu._controller(2).value}",
        "Player 2 deck: Select deck",
        f"Player 2 model: {menu._model_label(2)}",
        "Start match",
        "Back",
    ]
    menu.build_menu_buttons(labels, 0, top_ratio=0.20, bottom_ratio=0.88, width_ratio=0.70)
    menu.draw_background()
    menu.draw_title("Local Match", "Choose decks and controllers for both players")
    menu.draw_buttons()
    _save(game, output, "local-match", size)


def _draw_lan(menu, game, output, size, name):
    menu.refresh_layout()
    rows = menu._rows()
    menu.build_menu_buttons(
        rows,
        min(menu.selected, len(rows) - 1),
        top_ratio=0.27,
        bottom_ratio=0.82,
        width_ratio=0.68,
        enabled=menu._enabled(),
    )
    menu.draw_background()
    subtitles = {
        "root": "Host an authoritative match or join by IP address",
        "join_setup": "Enter the host's LAN address and port",
        "connecting": "The UI remains responsive while connecting",
        "host_lobby": (
            f"Hosting at {menu.local_ip}:"
            f"{menu.host.port if menu.host else game.settings.lan_port}"
        ),
        "guest_lobby": f"Connected to {menu.join_host}:{game.settings.lan_port}",
    }
    menu.draw_title("LAN Match", subtitles.get(menu.mode, ""))
    menu.draw_buttons()
    menu.draw_message(menu.message, menu.message_color)
    _save(game, output, name, size)


def _lan(game, output, size):
    _draw_lan(LanMenu(game), game, output, size, "lan-root")


def _lan_join(game, output, size):
    # //placeholder: deterministic review-only LAN identities and addresses.
    menu = LanMenu(game)
    menu.mode = "join_setup"
    menu.selected = 0
    menu.join_host = "192.168.1.42"
    menu.message = "Enter an IPv4, [IPv6]:port, or hostname"
    _draw_lan(menu, game, output, size, "lan-join")


def _lan_connecting(game, output, size):
    menu = LanMenu(game)
    menu.mode = "connecting"
    menu.selected = 1
    menu.join_host = "game-room.local"
    menu.message = "Connecting to game-room.local:47777…"
    _draw_lan(menu, game, output, size, "lan-connecting")


def _lan_host_waiting(game, output, size):
    menu = LanMenu(game)
    menu.mode = "host_lobby"
    menu.local_ip = "192.168.1.25"
    menu.host = SimpleNamespace(port=47777)
    menu.lobby = HostLobbyController(game.settings.player_name, lambda _deck: True)
    menu.message = "Waiting for a player on the trusted local network"
    _draw_lan(menu, game, output, size, "lan-host-waiting")


def _lan_lobby(game, output, size):
    menu = LanMenu(game)
    menu.mode = "guest_lobby"
    menu.join_host = "192.168.1.25"
    deck_id = menu.deck_ids[0] if menu.deck_ids else "No valid decks"
    menu.guest_ready = True
    menu.remote_lobby = {
        "host": {"name": "Host Player", "deck_id": deck_id, "ready": True},
        "guest": {"name": "Guest Player", "deck_id": deck_id, "ready": True},
        "status": "ready",
    }
    menu.message = "Both players are ready; waiting for the host to start"
    _draw_lan(menu, game, output, size, "lan-lobby-ready")


def _lan_error(game, output, size):
    menu = LanMenu(game)
    menu.mode = "join_setup"
    menu.selected = 2
    menu.message = "Connection timed out; verify the address, port, and firewall"
    menu.message_color = game.palette.danger
    _draw_lan(menu, game, output, size, "lan-connection-error")


def _lan_disconnected(game, output, size):
    menu = LanMenu(game)
    menu.mode = "join_setup"
    menu.selected = 2
    menu.message = "The host closed the LAN session; reconnect from this screen"
    menu.message_color = game.palette.danger
    _draw_lan(menu, game, output, size, "lan-disconnected")


def _settings(game, output, size):
    menu = OptionsMenu(game)
    menu.refresh_layout()
    menu.build_menu_buttons(menu._rows(), 0, top_ratio=0.18, bottom_ratio=0.90, width_ratio=0.64)
    menu.draw_background()
    menu.draw_title(
        "Settings",
        "Use Left/Right to adjust, Enter or click to activate",
    )
    menu.draw_buttons()
    _save(game, output, "settings", size)


def _decks(game, output, size):
    menu = DeckMenu(game)
    menu.refresh_layout()
    visible = menu.items[: min(10, len(menu.items))]
    menu.build_menu_buttons(visible, 0, top_ratio=0.22, bottom_ratio=0.86, width_ratio=0.64)
    menu.draw_background()
    menu.draw_title("Deck Management", "Create a deck or select one to edit")
    menu.draw_buttons()
    _save(game, output, "decks", size)


def _editor(game, output, size):
    menu = DeckBuilderMenu(game)
    menu.refresh_layout()
    menu.draw_background()
    menu.draw_title("Deck Builder", "New deck  •  0/12 cards  •  drag cards between lists")
    menu._draw_responsive_editor()
    _save(game, output, "deck-editor", size)


def _training(game, output, size):
    menu = TrainingMenu(game)
    menu.refresh_layout()
    menu.draw_training_cockpit()
    _save(game, output, "training-workbench-counter", size)
    if size == (640, 480):
        menu.setup_scroll = menu._current_setup_layout().max_scroll
        menu.draw_training_cockpit()
        _save(game, output, "training-workbench-counter-bottom", size)


def _training_matchup_setup(game, output, size):
    menu = TrainingMenu(game)
    menu.refresh_layout()
    menu.cockpit.switch(TrainingKind.MATCHUP_EVALUATION)
    menu.cockpit.set_value("run_label", "blue-vs-queen")
    menu.draw_training_cockpit()
    _save(game, output, "training-workbench-matchup", size)
    if size == (640, 480):
        menu.setup_scroll = menu._current_setup_layout().max_scroll
        menu.draw_training_cockpit()
        _save(game, output, "training-workbench-matchup-bottom", size)


def _training_builder(game, output, size):
    menu = TrainingMenu(game)
    menu.refresh_layout()
    menu.cockpit.switch(TrainingKind.DECK_BUILDER)
    menu.cockpit.set_value("run_label", "replicated-study")
    menu.cockpit.set_value("seeds", "400009, 450001, 500009, 550007")
    menu.cockpit.set_value("workers", "12")
    menu.draw_training_cockpit()
    _save(game, output, "training-workbench-builder", size)
    if size == (640, 480):
        menu.setup_scroll = menu._current_setup_layout().max_scroll
        menu.draw_training_cockpit()
        _save(game, output, "training-workbench-builder-bottom", size)


def _training_review(game, output, size):
    menu = TrainingMenu(game)
    menu.refresh_layout()
    menu.cockpit.switch(TrainingKind.DECK_BUILDER)
    menu.cockpit.set_value("run_label", "replicated-study")
    menu.cockpit.set_value("seeds", "400009, 450001, 500009, 550007")
    menu.cockpit.set_value("workers", "12")
    menu._launch()
    menu.draw_training_cockpit()
    _save(game, output, "training-workbench-review", size)


def _training_runs_menu(game):
    menu = TrainingMenu(game)
    menu.refresh_layout()
    menu.jobs = []
    # //placeholder: deterministic run history used only for responsive review.
    menu.database_runs = [
        TrainingRunSummary(
            run_id=f"DB {80 - index}",
            title=(
                "final-deck-discovery"
                if index % 3
                else "Killer Queen controller"
            ),
            status=("running", "completed", "completed", "failed")[index % 4],
            started=f"2026-09-{24 - index:02d}T{10 + index % 8:02d}:00:00",
            detail="visual review run",
            run_kind=(
                TrainingKind.PLAYER_DECK.value
                if index % 3 == 0
                else TrainingKind.DECK_BUILDER.value
            ),
        )
        for index in range(23)
    ]
    menu._linked_database_run_ids = set()
    menu.view = "runs"
    return menu


def _training_runs(game, output, size):
    menu = _training_runs_menu(game)
    menu.draw_training_runs()
    _save(game, output, "training-runs", size)


def _training_runs_filter(game, output, size):
    menu = _training_runs_menu(game)
    menu._open_run_filter()
    menu.run_filter_pending_status = 3
    menu.draw_training_runs()
    _save(game, output, "training-runs-filter", size)


def _sample_training_dashboard():
    # //placeholder: deterministic review-only telemetry; runtime uses live logs and database runs.
    job = TrainingJob(
        job_id="20260831-dragon-tactician",
        request={"kind": TrainingKind.DECK_BUILDER.value},
        command=[],
        created_at="2026-08-31T10:30:00",
        status="running",
        pid=4242,
        log_path="training.log",
        progress_path="progress.log",
        summary_path="summary.json",
    )
    telemetry = TrainingTelemetry(
        status="running",
        phase="deck_evolution",
        generation=14,
        total_generations=35,
        round_completed=37,
        round_total=60,
        best_score=128.4,
        workers=8,
        phase_progress=0.39,
        eta_seconds=1840,
        elapsed_seconds=1260,
        fitness_history=((1, 22.0), (3, 41.0), (6, 38.0), (9, 76.0), (12, 93.0), (14, 128.4)),
    )
    first_cards = ("Lučištník", "Panoš", "Strážce", "Alchymista", "Rytíř", "Vědma")
    second_cards = ("Drakobijec", "Kněz", "Zvěd", "Kovář", "Žoldnéř", "Průvodce")
    insights = TrainingInsights(
        run_kind=TrainingKind.DECK_BUILDER.value,
        subject="pygame · DB 70",
        generation_scores=(
            (1, -18.0, 14.0, 31.0, 20),
            (3, -4.0, 28.0, 52.0, 20),
            (6, 8.0, 46.0, 78.0, 20),
            (9, 21.0, 63.0, 98.0, 20),
            (12, 34.0, 79.0, 128.4, 20),
        ),
        favorable_matchups=(
            MatchupInsight("Moon Guard", "Ash Company", 84.2, 12, 3, first_cards, second_cards),
            MatchupInsight("Blue Banner", "Iron Choir", 71.8, 11, 5, second_cards, first_cards),
        ),
        difficult_matchups=(
            MatchupInsight("Glass Arrows", "Night Watch", -22.5, 10, 4, first_cards, second_cards),
            MatchupInsight("Oak Circle", "Red Talons", -14.3, 12, 6, second_cards, first_cards),
        ),
        top_cards=(("Lučištník", 108.0, 9), ("Panoš", 96.0, 7), ("Vědma", 83.0, 6), ("Kovář", 72.0, 8)),
        total_matches=120,
        distinct_decks=20,
        eligible_matchups=76,
        conclusions=(
            "Champion fitness improved by 97.4 across the recorded generations.",
            "The final population retains a 94.4-point spread, suggesting useful diversity.",
            "Lučištník has the strongest deck-level fitness signal in this run.",
            "76 matchup pairs satisfy the seven-shared-card diversity rule.",
        ),
    )
    return job, telemetry, insights


def _training_dashboard_page(game, output, size, page, name):
    menu = TrainingMenu(game)
    menu.refresh_layout()
    menu.dashboard_item, telemetry, insights = _sample_training_dashboard()
    menu.dashboard_page = page
    menu.draw_training_dashboard(telemetry, insights)
    _save(game, output, name, size)


def _training_dashboard(game, output, size):
    _training_dashboard_page(game, output, size, 0, "training-arena")


def _training_performance(game, output, size):
    _training_dashboard_page(game, output, size, 1, "training-performance")


def _training_matchups(game, output, size):
    _training_dashboard_page(game, output, size, 2, "training-matchups")


def _training_conclusions(game, output, size):
    _training_dashboard_page(game, output, size, 3, "training-conclusions")


def _sample_player_dashboard():
    # //placeholder: deterministic counter-training report for visual review.
    job = TrainingJob(
        job_id="20260901-killer-queen-counters",
        request={"kind": TrainingKind.PLAYER_DECK.value},
        command=[],
        created_at="2026-09-01T15:00:00",
        status="completed",
        pid=None,
        log_path="training.log",
        progress_path="progress.log",
        summary_path="summary.json",
    )
    telemetry = TrainingTelemetry(
        status="completed",
        phase="completed",
        generation=5,
        total_generations=5,
        best_score=146.2,
        workers=12,
        phase_progress=1.0,
        elapsed_seconds=512.0,
        fitness_history=((1, 18.0), (7, 46.0), (14, 72.0), (21, 101.0), (28, 127.0), (35, 146.2)),
    )
    insights = TrainingInsights(
        run_kind=TrainingKind.PLAYER_DECK.value,
        subject="Killer Queen",
        opponent="20 evolved counter decks",
        generation_scores=(
            (1, 71.0, 71.0, 71.0, 800),
            (2, 66.0, 66.0, 66.0, 800),
            (3, 61.0, 61.0, 61.0, 800),
            (4, 57.0, 57.0, 57.0, 800),
            (5, 54.0, 54.0, 54.0, 800),
        ),
        evaluation=(432, 96, 272),
        skill_evaluations=(
            (1, 568, 72, 160),
            (2, 528, 80, 192),
            (3, 488, 88, 224),
            (4, 456, 88, 256),
            (5, 432, 96, 272),
        ),
        total_evaluation_games=4000,
        elapsed_seconds=512.0,
        top_counter_name="Counter G5 #17",
        top_counter_win_rate=0.72,
        opponent_count=20,
        conclusions=(
            "The selected deck won 54.0% of 800 final evaluation games.",
            "Top counter Counter G5 #17 won 72.0% against the selected deck.",
            "Controller populations persisted while counter decks evolved.",
        ),
    )
    return job, telemetry, insights


def _training_player_page(game, output, size, page, name):
    menu = TrainingMenu(game)
    menu.refresh_layout()
    menu.dashboard_item, telemetry, insights = _sample_player_dashboard()
    menu.dashboard_page = page
    menu.draw_training_dashboard(telemetry, insights)
    _save(game, output, name, size)


def _training_player_learning(game, output, size):
    _training_player_page(game, output, size, 1, "training-player-learning")


def _training_player_evaluation(game, output, size):
    _training_player_page(game, output, size, 2, "training-player-evaluation")


def _training_player_conclusions(game, output, size):
    _training_player_page(game, output, size, 3, "training-player-conclusions")


def _training_quit_warning(game, output, size):
    menu = MainMenu(game)
    menu.refresh_layout()
    menu.draw_confirmation(
        "Training is still running",
        (
            "20260831-dragon-tactician",
            "Quitting will stop the UI-owned training process.",
            "Saved generations and artifacts will remain available.",
        ),
        "Stop and quit",
    )
    _save(game, output, "training-quit-warning", size)


def _training_about_page(game, output, size, page, name):
    menu = TrainingMenu(game)
    menu.refresh_layout()
    menu.about_page = page
    menu.draw_training_about()
    _save(game, output, name, size)


def _training_about_player(game, output, size):
    _training_about_page(game, output, size, 0, "training-about-counter")


def _training_about_matchup(game, output, size):
    _training_about_page(game, output, size, 1, "training-about-matchup")


def _training_about_builder(game, output, size):
    _training_about_page(game, output, size, 2, "training-about-builder")


def _training_about_recommendations(game, output, size):
    _training_about_page(game, output, size, 3, "training-about-recommendations")


def _sample_gameplay_state():
    # //placeholder: deterministic review-only cards; runtime loads real database cards.
    cards = [
        {
            "id": f"card-{index}",
            "name": f"Card {index + 1}",
            "hp": index + 1,
            "dmg": 5 - index,
            "owner": "local",
            "ability_name": "Tactical shift" if index == 0 else "",
            "ability_description": (
                "Move an allied card to a legal adjacent position."
                if index == 0
                else ""
            ),
        }
        for index in range(5)
    ]
    return {
        "status": "playing",
        "round": 3,
        "mana": "BLUE",
        "turn": "local",
        "local": {"score": 1, "deck_count": 5, "graveyard_count": 2, "hand": cards},
        "opponent": {"score": 1, "deck_count": 4, "graveyard_count": 3, "hand_count": 5},
        "board": [cards[0], None, cards[1], None, None, cards[2]],
        "dragon": None,
        "dragon_deck_count": 2,
        "winner": None,
        "game_state": "PLAY",
    }


def _gameplay(game, output, size):
    state = _sample_gameplay_state()
    game.current_legal_indices = [1, 3, 4]
    game.draw_match_state(state, "position")
    _save(game, output, "gameplay", size)


def _gameplay_tooltip(game, output, size):
    state = _sample_gameplay_state()
    game.draw_match_state(state, "card")
    if game.hand_card_rects:
        game.mouse_position = game.hand_card_rects[0].center
    game.mouse_right_clicked = True
    game.draw_match_state(state, "card")
    game.mouse_right_clicked = False
    _save(game, output, "gameplay-tooltip", size)


def _gameplay_play_or_pass(game, output, size):
    state = _sample_gameplay_state()
    game.selected_card_index = 1
    game.draw_match_state(state, "play_or_pass")
    _save(game, output, "gameplay-play-or-pass", size)


def _gameplay_ability_staged(game, output, size):
    state = _sample_gameplay_state()
    staged = state["local"]["hand"].pop(0)
    state["board"][1] = staged
    game.draw_match_state(state, "use_ability")
    _save(game, output, "gameplay-ability-staged", size)


def _gameplay_target_staged(game, output, size):
    state = _sample_gameplay_state()
    staged = state["local"]["hand"].pop(0)
    state["board"][1] = staged
    game.current_legal_indices = [0, 2, 5]
    game.selected_position = 2
    game.draw_match_state(state, "target")
    _save(game, output, "gameplay-target-staged", size)


def _battle_state(phase):
    state = _sample_gameplay_state()
    dragon = {
        "id": "dragon-red",
        "name": "Crimson Wyrm",
        "hp": 7 if phase != "dragon_defeated" else 0,
        "max_hp": 12,
        "dmg": 3,
        "owner": "opponent",
        "ability_name": "Scorch the Line",
        "ability_description": "Burns fragile challengers before combat.",
    }
    challenger = dict(state["board"][0])
    challenger.update({"name": "Moon Vanguard", "hp": 3, "max_hp": 5, "dmg": 4})
    state["board"][0] = challenger
    messages = {
        "reveal": "Crimson Wyrm enters the battle",
        "impact": "Moon Vanguard and Crimson Wyrm exchange blows",
        "card_defeated": "Moon Vanguard was defeated; board effects recalculate",
        "dragon_defeated": "Crimson Wyrm was defeated",
    }
    if phase == "card_defeated":
        challenger["hp"] = 0
        state["board"][0] = None
        state["board"][2] = {
            **state["board"][2],
            "name": "Lučištník",
            "hp": 4,
            "dmg": 7,
        }
        state["board"][5] = {
            **state["board"][5],
            "name": "Panoš",
            "hp": 6,
            "dmg": 3,
        }
    state.update(
        {
            "game_state": "BATTLE",
            "dragon": dragon,
            "battle": {
                "phase": phase,
                "card": None if phase == "reveal" else challenger,
                "slot": 0,
                "point_for": "local" if phase == "dragon_defeated" else None,
                "message": messages[phase],
            },
        }
    )
    return state


def _battle_reveal(game, output, size):
    game.draw_match_state(_battle_state("reveal"))
    _save(game, output, "battle-reveal", size)


def _battle_impact(game, output, size):
    game.draw_match_state(_battle_state("impact"))
    _save(game, output, "battle-impact", size)


def _battle_card_defeated(game, output, size):
    game.draw_match_state(_battle_state("card_defeated"))
    _save(game, output, "battle-card-defeated", size)


def _battle_result(game, output, size):
    game.draw_match_state(_battle_state("dragon_defeated"))
    _save(game, output, "battle-dragon-defeated", size)


def _result(game, output, size):
    state = {
        "status": "finished",
        "round": 4,
        "mana": "RED",
        "turn": "local",
        "local": {"score": 2, "deck_count": 2, "graveyard_count": 8, "hand": []},
        "opponent": {"score": 1, "deck_count": 1, "graveyard_count": 9, "hand_count": 0},
        "board": [None] * 6,
        "dragon": None,
        "dragon_deck_count": 0,
        "winner": "local",
    }
    game.draw_match_state(state, return_destination="lobby")
    _save(game, output, "match-result", size)


def _dialogs(game, output, size):
    # //placeholder: deterministic review-only run details for dense dialog coverage.
    menu = MainMenu(game)
    menu.refresh_layout()
    menu.draw_text_prompt("Host IP address or name", "192.168.1.25")
    _save(game, output, "dialog-text-input", size)
    menu.draw_confirmation(
        "Leave the active LAN match?",
        ("Your current match will end for both players.",),
        "Leave",
    )
    _save(game, output, "dialog-confirmation", size)
    menu.draw_lines_panel(
        "Training run details",
        (
            "Status: completed",
            "Started: 2026-08-30 12:00",
            "Best fitness: 128.40",
            "AI win rate: 63.0% (100 games)",
            "Output: .ui_training/20260830-professor-demo",
        ),
    )
    _save(game, output, "dialog-details", size)


def generate(output: Path, sizes=REVIEW_SIZES) -> list[Path]:
    output.mkdir(parents=True, exist_ok=True)
    for old_screenshot in output.glob("*.png"):
        old_screenshot.unlink()
    game = Game()
    renderers = (
        _main,
        _local,
        _lan,
        _lan_join,
        _lan_connecting,
        _lan_host_waiting,
        _lan_lobby,
        _lan_error,
        _lan_disconnected,
        _settings,
        _decks,
        _editor,
        _training,
        _training_matchup_setup,
        _training_builder,
        _training_review,
        _training_runs,
        _training_runs_filter,
        _training_dashboard,
        _training_performance,
        _training_matchups,
        _training_conclusions,
        _training_player_learning,
        _training_player_evaluation,
        _training_player_conclusions,
        _training_quit_warning,
        _training_about_player,
        _training_about_matchup,
        _training_about_builder,
        _training_about_recommendations,
        _gameplay,
        _gameplay_tooltip,
        _gameplay_play_or_pass,
        _gameplay_ability_staged,
        _gameplay_target_staged,
        _battle_reveal,
        _battle_impact,
        _battle_card_defeated,
        _battle_result,
        _result,
        _dialogs,
    )
    try:
        for size in sizes:
            game.settings.fullscreen = False
            game.resize(*size)
            for renderer in renderers:
                game.mouse_position = (0, 0)
                game.interaction_message = ""
                game.inspected_card_view = None
                game.mouse_right_clicked = False
                renderer(game, output, size)
    finally:
        pg.quit()
    return sorted(output.glob("*.png"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("/tmp/draci-ui-review"))
    args = parser.parse_args()
    for path in generate(args.output):
        print(path)


if __name__ == "__main__":
    main()
