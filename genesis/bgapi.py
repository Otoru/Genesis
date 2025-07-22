"""
Background API Command Handler
-----------------------------

This module provides functionality for executing FreeSWITCH background API commands
that don't block the event loop while waiting for completion.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Optional
from uuid import uuid4

from .events import ESLEvent
from .logger import logger
from .exceptions import UnconnectedError, ConnectionError
from .results import BackgroundJobResult

if TYPE_CHECKING:
    from .protocol import Protocol


class BackgroundAPI:
    """
    Handler for FreeSWITCH background API commands.
    
    This class manages the execution of bgapi commands and tracks their completion
    through BACKGROUND_JOB events.
    """
    
    def __init__(self, protocol: 'Protocol'):
        """
        Initialize the BackgroundAPI handler.
        
        Args:
            protocol: The Protocol instance to use for communication
        """
        self.protocol = protocol
        self._pending_jobs: dict[str, BackgroundJobResult] = {}
        self._handler_registered = False
        
    def _ensure_handler_registered(self) -> None:
        """Ensure the BACKGROUND_JOB event handler is registered."""
        if not self._handler_registered:
            self.protocol.on("BACKGROUND_JOB", self._handle_background_job)
            self._handler_registered = True
            logger.debug("Registered BACKGROUND_JOB event handler")
    
    async def _handle_background_job(self, event: ESLEvent) -> None:
        """Handle BACKGROUND_JOB completion events."""
        job_uuid = event.get("Job-UUID")
        if not job_uuid:
            logger.warning("Received BACKGROUND_JOB event without Job-UUID")
            return
            
        if job_uuid in self._pending_jobs:
            result = self._pending_jobs[job_uuid]
            logger.debug(f"Completing background job {job_uuid}")
            result.set_complete(event)
            self._delete_job(job_uuid)  # Remove from tracking after completion

            # After the job is complete, remove the specific filter for its Job-UUID
            # to keep the list of active filters clean.
            await self.protocol.send(f"filter delete Job-UUID {job_uuid}")
        else:
            logger.debug(f"Received BACKGROUND_JOB for unknown job {job_uuid}")
    
    async def execute(self, cmd: str, job_uuid: Optional[str] = None) -> BackgroundJobResult:
        """
        Execute a background API command.
        
        Args:
            cmd: The API command to execute (without 'bgapi' prefix)
            job_uuid: Optional custom Job-UUID. If not provided, one will be generated
            
        Returns:
            BackgroundJobResult: An object that can be awaited for completion
            
        Raises:
            UnconnectedError: If not connected to FreeSWITCH
            ConnectionError: If the connection is closing
            
        Example:
            bgapi = BackgroundAPI(protocol)
            result = await bgapi.execute("originate sofia/gateway/mygw/1234 &park()")
            # Do other work...
            await result  # Wait for completion
            print(result.response)  # Get the result
        """
        if not self.protocol.is_connected:
            raise UnconnectedError(f"Attempted to send bgapi command '{cmd[:30]}...' but not connected.")

        if self.protocol.writer and self.protocol.writer.is_closing():
            raise ConnectionError(f"Attempted to send bgapi command '{cmd[:30]}...' but writer is closing.")

        self._ensure_handler_registered()
        
        # Generate Job-UUID if not provided
        if job_uuid is None:
            job_uuid = str(uuid4())
        
        logger.debug(f"Executing bgapi command: '{cmd}' with Job-UUID: {job_uuid}")
        
        # Add an event filter for this specific Job-UUID to ensure we receive the BACKGROUND_JOB event
        # even if other filters (like for a specific channel UUID) are active.
        await self.protocol.send(f"filter Job-UUID {job_uuid}")
        
        # Send the bgapi command with custom Job-UUID header
        bgapi_cmd = f"bgapi {cmd}\nJob-UUID: {job_uuid}"
        response = await self.protocol.send(bgapi_cmd)
        
        # Verify the Job-UUID in the response
        reply_text = response.get("Reply-Text", "")
        if not reply_text.startswith("+OK Job-UUID: "):
            # If we can't get confirmation, treat as failed
            result = BackgroundJobResult(job_uuid, cmd)
            error_msg = f"Failed to get Job-UUID confirmation from bgapi response: {reply_text}"
            logger.error(error_msg)
            result.set_exception(Exception(error_msg))
            # Clean up the filter we just added
            await self.protocol.send(f"filter delete Job-UUID {job_uuid}")
            return result
        
        # Extract and verify the returned Job-UUID matches what we sent
        returned_job_uuid = reply_text.split("Job-UUID: ")[1].strip()
        if returned_job_uuid != job_uuid:
            logger.warning(f"Sent Job-UUID {job_uuid} but received {returned_job_uuid}")
            # Clean up the filter for the Job-UUID we thought we were using
            await self.protocol.send(f"filter delete Job-UUID {job_uuid}")
            # Use the one FreeSWITCH actually assigned and add a filter for it
            job_uuid = returned_job_uuid
            await self.protocol.send(f"filter Job-UUID {job_uuid}")
        
        # Create BackgroundJobResult for tracking the background job
        result = BackgroundJobResult(job_uuid, cmd)
        
        # Store the pending job
        self._pending_jobs[job_uuid] = result
        logger.debug(f"Registered background job {job_uuid} for tracking")
        
        return result
    
    def get_pending_jobs(self) -> dict[str, BackgroundJobResult]:
        """
        Get all currently pending background jobs.
        
        Returns:
            Dictionary mapping Job-UUIDs to their BackgroundJobResult objects
        """
        return self._pending_jobs.copy()
    
    def _delete_job(self, job_uuid: str) -> bool:
        """
        Remove a job from tracking (for garbage collection).
        
        This is used internally when BackgroundJobResult objects are deleted
        or when jobs complete normally.
        
        Args:
            job_uuid: The Job-UUID to remove from tracking
            
        Returns:
            True if the job was found and removed, False otherwise
        """
        if job_uuid in self._pending_jobs:
            del self._pending_jobs[job_uuid]
            logger.debug(f"Removed background job {job_uuid} from tracking")
            return True
        return False
    
    def cleanup(self) -> None:
        """Clean up all pending jobs and remove event handler."""
        for job_uuid, result in self._pending_jobs.items():
            result.set_exception(Exception(f"Background job {job_uuid} cancelled due to cleanup"))
        
        self._pending_jobs.clear()
        
        if self._handler_registered:
            self.protocol.remove("BACKGROUND_JOB", self._handle_background_job)
            self._handler_registered = False
            logger.debug("Cleaned up BackgroundAPI handler")
