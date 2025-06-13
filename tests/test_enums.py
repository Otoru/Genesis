import pytest

from genesis.enums import ChannelState, CallState


class TestChannelState:
    def test_channel_state_values(self):
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

    def test_channel_state_names(self):
        assert ChannelState.NEW.name == "NEW"
        assert ChannelState.EXECUTE.name == "EXECUTE"
        assert ChannelState.HANGUP.name == "HANGUP"

    def test_channel_state_from_int(self):
        assert ChannelState(4) == ChannelState.EXECUTE
        assert ChannelState(10) == ChannelState.HANGUP

    def test_channel_state_invalid_value(self):
        with pytest.raises(ValueError):
            ChannelState(99)


class TestCallState:
    def test_call_state_values(self):
        assert CallState.DOWN == 0
        assert CallState.DIALING.value > 0
        assert CallState.RINGING.value > 0
        assert CallState.ACTIVE.value > 0

    def test_call_state_names(self):
        assert CallState.DOWN.name == "DOWN"
        assert CallState.ACTIVE.name == "ACTIVE"
        assert CallState.HANGUP.name == "HANGUP"

    def test_call_state_auto_increment(self):
        # Test that auto() creates unique values
        states = [CallState.DIALING, CallState.RINGING, CallState.EARLY, CallState.ACTIVE]
        values = [state.value for state in states]
        assert len(set(values)) == len(values)  # All values should be unique

    def test_call_state_from_name(self):
        assert CallState["DOWN"] == CallState.DOWN
        assert CallState["ACTIVE"] == CallState.ACTIVE

    def test_call_state_invalid_name(self):
        with pytest.raises(KeyError):
            CallState["INVALID_STATE"]
