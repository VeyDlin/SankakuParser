from enum import Enum
from pathlib import Path
from Sankaku.Api.Models import MediaItem


class SkipReason(Enum):
    EXISTS = 'exists'                  # already on disk in full
    NEEDS_SIGN_IN = 'needs-sign-in'    # gated post, no file without a session


class DownloadReporter:
    """Receives download events. Every hook is a no-op; override what you need.

    Hooks are called from the download threads — several at once when files
    download in parallel — so a UI subclass must marshal them onto its own
    thread.
    """

    def page_started(self, page_number: int) -> None:
        pass


    def page_finished(self, page_number: int) -> None:
        pass


    def item_started(self, item: MediaItem) -> None:
        pass


    def item_progress(self, item: MediaItem, received: int, total: int | None) -> None:
        pass


    def item_saved(self, item: MediaItem, saved_count: int, path: Path) -> None:
        pass


    def item_skipped(self, item: MediaItem, reason: SkipReason) -> None:
        pass


    def item_failed(self, item: MediaItem, error: Exception) -> None:
        pass


    def item_cancelled(self, item: MediaItem) -> None:
        """A stop cut this file's transfer short; its partial file is gone."""
        pass


    def failed(self, message: str, error: Exception) -> None:
        pass


    def finished(self, saved_count: int, stopped: bool) -> None:
        pass
