from enum import Enum
from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.timer import Timer
from textual.widgets import Input, Label, OptionList, ProgressBar, Rule, Static
from rich.markup import escape
from Sankaku.Api.Client import SankakuApi
from Sankaku.Api.Endpoints import SankakuSite
from Sankaku.Api.Filters import ANONYMOUS_OPERATOR_LIMIT, SearchFilters, combine_query, count_operators
from Sankaku.Api.Models import MediaItem, SessionCheck, SessionStatus
from Sankaku.Auth.TokenStore import TokenStore
from Sankaku.Config import AppConfig, Settings
from Sankaku.Download.Control import DownloadControl
from Sankaku.Download.Downloader import UNLIMITED, DownloadOptions, Downloader
from Sankaku.Download.Reporter import SkipReason
from Sankaku.Tui.AccountMenu import AccountMenu
from Sankaku.Tui.AuthScreen import AuthResult, AuthScreen
from Sankaku.Tui.PaneReporter import PaneReporter
from Sankaku.Tui.Sites import site_title
from Sankaku.Tui.Suggestions import QueryInput, SuggestionMenu, completable_term
from Sankaku.Tui.DownloadList import DownloadList, Entry, EntryStatus
from Sankaku.Tui.FiltersScreen import FiltersScreen, summarize
from Sankaku.Tui.TagFormats import TagFormatPicker
from Sankaku.Tui.Widgets import Action, Toggle, format_size
from pathlib import Path
import asyncio
import re
import time


FALLBACK_FOLDER: str = 'download'
# Search + filters can make a very long name; folders get a readable prefix.
MAX_FOLDER_NAME: int = 64
# A known total keeps an idle bar empty instead of running the 'unknown' animation.
IDLE_TOTAL: int = 100

# ✳ (U+2733) is deliberately absent: it is an emoji and renders as a green
# tile in Windows Terminal. ✷ takes its place in the cycle.
SPINNER_FRAMES: tuple[str, ...] = ('✻', '✽', '✶', '✷', '✢', '·', '✢', '✷', '✶', '✽')
SPINNER_INTERVAL_SECONDS: float = 0.12

# Tab badges. Text glyphs only: ⏸ / ⬇ render as colour emoji in Windows Terminal.
BADGE_RUNNING: str = '↓'
BADGE_PAUSED: str = '‖'
BADGE_STOPPING: str = '■'

# Waiting for a pause in typing keeps one keystroke from becoming one request.
SUGGEST_DEBOUNCE_SECONDS: float = 0.25


def folder_name_for(query: str) -> str:
    # \W is Unicode-aware: Cyrillic, Japanese and other letters are kept, and
    # everything a file system could reject (punctuation, slashes, colons) goes.
    name = re.sub(r'[\W_]+', ' ', query)
    name = re.sub(r' +', '_', name.lower().strip())[:MAX_FOLDER_NAME].strip('_')

    return name or FALLBACK_FOLDER


def format_duration(seconds: float) -> str:
    total = int(seconds)
    if total < 60:
        return f'{total}s'

    minutes, secs = divmod(total, 60)
    if minutes < 60:
        return f'{minutes}m {secs:02d}s'

    hours, minutes = divmod(minutes, 60)

    return f'{hours}h {minutes:02d}m'


class AccountView(Enum):
    CHECKING = 'checking'
    SIGNED_IN = 'signed-in'
    SIGNED_OUT = 'signed-out'            # a user name is remembered, no session
    NEVER_SIGNED_IN = 'never-signed-in'  # nothing remembered at all
    ERROR = 'error'                      # the stored session failed to verify


