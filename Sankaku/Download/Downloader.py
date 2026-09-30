from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from pathlib import Path
from Sankaku.Api.Client import SankakuApi
from Sankaku.Api.Models import MediaItem
from Sankaku.Download.Control import DownloadControl
from Sankaku.Download.Reporter import DownloadReporter, SkipReason
from typing import Any
import json
import random
import threading


# Pause after resolving a gated post's real URL: one extra API call per item.
RESOLVE_DELAY_SECONDS: float = 1.5

UNLIMITED: int = -1


@dataclass(frozen=True)
class DownloadOptions:
    save_dir: Path
    tag_formats: tuple[str, ...] = ('txt',)
    formats_grouping: bool = False
    max_download: int = UNLIMITED
    page_delay: float = 3.0
    download_delay: float = 0.0
    jitter: float = 0.0
    parallel: int = 1
    skip_existing: bool = True


class Downloader:
    """Pages through a search and downloads its media.

    Up to `parallel` files are in flight at once. Each slot waits
    download_delay (+ random 0..jitter) after its file; the next page waits
    page_delay (+ jitter). Pause stops new files from starting, stop also
    cancels the ones in flight, and the limit counts files in flight so
    several slots never overshoot it.
    """

    def __init__(
        self,
        api: SankakuApi,
        options: DownloadOptions,
        control: DownloadControl | None = None,
        reporter: DownloadReporter | None = None
    ) -> None:
        self.api: SankakuApi = api
        self.options: DownloadOptions = options
        self.control: DownloadControl = control if control is not None else DownloadControl()
        self.reporter: DownloadReporter = reporter if reporter is not None else DownloadReporter()
        self.lock: threading.Lock = threading.Lock()
        self.saved_count: int = 0
        self.in_flight: int = 0
        self.page_number: int = 1


    def download(self, search_query: str) -> None:
        self.saved_count = 0
        self.in_flight = 0
        self.page_number = 1

        self.reporter.page_started(self.page_number)
        try:
            page = self.api.search(search_query)
        except Exception as err:
            self.reporter.failed('Search error', err)
            self.reporter.finished(self.saved_count, self.control.is_stopped)
            return

        with ThreadPoolExecutor(max_workers=max(1, self.options.parallel), thread_name_prefix='download') as pool:
            while page:
                if not self.download_page(page, pool):
                    break

                self.page_number += 1
                self.reporter.page_started(self.page_number)
                try:
                    page = self.api.next_page()
                except Exception as err:
                    self.reporter.failed('Error loading next page', err)
                    break

        self.reporter.finished(self.saved_count, self.control.is_stopped)


    def download_page(self, page: list[MediaItem], pool: ThreadPoolExecutor) -> bool:
        """Downloads one page. Returns False when the loop should not continue."""
        running: set[Future[None]] = set()
        slots = max(1, self.options.parallel)

        for item in page:
            # Hold a free slot before looking at the item, so pause, stop and
            # the limit are judged at the moment the file would really start.
            while len(running) >= slots:
                done, _ = wait(running, return_when=FIRST_COMPLETED)
                running -= done

            self.control.wait_while_paused()
            if self.control.is_stopped or self.limit_reached_with_in_flight():
                break

            if self.options.skip_existing and self.already_downloaded(item):
                self.reporter.item_skipped(item, SkipReason.EXISTS)
                continue

            if item.needs_resolve and not self.api.is_authorized:
                self.reporter.item_skipped(item, SkipReason.NEEDS_SIGN_IN)
                continue

            with self.lock:
                self.in_flight += 1

            running.add(pool.submit(self.run_item, item))

        if running:
            wait(running)

        self.reporter.page_finished(self.page_number)
        if self.control.is_stopped or self.is_limit_reached():
            return False

        self.control.sleep(self.options.page_delay + self.jitter())

        return not self.control.is_stopped


    def run_item(self, item: MediaItem) -> None:
        """One slot's work: download the item, then pace before the next one."""
        try:
            saved = self.download_item(item)
        except Exception as err:
            saved = False
            self.reporter.item_failed(item, err)
        finally:
            with self.lock:
                self.in_flight -= 1

        if saved:
            self.control.sleep(self.options.download_delay + self.jitter())


    def download_item(self, item: MediaItem) -> bool:
        """Downloads one post. Returns False when a stop cut the transfer short."""
        self.reporter.item_started(item)

        if item.needs_resolve:
            item.file_url = self.api.resolve_file_url(item)
            self.control.sleep(RESOLVE_DELAY_SECONDS)

        if not item.file_url:
            raise ValueError(f'post {item.id} has no file url')

        save_dir = self.directory_for(item)
        save_dir.mkdir(parents=True, exist_ok=True)
        media_path = self.media_path(item)

        completed = self.api.download_file(
            item.file_url,
            media_path,
            should_abort=lambda: self.control.is_stopped,
            on_progress=lambda received, total: self.reporter.item_progress(item, received, total)
        )
        if not completed:
            self.reporter.item_cancelled(item)
            return False

        self.write_tag_files(item, save_dir)

        with self.lock:
            self.saved_count += 1
            saved_count = self.saved_count

        self.reporter.item_saved(item, saved_count, media_path)

        return True


    def write_tag_files(self, item: MediaItem, save_dir: Path) -> None:
        if 'txt' in self.options.tag_formats:
            (save_dir / f'{item.id}.txt').write_text(', '.join(item.tags), encoding='utf-8')

        if 'json' in self.options.tag_formats:
            (save_dir / f'{item.id}.json').write_text(
                json.dumps(self.post_record(item), ensure_ascii=False, indent=2),
                encoding='utf-8'
            )


    def post_record(self, item: MediaItem) -> dict[str, Any]:
        """Machine-readable sidecar: post metadata plus tags grouped by category.

        The categories need one extra request (search results carry only a few
        typed tags). If it fails the file is still kept, with the tags listed
        without categories.
        """
        grouped: dict[str, list[str]] = {}
        try:
            typed = self.api.post_tags(item.id)
            self.control.sleep(RESOLVE_DELAY_SECONDS)
        except Exception:
            typed = []

        for tag in typed:
            grouped.setdefault(tag.category, []).append(tag.name)

        record: dict[str, Any] = {
            'id': item.id,
            'file': f'{item.id}.{item.file_format}',
            'rating': item.rating,
            'width': item.width,
            'height': item.height,
            'file_size': item.file_size,
            'md5': item.md5,
            'source': item.source,
            'created_at': item.created_at,
            'tags': grouped if grouped else {'uncategorized': item.tags}
        }

        return record


    def media_path(self, item: MediaItem) -> Path:
        return self.directory_for(item) / f'{item.id}.{item.file_format}'


    def already_downloaded(self, item: MediaItem) -> bool:
        """The file is on disk in full: same name, and the size the API reports.

        Checked against the disk rather than a download cache, so deleting a file
        by hand gets it downloaded again, and a partial file does not count.
        """
        path = self.media_path(item)
        try:
            size = path.stat().st_size
        except OSError:
            return False

        if item.file_size:
            return size == item.file_size

        return size > 0


    def jitter(self) -> float:
        if self.options.jitter <= 0:
            return 0.0

        return random.uniform(0.0, self.options.jitter)


    def directory_for(self, item: MediaItem) -> Path:
        if self.options.formats_grouping:
            return self.options.save_dir / item.file_format

        return self.options.save_dir


    def is_limit_reached(self) -> bool:
        if self.options.max_download <= 0:
            return False

        with self.lock:
            return self.saved_count >= self.options.max_download


    def limit_reached_with_in_flight(self) -> bool:
        if self.options.max_download <= 0:
            return False

        with self.lock:
            return self.saved_count + self.in_flight >= self.options.max_download
