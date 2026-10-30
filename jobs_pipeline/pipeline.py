import logging
from contextlib import contextmanager
from pathlib import Path
from time import perf_counter

from psycopg import Connection
from psycopg.types.json import Jsonb

from jobs_pipeline.parsing import DataError, file_hash, parse_record, read_batches

LOGGER = logging.getLogger(__name__)
SQL_DIRECTORY = Path(__file__).resolve().parent.parent / "sql"
WRITER_LOCK = 475602113


class LoadError(RuntimeError):
    pass


def run_sql(connection: Connection, name: str):
    return connection.execute((SQL_DIRECTORY / name).read_text(encoding="utf-8"))


@contextmanager
def writer_lock(connection: Connection):
    acquired = connection.execute("SELECT pg_try_advisory_lock(%s)", (WRITER_LOCK,)).fetchone()[0]
    if not acquired:
        raise LoadError("Another load is running. Wait for it to finish and retry.")
    try:
        yield
    finally:
        if not connection.closed:
            connection.execute("SELECT pg_advisory_unlock(%s)", (WRITER_LOCK,))


def initialize(connection: Connection):
    with connection.transaction():
        run_sql(connection, "schema.sql")


def stage_file(connection: Connection, path: Path, batch_size: int, file_id: int, digest: bytes):
    row_count = 0
    invalid_count = 0
    started = perf_counter()
    with connection.transaction():
        connection.execute("DELETE FROM staging.jobs WHERE file_id = %s", (file_id,))
        for batch in read_batches(path, batch_size):
            with connection.cursor().copy(
                "COPY staging.jobs (file_id, record_number, raw_record, job_skills, "
                "job_type_skills, record_hash, validation_error) FROM STDIN"
            ) as copy:
                for row in batch:
                    row_count += 1
                    try:
                        parsed = parse_record(row)
                        values = (
                            file_id,
                            row_count,
                            Jsonb(row),
                            Jsonb(parsed.skills) if parsed.skills is not None else None,
                            Jsonb(parsed.categories) if parsed.categories is not None else None,
                            parsed.record_hash,
                            None,
                        )
                    except DataError as error:
                        invalid_count += 1
                        values = (file_id, row_count, Jsonb(row), None, None, None, str(error))
                    copy.write_row(values)
            LOGGER.info("Staged %s records (%s invalid)", row_count, invalid_count)
        if not row_count:
            raise DataError("Input file contains no data records")
        if file_hash(path) != digest:
            raise DataError("Input file changed during ingestion. Retry with a stable copy.")
        connection.execute(
            "UPDATE staging.source_files SET status = 'staged', row_count = %s, "
            "invalid_count = %s, error = NULL WHERE file_id = %s",
            (row_count, invalid_count, file_id),
        )
    LOGGER.info("Staging finished in %.2f seconds", perf_counter() - started)
    if invalid_count:
        examples = connection.execute(
            "SELECT record_number, validation_error FROM staging.jobs "
            "WHERE file_id = %s AND validation_error IS NOT NULL ORDER BY record_number LIMIT 5",
            (file_id,),
        ).fetchall()
        detail = "; ".join(f"record {number}: {error}" for number, error in examples)
        raise DataError(f"Publication stopped. Invalid records: {invalid_count}. {detail}")


