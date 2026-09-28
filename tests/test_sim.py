"""Stdlib-only check for the core cache simulation (no Textual needed)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from memscope.sim import NUM_BLOCKS, NUM_SLOTS, SEQUENCE, CacheSim, slot_of


class TestCacheSim(unittest.TestCase):
    def test_slot_rule(self):
        for block in range(16):
            self.assertEqual(slot_of(block), block % NUM_SLOTS)

    def test_story_arc(self):
        """4 cold misses, 2 hits, evicting miss, consequence miss."""
        sim = CacheSim()
        kinds = [sim.step().kind for _ in range(len(SEQUENCE))]
        self.assertEqual(
            kinds,
            ["miss", "miss", "miss", "miss", "hit", "hit", "evict", "evict"],
        )

    def test_eviction_details(self):
        sim = CacheSim()
        for _ in range(6):
            sim.step()
        evicting = sim.step()
        self.assertEqual((evicting.address, evicting.slot, evicting.evicted), (4, 0, 0))
        consequence = sim.step()
        self.assertEqual((consequence.address, consequence.slot, consequence.evicted), (0, 0, 4))

    def test_scoreboard(self):
        sim = CacheSim()
        while not sim.done:
            sim.step()
        self.assertEqual((sim.hits, sim.misses, sim.evictions), (2, 6, 2))

    def test_back_and_reset(self):
        sim = CacheSim()
        sim.step()
        sim.step()
        sim.back()
        self.assertEqual(sim.pos, 1)
        self.assertEqual(sim.slots[1], None)  # second access undone
        sim.reset()
        self.assertEqual((sim.pos, sim.hits, sim.misses), (0, 0, 0))
        self.assertEqual(sim.slots, [None] * NUM_SLOTS)

    def test_explanations_are_friendly(self):
        sim = CacheSim()
        while not sim.done:
            r = sim.step()
            self.assertTrue(r.headline and r.detail)
            self.assertIn("mod", r.detail)  # mapping rule always stated

    def test_custom_submit_flow(self):
        """Learner-typed reads get the same hit/miss/evict treatment."""
        sim = CacheSim(sequence=())
        self.assertTrue(sim.done)  # nothing queued yet
        first = sim.submit(3)
        self.assertEqual((first.kind, first.slot, first.evicted), ("miss", 3, None))
        second = sim.submit(3)
        self.assertEqual(second.kind, "hit")
        third = sim.submit(7)  # 7 % 4 == 3: knocks out block 3
        self.assertEqual((third.kind, third.evicted), ("evict", 3))
        self.assertEqual((sim.hits, sim.misses, sim.evictions), (1, 2, 1))

    def test_custom_back_and_reset(self):
        sim = CacheSim(sequence=())
        sim.submit(5)
        sim.submit(5)
        sim.back()
        self.assertEqual((sim.pos, sim.hits), (1, 0))
        self.assertEqual(sim.slots[1], 5)
        sim.reset()  # typed reads stay queued, so R replays them
        self.assertEqual((sim.pos, sim.hits, sim.misses), (0, 0, 0))
        self.assertEqual(len(sim.sequence), 2)
        replayed = sim.step()
        self.assertEqual((replayed.address, replayed.kind), (5, "miss"))

    def test_each_slot_count(self):
        """Mapping rule holds for the 2/4/8 size choices."""
        for n in (2, 4, 8):
            with self.subTest(slots=n):
                for block in range(NUM_BLOCKS):
                    self.assertEqual(slot_of(block, n), block % n)
                sim = CacheSim(num_slots=n, sequence=(0, n))
                self.assertEqual(sim.step().kind, "miss")
                evicting = sim.step()
                self.assertEqual((evicting.slot, evicting.evicted), (0, 0))
                self.assertEqual(sim.evictions, 1)

    def test_eight_slots_fit_demo_blocks(self):
        sim = CacheSim(num_slots=8, sequence=tuple(range(8)))
        kinds = [sim.step().kind for _ in range(8)]
        self.assertEqual(kinds, ["miss"] * 8)  # no conflicts, no evictions
        self.assertEqual(sim.submit(0).kind, "hit")

    def test_evict_rule_uses_live_slot_count(self):
        sim = CacheSim(num_slots=2, sequence=(0, 2))
        sim.step()
        second = sim.step()
        self.assertIn("2 mod 2 = 0", second.detail)  # the new block's slot
        self.assertIn("0 mod 2 = 0", second.detail)  # the evicted block's slot

    def test_invalid_submit_rejected_plainly(self):
        sim = CacheSim(sequence=())
        for bad in (-1, NUM_BLOCKS, "3", 3.5, None):
            with self.subTest(address=bad):
                with self.assertRaises(ValueError) as ctx:
                    sim.submit(bad)
                self.assertIn(f"0 to {NUM_BLOCKS - 1}", str(ctx.exception))
        small = CacheSim(num_blocks=10, sequence=())
        with self.assertRaises(ValueError) as ctx:
            small.submit(10)
        self.assertIn("0 to 9", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
