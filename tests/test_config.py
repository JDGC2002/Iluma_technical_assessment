import pytest

from jobs_pipeline.config import Settings


@pytest.fixture
def env_file(tmp_path, monkeypatch):
    for key in (
        "INPUT_FILE",
        "BATCH_SIZE",
        "POSTGRES_DB",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "POSTGRES_HOST",
        "POSTGRES_PORT",
    ):
        monkeypatch.delenv(key, raising=False)
    path = tmp_path / ".env"
    path.write_text(
        'INPUT_FILE="my data.csv"\nBATCH_SIZE=7\nPOSTGRES_DB=jobs\n'
        'POSTGRES_USER=user\nPOSTGRES_PASSWORD="a@b:/password"\n',
        encoding="utf-8",
    )
    return path


def test_config_resolves_relative_file_and_keeps_password_private(env_file):
    settings = Settings.from_env(env_file)
    assert settings.input_file == env_file.parent / "my data.csv"
    assert settings.batch_size == 7
    assert settings.connection_parameters()["password"] == "a@b:/password"
    assert "a@b:/password" not in repr(settings)


def test_environment_overrides_file(env_file, monkeypatch):
    monkeypatch.setenv("BATCH_SIZE", "12")
    assert Settings.from_env(env_file).batch_size == 12


@pytest.mark.parametrize(
    "name,value",
    [
        ("BATCH_SIZE", "0"),
        ("BATCH_SIZE", "wrong"),
        ("POSTGRES_PORT", "65536"),
        ("POSTGRES_PASSWORD", ""),
    ],
)
def test_invalid_configuration_fails_early(env_file, monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError):
        Settings.from_env(env_file)
