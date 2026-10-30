INSERT INTO core.companies (name, name_key)
SELECT DISTINCT ON (lower(company)) company, lower(company)
FROM incoming
WHERE company IS NOT NULL
ORDER BY lower(company), company
ON CONFLICT (name_key) DO NOTHING;

INSERT INTO core.platforms (name, name_key)
SELECT DISTINCT ON (lower(platform)) platform, lower(platform)
FROM incoming
WHERE platform IS NOT NULL
ORDER BY lower(platform), platform
ON CONFLICT (name_key) DO NOTHING;

INSERT INTO core.job_titles (full_title, short_title)
SELECT DISTINCT full_title, short_title FROM incoming
ON CONFLICT (full_title, short_title) DO NOTHING;

INSERT INTO core.countries (name)
SELECT DISTINCT country FROM incoming WHERE country IS NOT NULL
ON CONFLICT (name) DO NOTHING;

INSERT INTO core.locations (label, country_id)
SELECT DISTINCT i.location, c.country_id
FROM incoming i
LEFT JOIN core.countries c ON c.name = i.country
WHERE i.location IS NOT NULL OR c.country_id IS NOT NULL
ON CONFLICT (label, country_id) DO NOTHING;

INSERT INTO core.skills (name)
SELECT DISTINCT skill FROM incoming_skills
ON CONFLICT (name) DO NOTHING;

INSERT INTO core.skill_categories (name)
SELECT DISTINCT unnest(categories) FROM incoming_taxonomy
ON CONFLICT (name) DO NOTHING;

INSERT INTO core.skill_category_memberships (skill_id, category_id)
SELECT DISTINCT s.skill_id, c.category_id
FROM incoming_taxonomy t
CROSS JOIN LATERAL unnest(t.categories) AS category(name)
JOIN core.skills s ON s.name = t.skill
JOIN core.skill_categories c ON c.name = category.name
ON CONFLICT (skill_id, category_id) DO NOTHING;

INSERT INTO core.schedule_types (name)
SELECT DISTINCT name FROM incoming_schedules
ON CONFLICT (name) DO NOTHING;

CREATE TEMP TABLE new_jobs ON COMMIT DROP AS
WITH inserted AS (
    INSERT INTO core.jobs (
        record_hash, company_id, title_id, platform_id, location_id, search_location,
        job_posted_date, job_work_from_home, job_no_degree_mention, job_health_insurance,
        salary_rate, salary_year_avg, salary_hour_avg, skills_reported, skill_categories_reported
    )
    SELECT
        i.record_hash, company.company_id, coalesce(title.title_id, missing_title.title_id),
        platform.platform_id, location.location_id, i.search_location,
        i.job_posted_date, i.job_work_from_home, i.job_no_degree_mention, i.job_health_insurance,
        i.salary_rate, i.salary_year_avg, i.salary_hour_avg,
        i.skills_reported, i.skill_categories_reported
    FROM incoming i
    LEFT JOIN core.companies company ON company.name_key = lower(i.company)
    LEFT JOIN core.platforms platform ON platform.name_key = lower(i.platform)
    LEFT JOIN core.job_titles title ON title.full_title = i.full_title
    LEFT JOIN core.job_titles missing_title ON i.full_title IS NULL
        AND missing_title.full_title IS NULL AND missing_title.short_title = i.short_title
    LEFT JOIN core.countries country ON country.name = i.country
    -- I use these fallback values to match a missing location label or country.
    LEFT JOIN core.locations location ON coalesce(location.label, '') = coalesce(i.location, '')
        AND coalesce(location.country_id, 0) = coalesce(country.country_id, 0)
    ON CONFLICT (record_hash) DO NOTHING
    RETURNING job_id, record_hash
)
SELECT * FROM inserted;

ANALYZE new_jobs;

INSERT INTO core.job_skills (job_id, skill_id)
SELECT j.job_id, s.skill_id
FROM new_jobs j
JOIN incoming_skills i USING (record_hash)
JOIN core.skills s ON s.name = i.skill
ON CONFLICT (job_id, skill_id) DO NOTHING;

INSERT INTO core.job_schedules (job_id, schedule_type_id)
SELECT j.job_id, s.schedule_type_id
FROM new_jobs j
JOIN incoming_schedules i USING (record_hash)
JOIN core.schedule_types s ON s.name = i.name
ON CONFLICT (job_id, schedule_type_id) DO NOTHING;
