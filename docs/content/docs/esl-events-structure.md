---
title: ESL Event Structure
weight: 30
---

FreeSWITCH communicates with your application through events sent over the Event Socket Layer (ESL). Understanding how these events are structured is essential for working with Genesis.

## Event Structure

An ESL event message consists of two parts:

- **Headers** - A key-value structure containing metadata about the event
- **Body** - Optional content that may contain additional data (like command responses)

## Raw Event Format

Here's an example of a raw ESL event:

```text
Content-Length: 625
Content-Type: text/event-plain
Job-UUID: 7f4db78a-17d7-11dd-b7a0-db4edd065621
Job-Command: originate
Job-Command-Arg: sofia/default/1005%20'%26park'
Event-Name: BACKGROUND_JOB
Core-UUID: 42bdf272-16e6-11dd-b7a0-db4edd065621
FreeSWITCH-Hostname: ser
FreeSWITCH-IPv4: 192.168.1.104
FreeSWITCH-IPv6: 127.0.0.1
Event-Date-Local: 2008-05-02%2007%3A37%3A03
Event-Date-GMT: Thu,%2001%20May%202008%2023%3A37%3A03%20GMT
Event-Date-timestamp: 1209685023894968
Event-Calling-File: mod_event_socket.c
Event-Calling-Function: api_exec
Event-Calling-Line-Number: 609
Content-Length: 41

+OK 7f4de4bc-17d7-11dd-b7a0-db4edd065621
```

The first section contains the headers (key-value pairs), followed by a blank line, and then the body content (if present).

## ESLEvent in Genesis

In Genesis, events are represented as `ESLEvent`, which is a subclass of Python's `UserDict`. This means you can access event data just like a dictionary.

### Accessing Headers

All headers are accessible as dictionary keys:

```python
# Access event name
event_name = event["Event-Name"]

# Access channel UUID
channel_uuid = event.get("Unique-ID")

# Access any header
core_uuid = event["Core-UUID"]
hostname = event["FreeSWITCH-Hostname"]
```

### Accessing the Body

If an event has a body, it's available through the `.body` property:

```python
# Check if event has body
if event.body:
    print(f"Event body: {event.body}")

# Access body directly
response = event.body
```

Genesis automatically parses the `Content-Length` header to determine if an event has a body and reads the specified number of bytes.

## Common Event Headers

Most events include these standard headers:

- `Event-Name` - The type of event (e.g., `CHANNEL_CREATE`, `HEARTBEAT`, `CUSTOM`)
- `Unique-ID` - Unique identifier for the channel or event
- `Core-UUID` - FreeSWITCH core instance identifier
- `Event-Date-Local` - Local timestamp of the event
- `Event-Date-GMT` - GMT timestamp of the event
- `Event-Date-timestamp` - Unix timestamp in microseconds

## Working with Events

### Example: Processing Channel Events

```python
from genesis import Consumer

app = Consumer("127.0.0.1", 8021, "ClueCon")

@app.handle("CHANNEL_CREATE")
async def on_channel_create(event):
    channel_uuid = event.get("Unique-ID")
    caller_id = event.get("Caller-Caller-ID-Number")
    print(f"New channel {channel_uuid} from {caller_id}")

@app.handle("CHANNEL_ANSWER")
async def on_channel_answer(event):
    channel_uuid = event.get("Unique-ID")
    print(f"Channel {channel_uuid} answered")

asyncio.run(app.start())
```

### Example: Accessing Channel Variables

Channel variables are prefixed with `variable_` in events:

```python
@app.handle("CHANNEL_CREATE")
async def on_channel_create(event):
    # Access channel variables
    caller_id = event.get("variable_effective_caller_id_number")
    context = event.get("variable_user_context")
    domain = event.get("variable_domain_name")
    
    print(f"Call from {caller_id} in context {context} on domain {domain}")
```

### Example: Command Responses

When you send commands, the response comes as an event with the result in the body:

```python
from genesis import Inbound

async with Inbound("127.0.0.1", 8021, "ClueCon") as client:
    response = await client.send("status")
    
    # Response headers
    print(f"Response type: {response.get('Content-Type')}")
    
    # Response body (if present)
    if response.body:
        print(f"Status output:\n{response.body}")
```

## URL Encoding

FreeSWITCH uses URL encoding for header values. Genesis automatically decodes these values when parsing events, so you can access them directly without manual decoding.

```python
# These are automatically decoded
event["Event-Date-Local"]  # "2008-05-02 07:37:03" (decoded from %20 and %3A)
event["Job-Command-Arg"]   # "sofia/default/1005 '&park'" (decoded from %20 and %26)
```

## Multiple Values

Some headers may appear multiple times in an event. When this happens, Genesis stores them as a list instead of a single value.

```python
# If a header appears multiple times
values = event["Some-Header"]
if isinstance(values, list):
    for value in values:
        print(value)
else:
    print(values)  # Single value
```