# GitHub Actions

```mermaid
flowchart LR
    A[Trigger] --> B[Install dependencies]
    B --> C[Lint and formatting]
    C --> D[33 tests]
    P[(Temporary PostgreSQL)] <--> D
    D --> E[Pass or fail]
```

## Triggers

- Pull requests to `main`.
- Pushes to `main`.
- Manual runs from GitHub Actions.

## Environment

| Component | Value |
| --- | --- |
| Runner | GitHub-hosted Ubuntu |
| Python | 3.12 |
| PostgreSQL | `postgres:18.6-bookworm` |
| Database | Temporary `jobs_test` |
| Data | Small CSV files created by the tests |
