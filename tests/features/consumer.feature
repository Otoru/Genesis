Feature: Consumer
  The consumer asks for every plain event, adds one filter per handler,
  and delivers the matching event.

  Scenario: HEARTBEAT subscription
    When a consumer handles HEARTBEAT
    Then the heartbeat handler ran
    And the journal shows the HEARTBEAT filter

  Scenario: CUSTOM sofia register
    When a consumer handles the custom subclass sofia register
    Then the handler received subclass sofia::register
    And the journal shows the subclass filter for sofia::register

  Scenario: BACKGROUND_JOB result
    When a consumer handles BACKGROUND_JOB
    Then the handler received the originate job result
    And the journal shows the BACKGROUND_JOB filter

  Scenario: CUSTOM mod audio stream play
    When a consumer handles the custom subclass mod audio stream play
    Then the handler received the audio stream play body
    And the journal shows the subclass filter for mod_audio_stream::play
