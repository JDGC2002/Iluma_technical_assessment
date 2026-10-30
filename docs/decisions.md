# My design decisions

I keep the reasoning here so the README can stay short. This document follows the same order I used to approach the assessment: understand the source, define the model, decide how to load it, and check the result.

## Scope and tools

I chose Python for reading and validating the CSV, PostgreSQL for the relational model and transformations, and Docker Compose for the database setup. This gives me a small stack where each part has a clear job.

For Python, I use the standard CSV and logging modules, Psycopg for the database connection, python-dotenv for configuration, and pytest for tests. SQL checks and database constraints cover the data-quality rules.

## What I found in the file

I reviewed all 785,741 records and 17 columns before choosing the model. The counts and examples are in [data-profile.json](data-profile.json).

| Finding | Count | My decision |
| --- | ---: | --- |
| Exact duplicate occurrences | 101 | Keep every occurrence in staging and one job per identity. |
| Additional duplicates differing only in skill order | 3 | Compare skill membership without order. |
| Expected distinct jobs | 785,637 | Use this count to check the first complete load. |
| Additional records lost by a company/title/location/time key | 740 | Use all 17 fields for identity. |
| Records with repeated skill names | 63,811 | Keep one relationship per job and skill. |
| Skills and skill/category memberships | 252 / 256 | Allow several categories per skill. |
| Skills with different category sets across records | 0 | Store the shared classification once and check it on later loads. |
| Records missing both skill fields | 117,037 | Record whether skill information was supplied. |
| Location labels associated with several countries | 1,167 | Identify a location by its label and reported country. |
| Nonempty full titles with several standardized titles | 0 | Store the title mapping once. |
| Records missing a company and full title | 1 | Keep the record with its supplied standardized title. |

## What I count as a job

I treat one job as one distinct record from the source. There is no listing ID or URL, so I do not have enough evidence to merge two records just because their company and title match. They may still differ in platform, search location, posting time, salary, flags, or skills.

This matters for later analysis: my job count describes the source records and may include several postings for the same vacancy.

## Fingerprints and duplicates

I calculate a SHA-256 fingerprint from a JSON array containing the 17 fields in a fixed order. Scalar values stay as they were read from the CSV. For the two skill fields, I parse the lists and dictionary, sort their members and keys, and remove repeated members. Missing collections remain null, separately from an empty list or dictionary.

That lets me merge exact repeats and records that differ only in skill order or repetition. A file name, record number, batch size, execution time, or database ID has no effect on the fingerprint. A different platform, salary, timestamp, or skill membership still produces a different job.

For the supplied file, my expected result is:

```text
785,741 source records = 785,637 jobs + 104 duplicate occurrences
```

I keep the original field strings in staging, including duplicate records. Cleaning a company name later does not change its source fingerprint.

## Missing skills and empty lists

I store the job's skills in `core.job_skills`. Two booleans on the job describe whether the source supplied skill information: `skills_reported` and `skill_categories_reported`.

| Input | Presence field | Relationships |
| --- | --- | --- |
| Both skill fields missing | `skills_reported = false` | No skill relationships. |
| Explicit `[]` | `skills_reported = true` | No skill relationships. |
| Populated list | `skills_reported = true` | The supplied skills. |
| Missing list, populated dictionary | `skills_reported = true` | The dictionary's explicit members. |

I set `skills_reported` when either skill field is supplied, and `skill_categories_reported` when the dictionary is supplied. Staging keeps the original value of each field. If both collections are present, I check that their memberships agree.

I need these presence fields because zero related skills can mean either missing information or an explicitly empty result. Keeping that distinction also agrees with the fingerprint rule.

## Validation and failed loads

I allow salary, company, full title, platform, schedule, location, country, and boolean flags to be missing. A supplied false value stays different from null. I require the standardized title and posting timestamp so I have a basic description and date for the record.

When a value is supplied, I check its format. Dates, booleans, salaries, lists, and dictionaries must parse correctly. Salary averages must be positive and finite. I keep posting timestamps without a time zone because the source gives no offset, and I keep salary values without guessing a currency or calculating missing amounts.

For a readable file, I finish staging all records and store any row errors. If I find invalid rows, I mark the file failed, report the count and example record numbers, and return a nonzero exit code before publication. If the CSV structure or encoding prevents a reliable read, I roll back staging and record a file-level error instead.

I also stop publication when a full title has conflicting standardized titles or a known skill has conflicting classifications. The staged records remain available, and the source-file entry explains the conflict.

I chose to publish a complete file at a time because this assessment gives me one file as a unit of work. A failed load leaves the previous successful data available. In operations, I would alert on the failure, inspect the staged data, fix the source or rule, and retry. A database connection issue may be worth an automatic retry. Invalid source data needs a correction first. This choice can delay fresh data, but it keeps an incomplete file from looking like a successful load.
