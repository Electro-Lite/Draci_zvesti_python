"""Bounded, run-scoped presentation data for completed deck evolution runs."""

from __future__ import annotations

import json
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class EvolutionCardRow:
    card_id: str
    name: str
    color: str
    copies: int


@dataclass(frozen=True)
class EvolutionDeck:
    deck_id: str
    name: str
    generation: int
    relative_fitness: float | None
    signature: str
    card_ids: tuple[str, ...]
    cards: tuple[EvolutionCardRow, ...]
    player_artifact_path: str | None = None


@dataclass(frozen=True)
class EvolutionGeneration:
    generation: int
    worst: float
    average: float
    best: float
    contenders: int
    exact_signatures: int
    scored_pairings: int

    @property
    def spread(self) -> float:
        return self.best - self.worst


@dataclass(frozen=True)
class EvolutionMatchup:
    opponent_id: str
    opponent_name: str
    generation: int
    relative_score: float


@dataclass(frozen=True)
class EvolutionCardSignal:
    card_id: str
    name: str
    first_presence: int
    first_total: int
    final_presence: int
    final_total: int
    first_mean_copies_when_present: float
    final_mean_copies_when_present: float


@dataclass(frozen=True)
class EvolutionCoverage:
    genome_rows: int
    stored_decks: int
    stored_compositions: int
    scored_pairings: int


@dataclass(frozen=True)
class EvolutionPresentation:
    training_id: int
    run_label: str
    seed: int | None
    requested_outer_generations: int
    requested_inner_generations: int
    generations: tuple[EvolutionGeneration, ...]
    decks: tuple[EvolutionDeck, ...]
    matchups: tuple[tuple[str, tuple[EvolutionMatchup, ...]], ...]
    card_signals: tuple[EvolutionCardSignal, ...]
    coverage: EvolutionCoverage
    default_deck_id: str | None
    issues: tuple[str, ...] = ()

    def deck(self, deck_id: str | None) -> EvolutionDeck | None:
        return next((deck for deck in self.decks if deck.deck_id == deck_id), None)

    def deck_matchups(self, deck_id: str | None) -> tuple[EvolutionMatchup, ...]:
        return dict(self.matchups).get(str(deck_id or ""), ())

    @property
    def first_generation(self) -> EvolutionGeneration | None:
        return self.generations[0] if self.generations else None

    @property
    def final_generation(self) -> EvolutionGeneration | None:
        return self.generations[-1] if self.generations else None


