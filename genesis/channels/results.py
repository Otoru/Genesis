"""
Result Handling for Asynchronous Operations
-------------------------------------------

This module provides classes for handling results from both blocking and
non-blocking FreeSWITCH operations. It introduces a common base class
for awaitable results to reduce code duplication.
"""

from __future__ import annotations

import asyncio
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Coroutine,
    Mapping,
    MutableMapping,
    Optional,
    Union,
)

from genesis.logger import logger

if TYPE_CHECKING:
    pass  # Future: Channel type hint


class AwaitableResult:
    """
    Base class for awaitable results from FreeSWITCH operations.

    This class provides the core boilerplate for creating future-like objects
    that can be awaited until a corresponding event from FreeSWITCH signals
    their completion or failure.
    """

    def __init__(self) -> None:
        self.completion_event: Optional[Mapping[str, Any]] = None
        self.exception: Optional[Exception] = None
        self._complete: asyncio.Event = asyncio.Event()

    @property
    def is_completed(self) -> bool:
        """Returns True if the operation has completed."""
        return self._complete.is_set()

    @property
    def is_successful(self) -> bool:
        """
        Returns True if the operation completed successfully.
        Raises ValueError if the operation hasn't completed yet.
        """
        if not self.is_completed:
            raise ValueError("Operation has not completed yet")
        return self.exception is None

    @property
    def response(self) -> Optional[str]:
        """
        Returns the response from the completed operation.
        Must be implemented by subclasses.
        """
        raise NotImplementedError

    def set_complete(self, event: Mapping[str, Any]) -> None:
        """Mark the operation as complete with the given event."""
        self.completion_event = event
        self._complete.set()

    def set_exception(self, exception: Exception) -> None:
        """Mark the operation as failed with the given exception."""
        self.exception = exception
        self._complete.set()

    async def wait(self) -> "AwaitableResult":
        """
        Wait for the operation to complete.

        Returns:
            Self, for method chaining

        Raises:
            The stored exception if the operation failed
        """
        await self._complete.wait()
        if self.exception:
            raise self.exception
        return self

    def __await__(self) -> Any:
        """Make the object awaitable directly."""
        return self.wait().__await__()

    def __bool__(self) -> bool:
        """
        Allow result object to be directly used in boolean contexts.

        Returns:
            True if the operation is completed, False otherwise.
        """
        return self._complete.is_set()


