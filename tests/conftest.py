import csv
import os

import psycopg
import pytest

from jobs_pipeline.parsing import COLUMNS
from jobs_pipeline.pipeline import initialize


@pytest.fixture
def row():
    return dict(
        zip(
            COLUMNS,
            (
                "Data Engineer",
                "Data Engineer",
                "Bogota",
                "via LinkedIn",
                "Full-time",
                "False",
                "Colombia",
                "2023-01-01 10:00:00",
                "False",
                "True",
                "Colombia",
                "year",
                "100000",
                "",
                "Example Company",
                "['python', 'sql']",
                "{'programming': ['python', 'sql']}",
            ),
            strict=True,
        )
    )


@pytest.fixture
def make_csv(tmp_path):
    counter = 0

    def write(rows, name=None):
        nonlocal counter
        counter += 1
        path = tmp_path / (name or f"jobs-{counter}.csv")
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
        return path

    return write


@pytest.fixture
def database():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to run the PostgreSQL integration tests")
    with psycopg.connect(url, autocommit=True) as connection:
        if not connection.info.dbname.endswith("_test"):
            pytest.fail("Integration tests require a database name ending in _test")
        initialize(connection)
        connection.execute(
            "TRUNCATE staging.source_files, core.companies, core.platforms, core.job_titles, "
            "core.countries, core.skills, core.skill_categories, core.schedule_types CASCADE"
        )
        yield connection
