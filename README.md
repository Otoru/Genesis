# What is Genesis?

[![Gitpod badge](https://img.shields.io/badge/Gitpod-ready--to--code-908a85?logo=gitpod)](https://gitpod.io/#https://github.com/Otoru/Genesis)
[![Tests badge](https://github.com/Otoru/Genesis/actions/workflows/tests.yml/badge.svg)](https://github.com/Otoru/Genesis/actions/workflows/tests.yml)
[![License badge](https://img.shields.io/github/license/otoru/Genesis.svg)](https://github.com/Otoru/Genesis/blob/master/LICENSE.md)

Client implementation of FreeSWITCH Event Socket protocol with asyncio.

## Inbound Socket Mode

```python
In [1]: from genesis import Client

In [2]: async with Client("127.0.0.1", 8021, "ClueCon") as client:
            response = await client.send("uptime")

In [3]: print(response)
{'Content-Type': 'command/reply', 'Reply-Text': '6943047'}
```

## What is FreeSwitch?

FreeSWITCH is a free and open-source application server for real-time communication, WebRTC, telecommunications, video and Voice over Internet Protocol (VoIP). Multiplatform, it runs on Linux, Windows, macOS and FreeBSD. It is used to build PBX systems, IVR services, videoconferencing with chat and screen sharing, wholesale least-cost routing, Session Border Controller (SBC) and embedded communication appliances. It has full support for encryption, ZRTP, DTLS, SIPS. It can act as a gateway between PSTN, SIP, WebRTC, and many other communication protocols. Its core library, libfreeswitch, can be embedded into other projects. It is licensed under the Mozilla Public License (MPL), a free software license.

By [wikipedia](https://en.wikipedia.org/wiki/FreeSWITCH).

## What is ESL?

ESL is a way to communicate with FreeSwitch. See more details [here](https://freeswitch.org/confluence/display/FREESWITCH/Event+Socket+Library).

## Why asyncio?

Asynchronous programming is a type of parallel programming in which a unit of work is allowed to run separately from the primary application thread. When the work is complete, it notifies the main thread about completion or failure of the worker thread. There are numerous benefits to using it, such as improved application performance and enhanced responsiveness. We adopted this way of working, as integrating genesis with other applications is simpler, since you only need to deal with python's native asynchronous programming interface.

## Contributors

Will be welcome ❤️

## Author

| [<img src="https://avatars0.githubusercontent.com/u/26543872?v=3&s=115"><br><sub>@Otoru</sub>](https://github.com/Otoru) |
| :----------------------------------------------------------------------------------------------------------------------: |
