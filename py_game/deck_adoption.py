"""Safe copy-to-My-decks service for completed training artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from cards.deck import Deck
from neat_ai.player_artifacts import clone_player_artifact


DEFAULT_PLAYER_LIBRARY = Path(__file__).resolve().parents[1] / "neat_ai" / "trained_ai"


@dataclass(frozen=True)
class AdoptableDeck:
    source_id: str
    source_name: str
    card_ids: tuple[str, ...]
    source_label: str
    player_artifact_manifest: str | None = None


@dataclass(frozen=True)
class AdoptionReceipt:
    deck_id: str
    name: str
    card_ids: tuple[str, ...]
    source_id: str
    player_artifact_path: str | None = None
    player_artifact_manifest: str | None = None


class DeckAdoptionError(RuntimeError):
    pass


class DeckAdoptionConflict(DeckAdoptionError):
    def __init__(self, message: str, existing_deck_id: str):
        super().__init__(message)
        self.existing_deck_id = existing_deck_id


def validate_adoption_name(name: str) -> str:
    value = str(name or "").strip()
    if not value:
        raise DeckAdoptionError("Enter a name for the new deck")
    if len(value) > 32:
        raise DeckAdoptionError("Deck names may contain at most 32 characters")
    if any(ord(character) < 32 for character in value):
        raise DeckAdoptionError("Deck names cannot contain control characters")
    return value


class DeckAdoptionService:
    def __init__(self, database, player_library: Path | None = None):
        self.database = database
        self.player_library = Path(player_library or DEFAULT_PLAYER_LIBRARY)

    def _signature(self, card_ids: tuple[str, ...]) -> str:
        return self.database._deck_signature(sorted(card_ids))

    def _conflict(self, name: str, signature: str):
        connection = self.database.conn_decks
        direct = connection.execute(
            """
            SELECT id, name, signature
            FROM decks
            WHERE COALESCE(is_AI, 0) = 0
              AND (LOWER(name) = LOWER(?) OR signature = ?)
            ORDER BY CASE WHEN LOWER(name) = LOWER(?) THEN 0 ELSE 1 END, id
            LIMIT 1
            """,
            (name, signature, name),
        ).fetchone()
        if direct is not None:
            return direct
        # Older user decks may predate the signature migration. Compare their
        # stored lines explicitly so an identical legacy composition is still
        # reported as a conflict instead of silently duplicated.
        for deck_id, deck_name, stored_signature in connection.execute(
            """
            SELECT id, name, signature FROM decks
            WHERE COALESCE(is_AI, 0) = 0
            """
        ).fetchall():
            line_key = stored_signature or deck_id
            rows = connection.execute(
                """
                SELECT card_id FROM deck_lines
                WHERE signature = ? OR (signature IS NULL AND deck_id = ?)
                ORDER BY rowid
                """,
                (line_key, deck_id),
            ).fetchall()
            if rows and self._signature(tuple(str(row[0]) for row in rows)) == signature:
                return (deck_id, deck_name, stored_signature)
        return None

    def adopt(self, source: AdoptableDeck, name: str) -> AdoptionReceipt:
        """Persist an exact fresh user copy, or fail without touching its source."""
        deck_name = validate_adoption_name(name)
        card_ids = tuple(str(card_id or "") for card_id in source.card_ids)
        if not card_ids or any(not card_id for card_id in card_ids):
            raise DeckAdoptionError("The saved source composition is missing card IDs")
        signature = self._signature(card_ids)
        conflict = self._conflict(deck_name, signature)
        if conflict is not None:
            reason = (
                "A user deck with this name already exists"
                if str(conflict[1]).lower() == deck_name.lower()
                else "This exact composition already exists in My decks"
            )
            raise DeckAdoptionConflict(reason, str(conflict[0]))

        cards = []
        missing = []
        for card_id in card_ids:
            card = self.database.load_card(card_id)
            if card is None:
                missing.append(card_id)
            else:
                cards.append(card)
        if missing:
            raise DeckAdoptionError(
                "Cannot copy this historical deck; missing cards: "
                + ", ".join(dict.fromkeys(missing))
            )

        deck = Deck()
        # Intentionally leave the identity blank. DBUtil.save_deck is UPSERT-
        # capable and passing the generated source ID could mutate another row.
        deck.id = ""
        deck.name = deck_name
        deck.description = f"Copied from {source.source_label}"
        deck.cards = cards
        try:
            deck.validate()
        except (TypeError, ValueError) as error:
            raise DeckAdoptionError(
                f"The exact historical composition is not a valid user deck: {error}"
            ) from error

        connection = self.database.conn_decks
        adopted_artifact = None
        try:
            # Do not call the general UPSERT-capable save path here. Adoption is
            # intentionally insert-only so a generated source or existing user
            # deck can never be overwritten, even during a name race.
            connection.execute("BEGIN IMMEDIATE")
            conflict = self._conflict(deck_name, signature)
            if conflict is not None:
                reason = (
                    "A user deck with this name already exists"
                    if str(conflict[1]).lower() == deck_name.lower()
                    else "This exact composition already exists in My decks"
                )
                raise DeckAdoptionConflict(reason, str(conflict[0]))

            deck_id = f"user_{uuid4().hex}"
            while deck_id == str(source.source_id) or connection.execute(
                "SELECT 1 FROM decks WHERE id = ?", (deck_id,)
            ).fetchone():
                deck_id = f"user_{uuid4().hex}"
            deck.id = deck_id
            connection.execute(
                """
                INSERT INTO decks
                    (id, name, description, power, fitness, is_AI, signature)
                VALUES (?, ?, ?, ?, ?, 0, ?)
                """,
                (
                    deck_id,
                    deck_name,
                    deck.description,
                    deck.power,
                    deck.neat_fitness,
                    signature,
                ),
            )
            existing_lines = connection.execute(
                "SELECT card_id FROM deck_lines WHERE signature = ? ORDER BY rowid",
                (signature,),
            ).fetchall()
            if existing_lines:
                persisted = tuple(str(row[0]) for row in existing_lines)
                if sorted(persisted) != sorted(card_ids):
                    raise DeckAdoptionError(
                        "Stored composition signature does not match the historical deck"
                    )
            else:
                connection.executemany(
                    "INSERT INTO deck_lines (deck_id, card_id, signature) VALUES (?, ?, ?)",
                    ((signature, card_id, signature) for card_id in card_ids),
                )

            saved = connection.execute(
                "SELECT id, COALESCE(is_AI, 0), signature FROM decks WHERE id = ?",
                (deck_id,),
            ).fetchone()
            if saved is None or int(saved[1] or 0) != 0:
                raise DeckAdoptionError(
                    "The saved copy could not be verified as a user deck"
                )
            persisted = tuple(
                str(row[0])
                for row in connection.execute(
                    "SELECT card_id FROM deck_lines WHERE signature = ? ORDER BY rowid",
                    (saved[2],),
                ).fetchall()
            )
            if sorted(persisted) != sorted(card_ids):
                raise DeckAdoptionError(
                    "The persisted card composition failed verification"
                )
            if source.player_artifact_manifest:
                try:
                    adopted_artifact = clone_player_artifact(
                        Path(source.player_artifact_manifest),
                        self.player_library,
                        deck,
                        role=f"adopted-{deck_id}",
                        display_name=f"{deck_name} · Deck Evolution AI",
                    )
                except (OSError, TypeError, ValueError) as error:
                    raise DeckAdoptionError(
                        f"Could not adopt the trained AI: {error}"
                    ) from error
            connection.commit()
        except DeckAdoptionError:
            connection.rollback()
            if adopted_artifact is not None:
                adopted_artifact.path.unlink(missing_ok=True)
                adopted_artifact.manifest_path.unlink(missing_ok=True)
            raise
        except Exception as error:
            connection.rollback()
            if adopted_artifact is not None:
                adopted_artifact.path.unlink(missing_ok=True)
                adopted_artifact.manifest_path.unlink(missing_ok=True)
            raise DeckAdoptionError(f"Could not save the deck copy: {error}") from error
        return AdoptionReceipt(
            deck_id,
            deck_name,
            card_ids,
            source.source_id,
            str(adopted_artifact.path) if adopted_artifact else None,
            str(adopted_artifact.manifest_path) if adopted_artifact else None,
        )
