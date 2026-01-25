
---
title: Welcome to Genesis
linkTitle: Documentation
type: docs
weight: 1
---

Genesis is a Python library that helps you build applications for **FreeSWITCH** using *asyncio*. Here you will find guides and references to get your projects up and running quickly.

## Core Building Blocks

Genesis provides three core modes for interacting with FreeSWITCH:

{{< cards cols="1" >}}
  {{< card link="Quickstart/inbound/" title="Inbound Socket" icon="code" subtitle="Send commands directly to FreeSWITCH and receive responses asynchronously." >}}
  {{< card link="Quickstart/consumer/" title="Consumer" icon="lightning-bolt" subtitle="Process FreeSWITCH events asynchronously using intuitive decorators." >}}
  {{< card link="Quickstart/outbound/" title="Outbound Socket" icon="phone" subtitle="Create dialplan-driven services to control calls in real-time." >}}
{{< /cards >}}

## Getting Started

{{% steps %}}

### Installation

Install Genesis using `pip`:

```bash
pip install genesis
```

### Choose Your Mode

Explore the Quickstart guide to learn how to work with each mode.

### Build Your Application

Use the CLI to run your applications in development or production mode.

{{% /steps %}}

## Learn More

- **New to FreeSWITCH or ESL?** Check out our [concepts guide]({{< relref "concepts.md" >}}) to understand the fundamentals.
- **Looking for examples?** See our [examples section]({{< relref "Examples/_index.md" >}}) for practical implementations.
- **Need advanced features?** Explore our [tools and tricks]({{< relref "Tools/_index.md" >}}) section.
