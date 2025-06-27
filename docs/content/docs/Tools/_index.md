---
title: Tools and Tricks
weight: 50
---

# Tools and Tricks

Here we list some useful tools to streamline your development process with Genesis.

## `filtrate`

The `filtrate` decorator allows you to filter FreeSWITCH events based on a key-value pair. A handler decorated with `filtrate` will only execute if the specified `key` exists in the event and, optionally, if its `value` matches.

| Argument | Type | Required | Default |
|----------|------|----------|---------|
| `key`    | str  | Yes      | N/A     |
| `value`  | str  | No       | N/A     |
| `regex`  | bool | No       | `False` |

### Filter by Key

This example processes any `sofia::register` event that contains the `from-user` key.

```python
@app.handle('sofia::register')
@filtrate('from-user')
def register(event):
    domain = event['from-host']
    username = event['from-user']
    date = event['Event-Date-Local']
    print(f'[{date}] {username}@{domain} - Registered.')
```

### Filter by Key and Value

This example processes `sofia::register` events only if the `from-user` key has a value of `1000`.

```python
@app.handle('sofia::register')
@filtrate('from-user', '1000')
def register(event):
    domain = event['from-host']
    username = event['from-user']
    date = event['Event-Date-Local']
    print(f'[{date}] {username}@{domain} - Registered.')
```

### Filter by Key and Regex Value

This example uses a regular expression to process `sofia::register` events where the `from-user` value is a 4-digit number starting with `1`.

```python
@app.handle('sofia::register')
@filtrate('from-user', '^1[0-9]{3}$', regex=True)
def register(event):
    domain = event['from-host']
    username = event['from-user']
    date = event['Event-Date-Local']
    print(f'[{date}] {username}@{domain} - Registered.')
```