class CommandResult(AwaitableResult):
    """
    Represents the result of a FreeSWITCH command execution (e.g., 'execute').

    This class provides a consistent interface for both blocking and non-blocking
    command executions. For blocking calls, the result is immediately available.
    For non-blocking calls, the result can be awaited or checked later.
    """

    def __init__(
        self,
        initial_event: Mapping[str, Any],
        app_uuid: Optional[str] = None,
        channel_uuid: Optional[str] = None,
        channel: Optional[Any] = None,
        command: str = "",
        application: str = "",
        data: Optional[str] = None,
    ) -> None:
        """
        Initialize a new command result.

        Args:
            initial_event: The initial event received when the command was sent
            app_uuid: The Application-UUID for tracking the command execution
            channel_uuid: The channel UUID this command is operating on
            channel: The channel object this command is operating on
            command: The command type (e.g., "execute", "hangup")
            application: The application name (e.g., "playback", "bridge")
            data: The application data/arguments
        """
        super().__init__()
        self.initial_event: Mapping[str, Any] = initial_event
        self.app_uuid = app_uuid
        self.channel_uuid = channel_uuid
        self.channel = channel
        self.command = command
        self.application = application
        self.data = data
        self._handler_registered = False

        # If the initial event is already a CHANNEL_EXECUTE_COMPLETE, mark as complete
        if (
            initial_event.get("Event-Name") == "CHANNEL_EXECUTE_COMPLETE"
            and app_uuid
            and initial_event.get("Application-UUID") == app_uuid
        ):
            self.set_complete(initial_event)
            logger.debug(
                f"CommandResult initialized with already completed event for app {application}"
            )

        # If we have a channel and app_uuid, register for completion events
        if channel and app_uuid and command == "execute" and not self.is_completed:
            self._register_completion_handler()

    @property
    def is_successful(self) -> bool:
        """
        Returns True if the operation completed successfully.

        A command is successful if it completes without an exception and
        the reply from FreeSWITCH indicates success (+OK or a non-error application response).

        Raises:
            ValueError: If the operation has not completed yet.
        """
        if not self.is_completed:
            raise ValueError("Operation has not completed yet")

        if self.exception is not None:
            return False

        # If there's no completion event, we can't determine success from the response.
        # Rely on the absence of an exception.
        if not self.completion_event:
            return True

        # For 'execute' commands, check the final application response
        if self.command == "execute":
            app_response = self.completion_event.get("Application-Response")
            # Many successful apps don't have a response. Failure is often indicated by "-ERR".
            if app_response and str(app_response).startswith("-ERR"):
                return False
            return True  # Assume success if no error response and no exception

        # For other commands (like hangup, etc.), check the reply text of the completion event
        reply_text = self.completion_event.get("Reply-Text", "")
        return str(reply_text).startswith("+OK")

    def _register_completion_handler(self) -> None:
        """Register a handler to listen for command completion events."""
        if self._handler_registered or not self.channel or not self.app_uuid:
            return

        self._handler_registered = True

        # Define the handler function
        async def completion_handler(channel: Any, event: Mapping[str, Any]) -> None:
            if (
                event.get("Event-Name") == "CHANNEL_EXECUTE_COMPLETE"
                and event.get("Application-UUID") == self.app_uuid
            ):
                logger.debug(
                    f"CommandResult received completion event for app_uuid={self.app_uuid}"
                )
                self.set_complete(event)
                # Remove the handler to avoid memory leaks
                if self.channel:
                    self.channel.remove("CHANNEL_EXECUTE_COMPLETE", completion_handler)

        # Register the handler with the channel
        logger.debug(
            f"CommandResult registering completion handler for app_uuid={self.app_uuid}"
        )
        self.channel.on("CHANNEL_EXECUTE_COMPLETE", completion_handler)

    @property
    def response(self) -> Optional[str]:
        """
        Returns the response from the completed command.

        For bgapi commands, this returns the body of the BACKGROUND_JOB event.
        For execute commands, this returns the Application-Response value.
        Returns None if the command hasn't completed.
        """
        if not self.is_completed or self.completion_event is None:
            return None

        if self.command == "bgapi":
            # For background jobs, the response is in the body
            return getattr(self.completion_event, "body", None)
        else:
            # For execute commands, use Application-Response
            app_response = self.completion_event.get("Application-Response")
            return str(app_response) if app_response is not None else None

    def set_complete(self, event: Mapping[str, Any]) -> None:
        """Mark the command as complete with the given event."""
        super().set_complete(event)
        logger.debug(
            f"Command {self.command} {self.application} {self.data} completed with "
            f"response: {event.get('Application-Response', 'N/A')}"
        )

    def set_exception(self, exception: Exception) -> None:
        """Mark the command as failed with the given exception."""
        super().set_exception(exception)
        logger.debug(
            f"Command {self.command} {self.application} {self.data} failed with exception: {exception}"
        )

    async def wait(self) -> "CommandResult":
        """
        Wait for the command to complete.

        Returns:
            Self, for method chaining

        Raises:
            The stored exception if the command failed
        """
        # If we have a channel and app_uuid but haven't registered a handler yet, do it now
        if (
            not self._handler_registered
            and self.channel
            and self.app_uuid
            and self.command == "execute"
            and not self.is_completed
        ):
            self._register_completion_handler()

        await super().wait()
        return self


class BackgroundJobResult(AwaitableResult):
    """
    Represents the result of a background job execution.

    This is a simpler alternative to CommandResult specifically for background jobs.
    """

    def __init__(self, job_uuid: str, command: str) -> None:
        """
        Initialize a new background job result.

        Args:
            job_uuid: The Job-UUID for tracking the job
            command: The command that was executed
        """
        super().__init__()
        self.job_uuid = job_uuid
        self.command = command

    @property
    def response(self) -> Optional[str]:
        """
        Returns the response body from the completed background job.
        Returns None if the job hasn't completed.
        """
        if not self.is_completed or self.completion_event is None:
            return None
        # Try attribute access first (for ESLEvent-like objects with body attribute)
        # then fall back to dict access
        body = None
        if hasattr(self.completion_event, "body"):
            body = getattr(self.completion_event, "body", None)
        elif (
            isinstance(self.completion_event, dict) and "body" in self.completion_event
        ):
            body = self.completion_event["body"]
        return str(body) if body is not None else None

    def set_complete(self, event: Mapping[str, Any]) -> None:
        """Mark the background job as complete with the given event."""
        super().set_complete(event)
        logger.debug(f"Background job {self.job_uuid} completed")

    def set_exception(self, exception: Exception) -> None:
        """Mark the background job as failed with the given exception."""
        super().set_exception(exception)
        logger.debug(
            f"Background job {self.job_uuid} failed with exception: {exception}"
        )

    @property
    def is_successful(self) -> bool:
        """
        Returns True if the operation completed successfully.

        A background job is successful if it completes without an exception
        and its response body starts with "+OK".

        Raises:
            ValueError: If the operation has not completed yet.
        """
        if not self.is_completed:
            raise ValueError("Operation has not completed yet")

        if self.exception is not None:
            return False

        response_body = self.response
        # A successful bgapi command has a body starting with "+OK"
        if response_body and response_body.strip().startswith("+OK"):
            return True

        return False

    async def wait(self) -> "BackgroundJobResult":
        """
        Wait for the background job to complete.

        Returns:
            Self, for method chaining

        Raises:
            The stored exception if the job failed
        """
        await super().wait()
        return self
