import pytest

from genesis.events import (
    ESLEvent, HeartbeatEvent, CustomEvent, ChannelCreateEvent,
    ChannelAnswerEvent, ChannelHangupEvent, ChannelDestroyEvent,
    ChannelExecuteEvent, ChannelExecuteCompleteEvent, ChannelBridgeEvent,
    ChannelUnbridgeEvent, ConferenceDataEvent, ConferenceEventEvent,
    ConferenceRecordEvent, ModuleUnloadEvent, ChannelHangupCompleteEvent,
    BackgroundJobEvent, ApiEvent, MessageEvent, PresenceInEvent, NotifyEvent
)


class TestESLEvent:
    def test_esl_event_creation(self):
        event = ESLEvent({"Event-Name": "TEST", "Unique-ID": "123"})
        assert event["Event-Name"] == "TEST"
        assert event["Unique-ID"] == "123"
        assert event.body is None

    def test_esl_event_with_body(self):
        event = ESLEvent({"Event-Name": "TEST"})
        event.body = "Test body content"
        assert event.body == "Test body content"

    def test_esl_event_dict_behavior(self):
        event = ESLEvent()
        event["test-key"] = "test-value"
        assert event["test-key"] == "test-value"
        assert "test-key" in event
        assert len(event) == 1

    def test_esl_event_get_method(self):
        event = ESLEvent({"existing": "value"})
        assert event.get("existing") == "value"
        assert event.get("missing") is None
        assert event.get("missing", "default") == "default"

    def test_esl_event_update(self):
        event = ESLEvent({"key1": "value1"})
        event.update({"key2": "value2", "key1": "updated"})
        assert event["key1"] == "updated"
        assert event["key2"] == "value2"

    def test_esl_event_items(self):
        event = ESLEvent({"key1": "value1", "key2": "value2"})
        items = list(event.items())
        assert ("key1", "value1") in items
        assert ("key2", "value2") in items

    def test_esl_event_keys(self):
        event = ESLEvent({"key1": "value1", "key2": "value2"})
        keys = list(event.keys())
        assert "key1" in keys
        assert "key2" in keys

    def test_esl_event_values(self):
        event = ESLEvent({"key1": "value1", "key2": "value2"})
        values = list(event.values())
        assert "value1" in values
        assert "value2" in values


class TestSpecificEventClasses:
    def test_heartbeat_event(self):
        event = HeartbeatEvent({"Event-Name": "HEARTBEAT"})
        assert isinstance(event, ESLEvent)
        assert event["Event-Name"] == "HEARTBEAT"

    def test_custom_event(self):
        event = CustomEvent({
            "Event-Name": "CUSTOM",
            "Event-Subclass": "test::event"
        })
        assert isinstance(event, ESLEvent)
        assert event["Event-Subclass"] == "test::event"

    def test_channel_create_event(self):
        event = ChannelCreateEvent({
            "Event-Name": "CHANNEL_CREATE",
            "Unique-ID": "test-uuid"
        })
        assert isinstance(event, ESLEvent)
        assert event["Unique-ID"] == "test-uuid"

    def test_channel_answer_event(self):
        event = ChannelAnswerEvent({"Event-Name": "CHANNEL_ANSWER"})
        assert isinstance(event, ESLEvent)

    def test_channel_hangup_event(self):
        event = ChannelHangupEvent({"Event-Name": "CHANNEL_HANGUP"})
        assert isinstance(event, ESLEvent)

    def test_channel_destroy_event(self):
        event = ChannelDestroyEvent({"Event-Name": "CHANNEL_DESTROY"})
        assert isinstance(event, ESLEvent)

    def test_channel_execute_event(self):
        event = ChannelExecuteEvent({
            "Event-Name": "CHANNEL_EXECUTE",
            "Application": "playback"
        })
        assert isinstance(event, ESLEvent)
        assert event["Application"] == "playback"

    def test_channel_execute_complete_event(self):
        event = ChannelExecuteCompleteEvent({
            "Event-Name": "CHANNEL_EXECUTE_COMPLETE",
            "Application": "playback",
            "Application-Response": "SUCCESS"
        })
        assert isinstance(event, ESLEvent)
        assert event["Application-Response"] == "SUCCESS"

    def test_channel_bridge_event(self):
        event = ChannelBridgeEvent({"Event-Name": "CHANNEL_BRIDGE"})
        assert isinstance(event, ESLEvent)

    def test_channel_unbridge_event(self):
        event = ChannelUnbridgeEvent({"Event-Name": "CHANNEL_UNBRIDGE"})
        assert isinstance(event, ESLEvent)

    def test_conference_data_event(self):
        event = ConferenceDataEvent({"Event-Name": "CONFERENCE_DATA"})
        assert isinstance(event, ESLEvent)

    def test_conference_event_event(self):
        event = ConferenceEventEvent({
            "Event-Name": "CONFERENCE_EVENT",
            "Action": "add-member"
        })
        assert isinstance(event, ESLEvent)
        assert event["Action"] == "add-member"

    def test_conference_record_event(self):
        event = ConferenceRecordEvent({"Event-Name": "CONFERENCE_RECORD"})
        assert isinstance(event, ESLEvent)

    def test_module_unload_event(self):
        event = ModuleUnloadEvent({"Event-Name": "MODULE_UNLOAD"})
        assert isinstance(event, ESLEvent)

    def test_channel_hangup_complete_event(self):
        event = ChannelHangupCompleteEvent({"Event-Name": "CHANNEL_HANGUP_COMPLETE"})
        assert isinstance(event, ESLEvent)

    def test_background_job_event(self):
        event = BackgroundJobEvent({
            "Event-Name": "BACKGROUND_JOB",
            "Job-UUID": "job-123"
        })
        assert isinstance(event, ESLEvent)
        assert event["Job-UUID"] == "job-123"

    def test_api_event(self):
        event = ApiEvent({"Event-Name": "API"})
        assert isinstance(event, ESLEvent)

    def test_message_event(self):
        event = MessageEvent({"Event-Name": "MESSAGE"})
        assert isinstance(event, ESLEvent)

    def test_presence_in_event(self):
        event = PresenceInEvent({"Event-Name": "PRESENCE_IN"})
        assert isinstance(event, ESLEvent)

    def test_notify_event(self):
        event = NotifyEvent({"Event-Name": "NOTIFY"})
        assert isinstance(event, ESLEvent)

    def test_event_inheritance_chain(self):
        # Test that all specific events inherit from ESLEvent
        events = [
            HeartbeatEvent(), CustomEvent(), ChannelCreateEvent(),
            ChannelAnswerEvent(), ChannelHangupEvent(), ChannelDestroyEvent(),
            ChannelExecuteEvent(), ChannelExecuteCompleteEvent(),
            ChannelBridgeEvent(), ChannelUnbridgeEvent(),
            ConferenceDataEvent(), ConferenceEventEvent(), ConferenceRecordEvent(),
            ModuleUnloadEvent(), ChannelHangupCompleteEvent(),
            BackgroundJobEvent(), ApiEvent(), MessageEvent(),
            PresenceInEvent(), NotifyEvent()
        ]
        
        for event in events:
            assert isinstance(event, ESLEvent)
            assert hasattr(event, 'body')
