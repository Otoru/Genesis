---
title: Command-Line Interface
weight: 40
---

The Genesis CLI provides commands to run and manage your FreeSWITCH ESL applications. It automatically detects your application code and supports both development and production modes.

## Global Options

| Option    | Description              |
|-----------|--------------------------|
| `--version` | Show the version and exit. |
| `--json` | Output logs in JSON format. |

## `genesis consumer`

Run an ESL event consumer application.

### Commands

- `genesis consumer dev` - Development mode with auto-reload
- `genesis consumer run` - Production mode

### Options

| Option      | Description                                               | Default     | Env Var |
|-------------|-----------------------------------------------------------|-------------|---------|
| `--host`    | FreeSWITCH host to connect to.                            | `127.0.0.1` | `ESL_HOST` |
| `--port`    | FreeSWITCH port to connect to.                            | `8021`      | `ESL_PORT` |
| `--password`| Password for authentication.                              | `ClueCon`   | `ESL_PASSWORD` |
| `--app`     | Variable name containing the Consumer app (defaults to `app` or first Consumer found). | `None` | `ESL_APP_NAME` |
| `--loglevel`| Logging level (debug, info, warning, error).              | `info`      | `ESL_LOG_LEVEL` |

### Examples

{{< tabs items="Development,Production" >}}

  {{< tab >}}
  **Development mode** with auto-reload:

  ```bash
  genesis consumer dev ./my_app.py --host 192.168.1.100 --password MySecretPassword
  ```
  {{< /tab >}}

  {{< tab >}}
  **Production mode**:

  ```bash
  genesis consumer run ./my_app.py --host 192.168.1.100 --password MySecretPassword
  ```
  {{< /tab >}}

{{< /tabs >}}

## `genesis outbound`

Run an outbound service application.

### Commands

- `genesis outbound dev` - Development mode with auto-reload
- `genesis outbound run` - Production mode

### Options

| Option      | Description                                               | Default     | Env Var |
|-------------|-----------------------------------------------------------|-------------|---------|
| `--host`    | Host to serve on.                                         | `127.0.0.1` | `ESL_APP_HOST` |
| `--port`    | Port to serve on.                                         | `9000`      | `ESL_APP_PORT` |
| `--app`     | Variable name containing the Outbound app (defaults to `app` or first Outbound found). | `None` | `ESL_APP_NAME` |
| `--loglevel`| Logging level (debug, info, warning, error).              | `info`      | `ESL_LOG_LEVEL` |

### Examples

{{< tabs items="Development,Production" >}}

  {{< tab >}}
  **Development mode** with auto-reload:

  ```bash
  genesis outbound dev ./my_outbound.py --host 0.0.0.0 --port 5000
  ```
  {{< /tab >}}

  {{< tab >}}
  **Production mode**:

  ```bash
  genesis outbound run ./my_outbound.py --host 0.0.0.0 --port 5000
  ```
  {{< /tab >}}

{{< /tabs >}}

## Application Discovery

{{< callout type="info" >}}
The CLI automatically discovers your application - no manual configuration needed!
{{< /callout >}}

{{% steps %}}

### Path

Imports the module from the file or directory path provided.

### App Detection

Looks for a variable named `app`, or the first `Consumer`/`Outbound` instance found.

### Custom App Name

Use `--app` to specify a different variable name.

{{% /steps %}}

### Example

```python
# my_app.py
from genesis import Consumer

app = Consumer("127.0.0.1", 8021, "ClueCon")

@app.handle("HEARTBEAT")
async def handler(event):
    print(event)
```

```bash
genesis consumer dev my_app.py
```