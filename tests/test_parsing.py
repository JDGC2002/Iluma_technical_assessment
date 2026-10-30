import pytest

from jobs_pipeline.parsing import DataError, parse_record, read_batches


@pytest.mark.parametrize(
    "field,value",
    [
        ("search_location", "Mexico"),
        ("salary_year_avg", "100001"),
        ("job_no_degree_mention", "True"),
    ],
)
def test_identity_retains_observation_differences(row, field, value):
    assert parse_record(row).record_hash != parse_record({**row, field: value}).record_hash


@pytest.mark.parametrize(
    "field,value",
    [
        ("job_skills", "{'python': 1}"),
        ("job_skills", "['python', 1]"),
        ("job_type_skills", "{'programming': 'python'}"),
        ("salary_year_avg", "NaN"),
        ("salary_year_avg", "0"),
        ("salary_hour_avg", "unknown"),
        ("job_work_from_home", "yes"),
        ("job_posted_date", "2023-02-30 10:00:00"),
        ("job_posted_date", "2023-01-01 10:00:00+01:00"),
        ("job_title_short", ""),
    ],
)
def test_invalid_values_are_not_silently_replaced(row, field, value):
    with pytest.raises(DataError):
        parse_record({**row, field: value})


def test_skill_membership_disagreement_is_visible(row):
    with pytest.raises(DataError, match="memberships disagree"):
        parse_record({**row, "job_skills": "['python']"})


def test_batches_preserve_multiline_csv_records(row, make_csv):
    row["job_title"] = 'Engineer, "Data"\nPlatform Team'
    path = make_csv([row] * 5)
    batches = list(read_batches(path, 2))
    assert [len(batch) for batch in batches] == [2, 2, 1]
    assert batches[0][0]["job_title"] == row["job_title"]
