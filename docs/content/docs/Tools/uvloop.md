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

## See also

- [uvloop on GitHub](https://github.com/MagicStack/uvloop)
- [Installation Guide]({{< relref "../installation.md" >}}) — base Genesis installation
