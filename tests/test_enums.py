"""
Tests for the enums module.
"""

import pytest

from genesis.enums import CallState, ChannelState


class TestChannelState:
    """Tests for ChannelState enumeration."""

    def test_channel_state_values(self) -> None:
        """Test that ChannelState has the expected values."""
        assert ChannelState.NEW == 0
        assert ChannelState.INIT == 1
        assert ChannelState.ROUTING == 2
        assert ChannelState.SOFT_EXECUTE == 3
        assert ChannelState.EXECUTE == 4
        assert ChannelState.EXCHANGE_MEDIA == 5
        assert ChannelState.PARK == 6
        assert ChannelState.CONSUME_MEDIA == 7
        assert ChannelState.HIBERNATE == 8
        assert ChannelState.RESET == 9
        assert ChannelState.HANGUP == 10
        assert ChannelState.REPORTING == 11
        assert ChannelState.DESTROY == 12
        assert ChannelState.NONE == 13

    def test_channel_state_count(self) -> None:
        """Test that ChannelState has exactly 14 states."""
        assert len(ChannelState) == 14

    def test_channel_state_is_int(self) -> None:
        """Test that ChannelState values are integers."""
        for state in ChannelState:
            assert isinstance(state.value, int)

    def test_channel_state_comparison(self) -> None:
        """Test that ChannelState values can be compared."""
        assert ChannelState.NEW < ChannelState.INIT
        assert ChannelState.HANGUP > ChannelState.EXECUTE
        assert ChannelState.DESTROY >= ChannelState.REPORTING

    def test_channel_state_name(self) -> None:
        """Test that ChannelState has correct names."""
        assert ChannelState.NEW.name == "NEW"
        assert ChannelState.HANGUP.name == "HANGUP"
        assert ChannelState.DESTROY.name == "DESTROY"


class TestCallState:
    """Tests for CallState enumeration."""

    def test_call_state_down_is_zero(self) -> None:
        """Test that DOWN is explicitly 0."""
        assert CallState.DOWN == 0

    def test_call_state_auto_values(self) -> None:
        """Test that auto() generates sequential values after DOWN."""
        assert CallState.DIALING > CallState.DOWN
        assert CallState.RINGING > CallState.DIALING
        assert CallState.EARLY > CallState.RINGING
        assert CallState.ACTIVE > CallState.EARLY

    def test_call_state_count(self) -> None:
        """Test that CallState has exactly 9 states."""
        assert len(CallState) == 9

    def test_call_state_is_int(self) -> None:
        """Test that CallState values are integers."""
        for state in CallState:
            assert isinstance(state.value, int)

    def test_call_state_name(self) -> None:
        """Test that CallState has correct names."""
        assert CallState.DOWN.name == "DOWN"
        assert CallState.ACTIVE.name == "ACTIVE"
        assert CallState.HANGUP.name == "HANGUP"

    def test_call_state_all_members(self) -> None:
        """Test that all expected CallState members exist."""
        expected = [
            "DOWN",
            "DIALING",
            "RINGING",
            "EARLY",
            "ACTIVE",
            "HELD",
            "RING_WAIT",
            "HANGUP",
            "UNHELD",
        ]
        actual = [state.name for state in CallState]
        assert actual == expected
