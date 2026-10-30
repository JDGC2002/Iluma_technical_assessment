SELECT 'Completed file has missing job references' AS error
WHERE EXISTS (
    SELECT 1 FROM staging.jobs s
    JOIN staging.source_files f USING (file_id)
    WHERE f.status = 'completed' AND (s.job_id IS NULL OR s.validation_error IS NOT NULL)
)
UNION ALL
SELECT 'Completed file counts do not match staging'
WHERE EXISTS (
    SELECT f.file_id
    FROM staging.source_files f
    LEFT JOIN staging.jobs s USING (file_id)
    WHERE f.status = 'completed'
    GROUP BY f.file_id
    HAVING count(s.record_number) <> f.row_count
        OR count(DISTINCT s.job_id) <> f.job_count
)
UNION ALL
SELECT 'Source fingerprint does not match its published job'
WHERE EXISTS (
    SELECT 1 FROM staging.jobs s
    JOIN core.jobs j USING (job_id)
    WHERE s.record_hash <> j.record_hash
)
UNION ALL
SELECT 'Skill relationship has no source skill information'
WHERE EXISTS (
    SELECT 1 FROM core.jobs j
    JOIN core.job_skills s USING (job_id)
    WHERE NOT j.skills_reported
);
