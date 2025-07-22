"""
Genesis Protocol
----------------

Here we will group what is common to the ESL client for inbound and outbound connections.
"""

from asyncio import (
    iscoroutinefunction,
    StreamWriter,
    StreamReader,
    create_task,
    to_thread,
    Event,
    Queue,
    Task,
    CancelledError,
    InvalidStateError,
    gather,
)
import asyncio
from typing import List, Dict, Optional, Callable, Coroutine, Any, Union
from abc import ABC
import logging

from genesis.exceptions import UnconnectedError, ConnectionError
from genesis.events import ESLEvent
from genesis.parser import parse_headers
from genesis.logger import logger, TRACE_LEVEL_NUM


class Protocol(ABC):
    def __init__(self):
        self.events = Queue()
        self.commands = Queue()
        self.is_connected = False
        self.is_lingering = False
        self.authentication_event = Event()
        self.producer: Optional[Task] = None
        self.consumer: Optional[Task] = None
        self.reader: Optional[StreamReader] = None
        self.writer: Optional[StreamWriter] = None
        self.handlers: Dict[
            str,
            List[
                Union[
                    Callable[[ESLEvent], None],
                    Callable[[ESLEvent], Coroutine[Any, Any, None]],
                ]
            ],
        ] = {}

    async def start(self) -> None:
        """Initiates a connection to a freeswitch."""
        self.is_connected = True

        logger.debug("Create tasks to work with ESL events.")
        self.producer = create_task(self.handler())
        self.consumer = create_task(self.consume())

    async def stop(self) -> None:
        """Terminates connection to a freeswitch."""
        self.is_connected = False

        if self.writer and not self.writer.is_closing():
            logger.debug("Close stream writer.")
            self.writer.close()
            try:
                await self.writer.wait_closed() # Ensure writer is closed before proceeding
            except Exception as e:
                logger.warning(f"Exception during writer.wait_closed(): {e}")


        tasks_to_await = []
        if self.producer:
            if not self.producer.done():
                logger.debug("Cancel event producer task.")
                self.producer.cancel()
                tasks_to_await.append(self.producer)
            else:
                # If already done, check for exceptions
                try:
                    exc = self.producer.exception()
                    if exc:
                        logger.warning(f"Producer task was already done with exception: {exc}")
                except CancelledError:
                    logger.debug("Producer task was already cancelled and done.")
                except InvalidStateError: # pragma: no cover
                    logger.debug("Producer task was done but in InvalidState (e.g. cancelled but not awaited).")


        if self.consumer:
            if not self.consumer.done():
                logger.debug("Cancel event consumer task.")
                self.consumer.cancel()
                tasks_to_await.append(self.consumer)
            else:
                try:
                    exc = self.consumer.exception()
                    if exc:
                        logger.warning(f"Consumer task was already done with exception: {exc}")
                except CancelledError:
                    logger.debug("Consumer task was already cancelled and done.")
                except InvalidStateError: # pragma: no cover
                    logger.debug("Consumer task was done but in InvalidState (e.g. cancelled but not awaited).")

        if tasks_to_await:
            logger.debug(f"Awaiting {len(tasks_to_await)} cancelled tasks.")
            # Gather results, allowing CancelledError to be raised and caught
            results = await gather(*tasks_to_await, return_exceptions=True)
            for i, result in enumerate(results):
                task_name = "Producer" if tasks_to_await[i] == self.producer else "Consumer"
                if isinstance(result, CancelledError):
                    logger.debug(f"{task_name} task successfully cancelled and awaited.")
                elif isinstance(result, Exception):
                    # Log the full exception info for better debugging
                    logger.error(f"{task_name} task raised an exception during/after cancellation: {result}", exc_info=True)
                else:
                    logger.debug(f"{task_name} task completed after cancellation signal (returned: {result}).")
        
        # Nullify to prevent reuse and help GC
        self.producer = None
        self.consumer = None
        self.writer = None
        self.reader = None

    async def handler(self) -> None:
        """Defines intelligence to treat received events."""
        while self.is_connected:
            request = None
            buffer = ""

            while self.is_connected:
                try:
                    content = await self.reader.readline()
                    if not content: # EOF, connection closed by peer
                        logger.debug("PROTOCOL.HANDLER: EOF received from reader.readline(). Peer closed connection.")
                        self.is_connected = False
                        break
                    buffer += content.decode("utf-8", errors="ignore")
                except CancelledError:
                    logger.debug("PROTOCOL.HANDLER: Task cancelled during reader.readline().")
                    self.is_connected = False
                    raise
                except ConnectionResetError:
                    logger.warning("PROTOCOL.HANDLER: Connection reset by peer during reader.readline().")
                    self.is_connected = False
                    break
                except Exception as e:
                    if self.is_connected: # Only log as error if we thought we were connected
                        logger.error(f"PROTOCOL.HANDLER: Error reading from stream: {str(e)}", exc_info=True)
                    else: # If not connected, this might be an expected error during shutdown
                        logger.debug(f"PROTOCOL.HANDLER: Exception during readline, but not connected: {str(e)}")
                    self.is_connected = False
                    break

                if buffer[-2:] == "\n\n" or buffer[-4:] == "\r\n\r\n":
                    request = buffer
                    logger.trace(f"Complete message received: {repr(request)}")
                    break

            if not request or not self.is_connected:
                logger.debug(f"PROTOCOL.HANDLER: Exiting handler loop. Request: {'present' if request else 'absent'}, is_connected: {self.is_connected}")
                break

            event = parse_headers(request)
            logger.trace(f"PROTOCOL.HANDLER: Parsed event: {event.get('Event-Name')}, raw: {request[:200]}...")

            if "Content-Length" in event:
                # Get the total length from the first Content-Length header
                length = int(event["Content-Length"].split("\n")[0])
                logger.trace(f"Total content length: {length} bytes")

                # Read the complete data
                try:
                    data = await self.reader.readexactly(length)
                    logger.trace(f"Received complete data: {data}")
                    complete_content = data.decode("utf-8", errors="ignore")
                    contentType = event.get("Content-Type", None)

                    if contentType:
                        logger.trace(f"Check content type of event: {event}")

                        if contentType not in [
                            "api/response",
                            "text/rude-rejection",
                            "log/data",
                        ]:
                            # Try to split headers and body
                            if "\n\n" in complete_content:
                                headers_part, body = complete_content.split("\n\n", 1)

                                # Here we check for multiple events in one message (can happen if event-lock is set)
                                event_parts = []

                                if "event-lock: true" in headers_part.lower():
                                    # Split the string on "Event-Name: "
                                    parts = headers_part.split("\nEvent-Name: ")

                                    if len(parts) > 1:
                                        event_parts = [parts[0]]

                                        for part in parts[1:]:
                                            event_parts.append(f"Event-Name: {part}")

                                        logger.debug(
                                            f"Split locked event into {len(event_parts)} separate events"
                                        )
                                else:
                                    event_parts = [headers_part]

                                # Process each event part
                                for idx, event_str in enumerate(event_parts):
                                    if idx == 0:
                                        # First event is the original event
                                        additional_headers = parse_headers(event_str)
                                        event.update(additional_headers)
                                        event.body = body
                                        await self.events.put(event)
                                    else:
                                        # More events are new events
                                        new_event = parse_headers(event_str)
                                        # Copy some headers from the original event
                                        for key in ["Content-Length", "Content-Type"]:
                                            if key in event:
                                                new_event[key] = event[key]
                                        new_event.body = body
                                        await self.events.put(new_event)
                                continue  # Skip the final event.put

                            else:
                                # If no clear header/body separation, treat everything as body
                                event.body = complete_content
                        else:
                            event.body = complete_content
                    else:
                        event.body = complete_content
                except CancelledError:
                    logger.debug("PROTOCOL.HANDLER: Task cancelled during content processing.")
                    self.is_connected = False
                    raise
                except Exception as e:
                    if self.is_connected:
                        logger.error(f"PROTOCOL.HANDLER: Error processing content for event: {str(e)}", exc_info=True)
                    else:
                        logger.debug(f"PROTOCOL.HANDLER: Exception during content processing, but not connected: {str(e)}")
                    self.is_connected = False
                    break # Exit main handler loop
            
            logger.trace(f"PROTOCOL.HANDLER: Putting event on queue: {event.get('Event-Name')}. Event data: {event}")
            try:
                await self.events.put(event)
            except CancelledError:
                logger.debug("PROTOCOL.HANDLER: Task cancelled during events.put().")
                self.is_connected = False
                raise
        logger.debug("PROTOCOL.HANDLER: Exited main while loop.")

    async def consume(self) -> None:
        """Arm all event processors."""
        while self.is_connected:
            try:
                # Add a timeout to events.get() to make it responsive to cancellation
                event = await asyncio.wait_for(self.events.get(), timeout=0.1)
                logger.trace(f"PROTOCOL.CONSUMER: Got event from queue: {event.get('Event-Name')}. Event data: {event}")
            except asyncio.TimeoutError:
                # This is expected if no events are incoming, allows checking self.is_connected
                continue 
            except CancelledError:
                logger.debug("PROTOCOL.CONSUMER: Task cancelled during events.get().")
                self.is_connected = False
                raise
            except Exception as e: # Should not happen with Queue.get unless queue is broken
                if self.is_connected:
                    logger.error(f"PROTOCOL.CONSUMER: Error getting event from queue: {str(e)}", exc_info=True)
                else:
                    logger.debug(f"PROTOCOL.CONSUMER: Exception during events.get(), but not connected: {str(e)}")
                self.is_connected = False
                break

            try:
                if logger.isEnabledFor(TRACE_LEVEL_NUM):
                    logger.trace(f"Received an event: '{event}'.")

                else:
                    if logger.isEnabledFor(logging.DEBUG):
                        name = event.get("Event-Name", None)
                        uuid = event.get("Unique-ID", None)

                        if uuid:
                            logger.debug(
                                f"Received an event: '{name}' for call '{uuid}'. "
                            )

                            if name == "CHANNEL_EXECUTE_COMPLETE":
                                application = event.get("Application")
                                response = event.get("Application-Response")

                                logger.debug(
                                    f"Application: '{application}' - Response: '{response}'."
                                )

                        else:
                            if name:
                                logger.debug(f"Received an event: '{name}'.")

                            elif "Content-Type" in event and event["Content-Type"] in [
                                "command/reply",
                                "auth/request",
                            ]:
                                reply = event.get("Reply-Text", None)

                                if reply and event["Content-Type"] == "command/reply":
                                    logger.debug(
                                        f"Received an command reply: '{reply}'."
                                    )

                                if reply and event["Content-Type"] == "auth/request":
                                    logger.debug(
                                        f"Received an authentication reply: '{event}'."
                                    )

            except Exception as e:
                logger.error(f"Error logging event: {str(e)} - Event: {event}")

            if "Content-Type" in event and event["Content-Type"] == "auth/request":
                self.authentication_event.set()

            elif "Content-Type" in event and event["Content-Type"] == "command/reply":
                await self.commands.put(event)

            elif "Content-Type" in event and event["Content-Type"] == "api/response":
                await self.commands.put(event)

            elif "Content-Type" in event and event["Content-Type"] in [
                "text/rude-rejection",
                "text/disconnect-notice",
            ]:
                if not (
                    "Content-Disposition" in event
                    and event["Content-Disposition"] == "linger"
                ):
                    await self.stop()

            identifier = event.get("Event-Name", None)

            if identifier == "CUSTOM":
                name = event.get("Event-Subclass", None)
            else:
                name = identifier

            if name:
                logger.trace(f"Get all handlers for '{name}'.")
                specific = self.handlers.get(name, [])
                generic = self.handlers.get("*", list())
                handlers = specific + generic

                if handlers:
                    for handler_func in handlers:
                        try:
                            if iscoroutinefunction(handler_func):
                                create_task(handler_func(event))
                            else:
                                create_task(to_thread(handler_func, event))
                        except Exception as e_handler_task:
                            logger.error(f"Error creating task for handler {handler_func}: {e_handler_task}", exc_info=True)
        logger.debug("PROTOCOL.CONSUMER: Exited main while loop.")

    def on(
        self,
        key: str,
        handler: Union[
            Callable[[ESLEvent], None], Callable[[ESLEvent], Coroutine[Any, Any, None]]
        ],
    ) -> None:
        """Associate a handler with an event key."""
        logger.debug(f"Register handler to '{key}' event.")
        self.handlers.setdefault(key, list()).append(handler)

    def remove(
        self,
        key: str,
        handler: Union[
            Callable[[ESLEvent], None], Callable[[ESLEvent], Coroutine[Any, Any, None]]
        ],
    ) -> None:
        """Removes the HANDLER from the list of handlers for the given event KEY name."""
        logger.debug(f"Remove handler to '{key}' event.")
        if key in self.handlers and handler in self.handlers[key]:
            self.handlers.setdefault(key, list()).remove(handler)

    async def send(self, cmd: str, reply_timeout: Optional[Union[float, int]] = None) -> ESLEvent:
        """Method used to send commands to freeswitch."""
        # TODO: Later we should set a fixed reply_timeout, but only after we migrated all api commands to bgapi
        if not self.is_connected:
            # Check if writer is None or closing before raising UnconnectedError
            # This can happen if stop() was called and nulled self.writer
            if not self.writer or self.writer.is_closing():
                 logger.warning(f"Attempted to send command '{cmd[:30]}...' but not connected and writer is closed/None.")
                 raise UnconnectedError("Not connected and writer is unavailable.")
            # If writer exists but is_connected is false, it's still an issue
            raise UnconnectedError(f"Attempted to send command '{cmd[:30]}...' but not connected.")


        if self.writer.is_closing(): # Should be caught by the above if is_connected is also false
            raise ConnectionError(f"Attempted to send command '{cmd[:30]}...' but writer is closing.")

        logger.debug(f"Send command to freeswitch: '{cmd}'.")
        lines = cmd.splitlines()

        for line in lines:
            self.writer.write((line + "\n").encode("utf-8"))

        self.writer.write("\n".encode("utf-8"))
        await self.writer.drain()

        # Add timeout to commands.get() to prevent indefinite blocking if consumer blocks/dies
        try:
            if reply_timeout is not None:
                response = await asyncio.wait_for(self.commands.get(), timeout=reply_timeout)
            else:
                response = await self.commands.get() # Wait indefinitely
        except asyncio.TimeoutError:
            logger.error(f"Timeout ({reply_timeout}s) waiting for command reply to '{cmd[:30]}...'. Consumer might be stuck or connection lost.")
            # Create a synthetic error event or raise a specific exception
            raise ConnectionError(f"Timeout waiting for reply to command: {cmd[:30]}")
        except CancelledError:
            logger.warning(f"Send command '{cmd[:30]}...' cancelled while waiting for reply.")
            raise # Propagate cancellation
        return response
