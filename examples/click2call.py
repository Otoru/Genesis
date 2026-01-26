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
