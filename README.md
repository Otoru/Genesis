# What is Genesis?

Client implementation of FreeSWITCH Event Socket protocol with asyncio.

[![Gitpod badge](https://img.shields.io/badge/Gitpod-ready%20to%20code-908a85?logo=gitpod)](https://gitpod.io/#https://github.com/Otoru/Genesis)
[![Tests badge](https://github.com/Otoru/Genesis/actions/workflows/tests.yml/badge.svg)](https://github.com/Otoru/Genesis/actions/workflows/tests.yml)
[![Build badge](https://github.com/Otoru/Genesis/actions/workflows/pypi.yml/badge.svg)](https://github.com/Otoru/Genesis/actions/workflows/pypi.yml)
[![License badge](https://img.shields.io/github/license/otoru/Genesis.svg)](https://github.com/Otoru/Genesis/blob/master/LICENSE.md)
[![Pypi Version badge](https://img.shields.io/pypi/v/Genesis)](https://pypi.org/project/genesis/)
[![Pypi python version badge](https://img.shields.io/pypi/pyversions/Genesis)](https://pypi.org/project/genesis/)
[![Pypi wheel badge](https://img.shields.io/pypi/wheel/Genesis)](https://pypi.org/project/genesis/)

## Inbound Socket Mode

```python
In [1]: from genesis import Inbound

In [2]: async with Inbound("127.0.0.1", 8021, "ClueCon") as client:
            response = await client.send("uptime")

In [3]: print(response)
{'Content-Type': 'command/reply', 'Reply-Text': '6943047'}
```

## Incoming Event handler

```python
In [1]: from genesis import Consumer

In [2]: app = Consumer("127.0.0.1", 8021, "ClueCon")

In [3]:  @app.handle("HEARTBEAT")
   ...:  async def handler(event):
   ...:     await asyncio.sleep(0.001)
   ...:     print(event)

In [4]: await app.start()
```

## Outbound Socket Mode

### XML dialplan example

```xml
<extension name="out socket">
   <condition>
      <action application="socket" data="127.0.0.1:5000 async full"/>
   </condition>
</extension>
```

### Python application code

```python

In [1]: from genesis import Outbound

In [2]: async def handler(session):
   ...:     await session.answer()
   ...:     await session.playback('ivr/ivr-welcome')
   ...:     await session.hangup()


In [3]: app = Outbound("127.0.0.1", 5000, handler)

In [4]: await app.start()
```

### Comments

- For simplify event object strtucuture, we decide work with dicts to store event headers. For events with body, your content is stored in some object, with `X-Event-Content` key.
- If a key purposely repeats in an event (Example: `Content-Length` in **BACKGROUND_JOB** event), we store both values in a list, in the order they are received.
- For practical reasons, every event handler should be awaitable.

## What is FreeSwitch?

FreeSWITCH is a free and open-source application server for real-time communication, WebRTC, telecommunications, video and Voice over Internet Protocol (VoIP). Multiplatform, it runs on Linux, Windows, macOS and FreeBSD. It is used to build PBX systems, IVR services, videoconferencing with chat and screen sharing, wholesale least-cost routing, Session Border Controller (SBC) and embedded communication appliances. It has full support for encryption, ZRTP, DTLS, SIPS. It can act as a gateway between PSTN, SIP, WebRTC, and many other communication protocols. Its core library, libfreeswitch, can be embedded into other projects. It is licensed under the Mozilla Public License (MPL), a free software license.

By [wikipedia](https://en.wikipedia.org/wiki/FreeSWITCH).

## What is ESL?

ESL is a way to communicate with FreeSwitch. See more details [here](https://freeswitch.org/confluence/display/FREESWITCH/Event+Socket+Library).

## Why asyncio?

Asynchronous programming is a type of parallel programming in which a unit of work is allowed to run separately from the primary application thread. When the work is complete, it notifies the main thread about completion or failure of the worker thread. There are numerous benefits to using it, such as improved application performance and enhanced responsiveness. We adopted this way of working, as integrating genesis with other applications is simpler, since you only need to deal with python's native asynchronous programming interface.

## How to contribute?

If you are thinking of contributing in any way to the project, you will be very welcome. Whether it's improving existing documentation, suggesting new features or running existing bugs, it's only by working together that the project will grow.

Do not forget to see our [Contributing Guide][2] and our [Code of Conduct][3] to always be aligned with the ideas of the project.

[2]: https://github.com/Otoru/Genesis/blob/master/CONTRIBUTING.md
[3]: https://github.com/Otoru/Genesis/blob/master/CODE_OF_CONDUCT.md

## Contributors

Will be welcome ❤️

## Author

| [<img src="https://avatars0.githubusercontent.com/u/26543872?v=3&s=115"><br><sub>@Otoru</sub>](https://github.com/Otoru) |
| :----------------------------------------------------------------------------------------------------------------------: |
