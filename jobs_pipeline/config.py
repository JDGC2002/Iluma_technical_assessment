import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import dotenv_values


@dataclass(frozen=True)
class Settings:
    input_file: Path
    batch_size: int
    database: str
    user: str
    password: str = field(repr=False)
    host: str = "127.0.0.1"
    port: int = 5432

    @classmethod
    def from_env(cls, env_file: Path) -> "Settings":
        env_file = env_file.resolve()
        values = {**dotenv_values(env_file), **os.environ}
        required = ("POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD")
        missing = [name for name in required if not values.get(name)]
        if missing:
            raise ValueError(f"Missing configuration: {', '.join(missing)}")
        try:
            batch_size = int(values.get("BATCH_SIZE", "10000"))
            port = int(values.get("POSTGRES_PORT", "5432"))
        except (TypeError, ValueError) as error:
            raise ValueError("BATCH_SIZE and POSTGRES_PORT must be integers") from error
        if batch_size < 1:
            raise ValueError("BATCH_SIZE must be positive")
        if not 1 <= port <= 65535:
            raise ValueError("POSTGRES_PORT must be between 1 and 65535")
        input_file = Path(values.get("INPUT_FILE") or "data_jobs.csv")
        if not input_file.is_absolute():
            input_file = env_file.parent / input_file
        return cls(
            input_file=input_file,
            batch_size=batch_size,
            database=values["POSTGRES_DB"],
            user=values["POSTGRES_USER"],
            password=values["POSTGRES_PASSWORD"],
            host=values.get("POSTGRES_HOST") or "127.0.0.1",
            port=port,
        )

    def connection_parameters(self) -> dict:
        return {
            "dbname": self.database,
            "user": self.user,
            "password": self.password,
            "host": self.host,
            "port": self.port,
            "connect_timeout": 10,
            "application_name": "jobs_pipeline",
            "autocommit": True,
        }
