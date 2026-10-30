import ast
import csv
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from itertools import islice
from pathlib import Path

COLUMNS = (
    "job_title_short",
    "job_title",
    "job_location",
    "job_via",
    "job_schedule_type",
    "job_work_from_home",
    "search_location",
    "job_posted_date",
    "job_no_degree_mention",
    "job_health_insurance",
    "job_country",
    "salary_rate",
    "salary_year_avg",
    "salary_hour_avg",
    "company_name",
    "job_skills",
    "job_type_skills",
)
BOOLEAN_COLUMNS = ("job_work_from_home", "job_no_degree_mention", "job_health_insurance")
NUMBER = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\Z")


class DataError(ValueError):
    pass


@dataclass
class ParsedRecord:
    record_hash: bytes
    skills: list[str] | None
    categories: dict[str, list[str]] | None


def parse_collection(value: str, field_name: str):
    if not value.strip():
        return None
    try:
        parsed = ast.literal_eval(value)
    except (ValueError, SyntaxError, RecursionError) as error:
        raise DataError(f"{field_name}: invalid Python literal") from error
    if field_name == "job_skills":
        return parse_members(parsed, field_name)
    if not isinstance(parsed, dict):
        raise DataError(f"{field_name}: expected a dictionary")
    if any(not isinstance(key, str) or not key.strip() for key in parsed):
        raise DataError(f"{field_name}: expected nonempty category names")
    return {key: parse_members(parsed[key], field_name) for key in sorted(parsed)}


def parse_members(value, field_name: str) -> list[str]:
    if not isinstance(value, list):
        raise DataError(f"{field_name}: expected a list")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise DataError(f"{field_name}: expected nonempty skill names")
    return sorted(set(value))


def parse_record(row: dict[str, str]) -> ParsedRecord:
    if not row["job_title_short"].strip():
        raise DataError("job_title_short: missing standardized title")
    date = row["job_posted_date"].strip()
    try:
        datetime.strptime(date, "%Y-%m-%d %H:%M:%S")
    except ValueError as error:
        raise DataError("job_posted_date: expected YYYY-MM-DD HH:MM:SS") from error
    for name in BOOLEAN_COLUMNS:
        if row[name].strip() not in ("", "True", "False"):
            raise DataError(f"{name}: expected True, False, or a missing value")
    for name in ("salary_year_avg", "salary_hour_avg"):
        value = row[name].strip()
        if value:
            if not NUMBER.fullmatch(value):
                raise DataError(f"{name}: invalid numeric format")
            try:
                amount = Decimal(value)
            except InvalidOperation as error:
                raise DataError(f"{name}: invalid amount") from error
            if not amount.is_finite() or amount <= 0:
                raise DataError(f"{name}: expected a positive finite amount")
    skills = parse_collection(row["job_skills"], "job_skills")
    categories = parse_collection(row["job_type_skills"], "job_type_skills")
    if skills is not None and categories is not None:
        grouped_skills = {skill for members in categories.values() for skill in members}
        if set(skills) != grouped_skills:
            raise DataError("job_skills and job_type_skills: memberships disagree")
    canonical = dict(row)
    canonical["job_skills"] = skills
    canonical["job_type_skills"] = categories
    payload = json.dumps(
        [canonical[name] for name in COLUMNS], ensure_ascii=False, separators=(",", ":")
    )
    record_hash = hashlib.sha256(payload.encode("utf-8")).digest()
    return ParsedRecord(record_hash, skills, categories)


def file_hash(path: Path) -> bytes:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").digest()


def read_batches(path: Path, batch_size: int):
    if batch_size < 1:
        raise ValueError("Batch size must be positive")
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, strict=True)
        headers = reader.fieldnames or []
        if len(headers) != len(COLUMNS) or set(headers) != set(COLUMNS):
            raise DataError("CSV headers must contain each of the 17 expected columns exactly once")
        while batch := list(islice(reader, batch_size)):
            for row in batch:
                if None in row or any(value is None for value in row.values()):
                    raise DataError("CSV record has an unexpected number of fields")
                if any("\x00" in value for value in row.values()):
                    raise DataError("CSV contains a null character unsupported by PostgreSQL text")
            yield batch
