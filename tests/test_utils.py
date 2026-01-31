"""
Tests for the utils module.
"""

import pytest

from genesis.utils import build_variable_string


class TestBuildVariableString:
    """Tests for build_variable_string function."""

    def test_empty_dict_returns_empty_string(self) -> None:
        """Test that an empty dictionary returns an empty string."""
        assert build_variable_string({}) == ""

    def test_single_boolean_true(self) -> None:
        """Test that boolean True is converted to lowercase 'true'."""
        result = build_variable_string({"ignore_early_media": True})
        assert result == "{ignore_early_media=true}"

    def test_single_boolean_false(self) -> None:
        """Test that boolean False is converted to lowercase 'false'."""
        result = build_variable_string({"ignore_early_media": False})
        assert result == "{ignore_early_media=false}"

    def test_integer_value(self) -> None:
        """Test that integers are not quoted."""
        result = build_variable_string({"my_custom_var": 123})
        assert result == "{my_custom_var=123}"

    def test_float_value(self) -> None:
        """Test that floats are not quoted."""
        result = build_variable_string({"timeout": 30.5})
        assert result == "{timeout=30.5}"

    def test_string_value_gets_quoted(self) -> None:
        """Test that string values are wrapped in single quotes."""
        result = build_variable_string({"caller_id_name": "John Doe"})
        assert result == "{caller_id_name='John Doe'}"

    def test_pre_quoted_single_quotes(self) -> None:
        """Test that pre-quoted strings with single quotes are kept as-is."""
        result = build_variable_string({"ringback": "'%(2000,4000,440.0,480.0)'"})
        assert result == "{ringback='%(2000,4000,440.0,480.0)'}"

    def test_pre_quoted_double_quotes(self) -> None:
        """Test that pre-quoted strings with double quotes are kept as-is."""
        result = build_variable_string({"custom": '"already quoted"'})
        assert result == '{custom="already quoted"}'

    def test_codec_string(self) -> None:
        """Test a typical codec string."""
        result = build_variable_string({"absolute_codec_string": "PCMA,PCMU"})
        assert result == "{absolute_codec_string='PCMA,PCMU'}"

    def test_multiple_variables(self) -> None:
        """Test multiple variables in one call."""
        result = build_variable_string(
            {
                "ignore_early_media": True,
                "timeout": 30,
                "caller_id_name": "Test",
            }
        )
        # Check that all parts are present (order may vary)
        assert result.startswith("{")
        assert result.endswith("}")
        assert "ignore_early_media=true" in result
        assert "timeout=30" in result
        assert "caller_id_name='Test'" in result

    def test_none_dict_handling(self) -> None:
        """Test that None values are converted to string 'None' and quoted."""
        result = build_variable_string({"empty_var": None})
        assert result == "{empty_var='None'}"

    def test_special_characters_in_key(self) -> None:
        """Test that keys with underscores work correctly."""
        result = build_variable_string({"my_special_var_name": "value"})
        assert result == "{my_special_var_name='value'}"