class SitePane(Vertical):
    """One tab: search form with filters, controls, status and the download list.

    Tabs are fully independent: each owns its client, control and workers, so
    both sites can download at the same time.
    """

    class StateChanged(Message):
        """Posted whenever the tab's download state changes, for its tab badge."""

        def __init__(self, site: SankakuSite, badge: str) -> None:
            super().__init__()
            self.site: SankakuSite = site
            self.badge: str = badge


    class AccountChanged(Message):
        """Posted whenever the tab's sign-in state changes, for the top bar."""

        def __init__(self, site: SankakuSite) -> None:
            super().__init__()
            self.site: SankakuSite = site


    def __init__(self, site: SankakuSite, config: AppConfig, token_store: TokenStore, id: str) -> None:
        super().__init__(id=id)
        self.site: SankakuSite = site
        self.config: AppConfig = config
        self.api: SankakuApi = SankakuApi(site, token_store=token_store)
        # Suggestions use their own anonymous client: they need no login and
        # must not share cursor state with a running download.
        self.suggest_api: SankakuApi = SankakuApi(site)
        self.control: DownloadControl | None = None
        self.running: bool = False
        self.checking: bool = True
        self.auth_error: str | None = None
        self.auth_retryable: bool = False
        self.saved_count: int = 0
        self.skipped_count: int = 0
        self.sign_in_count: int = 0
        self.failed_count: int = 0
        self.page_number: int = 0
        self.filters: SearchFilters = SearchFilters()
        self.options: DownloadOptions | None = None
        self.error_line: str = ''
        self.bytes_received: int = 0
        self.started_at: float = 0.0
        self.finished_line: str = ''
        self.spinner_frame: int = 0
        self.spinner: Timer | None = None


    def compose(self) -> ComposeResult:
        menu = SuggestionMenu(id='tag-menu')

        with Vertical(classes='form'):
            # The menu hangs directly under the query, so both share one group
            # and the row gap goes below the pair. The filter summary is always
            # there (showing 'no filters' when empty), so filters never shift
            # the form.
            with Vertical(classes='field-group'):
                with Horizontal(classes='field-row'):
                    yield Label('search', classes='caption')
                    yield QueryInput(
                        menu,
                        placeholder='tags, e.g. blue_sky long_hair',
                        id='query'
                    )
                    # A plain [x] toggle, not a star glyph: terminal fonts lack the
                    # star shapes and render them small and shifted.
                    yield Toggle('my likes', False, id='favorites')
                    yield Action('filters · 0', id='filters')
                yield menu
                yield Static('', id='filter-summary')

            with Horizontal(classes='field'):
                yield Label('folder', classes='caption')
                yield Input(id='folder', compact=True)

            with Horizontal(classes='field'):
                yield Label('limit', classes='caption')
                yield Input(placeholder='no limit · max number of media files', type='integer', id='limit', compact=True)

            with Horizontal(classes='field'):
                yield Label('options', classes='caption')
                # The tags picker changes width with what is chosen, so it goes
                # last: nothing sits to its right to be pushed around.
                yield Toggle('split by format', self.settings().split_by_format, id='group-formats')
                yield TagFormatPicker(self.settings().tag_formats, id='tag-formats')

        # Controls and state on one line: start when idle; pause/resume and
        # stop while running, then what is happening. The controls' box has a
        # fixed width, so swapping them never moves the status text.
        with Vertical(id='activity'):
            with Horizontal(id='status-line'):
                with Horizontal(id='player'):
                    yield Action('▶ start', 'accent', id='start', disabled=True)
                    yield Action('‖ pause', id='pause')
                    yield Action('■ stop', 'error', id='stop')
                yield Static('', id='status', classes='fill')
            yield ProgressBar(total=IDLE_TOTAL, id='overall', show_eta=False)

        yield Rule(id='list-rule')
        yield DownloadList(id='downloads')


    def on_mount(self) -> None:
        for widget_id in ('#overall', '#list-rule', '#downloads'):
            self.query_one(widget_id).display = False

        self.refresh_target()
        self.refresh_filters()
        self.refresh_controls()
        self.refresh_stats()
        self.check_auth()


    def on_unmount(self) -> None:
        if self.control is not None:
            self.control.stop()

        self.suggest_api.close()


    def on_action_pressed(self, event: Action.Pressed) -> None:
        action_id = event.action.id
        if action_id == 'start':
            self.start_download()
        elif action_id == 'filters':
            self.open_filters()
        elif action_id == 'pause':
            self.toggle_pause()
        elif action_id == 'stop':
            self.stop_download()


    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == 'query':
            tag = self.query_one('#tag-menu', SuggestionMenu).selected()
            if tag is not None:
                self.query_one('#query', QueryInput).accept(tag)
                return

        if event.input.id in ('query', 'folder', 'limit'):
            self.start_download()


    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.has_class('-invalid'):
            self.clear_error()

        if event.input.id == 'query':
            self.suggest(event.value)

        if event.input.id in ('query', 'folder'):
            self.refresh_target()


    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option.id is None:
            return

        query = self.query_one('#query', QueryInput)
        query.accept(event.option.id)
        query.focus()


    # ---- tag suggestions -------------------------------------------------

    @work(exclusive=True, group='suggest', exit_on_error=False)
    async def suggest(self, query: str) -> None:
        menu = self.query_one('#tag-menu', SuggestionMenu)
        term = completable_term(query)
        if term is None or self.running:
            menu.close()
            return

        # Exclusive: a newer keystroke cancels this worker during the sleep.
        await asyncio.sleep(SUGGEST_DEBOUNCE_SECONDS)
        suggestions = await asyncio.to_thread(self.suggest_api.autocomplete, term)

        if self.query_one('#query', QueryInput).has_focus:
            menu.show_tags(term, suggestions)


    def folder_name(self) -> str:
        typed = self.query_one('#folder', Input).value.strip()
        if typed:
            return typed

        return folder_name_for(self.search_label())


    def settings(self) -> Settings:
        return self.config.settings_for(self.site)


    def apply_settings(self) -> None:
        """Picks up saved settings. A running download keeps the ones it started with."""
        self.refresh_target()
        if self.running:
            return

        self.query_one('#tag-formats', TagFormatPicker).set_formats(self.settings().tag_formats)
        self.query_one('#group-formats', Toggle).value = self.settings().split_by_format


    def refresh_target(self) -> None:
        """The folder field's placeholder shows the name the search would get."""
        query = self.search_label()
        folder = self.query_one('#folder', Input)
        if not query:
            folder.placeholder = 'named after the search'
            return

        folder.placeholder = f'{folder_name_for(query)}  (from search)'


    # ---- filters ---------------------------------------------------------

    @property
    def tag_formats(self) -> tuple[str, ...]:
        return self.query_one('#tag-formats', TagFormatPicker).formats


    def search_label(self) -> str:
        """The search in words (tags plus filter summary) — names the folder."""
        parts = [self.query_one('#query', Input).value.strip(), *summarize(self.filters)]

        return ' '.join(part for part in parts if part)


    def open_filters(self) -> None:
        if self.running:
            return

        screen = FiltersScreen(
            self.suggest_api,
            self.filters,
            self.query_one('#query', Input).value,
            anonymous=not self.is_signed_in()
        )
        self.app.push_screen(screen, self.filters_closed)


    def filters_closed(self, filters: SearchFilters | None) -> None:
        if filters is None:
            return

        if self.query_one('#filters').has_class('-invalid'):
            self.clear_error()

        self.filters = filters
        self.refresh_filters()
        self.refresh_target()


    def on_toggle_changed(self, event: Toggle.Changed) -> None:
        if event.toggle.id == 'favorites':
            self.set_my_likes(event.value)


    def set_my_likes(self, on: bool) -> None:
        """"my likes" is the 'liked by' filter set to the signed-in user."""
        if self.running or not self.is_signed_in():
            return

        self.filters = self.filters.with_liked_by(self.username() if on else '')
        self.refresh_filters()
        self.refresh_target()


    def favorites_on(self) -> bool:
        me = self.username()

        return bool(me) and self.filters.liked_by.strip().lower() == me.lower()


    def refresh_filters(self) -> None:
        my_likes = self.query_one('#favorites', Toggle)
        my_likes.disabled = self.running or not self.is_signed_in()
        my_likes.value = self.favorites_on() and self.is_signed_in()

        parts = summarize(self.filters)
        button = self.query_one('#filters', Action)
        # Always with a count, 'filters · 0' included: the label keeps one shape.
        button.label = f'filters · {len(parts)}'
        button.disabled = self.running

        summary = self.query_one('#filter-summary', Static)
        summary.update(f'[dim]{escape(" · ".join(parts))}[/]' if parts else '[dim]no filters[/]')


    # ---- account ---------------------------------------------------------

    @work(thread=True, exclusive=True, group='auth', exit_on_error=False)
    def check_auth(self) -> None:
        self.app.call_from_thread(self.set_checking, True)
        result = self.api.restore_session()
        self.app.call_from_thread(self.auth_checked, result)


    def set_checking(self, checking: bool) -> None:
        self.checking = checking
        self.refresh_account()
        self.refresh_controls()


    def auth_checked(self, result: SessionCheck) -> None:
        self.auth_error = result.error or None
        self.auth_retryable = result.status is SessionStatus.UNREACHABLE
        self.set_checking(False)


    def open_account(self) -> None:
        """Signed in: the sign-out dropdown. Otherwise: the sign-in dialog."""
        if self.checking:
            return

        if self.is_signed_in():
            self.app.push_screen(AccountMenu(), self.account_menu_closed)
            return

        screen = AuthScreen(self.api, error=self.auth_error or '', can_retry=self.auth_retryable)
        self.app.push_screen(screen, self.auth_closed)


    def auth_closed(self, result: AuthResult | None) -> None:
        if result is AuthResult.SIGNED_IN:
            self.auth_error = None
            self.auth_retryable = False
        elif result is AuthResult.RETRY:
            self.check_auth()
            return

        self.refresh_account()


    def account_menu_closed(self, sign_out: bool | None) -> None:
        if not sign_out:
            return

        self.api.logout()
        self.auth_error = None
        self.auth_retryable = False
        self.refresh_account()


    def is_signed_in(self) -> bool:
        # With an unreachable server the tokens are kept but unverified: that
        # is an error state, not a signed-in one.
        return self.api.tokens is not None and self.auth_error is None


    def username(self) -> str:
        if self.api.tokens is not None and self.api.tokens.username:
            return self.api.tokens.username

        return self.api.remembered_username()


    def account_view(self) -> AccountView:
        if self.checking:
            return AccountView.CHECKING

        if self.auth_error is not None:
            return AccountView.ERROR

        if self.is_signed_in():
            return AccountView.SIGNED_IN

        if self.username():
            return AccountView.SIGNED_OUT

        return AccountView.NEVER_SIGNED_IN


    def refresh_account(self) -> None:
        self.post_message(self.AccountChanged(self.site))
        if self.is_mounted:
            self.refresh_filters()


    # ---- download --------------------------------------------------------

    def start_download(self) -> None:
        if self.running or self.checking:
            return

        typed = self.query_one('#query', Input).value.strip()
        query = combine_query(typed, self.filters)
        if not query:
            self.show_error('Enter a search or pick a filter', '#query')
            return

        if not self.is_signed_in() and count_operators(query) > ANONYMOUS_OPERATOR_LIMIT:
            self.show_error(
                f'Sankaku allows {ANONYMOUS_OPERATOR_LIMIT} advanced filters (date, type, duration, size, users) '
                'without sign-in · remove some or sign in',
                '#filters'
            )
            return

        self.clear_error()

        limit_text = self.query_one('#limit', Input).value.strip()
        limit = int(limit_text) if limit_text.isdigit() and int(limit_text) > 0 else UNLIMITED

        options = DownloadOptions(
            save_dir=self.config.save_root(self.site) / self.folder_name(),
            tag_formats=self.tag_formats,
            formats_grouping=self.query_one('#group-formats', Toggle).value,
            max_download=limit,
            page_delay=self.settings().page_delay,
            download_delay=self.settings().download_delay,
            jitter=self.settings().jitter,
            parallel=self.settings().parallel_downloads,
            skip_existing=self.settings().skip_existing
        )

        self.options = options
        self.saved_count = 0
        self.skipped_count = 0
        self.sign_in_count = 0
        self.failed_count = 0
        self.page_number = 0
        self.bytes_received = 0
        self.started_at = time.monotonic()
        self.finished_line = ''
        self.error_line = ''
        self.query_one('#tag-menu', SuggestionMenu).close()
        self.query_one('#activity').display = True
        self.query_one('#overall', ProgressBar).update(total=limit if limit > 0 else None, progress=0)
        self.query_one('#overall').display = limit > 0
        self.query_one('#list-rule').display = True
        downloads = self.query_one('#downloads', DownloadList)
        downloads.display = True
        downloads.clear()

        self.control = DownloadControl()
        self.running = True
        self.spinner = self.set_interval(SPINNER_INTERVAL_SECONDS, self.tick)
        self.refresh_controls()
        self.refresh_stats()
        self.run_download(query, options, self.control)


    # Worker groups are scoped per widget, so 'exclusive' never touches the
    # other tab's download.
    @work(thread=True, exclusive=True, group='download', exit_on_error=False)
    def run_download(self, query: str, options: DownloadOptions, control: DownloadControl) -> None:
        try:
            Downloader(self.api, options, control, PaneReporter(self)).download(query)
        except Exception as err:
            self.app.call_from_thread(self.report_failed, 'Download crashed', err)
            self.app.call_from_thread(self.report_finished, self.saved_count, True)


    def toggle_pause(self) -> None:
        if self.control is None or not self.running:
            return

        self.control.toggle_pause()
        self.refresh_controls()
        self.refresh_stats()


    def stop_download(self) -> None:
        if self.control is None or not self.running:
            return

        self.control.stop()
        self.refresh_controls()
        self.refresh_stats()


    def refresh_controls(self) -> None:
        paused = self.control is not None and self.control.is_paused
        stopping = self.control is not None and self.control.is_stopped

        start = self.query_one('#start', Action)
        start.display = not self.running
        start.disabled = self.checking

        pause = self.query_one('#pause', Action)
        pause.display = self.running and not stopping
        pause.label = '▶ resume' if paused else '‖ pause'
        pause.set_tone('accent' if paused else '')

        stop = self.query_one('#stop', Action)
        stop.display = self.running
        stop.disabled = stopping
        stop.label = '■ stopping…' if stopping else '■ stop'

        for widget_id in ('#query', '#folder', '#limit', '#tag-formats', '#group-formats'):
            self.query_one(widget_id).disabled = self.running

        self.refresh_filters()
        self.post_message(self.StateChanged(self.site, self.badge()))


    def badge(self) -> str:
        if not self.running:
            return ''

        if self.control is not None and self.control.is_stopped:
            return BADGE_STOPPING

        if self.control is not None and self.control.is_paused:
            return BADGE_PAUSED

        return BADGE_RUNNING


    def tick(self) -> None:
        self.spinner_frame = (self.spinner_frame + 1) % len(SPINNER_FRAMES)
        self.refresh_stats()


    def show_error(self, message: str, culprit: str | None = None) -> None:
        """Errors: red text in the status line, and the control at fault in red."""
        self.clear_error()
        self.error_line = f'[$error]{escape(message)}[/]'
        self.query_one('#activity').display = True
        if culprit is not None:
            widget = self.query_one(culprit)
            widget.add_class('-invalid')
            widget.focus()
        self.refresh_stats()


    def clear_error(self) -> None:
        self.error_line = ''
        for widget in self.query('.-invalid'):
            widget.remove_class('-invalid')
        self.refresh_stats()


    def refresh_stats(self) -> None:
        status = self.query_one('#status', Static)
        if not self.running:
            # Idle: blank until the first run; afterwards its outcome stays here.
            status.update(self.error_line or self.finished_line)
            return

        elapsed = time.monotonic() - self.started_at
        details = [format_duration(elapsed), f'{self.saved_count} saved']
        if self.skipped_count:
            details.append(f'{self.skipped_count} skipped')
        if self.sign_in_count:
            details.append(f'{self.sign_in_count} need sign-in')
        if self.failed_count:
            details.append(f'{self.failed_count} failed')
        if elapsed > 1 and self.bytes_received:
            details.append(f'{format_size(self.bytes_received / elapsed)}/s')

        summary = f'[dim]({" · ".join(details)})[/]'

        if self.control is not None and self.control.is_stopped:
            status.update(f'[$accent]■[/] Stopping {summary}')
        elif self.control is not None and self.control.is_paused:
            status.update(f'[$accent]‖[/] Paused · files in flight finish {summary}')
        else:
            frame = SPINNER_FRAMES[self.spinner_frame]
            status.update(f'[$accent]{frame}[/] Downloading page {self.page_number} {summary}')


    def entry_path(self, item: MediaItem) -> Path:
        options = self.options
        if options is None:
            return Path(f'{item.id}.{item.file_format}')

        folder = options.save_dir / item.file_format if options.formats_grouping else options.save_dir

        return folder / f'{item.id}.{item.file_format}'


    def entry_for(self, item: MediaItem) -> Entry:
        downloads = self.query_one('#downloads', DownloadList)
        entry = downloads.get(item.id)
        if entry is None:
            entry = Entry(item=item, path=self.entry_path(item))

        return entry


    # ---- reporter callbacks (UI thread) ----------------------------------

    def report_page_started(self, page_number: int) -> None:
        self.page_number = page_number
        self.refresh_stats()


    def report_item_started(self, item: MediaItem) -> None:
        entry = self.entry_for(item)
        entry.status = EntryStatus.DOWNLOADING
        self.query_one('#downloads', DownloadList).upsert(entry)


    def report_item_progress(self, item: MediaItem, received: int, total: int | None) -> None:
        entry = self.entry_for(item)
        self.bytes_received += max(received - entry.received, 0)
        entry.received = received
        entry.total = total
        self.query_one('#downloads', DownloadList).upsert(entry)


    def report_item_cancelled(self, item: MediaItem) -> None:
        entry = self.entry_for(item)
        entry.status = EntryStatus.CANCELLED
        entry.note = 'stopped before it finished'
        self.query_one('#downloads', DownloadList).upsert(entry)


    def report_item_saved(self, item: MediaItem, saved_count: int) -> None:
        entry = self.entry_for(item)
        entry.status = EntryStatus.SAVED
        if entry.total:
            entry.received = entry.total
        self.query_one('#downloads', DownloadList).upsert(entry)

        self.saved_count = saved_count
        self.query_one('#overall', ProgressBar).advance(1)
        self.refresh_stats()


    def report_item_skipped(self, item: MediaItem, reason: SkipReason) -> None:
        entry = self.entry_for(item)
        if reason is SkipReason.NEEDS_SIGN_IN:
            entry.status = EntryStatus.NEEDS_SIGN_IN
            self.sign_in_count += 1
        else:
            entry.status = EntryStatus.EXISTS
            self.skipped_count += 1

        self.query_one('#downloads', DownloadList).upsert(entry)
        self.refresh_stats()


    def report_item_failed(self, item: MediaItem, error: Exception) -> None:
        entry = self.entry_for(item)
        entry.status = EntryStatus.FAILED
        entry.note = str(error) or type(error).__name__
        self.query_one('#downloads', DownloadList).upsert(entry)

        self.failed_count += 1
        self.refresh_stats()


    def report_failed(self, message: str, error: Exception) -> None:
        self.error_line = f'[$error]{escape(message)} · {escape(str(error))}[/]'


    def report_finished(self, saved_count: int, stopped: bool) -> None:
        self.saved_count = saved_count
        self.running = False
        if self.spinner is not None:
            self.spinner.stop()
            self.spinner = None

        self.query_one('#overall').display = False

        duration = format_duration(time.monotonic() - self.started_at)
        counts = f'{saved_count} saved'
        if self.skipped_count:
            counts += f' · {self.skipped_count} skipped'
        if self.sign_in_count:
            counts += f' · {self.sign_in_count} need sign-in'
        if self.failed_count:
            counts += f' · {self.failed_count} failed'

        if stopped:
            self.finished_line = f'[$accent]■[/] Stopped [dim]({counts} in {duration})[/]'
        else:
            self.finished_line = f'[$accent]✓[/] Done [dim]({counts} in {duration})[/]'

        if not self.error_line:
            self.app.notify(f'{site_title(self.site)}: {"stopped" if stopped else "done"}, {saved_count} file(s) saved')

        self.refresh_controls()
        self.refresh_stats()
