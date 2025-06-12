---
title: Command line interface
weight: 3
---
# Command Line Interface

The Genesis CLI provides commands to run and manage your FreeSWITCH Event Socket applications. Below are the available commands and their usage.

## Usage

```bash
genesis [OPTIONS] COMMAND [ARGS]...
```

## Options

Option | Description
-- | --
--version | Show the version and exit.

## genesis consumer

Run your ESL events consumer.

### Usage

```bash
genesis consumer [OPTIONS] PATH
```

### Options

Option | Description | Default
-- | -- | --
--host TEXT | The host to connect on. | 127.0.0.1
--port INTEGER | The port to connect on. | 8021
--password TEXT | The password to authenticate on host. | ClueCon
--app TEXT | Variable that contains the Consumer app in the imported module or package. | None
--loglevel TEXT | The log level to use. | info

### Example

```bash
genesis consumer /path/to/your/app --host 192.168.1.100 --port 8021 --password MySecretPassword --loglevel debug
```

## genesis outbound

Run your outbound services.

### Usage

```bash
genesis outbound [OPTIONS] PATH
```

### Options

Option | Description | Default
-- | -- | --
--host TEXT | The host to serve on. | 127.0.0.1
--port INTEGER | The port to serve on. | 9000
--app TEXT | Variable that contains the Outbound app in the imported module or package. | None
--loglevel TEXT | The log level to use. | info

### Example

```bash
genesis outbound /path/to/your/app --host 192.168.1.100 --port 9000 --loglevel debug
```
