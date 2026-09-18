# /// script
# requires-python = ">=3.10"
# dependencies = ["textual==1.0.0"]
# ///
"""A clickable, two-level progress board for a plan tracked in TASKS.md.

Two expandable layers: the phase (the larger step) and, inside it, each task —
which opens to show the detail recorded in the companion history file. Expanding
works with the mouse (click the title) and with the keyboard (arrows to move,
right to open, left to close, Enter to toggle).

The file is watched and the board refreshes itself when the plan changes, keeping
whatever the reader had expanded or collapsed.

Run it (dependencies live in the PEP 723 header above; uv resolves them into its
own cache, nothing is installed system-wide):

    uv run claude-tasks.py [path/to/TASKS.md]

Keys: up/down move · right opens · left closes · Enter toggles · a expands all ·
c collapses all · r reloads · q quits
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from rich.markup import escape
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.reactive import reactive
from textual.widgets import Collapsible, Footer, Label, Static
from textual.widgets._collapsible import CollapsibleTitle

# TASKS.md is the convention; TRILHA.md is accepted so a repository that
# started on the older name keeps working.
BOARD_NAMES = ("TASKS.md", "TRILHA.md")

# Where the long-form detail lives. The first one that exists wins, so a project
# can name it in its own language.
DETAIL_NAMES = (
    Path("docs") / "historico-implementacao.md",
    Path("docs") / "task-details.md",
)

# The board's vocabulary. A section title that starts with one of these is an
# action section (decisions, blockers, debts) rather than a phase: it never
# starts collapsed, and its items may omit the icon because the icon is already
# in the title. Detecting it by icon instead of by section name keeps the board
# working in any language.
ICONS = ("✅", "▶️", "⬜", "⛔", "❓")
_ICON_GROUP = "|".join(ICONS)

SECTION = re.compile(r"^##\s+(.*)$")
ITEM = re.compile(rf"^\s*-\s+({_ICON_GROUP})\s*(.*)$")
ITEM_PLAIN = re.compile(rf"^\s*-\s+(?!{_ICON_GROUP})(.+)$")
LEADING_ICON = re.compile(rf"^({_ICON_GROUP})")

# A task line starts with its number: "12 · Ported the shell". The number is
# what links the board to the detail.
TASK_NUMBER = re.compile(r"^(\d+)\s*[·.\-)]")

# In the history file each task is "<icon> **Task N — title**" followed by its
# detail. No end anchor on purpose: the title may carry a trailing note such as
# "**Task 16 — ...** *(under review)*", and anchoring left that task with no
# detail at all.
HISTORY_TASK = re.compile(rf"^(?:{_ICON_GROUP})\s+\*\*Task\s+(\d+)\s*[—-]\s*(.*?)\*\*")

CSS_CLASS = {
    "✅": "done",
    "▶️": "running",
    "⬜": "todo",
    "⛔": "blocked",
    "❓": "decide",
}

# A bright band, this many characters wide, sweeps left-to-right over a
# running item's text and loops. SHIMMER_COLORS goes dim -> bright -> dim so
# the band has a soft edge instead of a hard cutoff.
SHIMMER_COLORS = ("#c9812f", "#e6a24a", "#f7c873", "#fff3d6", "#f7c873", "#e6a24a", "#c9812f")
SHIMMER_BASE = "#c9812f"
SHIMMER_WIDTH = len(SHIMMER_COLORS)
SHIMMER_FPS = 15


def shimmer_markup(text: str, frame: int) -> str:
    """`text` with a moving bright band, as Rich console markup.

    The band travels past both ends of the string before looping, so the
    glow visibly enters from the left and exits on the right rather than
    jumping back.
    """
    period = len(text) + SHIMMER_WIDTH
    center = (frame % period) - SHIMMER_WIDTH
    out: list[str] = []
    for i, ch in enumerate(text):
        offset = i - center
        color = SHIMMER_COLORS[offset] if 0 <= offset < SHIMMER_WIDTH else SHIMMER_BASE
        out.append(f"[bold {color}]{escape(ch)}[/]")
    return "".join(out)


def find_board(argv: list[str]) -> Path:
    """Locate the board file so the script can live anywhere.

    Order: the path given on the command line, then the current directory and
    its parents. Deliberately not derived from `__file__`: installed as a skill,
    this script sits outside the repository it reports on.
    """
    if len(argv) > 1:
        given = Path(argv[1]).expanduser().resolve()
        if not given.is_file():
            raise SystemExit(f"no board file at {given}")
        return given

    here = Path.cwd().resolve()
    for directory in [here, *here.parents]:
        for name in BOARD_NAMES:
            candidate = directory / name
            if candidate.is_file():
                return candidate

    raise SystemExit(
        f"no {BOARD_NAMES[0]} in the current directory or any parent.\n"
        f"Pass one: claude-tasks.py <path-to-board>"
    )


def find_detail_file(board: Path) -> Path | None:
    for name in DETAIL_NAMES:
        candidate = board.parent / name
        if candidate.is_file():
            return candidate
    return None


def read_details(path: Path | None) -> dict[int, str]:
    """Each task's detail, by task number, from the history file."""
    if path is None:
        return {}

    details: dict[int, str] = {}
    number: int | None = None
    body: list[str] = []

    def flush() -> None:
        if number is not None and body:
            details[number] = "\n".join(body).strip()

    for line in path.read_text(encoding="utf-8").splitlines():
        if match := HISTORY_TASK.match(line):
            flush()
            number, body = int(match.group(1)), []
            continue
        if number is None:
            continue
        # A heading or another bold block ends the current detail.
        if line.startswith("#") or line.startswith("**"):
            flush()
            number, body = None, []
            continue
        if line.strip():
            body.append(line.strip())

    flush()
    return details


