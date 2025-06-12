---
menu:
  main:
    identifier: "tools"
    weight: 3
---
# tools

Here we will list some methods that may be useful during the development of a Genesis project.

## Command Line Interface

The Genesis CLI provides commands to run and manage your FreeSWITCH Event Socket applications. Below are the available commands and their usage.

### Usage

```bash
genesis [OPTIONS] COMMAND [ARGS]...
```

### Options

Option | Description
-- | --
--version | Show the version and exit.

### genesis consumer

Run your ESL events consumer.

#### Usage

```bash
genesis consumer [OPTIONS] PATH
```

#### Options

Option | Description | Default
-- | -- | --
--host TEXT | The host to connect on. | 127.0.0.1
--port INTEGER | The port to connect on. | 8021
--password TEXT | The password to authenticate on host. | ClueCon
--app TEXT | Variable that contains the Consumer app in the imported module or package. | None
--loglevel TEXT | The log level to use. | info

#### Example

```bash
genesis consumer /path/to/your/app --host 192.168.1.100 --port 8021 --password MySecretPassword --loglevel debug
```

### genesis outbound

Run your outbound services.

#### Usage

```bash
genesis outbound [OPTIONS] PATH
```

#### Options

Option | Description | Default
-- | -- | --
--host TEXT | The host to serve on. | 127.0.0.1
--port INTEGER | The port to serve on. | 9000
--app TEXT | Variable that contains the Outbound app in the imported module or package. | None
--loglevel TEXT | The log level to use. | info

#### Example

```bash
genesis outbound /path/to/your/app --host 192.168.1.100 --port 9000 --loglevel debug
```

## Filtrate

When added to a function that will be used as a handler for FreeSwitch events, it ensures that this function will only process events that have the entered **key** and that have the **value** associated with that key.

| **Argument** | **Type** | **Required** | **Default** |
|--------------|----------|--------------|-------------|
| key          | str      | True         | N/A         |
| value        | str      | False        | N/A         |
| regex        | bool     | False        | False       |

### Key only

```python
@app.handle('sofia::register')
@filtrate('from-user')
def register(event):
    domain = event['from-host']
    username = event['from-user']
    date = event['Event-Date-Local']
    print(f'[{date}] {username}@{domain} - Registred.')
```

### With key and value

```python
@app.handle('sofia::register')
@filtrate('from-user', '1000')
def register(event):
    domain = event['from-host']
    username = event['from-user']
    date = event['Event-Date-Local']
    print(f'[{date}] {username}@{domain} - Registred.')
```

### With key and regex in value

```python
@app.handle('sofia::register')
@filtrate('from-user', '^1[0-9]{3}$', regex=True)
def register(event):
    domain = event['from-host']
    username = event['from-user']
    date = event['Event-Date-Local']
    print(f'[{date}] {username}@{domain} - Registred.')
```
