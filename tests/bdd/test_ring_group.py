"""RingGroup scenarios against the loopback ESL simulator."""

import asyncio
import re
from pathlib import Path
from typing import Any, List, Optional, Sequence, Set

from pytest_bdd import scenarios, then, when

from genesis import Inbound, InMemoryLoadBalancer, RingGroup, RingMode

from tests.bdd.world import World

FEATURE = Path(__file__).resolve().parents[1] / "features" / "ring_group.feature"
scenarios(str(FEATURE))

_ORIGINATION = re.compile(r"origination_uuid=([0-9a-fA-F-]+)")


class RecordingInbound(Inbound):
    """Counts public ``on`` registrations for ``CHANNEL_ANSWER``."""

    def __init__(self, host: str, port: int, password: str) -> None:
        super().__init__(host, port, password)
        self.answer_registrations = 0
        self.answer_registered: asyncio.Queue[int] = asyncio.Queue()

    def on(self, key: str, handler: Any) -> None:
        super().on(key, handler)
        if key != "CHANNEL_ANSWER":
            return
        self.answer_registrations += 1
        self.answer_registered.put_nowait(self.answer_registrations)


def originated_uuids(world: World) -> List[str]:
    found: List[str] = []
    for item in world.journal.commands():
        if "api originate " not in item.text:
            continue
        match = _ORIGINATION.search(item.text)
        if match is not None:
            found.append(match.group(1))
    return found


async def _emit_answered(world: World, channel_uuid: str) -> None:
    await world.server.emit(
        (
            ("Event-Name", "CHANNEL_STATE"),
            ("Channel-State", "CS_EXECUTE"),
            ("Unique-ID", channel_uuid),
        )
    )
    await world.server.emit(
        (
            ("Event-Name", "CHANNEL_ANSWER"),
            ("Channel-State", "CS_EXECUTE"),
            ("Unique-ID", channel_uuid),
        )
    )


async def _answer_parallel(
    world: World, client: RecordingInbound, size: int, index: int
) -> None:
    while True:
        count = await client.answer_registered.get()
        if count < size:
            continue
        uuids = originated_uuids(world)
        if len(uuids) < size:
            raise AssertionError("originate journal is shorter than the group")
        await _emit_answered(world, uuids[index])
        return


