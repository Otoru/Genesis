from typing import (
    Protocol,
    Any,
    runtime_checkable,
    Literal,
    Dict,
    List,
    Union,
    Awaitable,
    TYPE_CHECKING,
)
from enum import IntEnum
from asyncio import StreamReader, StreamWriter

if TYPE_CHECKING:
    from genesis.outbound import Session


@runtime_checkable
class WatcherProtocol(Protocol):
    def start(self) -> None: ...
    def stop(self) -> None: ...
    def join(self) -> None: ...
    def schedule(
        self, event_handler: Any, path: str, recursive: bool = False
    ) -> Any: ...


class OutboundHandler(Protocol):
    def __call__(self, session: "Session") -> Awaitable[None]: ...


HangupCause = Literal[
    "NONE",
    "UNALLOCATED_NUMBER",
    "NO_ROUTE_TRANSIT_NET",
    "NO_ROUTE_DESTINATION",
    "CHANNEL_UNACCEPTABLE",
    "CALL_AWARDED_DELIVERED",
    "NORMAL_CLEARING",
    "USER_BUSY",
    "NO_USER_RESPONSE",
    "NO_ANSWER",
    "SUBSCRIBER_ABSENT",
    "CALL_REJECTED",
    "NUMBER_CHANGED",
    "REDIRECTION_TO_NEW_DESTINATION",
    "EXCHANGE_ROUTING_ERROR",
    "DESTINATION_OUT_OF_ORDER",
    "INVALID_NUMBER_FORMAT",
    "FACILITY_REJECTED",
    "RESPONSE_TO_STATUS_ENQUIRY",
    "NORMAL_UNSPECIFIED",
    "NORMAL_CIRCUIT_CONGESTION",
    "NETWORK_OUT_OF_ORDER",
    "NORMAL_TEMPORARY_FAILURE",
    "SWITCH_CONGESTION",
    "ACCESS_INFO_DISCARDED",
    "REQUESTED_CHAN_UNAVAIL",
    "PRE_EMPTED",
    "FACILITY_NOT_SUBSCRIBED",
    "OUTGOING_CALL_BARRED",
    "INCOMING_CALL_BARRED",
    "BEARERCAPABILITY_NOTAUTH",
    "BEARERCAPABILITY_NOTAVAIL",
    "SERVICE_UNAVAILABLE",
    "BEARERCAPABILITY_NOTIMPL",
    "CHAN_NOT_IMPLEMENTED",
    "FACILITY_NOT_IMPLEMENTED",
    "SERVICE_NOT_IMPLEMENTED",
    "INVALID_CALL_REFERENCE",
    "INCOMPATIBLE_DESTINATION",
    "INVALID_MSG_UNSPECIFIED",
    "MANDATORY_IE_MISSING",
    "MESSAGE_TYPE_NONEXIST",
    "WRONG_MESSAGE",
    "IE_NONEXIST",
    "INVALID_IE_CONTENTS",
    "WRONG_CALL_STATE",
    "RECOVERY_ON_TIMER_EXPIRE",
    "MANDATORY_IE_LENGTH_ERROR",
    "PROTOCOL_ERROR",
    "INTERWORKING",
    "SUCCESS",
    "ORIGINATOR_CANCEL",
    "CRASH",
    "SYSTEM_SHUTDOWN",
    "LOSE_RACE",
    "MANAGER_REQUEST",
    "BLIND_TRANSFER",
    "ATTENDED_TRANSFER",
    "ALLOTTED_TIMEOUT",
    "USER_CHALLENGE",
    "MEDIA_TIMEOUT",
    "PICKED_OFF",
    "USER_NOT_REGISTERED",
    "PROGRESS_TIMEOUT",
    "INVALID_GATEWAY",
    "GATEWAY_DOWN",
    "INVALID_URL",
    "INVALID_PROFILE",
    "NO_PICKUP",
    "SRTP_READ_ERROR",
    "BOWOUT",
    "BUSY_EVERYWHERE",
    "DECLINE",
    "DOES_NOT_EXIST_ANYWHERE",
    "NOT_ACCEPTABLE",
    "UNWANTED",
    "NO_IDENTITY",
    "BAD_IDENTITY_INFO",
    "UNSUPPORTED_CERTIFICATE",
    "INVALID_IDENTITY",
    "STALE_DATE",
    "REJECT_ALL",
    "SWITCH_CAUSE_REJECT_ALL",
]

ESLHeaderValue = Union[str, List[str]]
ContextType = Dict[str, ESLHeaderValue]


class ChannelState(IntEnum):
    """Ordered channel states matching FreeSWITCH lifecycle progression."""

    NEW = 0
    INIT = 1
    ROUTING = 2
    SOFT_EXECUTE = 3
    EXECUTE = 4
    EXCHANGE_MEDIA = 5
    PARK = 6
    CONSUME_MEDIA = 7
    HIBERNATE = 8
    RESET = 9
    HANGUP = 10
    REPORTING = 11
    DESTROY = 12
    NONE = 13  # Special state, typically not part of normal flow

    @classmethod
    def from_freeswitch(cls, state_str: str) -> "ChannelState":
        """Convert FreeSWITCH state string (e.g., 'CS_EXECUTE') to enum."""
        # Remove 'CS_' prefix if present
        clean_name = (
            state_str.replace("CS_", "") if state_str.startswith("CS_") else state_str
        )
        return cls[clean_name]
