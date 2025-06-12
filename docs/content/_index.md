# Welcome to the Genesis docs

Genesis is a Python library that helps you build applications for
[FreeSWITCH](https://freeswitch.org/) using `asyncio`. Here you will find
guides and references to get your projects up and running quickly.

Genesis provides three core building blocks:

- **Inbound mode** for sending commands directly to FreeSWITCH.
- **Consumer mode** to process events asynchronously.
- **Outbound mode** for creating dialplan-driven services.

In addition, a small CLI is included to launch your applications.

## What is Freeswitch?

FreeSWITCH is a free and open-source application server for real-time communication, WebRTC, telecommunications, video and Voice over Internet Protocol (VoIP). Multiplatform, it runs on Linux, Windows, macOS and FreeBSD. It is used to build PBX systems, IVR services, videoconferencing with chat and screen sharing, wholesale least-cost routing, Session Border Controller (SBC) and embedded communication appliances. It has full support for encryption, ZRTP, DTLS, SIPS. It can act as a gateway between PSTN, SIP, WebRTC, and many other communication protocols. Its core library, libfreeswitch, can be embedded into other projects. It is licensed under the Mozilla Public License (MPL), a free software license.

By [wikipedia](https://en.wikipedia.org/wiki/FreeSWITCH).

## What is ESL?

ESL is the protocol used for your applications to interact with the freeswitch. See more details [here](https://freeswitch.org/confluence/display/FREESWITCH/Event+Socket+Library).

## Why asyncio?

Asynchronous programming is a type of parallel programming in which a unit of work is allowed to run separately from the primary application thread. When the work is complete, it notifies the main thread about completion or failure of the worker thread. There are numerous benefits to using it, such as improved application performance and enhanced responsiveness. We adopted this way of working, as integrating genesis with other applications is simpler, since you only need to deal with python's native asynchronous programming interface.

## How to start?

Start by following the [Installation](/Genesis/docs/Installation/) process described in the documentation and then take a look at our [quickstart](/Genesis/docs/Quickstart/) to learn how to work using Genesis.

## Next steps

- Get familiar with the [CLI](/Genesis/docs/CLI/) commands.
- Explore the [Tools](/Genesis/docs/Tools/) page for helper utilities.
- Dive into the [ESL events structure](/Genesis/docs/ESL-events-structure/) guide to understand how FreeSWITCH messages are represented.
