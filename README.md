# Genesis

[![Tests badge](https://github.com/Otoru/Genesis/actions/workflows/tests.yml/badge.svg)](https://github.com/Otoru/Genesis/actions/workflows/tests.yml)
[![Build badge](https://github.com/Otoru/Genesis/actions/workflows/pypi.yml/badge.svg)](https://github.com/Otoru/Genesis/actions/workflows/pypi.yml)
[![License badge](https://img.shields.io/github/license/otoru/Genesis.svg)](https://github.com/Otoru/Genesis/blob/master/LICENSE.md)
[![Pypi Version badge](https://img.shields.io/pypi/v/Genesis)](https://pypi.org/project/genesis/)
[![Pypi python version badge](https://img.shields.io/pypi/pyversions/Genesis)](https://pypi.org/project/genesis/)
[![Pypi wheel badge](https://img.shields.io/pypi/wheel/Genesis)](https://pypi.org/project/genesis/)

Genesis is a Python library designed to build asynchronous applications that interact with FreeSWITCH through the Event Socket Layer (ESL).

## Features

- **Asynchronous by Design:** Built with `asyncio` for high-performance, non-blocking I/O.
- **Inbound, Outbound, and Consumer Modes:** Supports all major ESL modes for comprehensive FreeSWITCH integration.
- **Decorator-Based Event Handling:** A simple and intuitive way to handle FreeSWITCH events.
- **OpenTelemetry Support:** Built-in instrumentation for tracing connections and commands.
- **Extensible and Customizable:** Easily extend and customize the library to fit your needs.

## Installation

Install Genesis using `pip`:

```bash
pip install genesis
```

## Quickstart

### Inbound Socket Mode

```python
import asyncio
from genesis import Inbound

async def uptime():
    async with Inbound("127.0.0.1", 8021, "ClueCon") as client:
        return await client.send("uptime")

async def main():
    response = await uptime()
    print(response)

asyncio.run(main())
```

### Consumer Mode

```python
import asyncio
from genesis import Consumer

app = Consumer("127.0.0.1", 8021, "ClueCon")

@app.handle("HEARTBEAT")
async def handler(event):
    await asyncio.sleep(0.001)
    print(event)

asyncio.run(app.start())
```

### Outbound Socket Mode

```python
import asyncio
from genesis import Outbound

async def handler(session):
    await session.answer()
    await session.playback('ivr/ivr-welcome')
    await session.hangup()

app = Outbound(handler, "127.0.0.1", 5000)

asyncio.run(app.start())
```

## Documentation

Full documentation is available on the [documentation website](https://otoru.github.io/Genesis/).

To preview the docs locally, install [Hugo](https://gohugo.io) and run:

```bash
hugo server --source docs --disableFastRender
```

## Running Tests

Install development dependencies with [Poetry](https://python-poetry.org) and execute the test suite using [tox](https://tox.wiki):

```bash
poetry install
tox
```

## How to Contribute

Contributions are welcome! Whether it's improving documentation, suggesting new features, or fixing bugs, your help is appreciated.

Please read our [Contributing Guide](CONTRIBUTING.md) and [Code of Conduct](CODE_OF_CONDUCT.md) to get started.

## Contributors

<table>
<tr>
    <td align="center" style="word-wrap: break-word; width: 150.0; height: 150.0">
        <a href=https://github.com/Otoru>
            <img src=https://avatars.githubusercontent.com/u/26543872?v=4 width="100;"  style="border-radius:50%;align-items:center;justify-content:center;overflow:hidden;padding-top:10px" alt=Vitor Hugo/>
            <br />
            <sub style="font-size:14px"><b>Vitor Hugo</b></sub>
        </a>
    </td>
    <td align="center" style="word-wrap: break-word; width: 150.0; height: 150.0">
        <a href=https://github.com/Netzvamp>
            <img src=https://avatars.githubusercontent.com/u/4619406?v=4 width="100;"  style="border-radius:50%;align-items:center;justify-content:center;overflow:hidden;padding-top:10px" alt=RL/>
            <br />
            <sub style="font-size:14px"><b>RL</b></sub>
        </a>
    </td>
    <td align="center" style="word-wrap: break-word; width: 150.0; height: 150.0">
        <a href=https://github.com/nativegold>
            <img src=https://avatars.githubusercontent.com/u/54573570?v=4 width="100;"  style="border-radius:50%;align-items:center;justify-content:center;overflow:hidden;padding-top:10px" alt=Dongwoon Kim/>
            <br />
            <sub style="font-size:14px"><b>Dongwoon Kim</b></sub>
        </a>
    </td>
</tr>
</table>

## License

This project is licensed under the MIT License - see the [LICENSE.md](LICENSE.md) file for details.