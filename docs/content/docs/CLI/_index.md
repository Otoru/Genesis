---
title: Command-Line Interface
weight: 40
---

# Command-Line Interface

The Genesis CLI provides commands to run and manage your FreeSWITCH ESL applications.

## Usage

```bash
genesis [OPTIONS] COMMAND [ARGS]...
```

## Options

| Option    | Description              |
|-----------|--------------------------|
| --version | Show the version and exit. |

## `genesis consumer`

Run an ESL event consumer.

### Usage

```bash
genesis consumer [OPTIONS] PATH
```

### Options

| Option      | Description                                               | Default     |
|-------------|-----------------------------------------------------------|-------------|
| --host      | The host to connect to.                                   | `127.0.0.1` |
| --port      | The port to connect to.                                   | `8021`      |
| --password  | The password for authentication.                          | `ClueCon`   |
| --app       | The variable containing the Consumer app in the module.   | `None`      |
| --loglevel  | The logging level.                                        | `info`      |

### Example

```bash
genesis consumer /path/to/your/app --host 192.168.1.100 --port 8021 --password MySecretPassword --loglevel debug
```

## `genesis outbound`

Run an outbound service.

### Usage

```bash
genesis outbound [OPTIONS] PATH
```

### Options

| Option      | Description                                               | Default     |
|-------------|-----------------------------------------------------------|-------------|
| --host      | The host to serve on.                                     | `127.0.0.1` |
| --port      | The port to serve on.                                     | `9000`      |
| --app       | The variable containing the Outbound app in the module.   | `None`      |
| --loglevel  | The logging level.                                        | `info`      |

### Example

```bash
genesis outbound /path/to/your/app --host 192.168.1.100 --port 9000 --loglevel debug
```