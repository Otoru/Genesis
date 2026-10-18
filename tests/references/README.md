# ESL references

Offline fixtures for the suite. Tests and CI do not start FreeSWITCH or Docker, and they do not read `/tmp`. How to run the suite is in [CONTRIBUTING.md](../../CONTRIBUTING.md#running-the-tests).

Each `*.raw` file has a sibling `*.meta.json`. The sidecar is the provenance. The bytes have no comment header. The research password is not in this tree. The public disconnect banner is, because that string is part of the captured frames.

## Pin

- FreeSWITCH `v1.11.3`
- Commit `ef32e205295e29f034f1453ad245ba5efb07b94a`
- `mod_event_socket.c` sha256 `2470d0b064151db03435ebabeaadaf4fd70375e52b41766718242784483a3bd0`
- Runtime banner from the captured status body: `FreeSWITCH (Version 1.11.3-release git ef32e20 2026-08-28 20:49:48Z 64bit)`

Simulator comments that cite `mod_event_socket.c` or `switch_event.c` refer to that checkout.

## Reproducing a capture

Build that commit with `mod_event_socket` and without `mod_sofia`. Configure still expects sofia-sip `v1.13.18` (`ad36ac8f755308e8b87f98a505e83d4e408e5cc3`) and spandsp `v3.1.1` (`8f1e1646bdec99eac5fd2cd92c35563f736b9b89`).

Modules present for these captures:

- console, logfile, commands, dptools, expr, hash
- dialplan_xml, loopback, event_socket, tone_stream

Event socket for the captures:

- listen `0.0.0.0:8021`
- no `apply-inbound-acl`, so the source default `loopback.auto` applies
- that list denies, then allows `127.0.0.0/8` and `::1/128`
- a client that is not loopback inside the process receives rude rejection
- an empty `password` parameter falls back to `ClueCon` in this source

Outbound sockets that produced the connect and exit captures:

- `async full` accepts `event`, `api`, and `linger`
- `async` without `full` accepts `myevents`
- `async` without `full` rejects `event` and `api` with `-ERR command not found`

Copy new bytes unchanged under `real/<version>/`. Add a sidecar with `kind`, `freeswitch_version`, `git`, `source`, and `captured_at`. Frames this server did not produce go under `synthetic/` with `"kind": "synthetic"`.

## Captured

Files under `real/1.11.3/` are unmodified copies, except where the sidecar sets `reconstructed`. Checks compared stable reply text, lengths, and encoding. They did not require a full channel-header dump to be byte-identical.

Whole files compared with the peer:

- `bad_auth.raw`: `auth/request`, then `-ERR invalid`, then a 67-byte disconnect
- `host_acl_rude_rejection.raw`: `text/rude-rejection`, body `Access Denied, go away.\n` (length 24), then the 67-byte disconnect

This rude rejection is an ACL denial. It is not a malformed frame.

Stable fields compared:

- `unicode_api_response.raw` is reconstructed (`reconstructed: true`). The sidecar source is `captures-from-container/report.json#unicode_api_body`. Body hex `636166c3a92de7a094e7a9b6`, declared length 12, seven Unicode code points. The body is raw UTF-8.
- `header_encoding.raw`: `command/reply` with no body and no `Content-Length`
- `encoded_event.raw`: `command/reply` plus `text/event-plain`, with percent-encoded header values (`+` is `%2B`, space is `%20`)
- `filter_isolation_a.raw`: a `CUSTOM` event subscribed and filtered on one connection was not delivered to the other. The subclass and marker were checked.
- `full_connect.raw` and `plain_connect.raw`: outbound `connect` sends no `auth/request`. `Reply-Text` on the wire is `%2BOK%0A`. `Control` is `full` or `single-channel`.
- `full_exit.raw` and `plain_exit.raw`: `exit` answers `+OK bye` and disconnects that socket. The listener stays up. `plain_exit.raw` also carries a late `-ERR command not found` from `api` on a non-full socket. `full_exit.raw` shows an `API` event before `+OK bye`.
- `sendmsg_log.raw`: `+OK`, then `CHANNEL_EXECUTE`, then `CHANNEL_EXECUTE_COMPLETE`, with `Application-UUID` equal to the client `Event-UUID`. `Application-Data` is `INFO%20esl-research`.
- `event_lock.raw`: `event-lock: true` on `sendmsg` still yields two outer frames. The bytes `event-lock` are not in the file.
- `bgapi_status.raw`: `command/reply` carries the client `Job-UUID`, then `BACKGROUND_JOB`. The job body in the capture is raw status text (369 bytes). The peer answers `api status` with `UP 0\n` and does not reproduce that body.
- `uuid_exists_false.raw` and `uuid_exists_true.raw`: `api/response` bodies are `false` and `true`, with no trailing newline
- `uuid_execute_missing.raw`: `api uuid_execute` is `-ERR uuid_execute Command not found!\n`. There is no `uuid_execute` API
- `uuid_dump_txt_note.txt`: default and `txt` dump body. Values are URL-encoded. `variable_research_note` is `caf%C3%A9%20test`
- `uuid_dump_plain.txt`: `plain` wraps every value in brackets and does not URL-encode. That is not the default
- `race_dump.raw`: an `api/response` `plain` dump, then `CHANNEL_EXECUTE` and `CHANNEL_EXECUTE_COMPLETE` as later frames. They share one `Application-UUID`. That header is not in the dump body
- `piped_eval.raw`: one write, two `api/response` bodies, `alpha` and `beta`

Reply text recorded from the same build, without its own raw file:

- good auth is `+OK accepted` and has no body
- an unknown command is `command/reply` `-ERR command not found` and has no body
- an unknown API is `api/response` with a 42-byte body that includes the trailing newline
- `uuid_dump` of an unknown channel is `-ERR No such channel!\n`
- `uuid_dump` with no argument is `-USAGE: <uuid> [format]\n`
- two `api eval` commands in one write yield bodies `alpha` (5) and `beta` (4)
- `filter delete` reply text has no `=`
- `nixevent` is `+OK events nixed`
- `noevents` is `+OK no longer listening for events`
- inbound `linger` with no session is `-ERR not controlling a session`
- auth split across two writes still authenticates. The peer was checked on a split of `auth lab` and `-password`, not on the original split at byte 6

Inbound `exit` was observed on this build: `+OK bye`, then a 67-byte disconnect with no `Content-Disposition`, then a new connection still receives `auth/request`. No raw file was kept. The saved exit captures are the outbound ones.

`tests/contract/test_parser_diff.py` parses `encoded_event.raw` and `filter_isolation_a.raw` with `genesis.protocol.parser` and compares those headers with the simulator codec. The simulator package does not import the parser.

## Source only

Described by that checkout and not stored as a capture. These are not live evidence.

- `userauth`
- `nixevent ALL`
- a negative filter, a regex filter, and case-insensitive filter match
- `filter delete all`
- inbound `myevents <uuid>`
- `linger` with a duration, and `Content-Disposition: linger` with `Content-Length: 0`
- `event-lock-pri`
- JSON and XML event formats
- an empty API body becoming `-ERR no reply\n`
- `Content-Length` below 0 or above 16 MiB
- a truncated body, or a length that disagrees with the body
- header termination with `\r\n` (these captures use `\n\n` only; the source accepts both)
- `_undef_` for an empty header value
- `CHANNEL_PARK` arriving before `-ERR command not found` on a non-full `api`. That order was seen and was not saved as its own file

The peer contains code for negative filters, a stored value that starts with `/` as a regular expression, case-insensitive equality, `filter delete all`, `nixevent ALL`, and a 16 MiB length cap. None of that was captured.

## Synthetic

Not produced by this FreeSWITCH.

- `short_body.raw`: declared length 10, four body bytes
- `bad_content_length.raw`: declared length 4, eight body bytes
- `legacy_payloads.py`, `consumer_payloads.py`, and `telemetry_payloads.py`: handwritten text for unit and consumer tests. They are not captures, and `genesis.protocol.parser` did not produce them

Reader tests that split one body on `event-lock: true` cover the current Genesis reader. This FreeSWITCH build emits two frames and does not put `event-lock` in the body.

## Simulator limits

`tests/simulator/` encodes a subset itself. It does not import `genesis`.

Commands the peer answers:

- inbound `auth/request`, `auth`, and the bad-auth disconnect
- `event plain`, `nixevent`, `noevents`, `filter`, `api`, `bgapi`
- `sendmsg`, `sendevent`, `linger`, `myevents`, `connect`, `exit`
- subscriptions and filters stored on that connection
- outbound `connect` with `Control: full` or `single-channel`
- on a non-full outbound socket, `api`, `bgapi`, `event`, `sendevent`, and `log` get `-ERR command not found`
- `uuid_bridge` and `uuid_kill` as command replies only. A successful `uuid_kill` removes that channel and its outbound session from later `uuid_exists`, `uuid_dump`, and `sendmsg`
- `sendmsg` to a uuid that is not a live channel: `-ERR invalid session id [<uuid>]`
- `sendmsg` with no uuid: `+OK` only while that socket still controls a live session. Otherwise `-ERR invalid session id []`
- a registered outbound session is a channel (`loopback/pilot`, `CS_EXECUTE`) until `uuid_kill`
- `uuid_exists` (`true` or `false`, no newline) and `uuid_dump` (default and `txt` are URL-encoded; `plain` uses brackets)
- `seed_channel` and `disappear_after` for a channel that outlives one socket. A new connection sees that row and does not receive events already delivered
- `open_executions`. `start_execution` and `complete_execution` take `connection_id` for the socket that should see the event. Closing the first socket does not finish the execute

The peer does not model:

- media, SIP, codecs, playback, a dialplan, or a PBX. `seed_channel` does not emit channel lifecycle events
- `CHANNEL_BRIDGE` after `uuid_bridge`
- the session private-event queue. `event-lock: true` is stored on the pending execute and does not hold the next `sendmsg`. The application does not run. The two channel events are emitted only when the scenario calls `start_execution` and then `complete_execution`, and the flag is not copied into those bodies
- `api uuid_execute`
- replaying events from a closed socket, or joining a dump and later channel events into one frame
- XML or JSON event subscriptions. The peer replies `-ERR unsupported event format`. That is the peer, not a captured FreeSWITCH rejection
- `userauth`
- the 369-byte `api status` body

Framing the peer does share with the pin:

- `Content-Length` counts UTF-8 bytes
- the blank line after the headers is not part of the body
- header values use the FreeSWITCH unsafe set, so `+` becomes `%2B`
- one TCP read is not one frame
- an event already queued may be written before the reply to the next command
- order across connections is not guaranteed
- `exit` closes that connection and leaves the listener up

Faults are off unless a scenario arms one: bad password, short body, bad `Content-Length`, drop, stall, rude rejection, disconnect before reply, ack then disconnect, truncated reply, or clean EOF. The rude-rejection fault uses the captured frame shape. The short-body and bad-length fixtures stay synthetic. Truncated reply writes the reply that command would have produced, except its last byte, then closes. Clean EOF closes the socket and does not send a disconnect notice.
