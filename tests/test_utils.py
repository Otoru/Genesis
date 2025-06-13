import pytest

from genesis.utils import build_variable_string


class TestBuildVariableString:
    def test_empty_variables(self):
        result = build_variable_string({})
        assert result == ""

    def test_boolean_variables(self):
        result = build_variable_string({'ignore_early_media': True})
        assert result == "{ignore_early_media=true}"
        
        result = build_variable_string({'ignore_early_media': False})
        assert result == "{ignore_early_media=false}"

    def test_string_variables(self):
        result = build_variable_string({'caller_id_name': "John Doe"})
        assert result == "{caller_id_name='John Doe'}"

    def test_numeric_variables(self):
        result = build_variable_string({'timeout': 30})
        assert result == "{timeout=30}"
        
        result = build_variable_string({'volume': 1.5})
        assert result == "{volume=1.5}"

    def test_pre_quoted_variables(self):
        result = build_variable_string({'ringback': "'%(2000,4000,440.0,480.0)'"})
        assert result == "{ringback='%(2000,4000,440.0,480.0)'}"

    def test_multiple_variables(self):
        variables = {
            'caller_id_name': 'John Doe',
            'timeout': 30,
            'ignore_early_media': True
        }
        result = build_variable_string(variables)
        
        # Order might vary, so check that all parts are present
        assert result.startswith("{")
        assert result.endswith("}")
        assert "caller_id_name='John Doe'" in result
        assert "timeout=30" in result
        assert "ignore_early_media=true" in result
        assert result.count(",") == 2  # Two commas for three variables

    def test_complex_string_values(self):
        result = build_variable_string({'absolute_codec_string': 'PCMA,PCMU'})
        assert result == "{absolute_codec_string='PCMA,PCMU'}"

    def test_double_quoted_strings(self):
        result = build_variable_string({'test_var': '"already quoted"'})
        assert result == '{test_var="already quoted"}'

    def test_single_quoted_strings(self):
        result = build_variable_string({'test_var': "'already quoted'"})
        assert result == "{test_var='already quoted'}"

    def test_zero_values(self):
        result = build_variable_string({'zero_int': 0, 'zero_float': 0.0})
        assert "zero_int=0" in result
        assert "zero_float=0.0" in result

    def test_none_values_converted_to_string(self):
        result = build_variable_string({'none_value': None})
        assert result == "{none_value='None'}"

    def test_special_characters_in_strings(self):
        result = build_variable_string({'special': 'test@domain.com'})
        assert result == "{special='test@domain.com'}"
