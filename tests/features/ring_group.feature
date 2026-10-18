Feature: Ring group
  A ring group originates through the inbound ESL simulator and answers only
  after the channel wait is registered.

  Scenario: parallel ring answers one callee
    When a parallel ring group calls three destinations and the second answers
    Then the answered channel is that second parallel destination
    And the other parallel legs are hung up

  Scenario: parallel ring when nobody answers
    When a parallel ring group calls two destinations and nobody answers
    Then no channel answered
    And every originated leg was hung up

  Scenario: sequential ring answers the first destination
    When a sequential ring group calls three destinations and the first answers
    Then the answered channel is that first sequential destination
    And only one sequential leg was originated

  Scenario: sequential ring answers the second destination
    When a sequential ring group calls two destinations and the second answers
    Then the answered channel is that second sequential destination
    And the first sequential leg was hung up

  Scenario: sequential ring when nobody answers
    When a sequential ring group calls two destinations and nobody answers
    Then no channel answered
    And every originated leg was hung up

  Scenario: ring group passes variables
    When a parallel ring group calls one destination with variables and it answers
    Then the originate command contains the variable
    And the answered channel is that variable destination

  Scenario: ring group uses a load balancer
    When a balancing ring group calls three destinations and the selected one answers
    Then the load balancer counted that destination during the call
    And the load balancer released that destination after the answer

  Scenario: load balancer shares a destination across groups
    When two balancing ring groups share a destination and each selected leg answers
    Then each shared-destination call was counted and then released

  Scenario: ring group timeout configuration
    When a parallel ring group uses a short timeout and nobody answers
    Then no channel answered
    And the short timeout elapsed inside the production bound
