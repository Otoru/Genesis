"""
Genesis Observability
---------------------

Observability module for Genesis, providing health and readiness checks, and metrics.
"""

import asyncio
from typing import Optional
from time import time
from enum import Enum

from fastapi import FastAPI, Response, status
from uvicorn import Config, Server
from prometheus_client import make_asgi_app

from genesis.observability.logger import logger


class AppType(str, Enum):
    CONSUMER = "consumer"
    OUTBOUND = "outbound"


class Observability:
    """
    Observability class
    -------------------

    Manages the observability server (FastAPI + Uvicorn).
    Exposes /metrics, /health, and /ready endpoints.
    """

    def __init__(self, port: int = 8000) -> None:
        self.port = port
        self.app = FastAPI(title="Genesis Observability")
        self.last_heartbeat: Optional[float] = None
        self.outbound_ready: bool = False
        self.app_type: AppType = AppType.CONSUMER

        self._setup_routes()

    def _setup_routes(self) -> None:
        # Metrics endpoint
        metrics_app = make_asgi_app()
        self.app.mount("/metrics", metrics_app)

        @self.app.get("/health")
        async def health(response: Response) -> dict:
            if self.app_type == AppType.CONSUMER:
                if self.last_heartbeat and (time() - self.last_heartbeat < 30):
                    return {"status": "ok"}
                response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
                return {"status": "unhealthy"}
            # Outbound: server up means healthy
            return {"status": "ok"}

        @self.app.get("/ready")
        async def ready(response: Response) -> dict:
            is_ready = False

            if self.app_type == AppType.CONSUMER:
                # For Consumer, we check if we received a heartbeat recently (e.g., in the last 30s)
                if self.last_heartbeat and (time() - self.last_heartbeat < 30):
                    is_ready = True
            elif self.app_type == AppType.OUTBOUND:
                # For Outbound, we check if the server is marked as ready (running)
                is_ready = self.outbound_ready

            if is_ready:
                return {"status": "ready"}
            else:
                response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
                return {"status": "not ready"}

    def set_app_type(self, app_type: AppType) -> None:
        self.app_type = app_type

    def record_heartbeat(self, *args, **kwargs) -> None:
        """Record the timestamp of a received heartbeat."""
        self.last_heartbeat = time()
        logger.debug("Heartbeat recorded.")

    def set_outbound_ready(self, ready: bool) -> None:
        """Set the readiness status for Outbound application."""
        self.outbound_ready = ready
        logger.debug(f"Outbound readiness set to: {ready}")

    async def start(self) -> None:
        """Start the observability server."""
        config = Config(
            app=self.app, host="0.0.0.0", port=self.port, log_level="warning"
        )
        server = Server(config)

        logger.info(f"Starting Observability Server on port {self.port}")
        await server.serve()


observability = Observability()
