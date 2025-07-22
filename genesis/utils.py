# genesis/utils.py
"""
Utility Functions
-----------------

This module provides miscellaneous utility functions for the Genesis library.
"""
from typing import Dict, Any

def build_variable_string(variables: Dict[str, Any]) -> str:
    """
    Build a FreeSWITCH variable string from a dictionary.

    Args:
        variables: Dictionary of FreeSWITCH variables and their values

    Returns:
        str: Formatted variable string in FreeSWITCH format

    Examples:
        >>> build_variable_string({'ignore_early_media': True})
        '{ignore_early_media=true}'

        >>> build_variable_string({'ignore_early_media': False})
        '{ignore_early_media=false}'

        >>> build_variable_string({'ringback': "'%(2000,4000,440.0,480.0)'"})
        "{ringback='%(2000,4000,440.0,480.0)'}"

        >>> build_variable_string({'caller_id_name': "John Doe"})
        "{caller_id_name='John Doe'}"

        >>> build_variable_string({'absolute_codec_string': 'PCMA,PCMU'})
        "{absolute_codec_string='PCMA,PCMU'}"

        >>> build_variable_string({'my_custom_var': 123})
        '{my_custom_var=123}'
    """
    if not variables:
        return ""

    def format_value(value: Any) -> str:
        if isinstance(value, bool):
            return str(value).lower()

        value_str = str(value)

        # Numbers should not be quoted
        if isinstance(value, (int, float)):
             return value_str

        # Check if it looks like a pre-quoted string for complex values like ringback
        # or if it contains characters that might require quoting (like spaces, commas if not part of a list)
        # A simple heuristic: if it contains spaces or is already quoted, use as-is or ensure quotes.
        # FreeSWITCH is generally flexible, but explicit quoting for non-numeric strings is safer.
        if (value_str.startswith("'") and value_str.endswith("'")) or \
           (value_str.startswith('"') and value_str.endswith('"')):
            return value_str

        # For other strings, wrap in single quotes.
        return f"'{value_str}'"

    var_pairs = [f"{key}={format_value(value)}" for key, value in variables.items()]
    return "{" + ",".join(var_pairs) + "}"
