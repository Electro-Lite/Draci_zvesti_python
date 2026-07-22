import pandas as pd

from .card_metrics import get_card_power_rating


def get_balance_candidates(
    min_times_played: int = 3,
    top_n: int = 5,
) -> pd.DataFrame:
    """Return likely nerf and buff candidates from card power ratings."""
    ratings = get_card_power_rating(min_times_played=min_times_played)
    if ratings.empty:
        return pd.DataFrame(
            columns=[
                "card_id",
                "recommendation",
                "power_rating",
                "average_score",
                "times_played",
                "total_copies",
                "average_copies",
            ]
        )

    nerfs = ratings.head(top_n).copy()
    nerfs["recommendation"] = "nerf"

    buffs = ratings.tail(top_n).copy()
    buffs["recommendation"] = "buff"

    result = pd.concat([nerfs, buffs], ignore_index=True)
    return result[
        [
            "card_id",
            "recommendation",
            "power_rating",
            "average_score",
            "times_played",
            "total_copies",
            "average_copies",
        ]
    ]
