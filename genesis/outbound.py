"""
Genesis outbound
----------------

ESL implementation used for outgoing connections on freeswitch.
"""

from __future__ import annotations


from asyncio import StreamReader, StreamWriter, start_server
from typing import Union, Dict, List, Optional

from collections.abc import Callable, Coroutine
from functools import partial
import socket

from genesis.logger import logger
from genesis.session import Session


class Outbound:
    """
    Outbound class
    -------------

    Given a valid set of information, start an ESL server that processes calls.

    Attributes:
    - host: required
        IP address the server should listen to.
    - port: required
        Network port the server should listen to.
    - handler: required
        Function that will take a session as an argument and will actually process the call.
    - myevents: optional
        If true, ask freeswitch to send us all events associated with the caller.
        Be aware that this prevents the ability to add other channels events to this session, so you get only the
        events from the first leg! Since genesis is managing the event filters this should be False in most cases!
    - linger: optional
        If true, asks that the events associated with the session come even after the call hangup.
    - active_sessions: Dict[str, Session]
        Dictionary of active sessions, keyed by the A-leg channel UUID.
    """

    def __init__(
        self,
        handler: Union[Callable[[Session], Coroutine], Callable[[Session], None]],
        host: str = "127.0.0.1",
        port: int = 9000,
        myevents: bool = False,
        linger: bool = True,
    ) -> None:
        self.host = host
        self.port = port
        self.app = handler
        self.myevents = myevents
        self.linger = linger
        self.server = None
        self.active_sessions: Dict[str, Session] = {}

    async def start(self, block: bool = True) -> None:
        """Start the application server."""
        handler = partial(self.handler, self)
        self.server = await start_server(
            handler, self.host, self.port, family=socket.AF_INET # type: ignore
        )
        address = f"{self.host}:{self.port}"
        logger.info(f"Start application server and listen on '{address}'.")
        if block:
            await self.server.serve_forever()
        else:
            await self.server.start_serving()

    async def stop(self) -> None:
        """Terminate the application server."""
        if self.server:
            logger.debug("Shutdown application server.")
            self.server.close()
            await self.server.wait_closed()
            
        # Clean up any remaining sessions
        for session_id, session in list(self.active_sessions.items()):
            try:
                logger.info(f"Cleaning up session {session_id} during server shutdown")
                await session.stop()
            except Exception as e:
                logger.error(f"Error stopping session {session_id}: {e}")
            
        self.active_sessions.clear()

    @staticmethod
    async def handler(
        server: Outbound, reader: StreamReader, writer: StreamWriter
    ) -> None:
        """Method used to process new connections."""
        logger.debug(f"Outbound.handler: New connection received from {writer.get_extra_info('peername')}")
        session = Session(reader, writer, myevents=server.myevents)
        session_id = None

        try:
            async with session:
                logger.debug(f"Outbound.handler: Session {session} started. Sending 'connect' command.")
                connect_event_context = await session.send("connect")
                logger.trace(f"Outbound.handler: 'connect' command sent. Received context: {connect_event_context}")
                session.context = connect_event_context

                await session._dispatch_event_to_channels(connect_event_context)

                if not session.channel_a:
                    logger.error("A-leg channel initialization failed via dispatch. Aborting handler.")
                    return

                # Store the session in active_sessions using the A-leg UUID as key
                session_id = session.channel_a.uuid
                server.active_sessions[session_id] = session
                logger.info(f"Outbound.handler: Added session {session_id} to active_sessions. Total active: {len(server.active_sessions)}")

                if server.myevents:
                    logger.debug("Send command to receive all call events (myevents).")
                    await session.send("myevents")
                else:
                    logger.debug("We don't use 'myevents', send command to receive all events for this session (events plain ALL).")
                    await session.send("events plain ALL")

                if server.linger:
                    logger.debug("Send linger command to FreeSWITCH.")
                    await session.send("linger")
                    session.linger = True

                logger.debug(f"Outbound.handler: Starting application handler server.app for session {session_id}.")
                try:
                    await server.app(session)
                except Exception as e:
                    logger.error(f"Unhandled exception in application handler: {e}", exc_info=True)
                    # Ensure hangup on error if the app didn't handle it
                    if session.channel_a and not session.channel_a.is_gone:
                        try:
                            logger.info("Hanging up call due to application handler error.")
                            await session.channel_a.hangup(cause="SYSTEM_ERROR")
                        except Exception as hangup_err:
                            logger.error(f"Error during hangup after application error: {hangup_err}")
                finally:
                    logger.debug(f"Outbound.handler: Application handler for session {session_id} finished (finally block).")
        except Exception as e_outer_handler:
            logger.error(f"Outbound.handler: Outer exception for session {session_id if session_id else 'unknown'}: {e_outer_handler}", exc_info=True)
            # Re-raise if necessary, or ensure cleanup
        finally:
            # Remove the session from active_sessions when done
            if session_id and session_id in server.active_sessions:
                del server.active_sessions[session_id]
                logger.info(f"Outbound.handler: Removed session {session_id} from active_sessions. Remaining active: {len(server.active_sessions)}")
            logger.info(f"Outbound.handler: Finished processing connection from {writer.get_extra_info('peername')}. Session ID was: {session_id if session_id else 'N/A'}")

    def get_active_sessions(self) -> List[Session]:
        """
        Returns a list of all active sessions.
        
        Returns:
            List of active Session objects
        """
        return list(self.active_sessions.values())
    
    def get_session_by_uuid(self, uuid: str) -> Optional[Session]:
        """
        Get a session by its A-leg UUID.
        
        Args:
            uuid: The UUID of the A-leg channel
            
        Returns:
            The Session if found, None otherwise
        """
        return self.active_sessions.get(uuid)
    
    def get_session_count(self) -> int:
        """
        Returns the number of active sessions.
        
        Returns:
            Count of active sessions
        """
        return len(self.active_sessions)
