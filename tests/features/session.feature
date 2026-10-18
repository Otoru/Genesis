Feature: Session and outbound
  Outbound pilots use an explicit full socket. Genesis still sends
  event plain all when events stay at the default, and a non-full peer
  rejects that command.

  Scenario: specific DTMF digit
    When a session listens for DTMF digit 1
    Then only that digit was delivered

  Scenario: wildcard DTMF
    When a session listens for every DTMF digit
    Then every DTMF digit was delivered

  Scenario: several DTMF handlers
    When a session has handlers for DTMF digits 1 and 2
    Then each DTMF handler ran once

  Scenario: wait returns the digit
    When a session waits for a DTMF event
    Then the wait returned digit 1

  Scenario: wait times out
    When a session waits for DTMF and no digit is emitted
    Then the DTMF wait timed out

  Scenario: wait honors on_dtmf
    When a session waits for DTMF and also handles digit 1
    Then the wait and the digit handler both saw 1

  Scenario: wait runs multiple handlers
    When a session waits for DTMF with handlers for 1 and 2 and digit 1 arrives
    Then only the handler for digit 1 ran

  Scenario: session exposes context
    When an outbound session is connected in full mode
    Then the context has the live connect fields

  Scenario: answer
    When the session answers the channel
    Then sendmsg was execute answer

  Scenario: park
    When the session parks the channel
    Then sendmsg was execute park

  Scenario: hangup
    When the session hangs up the channel
    Then sendmsg was execute hangup

  Scenario: sendmsg parameters
    When the session sends several sendmsg parameter sets
    Then each sendmsg parameter set was passed through

  Scenario: handler options and filter
    When an outbound handler asks for events and linger on a full peer
    Then the journal shows filter and event plain all

  Scenario: session helpers
    When the session uses log playback say and play_and_get_digits
    Then those helper applications were requested

  Scenario: blocking execute completes
    When a blocking playback completes with the same Application-UUID
    Then the playback result is that execute complete event

  Scenario: blocking execute times out
    When a blocking playback is given a short timeout and no complete event
    Then the blocking playback timed out