def _metadata_settings(value) -> dict:
    try:
        metadata = json.loads(value or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    settings = metadata.get("settings") if isinstance(metadata, dict) else None
    return settings if isinstance(settings, dict) else {}


def _group_cards(card_ids, metadata) -> tuple[EvolutionCardRow, ...]:
    counts = Counter(str(card_id) for card_id in card_ids)
    rows = []
    for card_id in dict.fromkeys(str(card_id) for card_id in card_ids):
        name, color = metadata.get(card_id, (card_id, "Unknown"))
        rows.append(EvolutionCardRow(card_id, name, color, counts[card_id]))
    return tuple(rows)


def load_evolution_presentation(
    database_path: Path,
    cards_database_path: Path,
    training_id: int,
) -> EvolutionPresentation:
    """Load bounded tables for one completed run; never scan raw PC matches."""
    connection = sqlite3.connect(
        f"file:{Path(database_path).resolve()}?mode=ro",
        uri=True,
        timeout=3.0,
    )
    connection.row_factory = sqlite3.Row
    issues = []
    try:
        training = connection.execute(
            "SELECT id, end_date, metadata FROM training WHERE id = ?",
            (training_id,),
        ).fetchone()
        if training is None:
            raise ValueError(f"Training run DB {training_id} does not exist")
        settings = _metadata_settings(training["metadata"])
        generation_rows = connection.execute(
            """
            SELECT g.gen, MIN(g.score) AS worst, AVG(g.score) AS average,
                   MAX(g.score) AS best, COUNT(*) AS contenders,
                   COUNT(DISTINCT d.signature) AS exact_signatures
            FROM genome g
            LEFT JOIN ai_training_decks d
              ON d.id = g.deck_id AND d.training_id = g.training_id
            WHERE g.training_id = ? AND g.score IS NOT NULL
            GROUP BY g.gen ORDER BY g.gen
            """,
            (training_id,),
        ).fetchall()
        genome_columns = {
            str(row[1]) for row in connection.execute("PRAGMA table_info(genome)")
        }
        artifact_column = (
            "g.pickle_path AS player_artifact_path"
            if "pickle_path" in genome_columns
            else "NULL AS player_artifact_path"
        )
        deck_rows = connection.execute(
            f"""
            SELECT d.id, COALESCE(NULLIF(d.name, ''), d.id) AS name,
                   d.signature, g.gen, g.score, {artifact_column}
            FROM ai_training_decks d
            LEFT JOIN genome g
              ON g.deck_id = d.id AND g.training_id = d.training_id
            WHERE d.training_id = ?
            ORDER BY COALESCE(g.gen, 0), d.id
            """,
            (training_id,),
        ).fetchall()
        deck_ids = [str(row["id"]) for row in deck_rows]
        line_rows = []
        if deck_ids:
            placeholders = ",".join("?" for _ in deck_ids)
            try:
                # Some historical databases have a damaged deck-line index
                # while the underlying rows remain readable. A bounded table
                # scan avoids that index and never crosses run deck IDs.
                line_rows = connection.execute(
                    f"""
                    SELECT l.deck_id, l.card_id, l.position
                    FROM ai_training_deck_lines AS l NOT INDEXED
                    WHERE l.deck_id IN ({placeholders})
                    ORDER BY l.deck_id, l.position
                    """,
                    deck_ids,
                ).fetchall()
            except sqlite3.Error as error:
                issues.append(f"Deck compositions are unavailable: {error}")

        matchup_rows = []
        try:
            # Trainer match IDs are run-prefixed. Reading that primary-key
            # range is both bounded and resilient to unrelated damaged rows.
            prefix = f"T{training_id}:"
            upper_bound = f"T{training_id};"
            matchup_rows = connection.execute(
                """
                SELECT m.deck_1, m.deck_2, m.gen, m.result
                FROM match_dbt AS m
                WHERE m.guid >= ? AND m.guid < ? AND m.result IS NOT NULL
                ORDER BY m.gen, m.guid
                """,
                (prefix, upper_bound),
            ).fetchall()
        except sqlite3.Error as error:
            issues.append(f"Run matchup evidence is unavailable: {error}")
    finally:
        connection.close()

    cards_by_deck: dict[str, list[str]] = defaultdict(list)
    for row in line_rows:
        cards_by_deck[str(row["deck_id"])].append(str(row["card_id"]))
    all_card_ids = sorted({card for cards in cards_by_deck.values() for card in cards})
    card_metadata = {}
    if all_card_ids and Path(cards_database_path).exists():
        card_connection = sqlite3.connect(
            f"file:{Path(cards_database_path).resolve()}?mode=ro",
            uri=True,
            timeout=2.0,
        )
        try:
            placeholders = ",".join("?" for _ in all_card_ids)
            for card_id, name, color in card_connection.execute(
                f"SELECT id, COALESCE(NULLIF(name, ''), id), "
                f"COALESCE(NULLIF(color, ''), 'Unknown') FROM cards "
                f"WHERE id IN ({placeholders})",
                all_card_ids,
            ):
                card_metadata[str(card_id)] = (str(name), str(color).title())
        finally:
            card_connection.close()

    decks = tuple(
        EvolutionDeck(
            deck_id=str(row["id"]),
            name=str(row["name"]),
            generation=int(row["gen"] or 0),
            relative_fitness=(
                float(row["score"]) if row["score"] is not None else None
            ),
            signature=str(row["signature"] or ""),
            card_ids=tuple(cards_by_deck.get(str(row["id"]), ())),
            cards=_group_cards(cards_by_deck.get(str(row["id"]), ()), card_metadata),
            player_artifact_path=(
                str(row["player_artifact_path"])
                if row["player_artifact_path"]
                else None
            ),
        )
        for row in deck_rows
    )
    names = {deck.deck_id: deck.name for deck in decks}
    matchup_map: dict[str, list[EvolutionMatchup]] = defaultdict(list)
    for row in matchup_rows:
        first, second = str(row["deck_1"]), str(row["deck_2"])
        score = float(row["result"])
        generation = int(row["gen"] or 0)
        matchup_map[first].append(
            EvolutionMatchup(second, names.get(second, second), generation, score)
        )
        matchup_map[second].append(
            EvolutionMatchup(first, names.get(first, first), generation, -score)
        )
    for values in matchup_map.values():
        values.sort(key=lambda item: item.relative_score, reverse=True)

    matchup_counts = Counter(int(row["gen"] or 0) for row in matchup_rows)
    generations = tuple(
        EvolutionGeneration(
            int(row["gen"] or 0),
            float(row["worst"]),
            float(row["average"]),
            float(row["best"]),
            int(row["contenders"] or 0),
            int(row["exact_signatures"] or 0),
            matchup_counts[int(row["gen"] or 0)],
        )
        for row in generation_rows
    )
    first_gen = generations[0].generation if generations else 0
    final_gen = generations[-1].generation if generations else 0
    generation_decks = {
        generation: [deck for deck in decks if deck.generation == generation]
        for generation in {first_gen, final_gen}
    }
    signals = []
    for card_id in all_card_ids:
        values = []
        for generation in (first_gen, final_gen):
            current = generation_decks.get(generation, ())
            counts = [deck.card_ids.count(card_id) for deck in current]
            present = [count for count in counts if count]
            values.append(
                (
                    len(present),
                    len(current),
                    sum(present) / len(present) if present else 0.0,
                )
            )
        if values[0][0] or values[1][0]:
            signals.append(
                EvolutionCardSignal(
                    card_id,
                    card_metadata.get(card_id, (card_id, "Unknown"))[0],
                    values[0][0],
                    values[0][1],
                    values[1][0],
                    values[1][1],
                    values[0][2],
                    values[1][2],
                )
            )
    signals.sort(
        key=lambda item: (
            item.final_presence / max(1, item.final_total)
            - item.first_presence / max(1, item.first_total),
            item.final_presence,
            item.name,
        ),
        reverse=True,
    )
    final_decks = [deck for deck in decks if deck.generation == final_gen]
    ranked_final = sorted(
        final_decks,
        key=lambda deck: (
            deck.relative_fitness if deck.relative_fitness is not None else float("-inf"),
            deck.deck_id,
        ),
        reverse=True,
    )
    missing_compositions = sum(1 for deck in decks if not deck.card_ids)
    if missing_compositions:
        issues.append(f"{missing_compositions} stored decks have no composition rows")
    if training["end_date"] is None:
        issues.append("Training database row is not marked complete")
    coverage = EvolutionCoverage(
        genome_rows=sum(row.contenders for row in generations),
        stored_decks=len(decks),
        stored_compositions=sum(1 for deck in decks if deck.card_ids),
        scored_pairings=len(matchup_rows),
    )
    return EvolutionPresentation(
        training_id=training_id,
        run_label=str(settings.get("run_label") or f"DB {training_id}"),
        seed=(int(settings["seed"]) if settings.get("seed") is not None else None),
        requested_outer_generations=int(settings.get("outer_generations", 0) or 0),
        requested_inner_generations=int(settings.get("evaluator_generations", 0) or 0),
        generations=generations,
        decks=decks,
        matchups=tuple((key, tuple(value)) for key, value in matchup_map.items()),
        card_signals=tuple(signals),
        coverage=coverage,
        default_deck_id=ranked_final[0].deck_id if ranked_final else None,
        issues=tuple(issues),
    )
