from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.widgets import Static
from rich.markup import escape
from rich.text import Text
from Sankaku.Api.Models import MediaItem
from Sankaku.Tui import Palette
from Sankaku.Tui.Widgets import Action, format_size
import os
import shutil
import subprocess
import sys


PROGRESS_WIDTH: int = 12
# Rows kept on screen. Beyond this the oldest are dropped (only while following
# the bottom, so nothing moves under a reader) and counted in a note on top.
MAX_ROWS: int = 400

# The follow button: its horizontal padding, and how far it is lifted from just
# below the list onto the list's last line.
FOLLOW_PADDING: int = 4
FOLLOW_LIFT: int = -2


class EntryStatus(Enum):
    DOWNLOADING = 'downloading'
    SAVED = 'saved'
    EXISTS = 'exists'                  # already on disk in full, skipped
    NEEDS_SIGN_IN = 'needs-sign-in'    # gated post while not signed in
    FAILED = 'failed'
    CANCELLED = 'cancelled'


# Short, self-explanatory words: a status never needs to be cut off. The one
# with a story behind it, 'failed', shows its error under 'info'.
LABELS: dict[EntryStatus, str] = {
    EntryStatus.SAVED: 'saved',
    EntryStatus.EXISTS: 'exists',
    EntryStatus.NEEDS_SIGN_IN: 'sign-in needed',
    EntryStatus.FAILED: 'failed',
    EntryStatus.CANCELLED: 'stopped'
}

MARKS: dict[EntryStatus, str] = {
    EntryStatus.DOWNLOADING: '↓',
    EntryStatus.SAVED: '✓',
    EntryStatus.EXISTS: '·',
    EntryStatus.NEEDS_SIGN_IN: '!',
    EntryStatus.FAILED: '✕',
    EntryStatus.CANCELLED: '·'
}

STATUS_COLOURS: dict[EntryStatus, str] = {
    EntryStatus.DOWNLOADING: '$accent',
    EntryStatus.SAVED: '$success',
    EntryStatus.EXISTS: '$text-muted',
    EntryStatus.NEEDS_SIGN_IN: '$accent',
    EntryStatus.FAILED: '$error',
    EntryStatus.CANCELLED: '$warning'
}


@dataclass
class Entry:
    item: MediaItem
    path: Path
    status: EntryStatus = EntryStatus.DOWNLOADING
    received: int = 0
    total: int | None = None
    note: str = ''          # skip reason or error text


