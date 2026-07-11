from pathlib import Path

from config import load_settings


def test_load_settings_defaults(monkeypatch):
    for key in (
        "SERVER_REPORT_DELAY_HOURS",
        "JOIN_BURST_WINDOW_SECONDS",
        "JOIN_BURST_THRESHOLD",
        "HEALTH_MESSAGE_SAMPLING",
        "DATA_DIR",
    ):
        monkeypatch.delenv(key, raising=False)

    settings = load_settings()

    assert settings.server_report_delay_hours == 72
    assert settings.join_burst_window_seconds == 300
    assert settings.join_burst_threshold == 5
    assert settings.health_message_sampling is False
    assert settings.data_dir == Path("data")


def test_load_settings_from_env(monkeypatch):
    monkeypatch.setenv("SERVER_REPORT_DELAY_HOURS", "12")
    monkeypatch.setenv("JOIN_BURST_WINDOW_SECONDS", "60")
    monkeypatch.setenv("JOIN_BURST_THRESHOLD", "3")
    monkeypatch.setenv("HEALTH_MESSAGE_SAMPLING", "true")
    monkeypatch.setenv("DATA_DIR", "/tmp/discordd-data")

    settings = load_settings()

    assert settings.server_report_delay_hours == 12
    assert settings.join_burst_window_seconds == 60
    assert settings.join_burst_threshold == 3
    assert settings.health_message_sampling is True
    assert settings.data_dir == Path("/tmp/discordd-data")
