---
title: ESL Event Structure
weight: 30
---

# ESL Event Structure

An event message in the Event Socket Layer (ESL) consists of two parts:

- A list of headers (a key-value structure).
- An optional body.

## Example

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

The first 17 lines are the headers, and the last line is the body.

In Genesis, events are represented as a subclass of `UserDict`. You can access all headers as dictionary keys, and the event body, if present, is available through the `.body` property.

```python
event["Core-UUID"]
# 42bdf272-16e6-11dd-b7a0-db4edd065621

event["Event-Calling-Line-Number"]
# 609

event.body
# +OK 7f4de4bc-17d7-11dd-b7a0-db4edd065621
```

To determine if an event has a body, Genesis parses the headers and checks for the `Content-Length` header. If it is present, Genesis reads the specified number of bytes and assigns them to the `.body` property.