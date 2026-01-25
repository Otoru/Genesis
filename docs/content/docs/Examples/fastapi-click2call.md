---
title: Click2Call API
weight: 10
parent: Examples
---

Simple REST API endpoint for click2call functionality using FastAPI and Genesis.

## Example Code

```python {filename="examples/click2call.py" base_url="https://github.com/Otoru/Genesis/blob/main"}
import os

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from genesis.types import ChannelState
from genesis import Inbound, Channel
from genesis.exceptions import TimeoutError, GenesisError

app = FastAPI()

FS_HOST = os.getenv("FS_HOST", "127.0.0.1")
FS_PORT = int(os.getenv("FS_PORT", "8021"))
FS_PASSWORD = os.getenv("FS_PASSWORD", "ClueCon")


class Request(BaseModel):
    source: str
    bridge: str


@app.post("/")
async def click2call(request: Request):
    try:
        async with Inbound(FS_HOST, FS_PORT, FS_PASSWORD) as client:
            caller = await Channel.create(client, request.source)
            await caller.wait(ChannelState.EXECUTE, timeout=10.0)

            callee = await Channel.create(client, request.bridge)
            await callee.wait(ChannelState.EXECUTE, timeout=10.0)

            await caller.bridge(callee)

            return {"status": "bridged"}

    except TimeoutError:
        raise HTTPException(status_code=408, detail="Call timeout")

    except GenesisError:
        raise HTTPException(status_code=500, detail="Internal error")
```

## Connection Strategies

The example uses a **per-request connection**, opening a new connection to FreeSWITCH for each request. This is simple and works well for low to moderate traffic.

**For production with high traffic**, consider implementing a persistent connection strategy with a healthcheck mechanism to detect and recover from connection failures. Recommended strategies:

- **Periodic ping**: Send `api status` periodically to verify connection is alive
- **Connection monitoring**: Monitor connection state and automatically reconnect on failure
- **Request-time validation**: Check connection health before each request and reconnect if needed

## Running the Example

{{% steps %}}

### 1. Clone the Repository

```bash
git clone https://github.com/Otoru/Genesis.git
cd Genesis
```

### 2. Install Dependencies

```bash
poetry install --with examples
```

### 3. Configure FreeSWITCH Connection

Set environment variables for your FreeSWITCH connection:

```bash
export FS_HOST=127.0.0.1
export FS_PORT=8021
export FS_PASSWORD=ClueCon
```

### 4. Run the Server

```bash
uvicorn examples.click2call:app --reload
```

The API will be available at `http://localhost:8000`.

### 5. Test the Endpoint

```bash
curl -X POST "http://localhost:8000/" \
  -H "Content-Type: application/json" \
  -d '{"source": "user/1000", "bridge": "user/1001"}'
```

{{% /steps %}}
