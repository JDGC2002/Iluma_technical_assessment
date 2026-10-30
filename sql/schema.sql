CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS staging;

CREATE TABLE IF NOT EXISTS core.companies (
    company_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text NOT NULL CHECK (btrim(name) <> ''),
    name_key text NOT NULL UNIQUE CHECK (name_key <> '')
);

CREATE TABLE IF NOT EXISTS core.platforms (
    platform_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text NOT NULL CHECK (btrim(name) <> ''),
    name_key text NOT NULL UNIQUE CHECK (name_key <> '')
);

CREATE TABLE IF NOT EXISTS core.job_titles (
    title_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    full_title text UNIQUE CHECK (btrim(full_title) <> ''),
    short_title text NOT NULL CHECK (btrim(short_title) <> ''),
    UNIQUE NULLS NOT DISTINCT (full_title, short_title)
);

CREATE TABLE IF NOT EXISTS core.countries (
    country_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text NOT NULL UNIQUE CHECK (btrim(name) <> '')
);

CREATE TABLE IF NOT EXISTS core.locations (
    location_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    label text CHECK (btrim(label) <> ''),
    country_id bigint REFERENCES core.countries,
    CHECK (label IS NOT NULL OR country_id IS NOT NULL),
    UNIQUE NULLS NOT DISTINCT (label, country_id)
);

CREATE TABLE IF NOT EXISTS core.skills (
    skill_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text NOT NULL UNIQUE CHECK (btrim(name) <> '')
);

CREATE TABLE IF NOT EXISTS core.skill_categories (
    category_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text NOT NULL UNIQUE CHECK (btrim(name) <> '')
);

CREATE TABLE IF NOT EXISTS core.skill_category_memberships (
    skill_id bigint REFERENCES core.skills,
    category_id bigint REFERENCES core.skill_categories,
    PRIMARY KEY (skill_id, category_id)
);

CREATE TABLE IF NOT EXISTS core.schedule_types (
    schedule_type_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text NOT NULL UNIQUE CHECK (btrim(name) <> '')
);

CREATE TABLE IF NOT EXISTS core.jobs (
    job_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    record_hash bytea NOT NULL UNIQUE CHECK (octet_length(record_hash) = 32),
    company_id bigint REFERENCES core.companies,
    title_id bigint NOT NULL REFERENCES core.job_titles,
    platform_id bigint REFERENCES core.platforms,
    location_id bigint REFERENCES core.locations,
    search_location text,
    job_posted_date timestamp NOT NULL,
    job_work_from_home boolean,
    job_no_degree_mention boolean,
    job_health_insurance boolean,
    salary_rate text,
    salary_year_avg numeric CHECK (salary_year_avg > 0 AND salary_year_avg < 'Infinity'::numeric),
    salary_hour_avg numeric CHECK (salary_hour_avg > 0 AND salary_hour_avg < 'Infinity'::numeric),
    skills_reported boolean NOT NULL,
    skill_categories_reported boolean NOT NULL,
    CHECK (NOT skill_categories_reported OR skills_reported)
);

CREATE TABLE IF NOT EXISTS core.job_skills (
    job_id bigint REFERENCES core.jobs,
    skill_id bigint REFERENCES core.skills,
    PRIMARY KEY (job_id, skill_id)
);

CREATE TABLE IF NOT EXISTS core.job_schedules (
    job_id bigint REFERENCES core.jobs,
    schedule_type_id bigint REFERENCES core.schedule_types,
    PRIMARY KEY (job_id, schedule_type_id)
);

CREATE TABLE IF NOT EXISTS staging.source_files (
    file_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    file_hash bytea NOT NULL UNIQUE CHECK (octet_length(file_hash) = 32),
    file_name text NOT NULL,
    status text NOT NULL DEFAULT 'received'
        CHECK (status IN ('received', 'staged', 'failed', 'completed')),
    row_count bigint NOT NULL DEFAULT 0,
    invalid_count bigint NOT NULL DEFAULT 0,
    job_count bigint NOT NULL DEFAULT 0,
    new_job_count bigint NOT NULL DEFAULT 0,
    error text,
    started_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    CHECK (invalid_count BETWEEN 0 AND row_count),
    CHECK (new_job_count BETWEEN 0 AND job_count),
    CHECK (job_count <= row_count),
    CHECK ((status = 'completed') = (completed_at IS NOT NULL))
);

CREATE TABLE IF NOT EXISTS staging.jobs (
    file_id bigint REFERENCES staging.source_files,
    record_number bigint CHECK (record_number > 0),
    raw_record jsonb NOT NULL,
    job_skills jsonb CHECK (jsonb_typeof(job_skills) = 'array'),
    job_type_skills jsonb CHECK (jsonb_typeof(job_type_skills) = 'object'),
    record_hash bytea CHECK (octet_length(record_hash) = 32),
    validation_error text,
    job_id bigint REFERENCES core.jobs,
    PRIMARY KEY (file_id, record_number),
    CHECK ((record_hash IS NULL) = (validation_error IS NOT NULL))
);
