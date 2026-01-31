from pathlib import Path
from unittest.mock import MagicMock, patch
import importlib.metadata

import pytest
from typer.testing import CliRunner

from genesis.cli import app
from genesis.consumer import Consumer
from genesis.outbound import Outbound
from genesis.cli.discover import get_app_name, get_import_string
from genesis.cli.utils import complete_log_levels
from genesis.cli.exceptions import CLIExcpetion


@pytest.fixture(autouse=True)
def mock_metrics_server(monkeypatch):
    # Set a random port or 0 to let OS choose, avoiding conflicts
    monkeypatch.setenv("GENESIS_METRICS_PORT", "0")
    # Disable colored output to ensure string assertions work in CI
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setenv("FORCE_COLOR", "0")
    monkeypatch.setenv("TERM", "dumb")

    # Patch logger.info to use simple print to avoid rich formatting issues
    import genesis.cli

    original_logger_info = genesis.cli.logger.info

    def simple_info(msg, *args, **kwargs):
        # Simple print without rich formatting
        print(f"INFO     {msg}")

    monkeypatch.setattr(genesis.cli.logger, "info", simple_info)
    monkeypatch.setattr(genesis.cli.logger, "warning", lambda *args, **kwargs: None)

    # We still keep the patch to avoid actual network binding if possible,
    # but the env var ensures if it DOES bind, it won't conflict.
    with patch("genesis.cli.start_http_server"):
        yield


runner = CliRunner()


class TestVersion:

    def test_version_flag_displays_version_and_exits(self) -> None:
        with patch("importlib.metadata.version", return_value="1.0.0"):
            result = runner.invoke(app, ["--version"])

            assert result.exit_code == 0
            assert "Genesis version: 1.0.0" in result.stdout

    def test_version_flag_reads_from_metadata(self) -> None:
        actual_version = importlib.metadata.version("genesis")
        result = runner.invoke(app, ["--version"])

        assert result.exit_code == 0
        assert f"Genesis version: {actual_version}" in result.stdout


class TestJSONLogging:

    def test_json_flag_accepted_without_error(self) -> None:
        result = runner.invoke(app, ["--json", "--version"])

        assert result.exit_code == 0
        assert "Genesis version:" in result.stdout


class TestMetricsServer:

    def test_metrics_server_does_not_crash_cli(self) -> None:
        result = runner.invoke(app, ["--version"])

        assert result.exit_code == 0


class TestConsumerCommands:

    def test_consumer_run_requires_path_argument(self) -> None:
        result = runner.invoke(app, ["consumer", "run"])

        assert result.exit_code != 0
        assert "Missing argument" in result.stdout or "Error" in result.stdout

    def test_consumer_dev_requires_path_argument(self) -> None:
        result = runner.invoke(app, ["consumer", "dev"])

        assert result.exit_code != 0
        assert "Missing argument" in result.stdout or "Error" in result.stdout

    def test_consumer_run_accepts_host_option(self) -> None:
        result = runner.invoke(app, ["consumer", "run", "--help"])

        assert result.exit_code == 0
        assert "--host" in result.stdout

    def test_consumer_run_accepts_port_option(self) -> None:
        result = runner.invoke(app, ["consumer", "run", "--help"])

        assert result.exit_code == 0
        assert "--port" in result.stdout

    def test_consumer_run_accepts_password_option(self) -> None:
        result = runner.invoke(app, ["consumer", "run", "--help"])

        assert result.exit_code == 0
        assert "--password" in result.stdout

    def test_consumer_run_accepts_app_option(self) -> None:
        result = runner.invoke(app, ["consumer", "run", "--help"])

        assert result.exit_code == 0
        assert "--app" in result.stdout

    def test_consumer_run_accepts_loglevel_option(self) -> None:
        result = runner.invoke(app, ["consumer", "run", "--help"])

        assert result.exit_code == 0
        assert "--loglevel" in result.stdout

    def test_consumer_dev_has_same_options_as_run(self) -> None:
        run_result = runner.invoke(app, ["consumer", "run", "--help"])
        dev_result = runner.invoke(app, ["consumer", "dev", "--help"])

        assert run_result.exit_code == 0
        assert dev_result.exit_code == 0

        assert "--host" in dev_result.stdout
        assert "--port" in dev_result.stdout
        assert "--password" in dev_result.stdout
        assert "--app" in dev_result.stdout
        assert "--loglevel" in dev_result.stdout


class TestOutboundCommands:

    def test_outbound_run_requires_path_argument(self) -> None:
        result = runner.invoke(app, ["outbound", "run"])

        assert result.exit_code != 0
        assert "Missing argument" in result.stdout or "Error" in result.stdout

    def test_outbound_dev_requires_path_argument(self) -> None:
        result = runner.invoke(app, ["outbound", "dev"])

        assert result.exit_code != 0
        assert "Missing argument" in result.stdout or "Error" in result.stdout

    def test_outbound_run_accepts_host_option(self) -> None:
        result = runner.invoke(app, ["outbound", "run", "--help"])

        assert result.exit_code == 0
        assert "--host" in result.stdout

    def test_outbound_run_accepts_port_option(self) -> None:
        result = runner.invoke(app, ["outbound", "run", "--help"])

        assert result.exit_code == 0
        assert "--port" in result.stdout

    def test_outbound_run_accepts_app_option(self) -> None:
        result = runner.invoke(app, ["outbound", "run", "--help"])

        assert result.exit_code == 0
        assert "--app" in result.stdout

    def test_outbound_run_accepts_loglevel_option(self) -> None:
        result = runner.invoke(app, ["outbound", "run", "--help"])

        assert result.exit_code == 0
        assert "--loglevel" in result.stdout

    def test_outbound_dev_has_same_options_as_run(self) -> None:
        run_result = runner.invoke(app, ["outbound", "run", "--help"])
        dev_result = runner.invoke(app, ["outbound", "dev", "--help"])

        assert run_result.exit_code == 0
        assert dev_result.exit_code == 0

        assert "--host" in dev_result.stdout
        assert "--port" in dev_result.stdout
        assert "--app" in dev_result.stdout
        assert "--loglevel" in dev_result.stdout