async def _answer_matching(
    world: World,
    client: RecordingInbound,
    dial_paths: Set[str],
    counts: Optional[List[tuple[str, int]]],
    stop: asyncio.Event,
) -> None:
    while not stop.is_set():
        waiter = asyncio.create_task(client.answer_registered.get())
        halted = asyncio.create_task(stop.wait())
        done, pending_tasks = await asyncio.wait(
            {waiter, halted}, return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending_tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        if waiter not in done:
            return
        uuids = originated_uuids(world)
        if not uuids:
            continue
        channel_uuid = uuids[-1]
        dial = world.server.channels.get(channel_uuid, "")
        if dial not in dial_paths:
            continue
        balancer = world.facts.get("balancer")
        if balancer is not None and counts is not None:
            counts.append((dial, await balancer.get_count(dial)))
        await _emit_answered(world, channel_uuid)


async def _stop_driver(driver: asyncio.Task[None]) -> None:
    if driver.done():
        await driver
        return
    driver.cancel()
    try:
        await driver
    except asyncio.CancelledError:
        pass


async def _ring(
    world: World,
    group: Sequence[str],
    mode: RingMode,
    timeout: float,
    variables: Optional[dict[str, str]] = None,
    balancer: Optional[InMemoryLoadBalancer] = None,
    client: Optional[Inbound] = None,
) -> None:
    started = asyncio.get_running_loop().time()
    if client is None:
        client = Inbound(world.server.host, world.server.port, world.server.password)
    async with client:
        answered = await RingGroup.ring(
            client,
            list(group),
            mode,
            timeout=timeout,
            variables=variables,
            balancer=balancer,
        )
    world.facts["answered"] = answered
    world.facts["elapsed"] = asyncio.get_running_loop().time() - started
    world.facts["channels"] = originated_uuids(world)
    world.facts["hangups"] = [uuid for uuid, _cause in world.server.hangups]
    if isinstance(client, RecordingInbound):
        world.facts["answer_registrations"] = client.answer_registrations


@when(
    "a parallel ring group calls three destinations and the second answers",
    target_fixture="ring",
)
def parallel_second_answers(world: World) -> World:
    async def _body() -> World:
        group = ["user/1001", "user/1002", "user/1003"]
        client = RecordingInbound(
            world.server.host, world.server.port, world.server.password
        )
        driver = asyncio.create_task(_answer_parallel(world, client, len(group), 1))
        try:
            await _ring(world, group, RingMode.PARALLEL, 2.0, client=client)
        finally:
            await _stop_driver(driver)
        world.facts["group"] = group
        assert world.facts["answer_registrations"] == len(group)
        return world

    return world.run(_body())


@then("the answered channel is that second parallel destination")
def answered_is_second_parallel(ring: World) -> None:
    answered = ring.facts["answered"]
    channels = ring.facts["channels"]
    assert answered is not None
    assert answered.uuid == channels[1]


@then("the other parallel legs are hung up")
def other_parallel_legs_hung_up(ring: World) -> None:
    channels = ring.facts["channels"]
    hangups = ring.facts["hangups"]
    assert channels[0] in hangups
    assert channels[2] in hangups
    assert channels[1] not in hangups


@when(
    "a parallel ring group calls two destinations and nobody answers",
    target_fixture="ring",
)
def parallel_nobody(world: World) -> World:
    async def _body() -> World:
        await _ring(world, ["user/1001", "user/1002"], RingMode.PARALLEL, 0.2)
        return world

    return world.run(_body())


@then("no channel answered")
def nobody_answered(ring: World) -> None:
    assert ring.facts["answered"] is None


@then("every originated leg was hung up")
def every_leg_hung_up(ring: World) -> None:
    channels = ring.facts["channels"]
    hangups = ring.facts["hangups"]
    assert channels
    assert all(uuid in hangups for uuid in channels)


@when(
    "a sequential ring group calls three destinations and the first answers",
    target_fixture="ring",
)
def sequential_first(world: World) -> World:
    async def _body() -> World:
        group = ["user/1001", "user/1002", "user/1003"]
        client = RecordingInbound(
            world.server.host, world.server.port, world.server.password
        )
        stop = asyncio.Event()
        driver = asyncio.create_task(
            _answer_matching(world, client, {group[0]}, None, stop)
        )
        try:
            await _ring(world, group, RingMode.SEQUENTIAL, 2.0, client=client)
        finally:
            stop.set()
            await _stop_driver(driver)
        assert world.facts["answer_registrations"] == 1
        return world

    return world.run(_body())


@then("the answered channel is that first sequential destination")
def answered_is_first_sequential(ring: World) -> None:
    answered = ring.facts["answered"]
    assert answered is not None
    assert answered.uuid == ring.facts["channels"][0]


@then("only one sequential leg was originated")
def only_one_sequential_leg(ring: World) -> None:
    assert len(ring.facts["channels"]) == 1


@when(
    "a sequential ring group calls two destinations and the second answers",
    target_fixture="ring",
)
def sequential_second(world: World) -> World:
    async def _body() -> World:
        group = ["user/1001", "user/1002"]
        client = RecordingInbound(
            world.server.host, world.server.port, world.server.password
        )
        stop = asyncio.Event()
        driver = asyncio.create_task(
            _answer_matching(world, client, {group[1]}, None, stop)
        )
        try:
            await _ring(world, group, RingMode.SEQUENTIAL, 0.5, client=client)
        finally:
            stop.set()
            await _stop_driver(driver)
        world.facts["first"] = world.facts["channels"][0]
        assert world.facts["answer_registrations"] == 2
        return world

    return world.run(_body())


@then("the answered channel is that second sequential destination")
def answered_is_second_sequential(ring: World) -> None:
    answered = ring.facts["answered"]
    channels = ring.facts["channels"]
    assert answered is not None
    assert answered.uuid == channels[1]


@then("the first sequential leg was hung up")
def first_sequential_hung_up(ring: World) -> None:
    assert ring.facts["first"] in ring.facts["hangups"]


@when(
    "a sequential ring group calls two destinations and nobody answers",
    target_fixture="ring",
)
def sequential_nobody(world: World) -> World:
    async def _body() -> World:
        await _ring(world, ["user/1001", "user/1002"], RingMode.SEQUENTIAL, 0.2)
        return world

    return world.run(_body())


@when(
    "a parallel ring group calls one destination with variables and it answers",
    target_fixture="ring",
)
def ring_with_variables(world: World) -> World:
    async def _body() -> World:
        group = ["user/1001"]
        client = RecordingInbound(
            world.server.host, world.server.port, world.server.password
        )
        driver = asyncio.create_task(_answer_parallel(world, client, len(group), 0))
        try:
            await _ring(
                world,
                group,
                RingMode.PARALLEL,
                2.0,
                variables={"custom_var": "test_value"},
                client=client,
            )
        finally:
            await _stop_driver(driver)
        assert world.facts["answer_registrations"] == 1
        return world

    return world.run(_body())


@then("the originate command contains the variable")
def originate_contains_variable(ring: World) -> None:
    commands = [item.text for item in ring.journal.commands()]
    assert any("custom_var=test_value" in command for command in commands)


@then("the answered channel is that variable destination")
def answered_variable_destination(ring: World) -> None:
    answered = ring.facts["answered"]
    assert answered is not None
    assert answered.uuid == ring.facts["channels"][0]


@when(
    "a balancing ring group calls three destinations and the selected one answers",
    target_fixture="ring",
)
def balancing_answers(world: World) -> World:
    async def _body() -> World:
        group = ["user/1001", "user/1002", "user/1003"]
        balancer = InMemoryLoadBalancer()
        world.facts["balancer"] = balancer
        counts: List[tuple[str, int]] = []
        client = RecordingInbound(
            world.server.host, world.server.port, world.server.password
        )
        stop = asyncio.Event()
        driver = asyncio.create_task(
            _answer_matching(world, client, {group[0]}, counts, stop)
        )
        try:
            await _ring(
                world, group, RingMode.BALANCING, 2.0, balancer=balancer, client=client
            )
        finally:
            stop.set()
            await _stop_driver(driver)
        world.facts["during"] = counts
        world.facts["after"] = await balancer.get_count(group[0])
        assert world.facts["answer_registrations"] == 1
        return world

    return world.run(_body())


@then("the load balancer counted that destination during the call")
def balancer_counted(ring: World) -> None:
    during = ring.facts["during"]
    assert during == [("user/1001", 1)]


@then("the load balancer released that destination after the answer")
def balancer_released(ring: World) -> None:
    assert ring.facts["after"] == 0
    answered = ring.facts["answered"]
    assert answered is not None
    assert answered.dial_path == "user/1001"


@when(
    "two balancing ring groups share a destination and each selected leg answers",
    target_fixture="ring",
)
def shared_destination(world: World) -> World:
    async def _body() -> World:
        balancer = InMemoryLoadBalancer()
        world.facts["balancer"] = balancer
        counts: List[tuple[str, int]] = []
        client = RecordingInbound(
            world.server.host, world.server.port, world.server.password
        )
        stop = asyncio.Event()
        driver = asyncio.create_task(
            _answer_matching(world, client, {"user/1001", "user/1002"}, counts, stop)
        )
        try:
            async with client:
                first = await RingGroup.ring(
                    client,
                    ["user/1001", "user/1002"],
                    RingMode.BALANCING,
                    timeout=2.0,
                    balancer=balancer,
                )
                first_after = await balancer.get_count("user/1001")
                second = await RingGroup.ring(
                    client,
                    ["user/1002", "user/1003"],
                    RingMode.BALANCING,
                    timeout=2.0,
                    balancer=balancer,
                )
                second_after = await balancer.get_count("user/1002")
        finally:
            stop.set()
            await _stop_driver(driver)
        idle = {
            dest: await balancer.get_count(dest)
            for dest in ("user/1001", "user/1003")
            if dest
            not in {
                getattr(first, "dial_path", None),
                getattr(second, "dial_path", None),
            }
        }
        world.facts["shared"] = {
            "during": counts,
            "first_after": first_after,
            "second_after": second_after,
            "first": getattr(first, "dial_path", None),
            "second": getattr(second, "dial_path", None),
            "idle": idle,
        }
        assert client.answer_registrations == 2
        return world

    return world.run(_body())


@then("each shared-destination call was counted and then released")
def shared_counts(ring: World) -> None:
    shared = ring.facts["shared"]
    assert shared["first"] == "user/1001"
    assert shared["second"] == "user/1002"
    assert ("user/1001", 1) in shared["during"]
    assert ("user/1002", 1) in shared["during"]
    assert shared["first_after"] == 0
    assert shared["second_after"] == 0
    assert all(count == 0 for count in shared["idle"].values())


@when(
    "a parallel ring group uses a short timeout and nobody answers",
    target_fixture="ring",
)
def short_timeout(world: World) -> World:
    async def _body() -> World:
        await _ring(world, ["user/1001"], RingMode.PARALLEL, 0.2)
        return world

    return world.run(_body())


@then("the short timeout elapsed inside the production bound")
def timeout_bound(ring: World) -> None:
    elapsed = ring.facts["elapsed"]
    assert 0.15 <= elapsed <= 0.5
