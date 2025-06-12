---
title: 'ESL events structure'
weight: 2
---
# ESL events structure

An event message has two parts:

- A list of headers (`key: value` based structure).
- A body (optional).

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

The first 17 lines are a set of headers and the last line is a representation of your body.

In genesis, events are a subclass of `UserDict`. Since all headers can be accessed as keys of this dictionary and the event body, if it exists, is accessible through the `.body` property.

```python
event["Core-UUID"]
# 42bdf272-16e6-11dd-b7a0-db4edd065621

event["Event-Calling-Line-Number"]
# 609

event.body
# +OK 7f4de4bc-17d7-11dd-b7a0-db4edd065621
```

For determinate if event has body, genesis read and parse all headers and observe if the `Content-Length` is present. If true, the next N sequential bytes received will be read (N being the header value) and this will be the value assigned to body.
