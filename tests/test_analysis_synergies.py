import unittest

try:
    import pandas as pd

    from neat_ai.analysis.synergies import estimate_card_combo_synergies
except ImportError:  # The lightweight game environment does not require pandas.
    pd = None


@unittest.skipUnless(pd is not None, "analysis dependencies are not installed")
class CardComboSynergyTests(unittest.TestCase):
    @staticmethod
    def _master(ab_effect=0.0, triple_effect=0.0, duplicate_pair_effect=0.0):
        rows = []
        guid = 0
        for repetition in range(30):
            for copies_a in range(3):
                for has_b in range(2):
                    for has_c in range(2):
                        guid += 1
                        score = 4 * copies_a + 3 * has_b + 2 * has_c
                        score += ab_effect * (copies_a > 0 and has_b > 0)
                        score += triple_effect * (copies_a > 0 and has_b > 0 and has_c > 0)
                        score += duplicate_pair_effect * (copies_a >= 2 and has_b > 0)
                        cards = ["baseline"] + ["A"] * copies_a + ["B"] * has_b + ["C"] * has_c
                        rows.extend(
                            {
                                "guid": str(guid),
                                "gen": 1 + repetition % 3,
                                "deck_id": str(guid),
                                "score": float(score),
                                "card_id": card,
                            }
                            for card in cards
                        )
        return pd.DataFrame(rows)

    def _metrics(self, **effects):
        return estimate_card_combo_synergies(
            self._master(**effects),
            group_count=1,
            min_appearances=10,
            ridge_alpha=1,
            shrinkage=0,
        ).set_index("combo")

    def test_independently_strong_cards_are_not_reported_as_synergy(self):
        metrics = self._metrics()
        self.assertLess(abs(metrics.loc["A + B", "synergy_score"]), 0.05)

    def test_pair_interaction_is_detected_beyond_card_main_effects(self):
        metrics = self._metrics(ab_effect=6.0)
        self.assertGreater(metrics.loc["A + B", "synergy_score"], 1.0)

    def test_three_card_interaction_remains_after_pair_correction(self):
        metrics = self._metrics(triple_effect=5.0)
        self.assertGreater(metrics.loc["A + B + C", "synergy_score"], 0.2)
        self.assertGreater(metrics.loc["A + B + C", "constituent_interaction"], 0.0)

    def test_duplicate_plus_card_interaction_is_distinct(self):
        metrics = self._metrics(duplicate_pair_effect=8.0)
        self.assertGreater(metrics.loc["2× A + B", "synergy_score"], 2.0)
        self.assertEqual(metrics.loc["2× A + B", "combo_type"], "duplicate_pair")


if __name__ == "__main__":
    unittest.main()
