-- View generated training data
WITH match_stats AS (
    -- Total matches per generation per training
    SELECT
        g.training_id,
        m.gen,
        COUNT(m.guid) AS matches_in_gen
    FROM match_dbt m
             JOIN genome g ON m.genome_1 = g.guid
    GROUP BY g.training_id, m.gen
),
     gen2_genome_matches AS (
         -- Count how many matches each specific genome played in generation 2
         SELECT
             g.training_id,
             g.guid,
             COUNT(m.guid) AS matches_played
         FROM genome g
                  LEFT JOIN match_dbt m
                            ON (g.guid = m.genome_1 OR g.guid = m.genome_2)
                                AND m.gen = 2
         WHERE g.gen = 2
         GROUP BY g.training_id, g.guid
     ),
     gen2_avg_matches AS (
         -- Average those match counts across all generation 2 genomes per training
         SELECT
             training_id,
             ROUND(AVG(matches_played), 2) AS avg_matches_per_genome_gen2
         FROM gen2_genome_matches
         GROUP BY training_id
     )
SELECT
    t.id AS training_id,
    t.start_date,
    COALESCE(MAX(ms.gen), 0) AS max_generation,
    COALESCE(SUM(ms.matches_in_gen), 0) AS total_matches,
    ROUND(COALESCE(AVG(ms.matches_in_gen), 0), 2) AS avg_matches_per_gen,
    COALESCE(g2.avg_matches_per_genome_gen2, 0) AS avg_genome_matches_gen2
FROM training t
         LEFT JOIN match_stats ms ON t.id = ms.training_id
         LEFT JOIN gen2_avg_matches g2 ON t.id = g2.training_id
GROUP BY
    t.id,
    t.start_date,
    g2.avg_matches_per_genome_gen2
ORDER BY t.id;

-- Simple best and worst card
WITH CardScores AS (
    -- 1. Calculate the average score for each card per training
    SELECT
        g.training_id,
        dl.card_id,
        AVG(g.score) AS avg_score
    FROM genome g
             JOIN ai_training_deck_lines dl ON g.deck_id = dl.deck_id
    WHERE g.score IS NOT NULL
    GROUP BY g.training_id, dl.card_id
),
     RankedCards AS (
         -- 2. Rank the cards from best to worst (and worst to best)
         SELECT
             training_id,
             card_id,
             avg_score,
             ROW_NUMBER() OVER(PARTITION BY training_id ORDER BY avg_score DESC) AS rank_best,
             ROW_NUMBER() OVER(PARTITION BY training_id ORDER BY avg_score ASC) AS rank_worst
         FROM CardScores
     )
-- 3. Extract the #1 best and #1 worst for each training into a single row
SELECT
    training_id,
    MAX(CASE WHEN rank_best = 1 THEN card_id END) AS best_card,
    ROUND(MAX(CASE WHEN rank_best = 1 THEN avg_score END), 2) AS best_score,
    MAX(CASE WHEN rank_worst = 1 THEN card_id END) AS worst_card,
    ROUND(MAX(CASE WHEN rank_worst = 1 THEN avg_score END), 2) AS worst_score
FROM RankedCards
WHERE rank_best = 1 OR rank_worst = 1
GROUP BY training_id
ORDER BY training_id;