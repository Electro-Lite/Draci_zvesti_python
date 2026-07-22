# analysis/card_metrics.py
import pandas as pd
from .data_loader import load_master_df

def get_card_tier_list() -> pd.DataFrame:
    """
    Calculates the average score of all decks containing each specific card.
    Useful for finding buff/nerf targets.
    """
    df = load_master_df()
    
    # Calculate metrics per card
    metrics = df.groupby('card_id').agg(
        average_score=('score', 'mean'),
        times_played=('guid', 'nunique'), # How many unique AI genomes used this card
        generations_survived=('gen', 'nunique')
    ).reset_index()
    
    # Sort by highest average score
    tier_list = metrics.sort_values(by='average_score', ascending=False)
    
    return tier_list