def can_open_folders() -> bool:
    """Whether a file manager can be shown here (not over a plain SSH session)."""
    if sys.platform in ('win32', 'darwin'):
        return True

    has_display = bool(os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY'))

    return has_display and shutil.which('xdg-open') is not None


def open_in_folder(path: Path) -> None:
    """Shows the file in the system file manager (selected, where supported)."""
    if sys.platform == 'win32':
        subprocess.Popen(['explorer', f'/select,{path}'])
    elif sys.platform == 'darwin':
        subprocess.Popen(['open', '-R', str(path)])
    else:
        subprocess.Popen(['xdg-open', str(path.parent)])


def progress_bar(received: int, total: int | None) -> Text:
    """A solid bar: the done part bright, the rest dim, then the percentage.

    Drawn in full from the very start (an empty bar at 0%) so the cell never
    jumps from a byte count to a bar once the size becomes known.
    """
    share = min(received / total, 1.0) if total else 0.0
    filled = round(share * PROGRESS_WIDTH)
    bar = Text('━' * filled, style=f'bold {Palette.ACCENT}')
    bar.append('━' * (PROGRESS_WIDTH - filled), style='dim')
    bar.append(f' {share * 100:3.0f}%')

    return bar


def format_length(seconds: float) -> str:
    total = int(round(seconds))
    minutes, secs = divmod(total, 60)
    if minutes < 60:
        return f'{minutes}:{secs:02d}'

    hours, minutes = divmod(minutes, 60)

    return f'{hours}:{minutes:02d}:{secs:02d}'


class DownloadRow(Vertical):
    """One file: a summary line with its own actions, and details that unfold.

    The cells are created up front and updated directly: progress can arrive
    before the row has finished mounting, when a query would find nothing.
    """

    def __init__(self, entry: Entry, can_open: bool) -> None:
        super().__init__(classes='download-row')
        self.entry: Entry = entry
        self.can_open: bool = can_open
        self.expanded: bool = False

        item = entry.item
        self.mark: Static = Static('', classes='cell mark')
        self.name_cell: Static = Static(escape(item.id), classes='cell name')
        self.type_cell: Static = Static(f'[dim]{escape(item.file_format)}[/]', classes='cell type')
        self.size_cell: Static = Static(f'[dim]{item.width}×{item.height}[/]' if item.width else '', classes='cell size')
        self.length_cell: Static = Static(f'[dim]{format_length(item.duration)}[/]' if item.duration else '', classes='cell length')
        self.weight: Static = Static('', classes='cell weight')
        self.status: Static = Static('', classes='cell status')
        self.info: Action = Action('info ▸', classes='row-info')
        self.opener: Action = Action('open', classes='row-open')
        self.details: Static = Static('', classes='row-details')
        self.details.display = False
        self.refresh_entry()


    def compose(self) -> ComposeResult:
        with Horizontal(classes='row-line'):
            yield self.mark
            yield self.name_cell
            yield self.type_cell
            yield self.size_cell
            yield self.length_cell
            yield self.weight
            yield self.status
            yield self.info
            yield self.opener
        yield self.details


    def refresh_entry(self) -> None:
        entry = self.entry
        faint = entry.status in (EntryStatus.EXISTS, EntryStatus.CANCELLED)
        self.set_class(faint, '-faint')

        size = entry.total or entry.item.file_size
        self.weight.update(f'[dim]{format_size(size)}[/]' if size else '')

        if entry.status is EntryStatus.DOWNLOADING:
            # The post's own size stands in until the transfer reports one.
            self.status.update(progress_bar(entry.received, entry.total or entry.item.file_size))
        else:
            colour = STATUS_COLOURS[entry.status]
            self.status.update(f'[{colour}]{LABELS[entry.status]}[/]')

        self.mark.update(f'[{STATUS_COLOURS[entry.status]}]{MARKS[entry.status]}[/]')

        # Hidden, not removed: the button keeps its place so the row never shifts.
        self.opener.styles.visibility = 'visible' if self.can_open and entry.path.exists() else 'hidden'

        if self.expanded:
            self.details.update(self.details_text())


    def details_text(self) -> str:
        entry = self.entry
        if entry.status is EntryStatus.FAILED:
            return f'[dim]error[/]  {escape(entry.note or "unknown error")}'

        if entry.item.tags:
            return f'[dim]tags · {len(entry.item.tags)}[/]  {escape(", ".join(entry.item.tags))}'

        return '[dim]no tags[/]'


    def on_action_pressed(self, event: Action.Pressed) -> None:
        event.stop()
        if event.action is self.info:
            self.toggle_details()
        elif event.action is self.opener and self.entry.path.exists():
            open_in_folder(self.entry.path)


    def toggle_details(self) -> None:
        self.expanded = not self.expanded
        self.details.display = self.expanded
        self.info.label = 'info ▾' if self.expanded else 'info ▸'
        if self.expanded:
            self.details.update(self.details_text())


class FollowScroll(VerticalScroll):
    """A scroll area that reports every scroll move (for the follow button)."""

    class Moved(Message):
        def __init__(self, upward: bool, at_bottom: bool) -> None:
            super().__init__()
            self.upward: bool = upward
            self.at_bottom: bool = at_bottom


    def watch_scroll_y(self, old_value: float, new_value: float) -> None:
        super().watch_scroll_y(old_value, new_value)
        self.post_message(self.Moved(new_value < old_value, new_value >= self.max_scroll_y - 1))


class DownloadList(Vertical):
    """Every file of the current download, newest at the bottom.

    Follows the bottom like a terminal: scrolling up a little stops following,
    scrolling back down resumes it. (Textual's anchor() is not used: while the
    rows were shorter than the view it scrolled to a negative offset and pushed
    the first row to the bottom edge.) While not following, a
    button in the middle of the bottom edge jumps back down and counts the rows
    added meanwhile.
    """

    def __init__(self, id: str) -> None:
        super().__init__(id=id)
        self.rows: dict[str, DownloadRow] = {}
        self.can_open: bool = can_open_folders()
        self.unseen: int = 0
        self.dropped: int = 0
        # Follow state follows the user's scrolling, not the geometry: while a
        # new row is being laid out the list is briefly taller than it is
        # scrolled, which must not count as "the user left the bottom".
        self.following: bool = True


    def compose(self) -> ComposeResult:
        with Horizontal(classes='list-header'):
            yield Static('', classes='cell mark')
            yield Static('file', classes='cell name')
            yield Static('type', classes='cell type')
            yield Static('size', classes='cell size')
            yield Static('length', classes='cell length')
            yield Static('weight', classes='cell weight')
            yield Static('status', classes='cell status')
            yield Static('', classes='cell actions')
        with FollowScroll(id='rows'):
            yield Static('', id='dropped-note')
        with Horizontal(id='follow-bar'):
            yield Action('', 'accent', id='follow')


    def on_mount(self) -> None:
        self.query_one('#dropped-note', Static).display = False
        self.refresh_follow()


    def on_resize(self) -> None:
        self.refresh_follow()


    def clear(self) -> None:
        for row in self.rows.values():
            row.remove()
        self.rows.clear()
        self.unseen = 0
        self.dropped = 0
        self.following = True
        self.query_one('#dropped-note', Static).display = False
        self.refresh_follow()


    def get(self, key: str) -> Entry | None:
        row = self.rows.get(key)

        return row.entry if row is not None else None


    def upsert(self, entry: Entry) -> None:
        key = entry.item.id
        row = self.rows.get(key)
        if row is not None:
            row.entry = entry
            row.refresh_entry()
            return

        was_following = self.following
        row = DownloadRow(entry, self.can_open)
        self.rows[key] = row
        self.query_one('#rows', FollowScroll).mount(row)
        if was_following:
            self.trim()
            self.stick_to_bottom()
        else:
            self.unseen += 1

        self.refresh_follow()


    def stick_to_bottom(self) -> None:
        """Scrolls to the end once the new row is laid out."""
        rows = self.query_one('#rows', FollowScroll)
        self.call_after_refresh(rows.scroll_end, animate=False)


    def trim(self) -> None:
        """Drops the oldest rows past MAX_ROWS (called only while following)."""
        while len(self.rows) > MAX_ROWS:
            oldest = next(iter(self.rows))
            self.rows.pop(oldest).remove()
            self.dropped += 1

        note = self.query_one('#dropped-note', Static)
        note.display = self.dropped > 0
        note.update(f'[dim]{self.dropped} earlier file(s) not shown[/]')


    def on_follow_scroll_moved(self, event: FollowScroll.Moved) -> None:
        if event.at_bottom:
            self.following = True
            self.unseen = 0
        elif event.upward:
            self.following = False

        self.refresh_follow()


    def on_action_pressed(self, event: Action.Pressed) -> None:
        if event.action.id != 'follow':
            return

        event.stop()
        self.following = True
        self.stick_to_bottom()
        self.unseen = 0
        self.refresh_follow()


    def refresh_follow(self) -> None:
        bar = self.query_one('#follow-bar', Horizontal)
        bar.display = bool(self.rows) and not self.following
        label = '↓ scroll to bottom'
        if self.unseen:
            label += f' · {self.unseen} new'
        self.query_one('#follow', Action).label = label

        # Centre it over the bottom line of the list (overlays ignore align).
        width = len(label) + FOLLOW_PADDING
        left = max((self.size.width - width) // 2, 0)
        bar.styles.offset = (left, FOLLOW_LIFT)
