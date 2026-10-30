import os
import shutil

import psycopg
import pytest

from jobs_pipeline import pipeline
from jobs_pipeline.parsing import DataError
from jobs_pipeline.pipeline import LoadError, check_quality, load_file, writer_lock

pytestmark = pytest.mark.integration


def count(database, table):
    return database.execute(
        psycopg.sql.SQL("SELECT count(*) FROM {}").format(psycopg.sql.Identifier("core", table))
    ).fetchone()[0]


def test_deduplication_keeps_every_source_occurrence(database, row, make_csv):
    changed = {
        **row,
        "job_skills": "['sql', 'python', 'python']",
        "job_type_skills": "{'programming': ['sql', 'python']}",
    }
    result = load_file(database, make_csv([row, row, changed]), 2)
    assert (result["rows"], result["jobs"], result["duplicates"]) == (3, 1, 2)
    assert count(database, "job_skills") == 2
    assert database.execute(
        "SELECT record_number, raw_record FROM staging.jobs ORDER BY record_number"
    ).fetchall() == [(1, row), (2, row), (3, changed)]
    check_quality(database)


def test_presence_metadata_distinguishes_missing_and_empty(database, row, make_csv):
    rows = [
        {**row, "job_skills": "", "job_type_skills": ""},
        {**row, "job_skills": "[]", "job_type_skills": "{}"},
        row,
        {**row, "job_skills": ""},
    ]
    load_file(database, make_csv(rows), 2)
    actual = database.execute(
        "SELECT j.skills_reported, j.skill_categories_reported, "
        "(SELECT count(*) FROM core.job_skills k WHERE k.job_id = j.job_id) "
        "FROM staging.jobs s JOIN core.jobs j USING (job_id) ORDER BY s.record_number"
    ).fetchall()
    assert actual == [(False, False, 0), (True, True, 0), (True, True, 2), (True, True, 2)]


def test_repeated_renamed_reordered_and_overlapping_files(database, row, make_csv):
    other = {**row, "job_via": "via Second Platform"}
    path = make_csv([row, other])
    load_file(database, path, 1)
    before = database.execute(
        "SELECT job_id, record_hash FROM core.jobs ORDER BY job_id"
    ).fetchall()
    renamed = path.with_name("renamed.csv")
    shutil.copyfile(path, renamed)
    assert load_file(database, renamed, 7)["skipped"]
    assert load_file(database, path, 10)["skipped"]
    assert load_file(database, make_csv([other, row]), 3)["new_jobs"] == 0
    overlap = make_csv([row, {**row, "job_posted_date": "2023-01-02 10:00:00"}])
    assert load_file(database, overlap, 2)["new_jobs"] == 1
    assert (
        database.execute(
            "SELECT job_id, record_hash FROM core.jobs ORDER BY job_id LIMIT 2"
        ).fetchall()
        == before
    )
    check_quality(database)


def test_later_load_adds_new_entities(database, row, make_csv):
    load_file(database, make_csv([row]), 1)
    new = {
        **row,
        "job_title": "Rust Engineer",
        "company_name": "New Company",
        "job_via": "via New Platform",
        "job_location": "Berlin",
        "job_country": "Germany",
        "job_skills": "['rust']",
        "job_type_skills": "{'new_category': ['rust']}",
        "job_schedule_type": "Contractor and Part-time",
    }
    assert load_file(database, make_csv([new]), 1)["new_jobs"] == 1
    for table, expected in (
        ("skills", 3),
        ("platforms", 2),
        ("companies", 2),
        ("countries", 2),
        ("skill_categories", 2),
        ("schedule_types", 3),
    ):
        assert count(database, table) == expected
    assert count(database, "job_schedules") == 3
    linked = database.execute(
        "SELECT s.name, p.name, t.full_title FROM core.jobs j "
        "JOIN core.job_skills k USING (job_id) JOIN core.skills s USING (skill_id) "
        "JOIN core.platforms p USING (platform_id) JOIN core.job_titles t USING (title_id) "
        "WHERE s.name = 'rust'"
    ).fetchall()
    assert linked == [("rust", "New Platform", "Rust Engineer")]


def test_invalid_rows_remain_in_staging_and_can_be_repaired(database, row, make_csv):
    path = make_csv([row, {**row, "job_skills": "broken"}])
    with pytest.raises(DataError, match="Invalid records: 1"):
        load_file(database, path, 1)
    assert count(database, "jobs") == 0
    assert database.execute("SELECT count(*) FROM staging.jobs").fetchone()[0] == 2
    assert database.execute(
        "SELECT status, invalid_count FROM staging.source_files"
    ).fetchone() == ("failed", 1)
    with pytest.raises(DataError):
        load_file(database, path, 4)
    assert database.execute("SELECT count(*) FROM staging.jobs").fetchone()[0] == 2
    repaired = make_csv([row, {**row, "job_posted_date": "2023-01-02 10:00:00"}], path.name)
    assert load_file(database, repaired, 2)["new_jobs"] == 2
    check_quality(database)


