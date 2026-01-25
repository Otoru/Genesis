---
title: Key Concepts
weight: 5
---

Understanding the core concepts behind Genesis will help you build better FreeSWITCH applications.

## What is FreeSWITCH?

FreeSWITCH is a free and open-source application server for real-time communication, WebRTC, telecommunications, video and Voice over Internet Protocol (VoIP). Multiplatform, it runs on Linux, Windows, macOS and FreeBSD. It is used to build PBX systems, IVR services, videoconferencing with chat and screen sharing, wholesale least-cost routing, Session Border Controller (SBC) and embedded communication appliances. It has full support for encryption, ZRTP, DTLS, SIPS. It can act as a gateway between PSTN, SIP, WebRTC, and many other communication protocols. Its core library, libfreeswitch, can be embedded into other projects. It is licensed under the Mozilla Public License (MPL), a free software license.

By [wikipedia](https://en.wikipedia.org/wiki/FreeSWITCH).

## What is ESL?

ESL (Event Socket Layer) is the protocol used for your applications to interact with FreeSWITCH. It allows bidirectional communication, enabling you to:

- **Send commands** to FreeSWITCH to control calls, channels, and system behavior
- **Receive events** about what's happening in the system (call state changes, channel events, etc.)

ESL provides a powerful way to integrate external applications with FreeSWITCH, enabling real-time control and monitoring. See more details [here](https://freeswitch.org/confluence/display/FREESWITCH/Event+Socket+Library).

## Why asyncio?

Asynchronous programming allows units of work to run separately from the primary application thread. When work completes, it notifies the main thread about completion or failure. 

### Benefits

- **Improved performance** - Handle many concurrent operations efficiently
- **Enhanced responsiveness** - Non-blocking I/O keeps your application responsive
- **Better integration** - Works seamlessly with other async Python libraries
- **Simpler code** - Use Python's native async/await syntax

We adopted this approach because integrating Genesis with other applications is simpler, since you only need to deal with Python's native asynchronous programming interface.

## Genesis Architecture

Genesis provides three main modes of operation:

{{< cards cols="1" >}}
  {{< card link="../Quickstart/inbound/" title="Inbound Socket" icon="code" subtitle="Your application connects to FreeSWITCH to send commands." >}}
  {{< card link="../Quickstart/consumer/" title="Consumer" icon="lightning-bolt" subtitle="Your application subscribes to FreeSWITCH events." >}}
  {{< card link="../Quickstart/outbound/" title="Outbound Socket" icon="phone" subtitle="FreeSWITCH connects to your application for call control." >}}
{{< /cards >}}

Each mode serves different use cases and can be used together in the same application if needed.
