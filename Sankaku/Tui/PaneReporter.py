from pathlib import Path
from typing import TYPE_CHECKING
from Sankaku.Api.Models import MediaItem
from Sankaku.Download.Reporter import DownloadReporter, SkipReason
import time

if TYPE_CHECKING:
    from Sankaku.Tui.SitePane import SitePane


# A chunk arrives every 64 KB; repainting on each one floods the UI thread.
PROGRESS_INTERVAL_SECONDS: float = 0.1


class PaneReporter(DownloadReporter):
    """Forwards download events from the worker thread onto the UI thread."""

    def __init__(self, pane: 'SitePane') -> None:
        self.pane: 'SitePane' = pane
        # Per item: parallel transfers must not throttle each other's updates.
        self.last_progress: dict[str, float] = {}


    def page_started(self, page_number: int) -> None:
        self.pane.app.call_from_thread(self.pane.report_page_started, page_number)


    def item_started(self, item: MediaItem) -> None:
        self.last_progress[item.id] = 0.0
        self.pane.app.call_from_thread(self.pane.report_item_started, item)


    def item_progress(self, item: MediaItem, received: int, total: int | None) -> None:
        now = time.monotonic()
        finished = total is not None and received >= total
        if not finished and now - self.last_progress.get(item.id, 0.0) < PROGRESS_INTERVAL_SECONDS:
            return

        self.last_progress[item.id] = now
        self.pane.app.call_from_thread(self.pane.report_item_progress, item, received, total)


    def item_saved(self, item: MediaItem, saved_count: int, path: Path) -> None:
        self.pane.app.call_from_thread(self.pane.report_item_saved, item, saved_count)


    def item_skipped(self, item: MediaItem, reason: SkipReason) -> None:
        self.pane.app.call_from_thread(self.pane.report_item_skipped, item, reason)


    def item_failed(self, item: MediaItem, error: Exception) -> None:
        self.pane.app.call_from_thread(self.pane.report_item_failed, item, error)


    def item_cancelled(self, item: MediaItem) -> None:
        self.pane.app.call_from_thread(self.pane.report_item_cancelled, item)


    def failed(self, message: str, error: Exception) -> None:
        self.pane.app.call_from_thread(self.pane.report_failed, message, error)


    def finished(self, saved_count: int, stopped: bool) -> None:
        self.pane.app.call_from_thread(self.pane.report_finished, saved_count, stopped)
