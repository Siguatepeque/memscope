"""Direct-mapped cache simulation for a small memory.

The built-in sequence covers cold misses, hits, and a conflict eviction.
`submit()` adds an address for custom reads. This module has no Textual
imports, so its tests only need the standard library.
"""

from __future__ import annotations

from dataclasses import dataclass, field

NUM_BLOCKS = 16
NUM_SLOTS = 4

# The built-in program: read blocks 0-3, re-read 0-1 (hits),
# then read 4 (evicts 0), then re-read 0 (miss, it was just evicted).
SEQUENCE: tuple[int, ...] = (0, 1, 2, 3, 0, 1, 4, 0)


def slot_of(block: int, num_slots: int = NUM_SLOTS) -> int:
    """Direct-mapped slot for a block address."""
    return block % num_slots


def block_value(block: int) -> int:
    """Demo contents of a memory block (so the memory view has values)."""
    return block * 10


@dataclass
class StepResult:
    step_no: int          # 1-based position in SEQUENCE
    total: int
    address: int
    slot: int
    hit: bool
    evicted: int | None   # block that was dropped, if any
    cache_after: tuple[int | None, ...]
    kind: str             # "hit" | "miss" | "evict"
    headline: str
    detail: str


def _explain(
    address: int, slot: int, hit: bool, evicted: int | None, num_slots: int = NUM_SLOTS
) -> tuple[str, str, str]:
    rule = f"Rule: slot = block mod {num_slots}, so {address} mod {num_slots} = {slot}."
    if hit:
        return (
            "hit",
            f"HIT: block {address} was already in slot {slot}.",
            f"The CPU reads it straight from the fast cache; no trip to main memory. {rule}",
        )
    if evicted is None:
        return (
            "miss",
            f"MISS: block {address} is not in the cache yet (cold miss).",
            f"Slot {slot} was empty, so the CPU waits for main memory (slow) and keeps "
            f"a copy in slot {slot} for next time. {rule}",
        )
    return (
        "evict",
        f"MISS + EVICT: block {address} replaces block {evicted} in slot {slot}.",
        f"Slot {slot} already held block {evicted} (same slot because {evicted} mod "
        f"{num_slots} = {slot} too). The cache fits only one block per slot, so block "
        f"{evicted} is dropped and the CPU waits for memory to fetch block {address}. {rule}",
    )


@dataclass
class CacheSim:
    num_blocks: int = NUM_BLOCKS
    num_slots: int = NUM_SLOTS
    sequence: tuple[int, ...] = SEQUENCE
    slots: list[int | None] = field(default_factory=lambda: [None] * NUM_SLOTS)
    pos: int = 0  # number of accesses consumed
    history: list[StepResult] = field(default_factory=list)
    hits: int = 0
    misses: int = 0
    evictions: int = 0

    def __post_init__(self) -> None:
        if len(self.slots) != self.num_slots:
            self.slots = [None] * self.num_slots
        else:
            self.slots = list(self.slots)
        for addr in self.sequence:
            if not 0 <= addr < self.num_blocks:
                raise ValueError(f"address {addr} outside 0..{self.num_blocks - 1}")

    @property
    def done(self) -> bool:
        return self.pos >= len(self.sequence)

    def peek_next(self) -> int | None:
        return None if self.done else self.sequence[self.pos]

    def submit(self, address: int) -> StepResult:
        """Log a learner-chosen read and step it. Same treatment as `step`.

        Appends to the access log, so calling it while rewound (pos < len)
        queues the read at the end instead of reading it immediately.
        Raises ValueError with plain words for anything outside memory.
        """
        if not isinstance(address, int) or not 0 <= address < self.num_blocks:
            raise ValueError(f"Use a whole number from 0 to {self.num_blocks - 1}.")
        self.sequence = tuple(self.sequence) + (address,)
        result = self.step()
        assert result is not None
        return result

    def step(self) -> StepResult | None:
        """Advance one access. Returns None when the sequence is finished."""
        if self.done:
            return None
        address = self.sequence[self.pos]
        slot = address % self.num_slots
        current = self.slots[slot]
        hit = current == address
        evicted = None if (hit or current is None) else current
        if hit:
            self.hits += 1
        else:
            self.misses += 1
            if evicted is not None:
                self.evictions += 1
            self.slots[slot] = address
        kind, headline, detail = _explain(address, slot, hit, evicted, self.num_slots)
        result = StepResult(
            step_no=self.pos + 1,
            total=len(self.sequence),
            address=address,
            slot=slot,
            hit=hit,
            evicted=evicted,
            cache_after=tuple(self.slots),
            kind=kind,
            headline=headline,
            detail=detail,
        )
        self.history.append(result)
        self.pos += 1
        return result

    def back(self) -> StepResult | None:
        """Undo one access. Returns the new current step, or None at the start."""
        if not self.history:
            return None
        self.history.pop()
        self.pos -= 1
        last = self.history[-1] if self.history else None
        self.slots = list(last.cache_after) if last else [None] * self.num_slots
        self._recount()
        return last

    def reset(self) -> None:
        self.slots = [None] * self.num_slots
        self.pos = 0
        self.history.clear()
        self.hits = 0
        self.misses = 0
        self.evictions = 0

    def _recount(self) -> None:
        self.hits = sum(1 for r in self.history if r.hit)
        self.misses = sum(1 for r in self.history if not r.hit)
        self.evictions = sum(1 for r in self.history if r.evicted is not None)
