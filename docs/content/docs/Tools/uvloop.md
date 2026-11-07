---
title: uvloop
weight: 15
---

[uvloop](https://github.com/MagicStack/uvloop) is a fast, drop-in replacement for the default asyncio event loop, built on libuv.

On **Unix** (Linux and macOS), using uvloop can improve asyncio performance.

{{< callout type="warning" >}}
uvloop is **not supported on Windows**.
{{< /callout >}}

## Installation

Install Genesis with the uvloop extra:

```bash
pip install genesis[uvloop]
```

## Usage

When the extra is installed, the Genesis CLI uses uvloop automatically.

In your own entry point, pass `new_event_loop` as the loop factory. It returns a uvloop loop when uvloop is available and a default asyncio loop otherwise:

```python
import asyncio

from genesis import new_event_loop

with asyncio.Runner(loop_factory=new_event_loop) as runner:
    runner.run(main())
```

{{< callout type="info" >}}
`use_uvloop()` is deprecated. It sets a global event loop policy, and asyncio policies are deprecated since Python 3.14 and removed in 3.16.
{{< /callout >}}

## See also

- [uvloop on GitHub](https://github.com/MagicStack/uvloop)
- [Installation Guide]({{< relref "../installation.md" >}}) — base Genesis installation
