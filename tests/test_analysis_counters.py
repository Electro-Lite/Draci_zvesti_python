import itertools
import unittest

try:
    import pandas as pd

    from neat_ai.analysis.counters import estimate_card_counters
except ImportError:  # Analysis dependencies are optional in the game runtime.
    pd = None


@unittest.skipUnless(pd is not None, "analysis dependencies are not installed")
class CardCounterTests(unittest.TestCase):
    @staticmethod
    def _evidence(card_counter_effect=0.0, build_counter_effect=0.0):
        variable_cards = ("X", "Y", "Z", "strong")
        decks = []
        master_rows = []
        for index, flags in enumerate(itertools.product((0, 1), repeat=4)):
            cards = {card for card, present in zip(variable_cards, flags) if present}
            cards.add("baseline")
            deck_id = f"deck-{index}"
            decks.append((deck_id, cards))
            master_rows.extend(
                {
                    "guid": deck_id,
                    "gen": 1,
                    "deck_id": deck_id,
                    "score": 0.0,
                    "card_id": card,
                }
                for card in cards
            )

        matchup_rows = []
        for (deck_a, cards_a), (deck_b, cards_b) in itertools.combinations(decks, 2):
            score = 10.0 * (("strong" in cards_a) - ("strong" in cards_b))
            score += card_counter_effect * (
                (("X" in cards_a) and ("Y" in cards_b))
                - (("X" in cards_b) and ("Y" in cards_a))
            )
            score += build_counter_effect * (
                (("X" in cards_a) and {"Y", "Z"}.issubset(cards_b))
                - (("X" in cards_b) and {"Y", "Z"}.issubset(cards_a))
            )
            matchup_rows.append({
                "deck_1": deck_a,
                "deck_2": deck_b,
                "outer_gen": 1,
                "sample_count": 20,
                "g1_score": score,
                "g2_score": -score,
            })
        return pd.DataFrame(master_rows), pd.DataFrame(matchup_rows)

    def _metrics(self, **effects):
        master, matchups = self._evidence(**effects)
        return estimate_card_counters(
            master,
            matchups,
            min_matchups=4,
            min_target_appearances=8,
            max_target_builds=100,
            ridge_alpha=1.0,
            shrinkage=0.0,
        ).set_index(["counter_card", "target_type", "target"])

    def test_generally_strong_card_is_not_mislabeled_as_specific_counter(self):
        metrics = self._metrics()
        self.assertLess(abs(metrics.loc[("strong", "card", "Y"), "counter_score"]), 0.1)

    def test_card_specific_counter_is_detected(self):
        metrics = self._metrics(card_counter_effect=8.0)
        self.assertGreater(metrics.loc[("X", "card", "Y"), "counter_score"], 1.0)

    def test_counter_against_two_card_build_is_detected(self):
        metrics = self._metrics(build_counter_effect=10.0)
        self.assertGreater(metrics.loc[("X", "build", "Y + Z"), "counter_score"], 1.0)


if __name__ == "__main__":
    unittest.main()