def publish_file(connection: Connection, file_id: int) -> dict:
    started = perf_counter()
    with connection.transaction():
        LOGGER.info("Preparing staged records")
        connection.execute(
            "CREATE TEMP TABLE incoming_source ON COMMIT DROP AS "
            "SELECT DISTINCT ON (record_hash) record_hash, raw_record, job_skills, job_type_skills "
            "FROM staging.jobs WHERE file_id = %s ORDER BY record_hash, record_number",
            (file_id,),
        )
        run_sql(connection, "prepare.sql")
        LOGGER.info("Checking title mappings and skill classifications")
        conflicts = run_sql(connection, "validate.sql").fetchall()
        if conflicts:
            raise DataError("; ".join(row[0] for row in conflicts))
        LOGGER.info("Publishing entities, jobs, and relationships")
        run_sql(connection, "publish.sql")
        connection.execute(
            "UPDATE staging.jobs s SET job_id = j.job_id FROM core.jobs j "
            "WHERE s.file_id = %s AND s.record_hash = j.record_hash",
            (file_id,),
        )
        row_count, job_count, linked_count = connection.execute(
            "SELECT count(*), count(DISTINCT record_hash), count(job_id) "
            "FROM staging.jobs WHERE file_id = %s",
            (file_id,),
        ).fetchone()
        new_job_count = connection.execute("SELECT count(*) FROM new_jobs").fetchone()[0]
        if linked_count != row_count:
            raise LoadError("Some staged records could not be linked to a job")
        expected_skills, published_skills = connection.execute(
            "SELECT (SELECT count(*) FROM incoming_skills JOIN new_jobs USING (record_hash)), "
            "(SELECT count(*) FROM core.job_skills JOIN new_jobs USING (job_id))"
        ).fetchone()
        expected_schedules, published_schedules = connection.execute(
            "SELECT (SELECT count(*) FROM incoming_schedules JOIN new_jobs USING (record_hash)), "
            "(SELECT count(*) FROM core.job_schedules JOIN new_jobs USING (job_id))"
        ).fetchone()
        if expected_skills != published_skills or expected_schedules != published_schedules:
            raise LoadError("Published skill or schedule counts do not match the staged data")
        connection.execute(
            "UPDATE staging.source_files SET status = 'completed', completed_at = now(), "
            "error = NULL, job_count = %s, new_job_count = %s WHERE file_id = %s",
            (job_count, new_job_count, file_id),
        )
    result = {
        "file_id": file_id,
        "rows": row_count,
        "jobs": job_count,
        "new_jobs": new_job_count,
        "duplicates": row_count - job_count,
        "skipped": False,
    }
    LOGGER.info(
        "Published %s new jobs from %s records (%s distinct, %s duplicates) in %.2f seconds",
        new_job_count,
        row_count,
        job_count,
        row_count - job_count,
        perf_counter() - started,
    )
    return result


def load_file(connection: Connection, path: Path, batch_size: int) -> dict:
    if not path.is_file():
        raise DataError(f"Input file does not exist: {path}")
    if batch_size < 1:
        raise ValueError("Batch size must be positive")
    digest = file_hash(path)
    with writer_lock(connection):
        initialize(connection)
        existing = connection.execute(
            "SELECT file_id, status, row_count, job_count, new_job_count "
            "FROM staging.source_files WHERE file_hash = %s",
            (digest,),
        ).fetchone()
        if existing and existing[1] == "completed":
            LOGGER.info("File already completed, skipping (file_id=%s)", existing[0])
            return {
                "file_id": existing[0],
                "rows": existing[2],
                "jobs": existing[3],
                "new_jobs": 0,
                "duplicates": existing[2] - existing[3],
                "skipped": True,
            }
        file_id = connection.execute(
            "INSERT INTO staging.source_files (file_hash, file_name) VALUES (%s, %s) "
            "ON CONFLICT (file_hash) DO UPDATE SET status = 'received', error = NULL, "
            "row_count = 0, invalid_count = 0, job_count = 0, new_job_count = 0, "
            "started_at = now() RETURNING file_id",
            (digest, path.name),
        ).fetchone()[0]
        try:
            stage_file(connection, path, batch_size, file_id, digest)
            return publish_file(connection, file_id)
        except Exception as error:
            if not connection.closed:
                connection.execute(
                    "UPDATE staging.source_files SET status = 'failed', error = %s "
                    "WHERE file_id = %s",
                    (str(error)[:4000], file_id),
                )
            raise


def check_quality(connection: Connection):
    failures = run_sql(connection, "quality.sql").fetchall()
    if failures:
        raise LoadError("; ".join(row[0] for row in failures))
    jobs, relationships = connection.execute(
        "SELECT (SELECT count(*) FROM core.jobs), (SELECT count(*) FROM core.job_skills)"
    ).fetchone()
    LOGGER.info(
        "Quality checks passed: %s jobs and %s job-skill relationships", jobs, relationships
    )
