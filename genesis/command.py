"""
Command Result Handling
----------------------

This module provides classes for handling command execution results in FreeSWITCH.
"""

from __future__ import annotations

import asyncio
from typing import Optional, TYPE_CHECKING, Any

from .events import ESLEvent
from .logger import logger

if TYPE_CHECKING:
    from .channel import Channel

class CommandResult:
    """
    Represents the result of a FreeSWITCH command execution.
    
    This class provides a consistent interface for both blocking and non-blocking
    command executions. For blocking calls, the result is immediately available.
    For non-blocking calls, the result can be awaited or checked later.
    """
    
    def __init__(
        self, 
        initial_event: ESLEvent, 
        app_uuid: Optional[str] = None, 
        channel_uuid: Optional[str] = None,
        channel: Optional['Channel'] = None,
        command: str = "",
        application: str = "",
        data: Optional[str] = None
    ):
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
        self.initial_event = initial_event
        self.app_uuid = app_uuid
        self.channel_uuid = channel_uuid
        self.channel = channel
        self.command = command
        self.application = application
        self.data = data
        self.complete_event: Optional[ESLEvent] = None
        self.exception: Optional[Exception] = None
        self._complete = asyncio.Event()
        self._handler_registered = False
        
        # If the initial event is already a CHANNEL_EXECUTE_COMPLETE, mark as complete
        if initial_event.get("Event-Name") == "CHANNEL_EXECUTE_COMPLETE" and \
           app_uuid and initial_event.get("Application-UUID") == app_uuid:
            self.complete_event = initial_event
            self._complete.set()
            logger.debug(f"CommandResult initialized with already completed event for app {application}")
        
        # If we have a channel and app_uuid, register for completion events
        if channel and app_uuid and command == "execute" and not self.is_completed:
            self._register_completion_handler()
    
    def _register_completion_handler(self) -> None:
        """Register a handler to listen for command completion events."""
        if self._handler_registered or not self.channel or not self.app_uuid:
            return
        
        self._handler_registered = True
        
        # Define the handler function
        async def completion_handler(channel, event):
            if event.get("Event-Name") == "CHANNEL_EXECUTE_COMPLETE" and \
               event.get("Application-UUID") == self.app_uuid:
                logger.debug(f"CommandResult received completion event for app_uuid={self.app_uuid}")
                self.set_complete(event)
                # Remove the handler to avoid memory leaks
                if self.channel:
                    self.channel.remove("CHANNEL_EXECUTE_COMPLETE", completion_handler)
        
        # Register the handler with the channel
        logger.debug(f"CommandResult registering completion handler for app_uuid={self.app_uuid}")
        self.channel.on("CHANNEL_EXECUTE_COMPLETE", completion_handler)
    
    @property
    def is_completed(self) -> bool:
        """Returns True if the command execution has completed."""
        return self._complete.is_set()
    
    @property
    def is_successful(self) -> bool:
        """
        Returns True if the command completed successfully.
        Raises ValueError if the command hasn't completed yet.
        """
        if not self.is_completed:
            raise ValueError("Command execution hasn't completed yet")
        return self.exception is None
    
    @property
    def response(self) -> Optional[str]:
        """
        Returns the Application-Response value from the complete event, if available.
        Returns None if the command hasn't completed or doesn't have a response.
        """
        if not self.is_completed or not self.complete_event:
            return None
        return self.complete_event.get("Application-Response")
    
    def set_complete(self, event: ESLEvent) -> None:
        """Mark the command as complete with the given event."""
        self.complete_event = event
        self._complete.set()
        logger.debug(
            f"Command {self.command} {self.application} {self.data} completed with "
            f"response: {event.get('Application-Response', 'N/A')}"
        )
    
    def set_exception(self, exception: Exception) -> None:
        """Mark the command as failed with the given exception."""
        self.exception = exception
        self._complete.set()
        logger.debug(
            f"Command {self.command} {self.application} {self.data} failed with exception: {exception}"
        )
    
    def __bool__(self) -> bool:
        """
        Allow CommandResult to be directly used in boolean contexts.
        
        Returns:
            True if the command is completed, False otherwise.
        """
        return self._complete.is_set()
    
    async def wait(self) -> 'CommandResult':
        """
        Wait for the command to complete.
        
        Returns:
            Self, for method chaining
            
        Raises:
            The stored exception if the command failed
        """
        # If we have a channel and app_uuid but haven't registered a handler yet, do it now
        if not self._handler_registered and self.channel and self.app_uuid and \
           self.command == "execute" and not self.is_completed:
            self._register_completion_handler()
            
        await self._complete.wait()
        if self.exception:
            raise self.exception
        return self
    
    def __await__(self):
        """Make the object awaitable directly."""
        return self.wait().__await__()
