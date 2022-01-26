import pytest

from genesis import filtrate


def test_filtrate_is_a_callable():
    """Verify if 'filtrate' is a callable."""
    assert callable(filtrate)


def test_filtrate_require_a_single_argument():
    """Verify if 'filtrate' is a callable."""
    msg = "filtrate() missing 1 required positional argument: 'key'"
    with pytest.raises(TypeError) as exc:
        filtrate()  # pylint: disable=no-value-for-parameter
        assert msg in str(exc)
