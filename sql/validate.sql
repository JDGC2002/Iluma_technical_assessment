WITH title_conflicts AS (
    SELECT full_title
    FROM incoming
    WHERE full_title IS NOT NULL
    GROUP BY full_title
    HAVING count(DISTINCT short_title) > 1
    UNION
    SELECT i.full_title
    FROM incoming i
    JOIN core.job_titles t ON t.full_title = i.full_title
    WHERE t.short_title <> i.short_title
), existing_taxonomy AS (
    SELECT s.name AS skill, array_agg(c.name ORDER BY c.name) AS categories
    FROM core.skill_category_memberships m
    JOIN core.skills s USING (skill_id)
    JOIN core.skill_categories c USING (category_id)
    GROUP BY s.name
), skill_conflicts AS (
    SELECT skill
    FROM incoming_taxonomy
    GROUP BY skill
    HAVING count(*) > 1
    UNION
    SELECT i.skill
    FROM incoming_taxonomy i
    JOIN existing_taxonomy e USING (skill)
    WHERE i.categories <> e.categories
)
SELECT 'Conflicting standardized title: ' || full_title AS error
FROM title_conflicts
UNION ALL
SELECT 'Conflicting skill classification: ' || skill
FROM skill_conflicts
LIMIT 5;