@dataclass
class Section:
    title: str
    items: list[tuple[str, str]] = field(default_factory=list)
    prose: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.items)

    @property
    def done(self) -> int:
        return sum(1 for icon, _ in self.items if icon == "✅")

    @property
    def is_phase(self) -> bool:
        """A phase tracks progress; an action section does not."""
        return self.total > 0 and not LEADING_ICON.match(self.title)

    @property
    def complete(self) -> bool:
        return self.is_phase and self.done == self.total

    def label(self) -> str:
        """Block title, with a progress bar when the section is a phase."""
        if not self.is_phase:
            return self.title
        bar = "█" * self.done + "░" * (self.total - self.done)
        return f"{self.title}   {bar}  {self.done}/{self.total}"


def read_sections(path: Path) -> tuple[list[str], list[Section]]:
    preamble: list[str] = []
    sections: list[Section] = []
    current: Section | None = None

    for line in path.read_text(encoding="utf-8").splitlines():
        if match := SECTION.match(line):
            current = Section(title=match.group(1).strip())
            sections.append(current)
            continue
        if current is None:
            preamble.append(line)
            continue
        if match := ITEM.match(line):
            current.items.append((match.group(1), match.group(2).strip()))
        elif match := ITEM_PLAIN.match(line):
            # Inherit the icon from the section title, which is where it is in
            # action sections.
            head = LEADING_ICON.match(current.title)
            current.items.append(
                (head.group(1) if head else "⬜", match.group(1).strip())
            )
        else:
            current.prose.append(line)

    return preamble, sections


