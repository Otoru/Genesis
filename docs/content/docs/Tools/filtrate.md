---
title: Filtrate
weight: 10
---

The `filtrate` decorator allows you to filter events based on key-value pairs. A handler decorated with `filtrate` will only execute if the specified key exists in the event and, optionally, if its value matches.

{{< callout type="info" >}}
The `filtrate` decorator must be placed **after** the `@app.handle()` decorator.
{{< /callout >}}

## Parameters

| Argument | Type | Required | Default | Description |
|----------|------|----------|---------|-------------|
| `key`    | str  | Yes      | N/A     | Event header key to check |
| `value`  | str  | No       | N/A     | Exact value to match (or regex pattern if `regex=True`) |
| `regex`  | bool | No       | `False` | Whether `value` should be treated as a regular expression |

## Filter by Key Only

Process events that contain a specific key, regardless of its value:

```python
from genesis import Consumer, filtrate

app = Consumer("127.0.0.1", 8021, "ClueCon")

@app.handle('sofia::register')
@filtrate('from-user')
async def register(event):
    domain = event['from-host']
    username = event['from-user']
    date = event['Event-Date-Local']
    print(f'[{date}] {username}@{domain} - Registered.')
```

## Filter by Key and Exact Value

Process events only when a key has a specific value:

```python
@app.handle('sofia::register')
@filtrate('from-user', '1000')
async def register_user_1000(event):
    domain = event['from-host']
    username = event['from-user']
    print(f'{username}@{domain} - Registered.')
```

## Filter by Key and Regex Pattern

Use regular expressions for pattern matching:

```python
@app.handle('sofia::register')
@filtrate('from-user', '^1[0-9]{3}$', regex=True)
async def register_extension_range(event):
    # Only processes users 1000-1999
    domain = event['from-host']
    username = event['from-user']
    print(f'{username}@{domain} - Registered (extension range).')
```

## Multiple Filters

You can stack multiple `filtrate` decorators to apply multiple conditions:

```python
@app.handle('CHANNEL_CREATE')
@filtrate('variable_user_context', 'default')
@filtrate('Call-Direction', 'inbound')
async def handle_inbound_default(event):
    # Only processes inbound calls in the default context
    caller_id = event.get('Caller-Caller-ID-Number')
    print(f'Inbound call from {caller_id}')
```

## Use Cases

- Filter events by channel variables
- Process events for specific users or domains
- Route events based on custom headers
- Pattern matching for extension ranges or phone numbers
