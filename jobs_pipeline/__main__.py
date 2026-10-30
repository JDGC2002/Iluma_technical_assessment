import argparse
import csv
import logging
from pathlib import Path

import psycopg

from jobs_pipeline.config import Settings
from jobs_pipeline.pipeline import check_quality, initialize, load_file, writer_lock


def main() -> int:
    parser = argparse.ArgumentParser(description="Load job postings from CSV into PostgreSQL.")
    parser.add_argument("command", choices=("init", "load", "check"))
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        settings = Settings.from_env(args.env_file)
        with psycopg.connect(**settings.connection_parameters()) as connection:
            if args.command == "init":
                with writer_lock(connection):
                    initialize(connection)
                logging.info("Database schema initialized")
            elif args.command == "load":
                load_file(connection, settings.input_file, settings.batch_size)
            else:
                check_quality(connection)
    except (ValueError, RuntimeError, OSError, csv.Error, psycopg.Error) as error:
        logging.error("Command stopped: %s", error)
        return 1
    except KeyboardInterrupt:
        logging.error("Command interrupted. The incomplete file can be retried.")
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
