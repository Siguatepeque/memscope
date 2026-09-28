"""Textual TUI for memscope: a tiny memory-and-cache explorer.

Fullscreen app (inline mode is unsupported on Windows). Everything is
keyboard-operable; status is always conveyed with words + symbols, never
color alone.
"""

from __future__ import annotations

from rich import box
from rich.table import Table
from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual import events
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, Input, ProgressBar, Static

from .sim import NUM_BLOCKS, NUM_SLOTS, SEQUENCE, CacheSim, StepResult, block_value, slot_of

SIZE_OPTIONS = (2, 4, 8)

INTRO_HEADLINE = "A tiny program is about to read 8 memory blocks."
INTRO_DETAIL = (
    "Each LOAD asks the cache first. A HIT reads straight from the fast cache; "
    "a MISS waits for slow main memory and keeps a copy. "
    "Mapping rule: slot = block mod {n}, so blocks sharing a slot compete "
    "for it. Press Step (Space) to take the first access."
)
CUSTOM_INTRO_HEADLINE = "Type any block number below and press Enter."
CUSTOM_INTRO_DETAIL = (
    "Every read gets the same treatment as the demo: HIT reads the fast cache, "
    "MISS waits for slow memory and keeps a copy, EVICT drops the block that "
    "shared the slot. Mapping rule: slot = block mod {n}."
)

WELCOME_LINES = (
    "GUIDED DEMO \u2022 8 STEPS \u2022 ~2 MINUTES",
    "Goal: watch a tiny program read memory and see cache HITS, MISSES, and EVICTIONS happen.",
    "What happens: you step through 8 preset reads, one at a time. Each step explains what happened and why.",
    "Your first move: press SPACE (or click Step \u25b6, already selected).",
    "Scope: fixed 8-step demo: step, back, reset, replay. For your own numbers, press T (Try your own).",
)
CUSTOM_WELCOME_LINES = (
    "TRY YOUR OWN \u2022 TYPE ANY BLOCK 0\u201315",
    "Goal: test your hunches. Pick blocks and watch HITS, MISSES, and EVICTIONS happen.",
    "What happens: type a number below and press Enter. Every read is explained just like the demo.",
    "Back (B) undoes a read, R clears everything and starts over.",
    "Cache size: 2, 4, or 8 slots. Changing it resets everything. Press T to return to the guided demo.",
)


def _count(n: int, word: str) -> str:
    """Pluralized tally, e.g. '1 eviction' / '2 evictions'."""
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


class HelpScreen(ModalScreen):
    """Centered `?` overlay: grouped shortcuts. Esc/? closes."""

    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("question_mark", "close", "Close"),
        Binding("q", "close", "Close"),
    ]

    CSS = """
    HelpScreen {
        align: center middle;
    }
    #help-panel {
        width: auto;
        max-width: 58;
        margin: 0 2;
        height: auto;
        background: #141b2e;
        border: solid #ffb454;
        padding: 1 2;
    }
    #help-panel Static {
        height: auto;
        margin-bottom: 1;
    }
    """

    def compose(self) -> ComposeResult:
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column(style="bold #ffb454")
        table.add_column()
        table.add_row("Space / → / N", "step one access (or click Step ▶)")
        table.add_row("← / B", "step back (or click ◀ Back)")
        table.add_row("R", "reset & replay (Try-your-own: clears your reads)")
        table.add_row("T", "switch Guided demo ⇄ Try your own")
        table.add_row("Enter", "submit a typed block (Try-your-own)")
        table.add_row("2 / 4 / 8", "cache slots (resets everything)")
        table.add_row("Tab / mouse", "move focus between controls")
        table.add_row("? / Esc / Q", "close this help")
        table.add_row("Q (outside help)", "quit")
        panel = Vertical(id="help-panel")
        panel.border_title = "memscope keys"
        with panel:
            yield Static(Text("What is this?", style="bold #ffb454"))
            yield Static(
                Text(
                    "Two ways to learn. Guided demo (~2 min): a tiny program reads "
                    "8 memory blocks while the cache watches. Try your own (T): "
                    "type any block 0–15 and every read is explained the same way. "
                    "Cache size 2/4/8 changes the mapping rule: slot = block mod N."
                )
            )
            yield Static(Text("Keys", style="bold #ffb454"))
            yield Static(table)
            yield Static(Text("Evictions are marked ⇄ EVICT plus words, never color alone.", style="dim"))
            yield Static(Text("Press Esc, ?, or Q to close.", style="bold #ffb454"))

    def action_close(self) -> None:
        self.app.pop_screen()


