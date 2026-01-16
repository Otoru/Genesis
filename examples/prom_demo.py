
import asyncio
import logging
import random
from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from prometheus_client import start_http_server

from genesis import Inbound
from genesis.logger import reconfigure_logger

# 1. Setup OpenTelemetry with Prometheus Exporter
# Start Prometheus client HTTP server on port 8000
start_http_server(8000)

metric_reader = PrometheusMetricReader()
provider = MeterProvider(
    resource=Resource.create({"service.name": "genesis-demo"}),
    metric_readers=[metric_reader],
)
metrics.set_meter_provider(provider)


async def main():
    print("Prometheus metrics available at http://localhost:8000/metrics")
    print("Generating traffic... (Press Ctrl+C to stop)")
    
    reconfigure_logger(use_json=False)

    # Mocking connection to generate metrics without real FreeSWITCH
    # Ideally we'd valid connection, but for demo we assume user runs it against FS or we assume failures generate metrics too?
    # Actually, ConnectionError stops everything.
    # So we need a running FS or mock.
    # Since I don't have FS, I'll rely on the fact that I can't easily run this fully.
    # BUT, the user probably has FS.
    # I will create a script that tries to connect.
    
    host = "127.0.0.1"
    port = 8021
    password = "ClueCon"

    try:
        async with Inbound(host, port, password) as client:
            while True:
                # Send a command (generates genesis.commands.sent)
                await client.send("uptime")
                
                # Sleep a bit
                await asyncio.sleep(2)
                
    except Exception as e:
        print(f"Connection failed: {e}")
        print("Metrics are still exposed. Check them out!")
        print("Note: To see more metrics, ensure FreeSWITCH is running.")
        
        # Keep process alive to serve metrics
        while True:
            await asyncio.sleep(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