class Board(App):
    CSS = """
    Screen { background: $surface; }
    #title { padding: 0 2; text-style: bold; color: $primary; }
    #summary { padding: 1 2 0 2; color: $text-muted; }
    Collapsible { border: none; background: transparent; }
    CollapsibleTitle { color: $text; text-style: bold; }
    .item { padding: 0 0 0 2; }
    .done { color: $text-muted; }
    .running { color: $warning; text-style: bold; }
    .todo { color: $text; }
    .blocked { color: $error; }
    .decide { color: $accent; }
    .detail { padding: 0 0 1 4; color: $text-muted; }
    """

    # priority=True is required on the arrows: the scrollable container binds
    # up/down for scrolling and swallows the key before it reaches the app —
    # without this, focus never leaves the first item.
    BINDINGS = [
        Binding("down", "next", "down", priority=True),
        Binding("up", "previous", "up", priority=True),
        Binding("right", "open", "open", priority=True),
        Binding("left", "close", "close", priority=True),
        Binding("enter", "toggle", "toggle", priority=True),
        ("a", "expand_all", "all"),
        ("c", "collapse_all", "none"),
        ("r", "reload", "reload"),
        ("q", "quit", "quit"),
    ]

    mtime = reactive(0.0)

    def __init__(self, board: Path) -> None:
        super().__init__()
        self.board = board
        self.detail_file = find_detail_file(board)
        self.details: dict[int, str] = {}
        self._shimmer_frame = 0
        # (widget, plain text) for whatever is currently "running" — rebuilt
        # on every reload(), animated independently by _tick_shimmer().
        self._shimmer_targets: list[tuple[Static | Collapsible, str]] = []

    def compose(self) -> ComposeResult:
        yield Label("", id="title")
        yield Label("", id="summary")

        # VerticalScroll is focusable by default, so the first Down focused the
        # container instead of the first title — the keypress looked swallowed.
        # Only titles should take focus.
        body = VerticalScroll(id="body")
        body.can_focus = False
        yield body

        yield Footer()

    def on_mount(self) -> None:
        self.reload()
        # Watching by mtime keeps this dependency-free; a filesystem watcher
        # would be a library for one line of work.
        self.set_interval(1.0, self._check_file)
        self.set_interval(1 / SHIMMER_FPS, self._tick_shimmer)

    def _tick_shimmer(self) -> None:
        if not self._shimmer_targets:
            return
        self._shimmer_frame += 1
        for widget, text in self._shimmer_targets:
            markup = shimmer_markup(text, self._shimmer_frame)
            if isinstance(widget, Collapsible):
                widget.title = markup
            else:
                widget.update(markup)

    def _check_file(self) -> None:
        try:
            current = self.board.stat().st_mtime
        except OSError:
            return
        if current != self.mtime:
            self.reload()

    def reload(self) -> None:
        # Remember what is expanded, so refreshing after a change does not
        # collapse the board under the reader.
        expanded = {c.title: not c.collapsed for c in self.query(Collapsible)}

        self.mtime = self.board.stat().st_mtime
        self.details = read_details(self.detail_file)
        preamble, sections = read_sections(self.board)

        heading = next(
            (l.lstrip("# ").strip() for l in preamble if l.startswith("# ")),
            self.board.stem,
        )
        self.query_one("#title", Label).update(heading)

        done = sum(s.done for s in sections if s.is_phase)
        total = sum(s.total for s in sections if s.is_phase)
        needs_action = sum(s.total for s in sections if not s.is_phase)
        self.query_one("#summary", Label).update(
            f"{done} of {total} tasks  ·  {needs_action} items need attention"
        )

        body = self.query_one("#body", VerticalScroll)
        body.remove_children()

        # Rebuilt from scratch below; _tick_shimmer() only reads this list,
        # so it's safe to replace in one shot once the loop below is done.
        shimmer_targets: list[tuple[Static | Collapsible, str]] = []

        for section in sections:
            label = section.label()
            # A previous choice wins; on first load a finished phase starts
            # collapsed and everything else starts open.
            is_open = expanded.get(label, not section.complete)

            children: list[Static | Collapsible] = []
            section_running = False
            for icon, text in section.items:
                item_label = f"{icon}  {text}"
                classes = f"item {CSS_CLASS[icon]}"
                detail = None
                if match := TASK_NUMBER.match(text):
                    detail = self.details.get(int(match.group(1)))

                # A task with recorded detail expands too. Without detail it
                # would open to show nothing, so it stays a plain line — the
                # triangle appears only where there is something to read.
                if detail:
                    item_widget: Static | Collapsible = Collapsible(
                        Static(detail, classes="detail"),
                        title=item_label,
                        collapsed=not expanded.get(item_label, False),
                        classes=classes,
                    )
                else:
                    item_widget = Static(item_label, classes=classes)
                children.append(item_widget)

                if icon == "▶️":
                    section_running = True
                    shimmer_targets.append((item_widget, item_label))

            if not children:
                prose = "\n".join(section.prose).strip()
                if not prose:
                    continue
                children = [Static(prose, classes="item")]

            phase_widget = Collapsible(*children, title=label, collapsed=not is_open)
            # A phase currently doing something shimmers too, not just the
            # task inside it — the board's job is to say "this is moving".
            if section.is_phase and section_running:
                shimmer_targets.append((phase_widget, label))
            body.mount(phase_widget)

        self._shimmer_targets = shimmer_targets
        self._shimmer_frame = 0

    def _visible_titles(self) -> list[CollapsibleTitle]:
        """Titles the reader can actually see, in screen order.

        Textual's focus_next does not skip a title nested inside a collapsed
        block, which made Down appear stuck. A title qualifies here only if no
        block ABOVE it is collapsed — its own block being collapsed does not
        hide its title.
        """
        visible: list[CollapsibleTitle] = []
        for title in self.query(CollapsibleTitle):
            own = title.parent
            ancestor = own.parent if own is not None else None
            hidden = False
            while ancestor is not None:
                if isinstance(ancestor, Collapsible) and ancestor.collapsed:
                    hidden = True
                    break
                ancestor = ancestor.parent
            if not hidden:
                visible.append(title)
        return visible

    def _move(self, step: int) -> None:
        titles = self._visible_titles()
        if not titles:
            return
        current = self.focused
        if current in titles:
            target = titles[(titles.index(current) + step) % len(titles)]
        else:
            target = titles[0] if step > 0 else titles[-1]
        target.focus()
        target.scroll_visible(animate=False)

    def _focused_block(self) -> Collapsible | None:
        node = self.focused
        while node is not None:
            if isinstance(node, Collapsible):
                return node
            node = node.parent
        return None

    def action_next(self) -> None:
        self._move(1)

    def action_previous(self) -> None:
        self._move(-1)

    def action_open(self) -> None:
        # Already open: Right steps into the first item inside, which is what a
        # tree is expected to do.
        if (block := self._focused_block()) is not None:
            if block.collapsed:
                block.collapsed = False
            else:
                self._move(1)

    def action_close(self) -> None:
        # Already closed: Left steps back out to the item above.
        if (block := self._focused_block()) is not None:
            if not block.collapsed:
                block.collapsed = True
            else:
                self._move(-1)

    def action_toggle(self) -> None:
        if (block := self._focused_block()) is not None:
            block.collapsed = not block.collapsed

    def action_expand_all(self) -> None:
        for block in self.query(Collapsible):
            block.collapsed = False

    def action_collapse_all(self) -> None:
        for block in self.query(Collapsible):
            block.collapsed = True

    def action_reload(self) -> None:
        self.reload()


if __name__ == "__main__":
    # On Windows stdout starts out as cp1252 and the board's icons blow up the
    # encoding. A PowerShell launcher used to handle this; without one, the
    # script has to guarantee UTF-8 itself.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

    Board(find_board(sys.argv)).run()