class MemScopeApp(App):
    """Memory and cache explorer."""

    TITLE = "memscope"
    SUB_TITLE = "memory & cache explorer"

    BINDINGS = [
        Binding("space", "next", "Step"),
        Binding("right", "next", "Step"),
        Binding("n", "next", "Step"),
        Binding("left", "back", "Back"),
        Binding("b", "back", "Back"),
        Binding("r", "reset", "Reset"),
        Binding("t", "toggle_mode", "Own reads"),
        Binding("2", "size_2", "Size", show=False),
        Binding("4", "size_4", "Size", show=False),
        Binding("8", "size_8", "Size", show=False),
        Binding("question_mark", "help", "Help (?)"),
        Binding("q", "quit", "Quit"),
    ]

    CSS = """
    Screen {
        background: #0d1220;
        color: #ece7d9;
    }
    #main {
        padding: 0 1;
        overflow-y: auto;
    }
    #welcome {
        height: auto;
        border: solid #ffb454;
    }
    #welcome-text {
        height: auto;
    }
    .panel {
        background: #141b2e;
        border: solid #2b3a55;
        padding: 0 1;
        margin-bottom: 1;
    }
    #topbar {
        height: auto;
    }
    #program {
        height: auto;
        color: #c9d4ea;
    }
    #score {
        height: auto;
        color: #c9d4ea;
    }
    #views {
        height: auto;
    }
    #mem-panel, #cache-panel {
        width: 1fr;
        height: auto;
        margin-right: 1;
    }
    #cache-panel {
        margin-right: 0;
    }
    #access {
        height: auto;
    }
    #access-line {
        height: auto;
    }
    #explain {
        height: auto;
    }
    #legend {
        height: auto;
        color: #9fb0cc;
    }
    #controls {
        height: auto;
        align: center middle;
    }
    #sizes {
        height: auto;
        align: center middle;
    }
    #controls Button, #sizes Button {
        margin: 0 1;
    }
    #controls Button:focus, #sizes Button:focus {
        text-style: bold underline;
    }
    #sizes-label {
        height: auto;
        color: #9fb0cc;
        margin: 0 1;
    }
    #custom {
        height: auto;
    }
    #addr-row {
        height: auto;
    }
    #addr {
        width: 1fr;
    }
    #addr-error {
        height: auto;
        color: #fb7185;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self.mode: str = "guided"  # or "custom"
        self.num_slots: int = NUM_SLOTS
        self.sim = CacheSim()
        self.last: StepResult | None = None
        self.addr_error: str = ""

    # -- layout ---------------------------------------------------------
    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Vertical(id="main"):
            with Vertical(id="welcome", classes="panel"):
                yield Static(self._welcome_text(), id="welcome-text")
            with Vertical(id="topbar", classes="panel"):
                yield Static(self._program_text(), id="program")
                yield Static(self._score_text(), id="score")
            with Horizontal(id="views"):
                with Vertical(id="mem-panel", classes="panel"):
                    yield Static(self._memory_table(), id="memory")
                with Vertical(id="cache-panel", classes="panel"):
                    yield Static(self._cache_table(), id="cache")
            with Vertical(id="access", classes="panel"):
                yield Static(Text("Press Space to take the first access.", style="bold"), id="access-line")
                yield ProgressBar(total=len(self.sim.sequence), show_eta=False, id="progress")
            with Vertical(classes="panel", id="custom"):
                with Horizontal(id="addr-row"):
                    yield Input(placeholder="Type a block number 0-15, press Enter", id="addr")
                    yield Button("Read ▶", id="submit", variant="primary")
                yield Static("", id="addr-error")
            with Vertical(classes="panel", id="explain-wrap"):
                yield Static(self._explain_text(), id="explain")
            yield Static(
                "✓ HIT = found in cache   ✗ MISS = fetched from memory   "
                "⇄ EVICT = dropped to make room   ● = cached   ▶ = current access",
                id="legend",
            )
            with Horizontal(id="controls"):
                yield Button("◀ Back (B)", id="back")
                yield Button("Step ▶ (Space)", id="next", variant="primary")
                yield Button("Reset (R)", id="reset")
                yield Button("Try your own (T)", id="mode")
            with Horizontal(id="sizes"):
                yield Static("Cache slots:", id="sizes-label")
                yield Button("2 slots", id="size-2")
                yield Button("4 slots ✓", id="size-4", disabled=True)
                yield Button("8 slots", id="size-8")
        yield Footer()

    def on_mount(self) -> None:
        panel = self.query_one("#mem-panel", Vertical)
        panel.border_title = "Main memory: 16 blocks"
        self.query_one("#welcome", Vertical).border_title = "Start here: guided demo"
        self.query_one("#access", Vertical).border_title = "Now accessing"
        self.query_one("#custom", Vertical).border_title = "Try your own: type a block 0-15"
        self.query_one("#explain-wrap", Vertical).border_title = "What happened & why"
        self.set_focus(self.query_one("#next", Button))
        self._refresh()

    # -- actions --------------------------------------------------------
    def _modal_open(self) -> bool:
        # App-level keys (Space/N/Back/...) must not step the sim
        # while the help overlay is on top.
        return isinstance(self.screen, ModalScreen)

    def _typing(self) -> bool:
        # While the address box has focus, keys belong to it: typing
        # "8" must not reset the cache, Space must not step, etc.
        return isinstance(self.focused, Input)

    @property
    def finished(self) -> bool:
        # Only the guided demo can finish; custom reads never run out.
        return self.mode == "guided" and self.sim.done

    def _new_sim(self, sequence: tuple[int, ...]) -> None:
        self.sim = CacheSim(num_slots=self.num_slots, sequence=sequence)
        self.last = None
        self.addr_error = ""

    def action_next(self) -> None:
        if self._modal_open() or self._typing() or self.sim.done:
            return
        self.last = self.sim.step()
        assert self.last is not None
        if self.finished:
            self.notify(
                f"{_count(self.sim.hits, 'hit')}, "
                f"{_count(self.sim.misses, 'miss')}, "
                f"{_count(self.sim.evictions, 'eviction')}. Press R to replay.",
                title="Sequence finished",
                severity="information",
            )
        self._refresh()

    def action_back(self) -> None:
        if self._modal_open() or self._typing():
            return
        self.last = self.sim.back()
        self._refresh()

    def action_reset(self) -> None:
        if self._modal_open() or self._typing():
            return
        self.sim.reset()
        self.last = None
        self.addr_error = ""
        self._refresh()
        self.set_focus(self.query_one("#next", Button))

    def action_toggle_mode(self) -> None:
        if self._modal_open() or self._typing():
            return
        self._do_toggle_mode()

    def _do_toggle_mode(self) -> None:
        if self.mode == "guided":
            self.mode = "custom"
            self._new_sim(())
        else:
            self.mode = "guided"
            self._new_sim(SEQUENCE)
        self.query_one("#addr", Input).value = ""
        self._refresh()
        if self.mode == "custom":
            # Deferred: focusing the input in the same tick that reveals
            # its panel loses to the pending reflow (focus lands on Reset).
            self.set_timer(0.05, lambda: self._focus_addr())
        else:
            self.set_focus(self.query_one("#next", Button))

    def _focus_addr(self) -> None:
        if self.mode == "custom":
            self.query_one("#addr", Input).focus()

    def action_size_2(self) -> None:
        self._set_size(2)

    def action_size_4(self) -> None:
        self._set_size(4)

    def action_size_8(self) -> None:
        self._set_size(8)

    def _set_size(self, n: int) -> None:
        if self._modal_open() or self._typing() or n == self.num_slots:
            return
        self._do_set_size(n)

    def _do_set_size(self, n: int) -> None:
        self.num_slots = n
        self._new_sim(SEQUENCE if self.mode == "guided" else ())
        self._refresh()

    def _submit_addr(self) -> None:
        """Read the address box: one block per submit, plain-word errors."""
        if self._modal_open():
            return
        raw = self.query_one("#addr", Input).value.strip()
        try:
            address = int(raw)
        except ValueError:
            self.addr_error = "Use a whole number from 0 to 15."
            self._refresh()
            return
        try:
            self.last = self.sim.submit(address)
        except ValueError as exc:
            self.addr_error = str(exc)
            self._refresh()
            return
        self.addr_error = ""
        self.query_one("#addr", Input).value = ""
        self._refresh()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "addr":
            self._submit_addr()

    def action_help(self) -> None:
        if self._typing():
            return
        self.push_screen(HelpScreen())

    def on_resize(self, event: events.Resize) -> None:
        # Narrow terminals: stack memory/cache vertically (a side-by-side
        # row would clip) and hide the secondary legend strip.
        try:
            narrow = event.size.width < 90
            self.query_one("#legend").display = not narrow
            self.query_one("#views").styles.layout = "vertical" if narrow else "horizontal"
        except Exception:
            return

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "next":
            self.action_next()
        elif event.button.id == "back":
            self.action_back()
        elif event.button.id == "reset":
            self.action_reset()
        elif event.button.id == "mode":
            self._do_toggle_mode()
        elif event.button.id == "submit":
            self._submit_addr()
        elif event.button.id in ("size-2", "size-4", "size-8"):
            self._do_set_size(int(event.button.id.split("-")[1]))

    # -- rendering ------------------------------------------------------
    def _refresh(self) -> None:
        guided = self.mode == "guided"
        self.query_one("#welcome-text", Static).update(self._welcome_text())
        self.query_one("#welcome").display = self.last is None
        self.query_one("#topbar", Vertical).border_title = (
            "Tiny program + scoreboard" if guided else "Your reads + scoreboard"
        )
        self.query_one("#cache-panel", Vertical).border_title = (
            f"Cache: {self.num_slots} slots, direct-mapped"
        )
        self.query_one("#custom").display = not guided
        self.query_one("#addr-error", Static).update(
            Text(self.addr_error, style="bold") if self.addr_error else Text("")
        )
        self.query_one("#program", Static).update(self._program_text())
        self.query_one("#score", Static).update(self._score_text())
        self.query_one("#memory", Static).update(self._memory_table())
        self.query_one("#cache", Static).update(self._cache_table())
        self.query_one("#access-line", Static).update(self._access_text())
        self.query_one("#explain", Static).update(self._explain_text())
        self.query_one("#progress", ProgressBar).update(
            total=max(1, len(self.sim.sequence)), progress=self.sim.pos
        )
        next_btn = self.query_one("#next", Button)
        back_btn = self.query_one("#back", Button)
        # Snapshot focus BEFORE flipping disabled flags: disabling the
        # focused widget synchronously moves focus elsewhere.
        was_next_focused = self.focused is next_btn
        next_btn.disabled = self.sim.done
        back_btn.disabled = not self.sim.history
        if not guided and self.sim.done:
            next_btn.label = "Type a number (Enter)"
        elif self.sim.done:
            next_btn.label = "Done: Reset (R)"
        elif not self.sim.history:
            next_btn.label = "\u25b6 Start: Step (Space)"
        else:
            next_btn.label = "Step \u25b6 (Space)"
        self.query_one("#mode", Button).label = (
            "Try your own (T)" if guided else "Guided demo (T)"
        )
        for n in SIZE_OPTIONS:
            btn = self.query_one(f"#size-{n}", Button)
            btn.disabled = n == self.num_slots
            btn.label = f"{n} slots \u2713" if n == self.num_slots else f"{n} slots"
        # Never strand focus on a button that just became disabled. Deferred
        # via a short timer so it runs after Textual's own focus fixup,
        # which otherwise parks focus on the nearest sibling (Back).
        if next_btn.disabled and was_next_focused:
            self.set_timer(0.05, lambda: self._focus_reset())
        elif guided and not self.sim.history and self.focused is not next_btn:
            # Fresh start: the welcome panel promises Step is selected.
            self.set_timer(0.05, lambda: self._focus_next())

    def _focus_reset(self) -> None:
        self.query_one("#reset", Button).focus()

    def _focus_next(self) -> None:
        next_btn = self.query_one("#next", Button)
        if not next_btn.disabled:
            next_btn.focus()

    def _welcome_text(self) -> Text:
        t = Text()
        lines = WELCOME_LINES if self.mode == "guided" else CUSTOM_WELCOME_LINES
        for i, line in enumerate(lines):
            if i:
                t.append("\n")
            if i == 0:
                style = "bold #ffb454"
            elif i == 3:
                style = "bold"
            elif i == 4:
                style = "dim"
            else:
                style = ""
            t.append(line, style=style)
        return t

    def _program_text(self) -> Text:
        t = Text()
        if self.mode == "guided":
            t.append("program:  ", style="bold #ffb454")
        else:
            t.append("your reads:  ", style="bold #ffb454")
        if not self.sim.sequence:
            t.append("(none yet, type a number below and press Enter)", style="dim")
            return t
        for i, addr in enumerate(self.sim.sequence):
            if i < self.sim.pos:
                style = "dim"
            elif i == self.sim.pos and not self.sim.done:
                style = "bold reverse"
            else:
                style = ""
            t.append(f" {addr} ", style=style)
        t.append(f"   step {self.sim.pos}/{len(self.sim.sequence)}", style="dim")
        return t

    def _score_text(self) -> Text:
        t = Text()
        t.append("score:  ", style="bold #ffb454")
        t.append(f"✓ Hits {self.sim.hits}   ", style="bold #4ade80")
        t.append(f"✗ Misses {self.sim.misses}   ", style="bold #fb7185")
        t.append(f"⇄ Evictions {self.sim.evictions}", style="bold #facc15")
        return t

    def _memory_table(self) -> Table:
        grid = Table.grid(padding=(0, 2))
        for _ in range(4):
            grid.add_column(justify="center")
        cached = set(b for b in self.sim.slots if b is not None)
        current = self.last.address if self.last else self.sim.peek_next()
        cells: list[Text] = []
        for b in range(NUM_BLOCKS):
            marker = " ●" if b in cached else ""
            cell = Text(f"[{b:2d}] {block_value(b):<3d}{marker}")
            if self.last is not None and b == self.last.address:
                cell.stylize("bold reverse")
                cell.append(" ▶")
            elif b == current and self.last is None:
                cell.stylize("bold #ffb454")
                cell.append(" ▶")
            elif b in cached:
                cell.stylize("bold #4ade80")
            else:
                cell.stylize("dim")
            cells.append(cell)
        for row in range(4):
            grid.add_row(*cells[row * 4 : row * 4 + 4])
        return grid

    def _cache_table(self) -> Table:
        table = Table(
            "slot",
            "block",
            "status",
            box=box.SIMPLE,
            show_edge=False,
            padding=(0, 1),
            header_style="bold #ffb454",
        )
        active_slot = self.last.slot if self.last else None
        for s in range(self.sim.num_slots):
            held = self.sim.slots[s]
            if held is None:
                block_cell: Text | str = Text("— empty —", style="dim")
                status = ""
            else:
                block_cell = Text(f"{held}  (val {block_value(held)})")
                if s == active_slot and self.last is not None:
                    if self.last.hit:
                        status = "\u2190 HIT here"
                    elif self.last.evicted is None:
                        status = "\u2190 just loaded"
                    else:
                        status = f"\u2190 just loaded, evicted {self.last.evicted}"
                else:
                    status = ""
            row_style = "bold reverse" if s == active_slot and self.last is not None else ""
            table.add_row(f"{s}", block_cell, status, style=row_style)
        return table

    def _access_text(self) -> Text:
        if self.last is None:
            if self.mode == "custom":
                if not self.sim.sequence:
                    return Text(
                        "Type a block number 0\u201315 below, then press Enter.",
                        style="bold",
                    )
                return Text(
                    "Press Space to replay your reads, or type a number below to add another.",
                    style="bold",
                )
            nxt = self.sim.peek_next()
            return Text(
                f"\u25ba START HERE: press SPACE (or click the highlighted Step button). "
                f"Next up: LOAD block {nxt}.",
                style="bold",
            )
        r = self.last
        t = Text()
        t.append(f"Access {r.step_no}/{r.total} · LOAD block {r.address}  →  ", style="bold")
        if r.kind == "hit":
            t.append(" ✓ HIT ", style="bold black on #4ade80")
        elif r.kind == "miss":
            t.append(" ✗ MISS ", style="bold black on #fb7185")
        else:
            t.append(
                f" ✗ MISS + ⇄ EVICT (block {r.evicted}) ",
                style="bold black on #facc15",
            )
        if self.finished:
            t.append("   · finished (R replays)", style="dim")
        return t

    def _explain_text(self) -> Text:
        t = Text()
        if self.last is None:
            if self.mode == "custom":
                t.append(CUSTOM_INTRO_HEADLINE + "\n", style="bold #ffb454")
                t.append(CUSTOM_INTRO_DETAIL.format(n=self.num_slots))
            else:
                t.append(INTRO_HEADLINE + "\n", style="bold #ffb454")
                t.append(INTRO_DETAIL.format(n=self.num_slots))
            return t
        r = self.last
        t.append(r.headline + "\n", style="bold #ffb454")
        t.append(r.detail)
        if self.finished:
            t.append(
                f"\nFinal: {_count(self.sim.hits, 'hit')}, "
                f"{_count(self.sim.misses, 'miss')}, "
                f"{_count(self.sim.evictions, 'eviction')}. The two re-reads hit, block 4 "
                "knocked block 0 out, and the last read paid for it. Press R to replay.",
                style="bold",
            )
        return t


def main() -> None:
    """Entry point for the `memscope` console script. Import-safe."""
    MemScopeApp().run()


if __name__ == "__main__":
    main()