class TestCLIHelp:

    def test_main_help_shows_consumer_command(self) -> None:
        result = runner.invoke(app, ["--help"])

        assert result.exit_code == 0
        assert "consumer" in result.stdout

    def test_main_help_shows_outbound_command(self) -> None:
        result = runner.invoke(app, ["--help"])

        assert result.exit_code == 0
        assert "outbound" in result.stdout

    def test_consumer_help_shows_run_command(self) -> None:
        result = runner.invoke(app, ["consumer", "--help"])

        assert result.exit_code == 0
        assert "run" in result.stdout

    def test_consumer_help_shows_dev_command(self) -> None:
        result = runner.invoke(app, ["consumer", "--help"])

        assert result.exit_code == 0
        assert "dev" in result.stdout

    def test_outbound_help_shows_run_command(self) -> None:
        result = runner.invoke(app, ["outbound", "--help"])

        assert result.exit_code == 0
        assert "run" in result.stdout

    def test_outbound_help_shows_dev_command(self) -> None:
        result = runner.invoke(app, ["outbound", "--help"])

        assert result.exit_code == 0
        assert "dev" in result.stdout


class TestCLIExceptions:

    def test_consumer_with_nonexistent_file(self) -> None:
        result = runner.invoke(app, ["consumer", "run", "/nonexistent/path/to/app.py"])

        assert result.exit_code != 0

    def test_outbound_with_nonexistent_file(self) -> None:
        result = runner.invoke(app, ["outbound", "run", "/nonexistent/path/to/app.py"])

        assert result.exit_code != 0


class TestDiscoverModule:

    def test_get_import_string_with_nonexistent_path(self) -> None:
        with pytest.raises(CLIExcpetion, match="does not exist"):
            get_import_string(Consumer, Path("/nonexistent/path.py"))

    def test_get_import_string_requires_path(self) -> None:
        with pytest.raises(CLIExcpetion, match="path.*is required"):
            get_import_string(Consumer, None)

    def test_get_app_name_with_valid_consumer(self, tmp_path: Path) -> None:
        app_file = tmp_path / "test_app.py"
        app_file.write_text("from genesis.consumer import Consumer\napp = Consumer()")

        import sys

        sys.path.insert(0, str(tmp_path))

        try:
            app_name = get_app_name(Consumer, "test_app")
            assert app_name == "app"
        finally:
            sys.path.remove(str(tmp_path))

    def test_get_app_name_with_custom_name(self, tmp_path: Path) -> None:
        app_file = tmp_path / "custom.py"
        app_file.write_text(
            "from genesis.consumer import Consumer\nmy_app = Consumer()"
        )

        import sys

        sys.path.insert(0, str(tmp_path))

        try:
            app_name = get_app_name(Consumer, "custom", app_name="my_app")
            assert app_name == "my_app"
        finally:
            sys.path.remove(str(tmp_path))

    def test_get_app_name_with_nonexistent_app_name(self, tmp_path: Path) -> None:
        app_file = tmp_path / "test.py"
        app_file.write_text("from genesis.consumer import Consumer\napp = Consumer()")

        import sys

        sys.path.insert(0, str(tmp_path))

        try:
            with pytest.raises(CLIExcpetion, match="Could not find app name"):
                get_app_name(Consumer, "test", app_name="nonexistent")
        finally:
            sys.path.remove(str(tmp_path))

    def test_get_app_name_with_wrong_type(self, tmp_path: Path) -> None:
        app_file = tmp_path / "wrong.py"
        app_file.write_text("app = 'not a consumer'")

        import sys

        sys.path.insert(0, str(tmp_path))

        try:
            with pytest.raises(CLIExcpetion, match="doesn't seem to be"):
                get_app_name(Consumer, "wrong", app_name="app")
        finally:
            sys.path.remove(str(tmp_path))

    def test_get_app_name_no_consumer_found(self, tmp_path: Path) -> None:
        app_file = tmp_path / "empty.py"
        app_file.write_text("x = 1")

        import sys

        sys.path.insert(0, str(tmp_path))

        try:
            with pytest.raises(CLIExcpetion, match="Could not find.*try using --app"):
                get_app_name(Consumer, "empty")
        finally:
            sys.path.remove(str(tmp_path))

    def test_get_app_name_import_error(self) -> None:
        with pytest.raises(CLIExcpetion, match="__init__.py"):
            get_app_name(Consumer, "nonexistent_module_xyz")


class TestUtilsModule:

    def test_complete_log_levels_with_empty_string(self) -> None:
        levels = list(complete_log_levels(""))

        assert "debug" in levels
        assert "info" in levels
        assert "warning" in levels
        assert "error" in levels
        assert "critical" in levels

    def test_complete_log_levels_with_prefix(self) -> None:
        levels = list(complete_log_levels("de"))

        assert "debug" in levels
        assert "info" not in levels
        assert "error" not in levels

    def test_complete_log_levels_with_full_match(self) -> None:
        levels = list(complete_log_levels("info"))

        assert "info" in levels
        assert len(levels) == 1

    def test_complete_log_levels_with_no_match(self) -> None:
        levels = list(complete_log_levels("xyz"))

        assert len(levels) == 0

    def test_complete_log_levels_case_sensitive(self) -> None:
        levels = list(complete_log_levels("IN"))

        assert len(levels) == 0
