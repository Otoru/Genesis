Feature: Connection recovery
  A lost ESL socket stops the local flow. The application does not retry
  that command and does not open another socket. Hanging up afterwards
  is a new Inbound, aimed at the call seeded before the drop. A missing
  call raises ChannelNotFound and the application stops.

  Scenario: lost connection stops the local flow
    When the local flow loses the connection before the reply
    Then the flow stopped after ConnectionLost
    And the journal has no retry and no reconnect

  Scenario: new inbound hangs up the surviving call
    When a new inbound hangs up the seeded call after the connection drop
    Then that seeded call was hung up
    And the journal has no retry of the lost command

  Scenario: missing call ends the application
    When a new inbound asks for a missing call
    Then the application ended on ChannelNotFound
    And the journal has one connection and no hangup
