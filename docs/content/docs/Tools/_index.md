---
title: Tools and tricks
weight: 4
---
# Tools

Here we will list some methods that may be useful during the development of a Genesis project.

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
