from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Label, OptionList, Rule, Static
from rich.markup import escape
from Sankaku.Config import (
    MAX_DELAY_SECONDS,
    MAX_PARALLEL_DOWNLOADS,
    MIN_PARALLEL_DOWNLOADS,
    TAG_FORMATS,
    AppConfig,
    Settings,
    resolve_path
)
from Sankaku.Api.Endpoints import SankakuSite
from Sankaku.Tui.Navigation import ArrowNavigation
from Sankaku.Tui.Sites import site_title
from Sankaku.Tui.Suggestions import PathInput, SuggestionMenu, folder_suggestions
from Sankaku.Tui.Widgets import Action, Toggle
import asyncio


class SettingsScreen(ModalScreen[bool], ArrowNavigation):
    """One site's settings (Chan and Idol are configured separately).

    Dismisses with True when they were saved.
    """

    BINDINGS = [Binding('escape', 'close', 'Close')]


    def __init__(self, config: AppConfig, site: SankakuSite) -> None:
        super().__init__()
        self.config: AppConfig = config
        self.site: SankakuSite = site
        # Suggestions answer typing only: the value the field opens with (and
        # its initial Changed event) must not pop the list up unasked.
        self.edited: bool = False


    def compose(self) -> ComposeResult:
        settings = self.config.settings_for(self.site)
        menu = SuggestionMenu(id='path-menu')

        with Vertical(id='settings-dialog'):
            with Horizontal(classes='line'):
                yield Static(f'[b]{site_title(self.site)}[/] settings', id='settings-title', classes='fill')
                yield Action('esc', id='close')

            yield Rule()

            yield Static('[dim]where to save[/]', classes='section')
            with Vertical(classes='field-group'):
                with Horizontal(classes='field-row'):
                    yield Label('save folder', classes='caption')
                    yield PathInput(menu, value=settings.save_dir, placeholder='data', id='save-dir')
                yield menu
                yield Static('', id='save-dir-hint', classes='hint-row')

            yield Static('[dim]request speed[/]', classes='section')
            yield from self.number_field('page-delay', 'page delay', settings.page_delay, 's · pause before the next page')
            yield from self.number_field('download-delay', 'file delay', settings.download_delay, 's · pause after each file')
            yield from self.number_field('jitter', 'jitter', settings.jitter, 's · random extra 0…N added to every pause')
            yield from self.number_field(
                'parallel',
                'parallel',
                settings.parallel_downloads,
                f'files at once ({MIN_PARALLEL_DOWNLOADS}–{MAX_PARALLEL_DOWNLOADS}) · more may hit rate limits'
            )

            yield Static('[dim]defaults for new downloads[/]', classes='section')
            with Horizontal(classes='field'):
                yield Label('options', classes='caption')
                yield Toggle('tags .txt', 'txt' in settings.tag_formats, id='tags-txt')
                yield Toggle('tags .json', 'json' in settings.tag_formats, id='tags-json')
                yield Toggle('split by format', settings.split_by_format, id='split-by-format')
            with Horizontal(classes='field'):
                yield Label('', classes='caption')
                yield Toggle('skip files already downloaded', settings.skip_existing, id='skip-existing')

            # Dialog convention: actions sit bottom-right, the confirming one
            # last. The error takes the free left part of that row, so showing
            # it never shifts the form.
            with Horizontal(classes='line actions'):
                yield Static('', id='settings-error', classes='fill message')
                yield Action('cancel', id='cancel')
                yield Action('❯ save', 'accent', id='save')


    def number_field(self, field_id: str, caption: str, value: float, hint: str) -> ComposeResult:
        with Horizontal(classes='field'):
            yield Label(caption, classes='caption')
            yield Input(value=format_number(value), type='number', id=field_id, compact=True, classes='number')
            yield Static(f'[dim]{escape(hint)}[/]', classes='unit')


    def on_mount(self) -> None:
        self.refresh_path_hint()
        self.query_one('#save-dir', PathInput).focus()


    def on_action_pressed(self, event: Action.Pressed) -> None:
        action_id = event.action.id
        if action_id == 'save':
            self.save()
        elif action_id in ('cancel', 'close'):
            self.action_close()


    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == 'save-dir':
            self.refresh_path_hint()
            if event.value != self.config.settings_for(self.site).save_dir:
                self.edited = True
            if self.edited:
                self.suggest_folders(event.value)


    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == 'save-dir':
            choice = self.query_one('#path-menu', SuggestionMenu).selected()
            if choice is not None:
                self.query_one('#save-dir', PathInput).accept(choice)
                return

        self.save()


    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option.id is None:
            return

        path = self.query_one('#save-dir', PathInput)
        path.accept(event.option.id)
        path.focus()


    def action_close(self) -> None:
        self.dismiss(False)


    @work(exclusive=True, group='folders', exit_on_error=False)
    async def suggest_folders(self, value: str) -> None:
        # Listing a folder can be slow (network drives): keep it off the UI thread.
        folders = await asyncio.to_thread(folder_suggestions, self.config.root, value)
        if self.query_one('#save-dir', PathInput).has_focus:
            self.query_one('#path-menu', SuggestionMenu).show_folders(folders)


    def refresh_path_hint(self) -> None:
        value = self.query_one('#save-dir', PathInput).value
        target = resolve_path(self.config.root, value)
        state = 'exists' if target.is_dir() else 'will be created'
        self.query_one('#save-dir-hint', Static).update(f'[dim]→ {escape(str(target))} · {state}[/]')


    def save(self) -> None:
        try:
            settings = self.read_form()
        except ValueError as err:
            self.query_one('#settings-error', Static).update(f'[$error]{escape(str(err))}[/]')
            return

        self.config.update(self.site, settings)
        self.dismiss(True)


    def read_form(self) -> Settings:
        save_dir = self.query_one('#save-dir', PathInput).value.strip()
        if not save_dir:
            raise ValueError('save folder cannot be empty')

        parallel = self.read_number('#parallel', 'parallel')
        if not parallel.is_integer() or not MIN_PARALLEL_DOWNLOADS <= parallel <= MAX_PARALLEL_DOWNLOADS:
            raise ValueError(f'parallel must be a whole number from {MIN_PARALLEL_DOWNLOADS} to {MAX_PARALLEL_DOWNLOADS}')

        return Settings(
            save_dir=save_dir,
            page_delay=self.read_number('#page-delay', 'page delay'),
            download_delay=self.read_number('#download-delay', 'file delay'),
            jitter=self.read_number('#jitter', 'jitter'),
            parallel_downloads=int(parallel),
            tag_formats=tuple(
                name for name in TAG_FORMATS if self.query_one(f'#tags-{name}', Toggle).value
            ),
            split_by_format=self.query_one('#split-by-format', Toggle).value,
            skip_existing=self.query_one('#skip-existing', Toggle).value
        )


    def read_number(self, selector: str, name: str) -> float:
        text = self.query_one(selector, Input).value.strip()
        try:
            value = float(text)
        except ValueError:
            raise ValueError(f'{name} must be a number') from None

        if not 0 <= value <= MAX_DELAY_SECONDS:
            raise ValueError(f'{name} must be between 0 and {MAX_DELAY_SECONDS:g}')

        return value


def format_number(value: float) -> str:
    return f'{value:g}'
