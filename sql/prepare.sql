CREATE TEMP TABLE incoming ON COMMIT DROP AS
SELECT
    record_hash,
    nullif(btrim(raw_record ->> 'company_name'), '') AS company,
    nullif(btrim(raw_record ->> 'job_title'), '') AS full_title,
    btrim(raw_record ->> 'job_title_short') AS short_title,
    nullif(regexp_replace(btrim(raw_record ->> 'job_via'), '^via ', ''), '') AS platform,
    nullif(btrim(raw_record ->> 'job_location'), '') AS location,
    nullif(btrim(raw_record ->> 'job_country'), '') AS country,
    nullif(btrim(raw_record ->> 'search_location'), '') AS search_location,
    btrim(raw_record ->> 'job_posted_date')::timestamp AS job_posted_date,
    nullif(btrim(raw_record ->> 'job_work_from_home'), '')::boolean AS job_work_from_home,
    nullif(btrim(raw_record ->> 'job_no_degree_mention'), '')::boolean AS job_no_degree_mention,
    nullif(btrim(raw_record ->> 'job_health_insurance'), '')::boolean AS job_health_insurance,
    nullif(btrim(raw_record ->> 'salary_rate'), '') AS salary_rate,
    nullif(btrim(raw_record ->> 'salary_year_avg'), '')::numeric AS salary_year_avg,
    nullif(btrim(raw_record ->> 'salary_hour_avg'), '')::numeric AS salary_hour_avg,
    job_skills IS NOT NULL OR job_type_skills IS NOT NULL AS skills_reported,
    job_type_skills IS NOT NULL AS skill_categories_reported,
    raw_record ->> 'job_schedule_type' AS schedule,
    coalesce(job_skills, grouped.skills, '[]'::jsonb) AS skills
FROM incoming_source
LEFT JOIN LATERAL (
    SELECT jsonb_agg(DISTINCT member.value) AS skills
    FROM jsonb_each(job_type_skills) AS category
    CROSS JOIN LATERAL jsonb_array_elements(category.value) AS member
) AS grouped ON job_skills IS NULL;

CREATE TEMP TABLE incoming_skills ON COMMIT DROP AS
SELECT record_hash, member.skill
FROM incoming
CROSS JOIN LATERAL jsonb_array_elements_text(skills) AS member(skill);

CREATE TEMP TABLE incoming_schedules ON COMMIT DROP AS
SELECT DISTINCT record_hash, btrim(part.name) AS name
FROM incoming
CROSS JOIN LATERAL regexp_split_to_table(
    schedule, ',\s*(and\s+)?|\s+and\s+'
) AS part(name)
WHERE btrim(part.name) <> '';

CREATE TEMP TABLE incoming_taxonomy ON COMMIT DROP AS
WITH definitions AS (
    SELECT row_number() OVER () AS definition_id, job_type_skills
    FROM (SELECT DISTINCT job_type_skills FROM incoming_source) AS dictionaries
    WHERE job_type_skills IS NOT NULL
), members AS (
    SELECT definition_id, category.key AS category, member.skill
    FROM definitions
    CROSS JOIN LATERAL jsonb_each(job_type_skills) AS category
    CROSS JOIN LATERAL jsonb_array_elements_text(category.value) AS member(skill)
)
SELECT DISTINCT skill, array_agg(DISTINCT category ORDER BY category) AS categories
FROM members
GROUP BY definition_id, skill;

ANALYZE incoming;
ANALYZE incoming_skills;
ANALYZE incoming_schedules;
ANALYZE incoming_taxonomy;