def test_publication_failure_rolls_back_entities_and_retries(database, row, make_csv, monkeypatch):
    previous = load_file(database, make_csv([row]), 1)
    queries = (
        "SELECT * FROM core.jobs ORDER BY job_id",
        "SELECT * FROM core.skills ORDER BY skill_id",
    )
    before = [database.execute(query).fetchall() for query in queries]
    new = {**row, "job_skills": "['rust']", "job_type_skills": "{'programming': ['rust']}"}
    path = make_csv([new])
    original = pipeline.run_sql

    def fail_publication(connection, name):
        result = original(connection, name)
        if name == "publish.sql":
            raise LoadError("Injected publication failure")
        return result

    with monkeypatch.context() as patch:
        patch.setattr(pipeline, "run_sql", fail_publication)
        with pytest.raises(LoadError, match="Injected"):
            load_file(database, path, 1)
    assert [database.execute(query).fetchall() for query in queries] == before
    assert database.execute(
        "SELECT status FROM staging.source_files ORDER BY file_id"
    ).fetchall() == [("completed",), ("failed",)]
    assert (
        database.execute(
            "SELECT raw_record FROM staging.jobs WHERE file_id = %s", (previous["file_id"],)
        ).fetchone()[0]
        == row
    )
    assert load_file(database, path, 2)["new_jobs"] == 1
    assert count(database, "jobs") == 2
    assert count(database, "skills") == 3
    assert database.execute("SELECT count(*) FROM staging.source_files").fetchone()[0] == 2


@pytest.mark.parametrize(
    "change,message",
    [
        ({"job_type_skills": "{'databases': ['python', 'sql']}"}, "skill classification"),
        ({"job_title_short": "Data Analyst"}, "standardized title"),
    ],
)
def test_existing_dependencies_cannot_change_silently(database, row, make_csv, change, message):
    load_file(database, make_csv([row]), 1)
    with pytest.raises(DataError, match=message):
        load_file(database, make_csv([{**row, **change}]), 1)
    assert count(database, "jobs") == 1
    assert count(database, "skill_categories") == 1
    assert database.execute("SELECT count(*) FROM staging.jobs").fetchone()[0] == 2


def test_nullable_location_components_have_stable_identity(database, row, make_csv):
    rows = [
        {**row, "job_location": ""},
        {**row, "job_location": "", "job_posted_date": "2023-01-02 10:00:00"},
        {**row, "job_location": "Paris", "job_country": ""},
        {
            **row,
            "job_location": "",
            "job_country": "",
            "job_title": "",
            "company_name": "",
            "salary_year_avg": "",
            "job_work_from_home": "",
        },
    ]
    load_file(database, make_csv(rows), 2)
    assert count(database, "jobs") == 4
    assert count(database, "locations") == 2
    assert (
        database.execute("SELECT count(*) FROM core.jobs WHERE location_id IS NULL").fetchone()[0]
        == 1
    )
    assert database.execute(
        "SELECT j.company_id, t.full_title, t.short_title, j.salary_year_avg, "
        "j.salary_hour_avg, j.job_work_from_home FROM staging.jobs s "
        "JOIN core.jobs j USING (job_id) JOIN core.job_titles t USING (title_id) "
        "WHERE s.record_number = 4"
    ).fetchone() == (None, None, row["job_title_short"], None, None, None)
    assert (
        database.execute(
            "SELECT j.job_work_from_home FROM staging.jobs s "
            "JOIN core.jobs j USING (job_id) WHERE s.record_number = 1"
        ).fetchone()[0]
        is False
    )


def test_second_writer_fails_without_changing_data(database, row, make_csv):
    load_file(database, make_csv([row]), 1)
    queries = (
        "SELECT * FROM core.jobs ORDER BY job_id",
        "SELECT * FROM staging.jobs ORDER BY file_id, record_number",
        "SELECT * FROM staging.source_files ORDER BY file_id",
    )
    before = [database.execute(query).fetchall() for query in queries]
    with psycopg.connect(os.environ["TEST_DATABASE_URL"], autocommit=True) as other:
        with writer_lock(other):
            with pytest.raises(LoadError, match="Another load is running"):
                load_file(database, make_csv([row]), 1)
    assert [database.execute(query).fetchall() for query in queries] == before


def test_file_contract_failure_preserves_previous_publication(database, row, make_csv, tmp_path):
    load_file(database, make_csv([row]), 1)
    broken = tmp_path / "broken.csv"
    broken.write_text("wrong,headers\na,b\n", encoding="utf-8")
    with pytest.raises(DataError, match="headers"):
        load_file(database, broken, 1)
    assert count(database, "jobs") == 1
    assert database.execute(
        "SELECT status, row_count FROM staging.source_files WHERE file_name = 'broken.csv'"
    ).fetchone() == ("failed", 0)
    check_quality(database)


def test_file_changed_during_staging_is_not_published(database, row, make_csv, monkeypatch):
    path = make_csv([row])
    original_digest = pipeline.file_hash(path)
    digests = iter([original_digest, bytes(32)])
    monkeypatch.setattr(pipeline, "file_hash", lambda _: next(digests))
    with pytest.raises(DataError, match="changed during ingestion"):
        load_file(database, path, 1)
    assert count(database, "jobs") == 0
    assert database.execute("SELECT count(*) FROM staging.jobs").fetchone()[0] == 0
    assert database.execute("SELECT status FROM staging.source_files").fetchone()[0] == "failed"
