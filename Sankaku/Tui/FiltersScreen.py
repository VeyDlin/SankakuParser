from dataclasses import replace
from datetime import date
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Label, OptionList, Rule, Static
from rich.markup import escape
from Sankaku.Api.Client import SankakuApi
from Sankaku.Api.Filters import (
    ANONYMOUS_OPERATOR_LIMIT,
    DateRange,
    Duration,
    FileType,
    Resolution,
    SearchFilters,
    Sort,
    count_operators
)
from Sankaku.Tui.Navigation import ArrowNavigation
from Sankaku.Tui.Sites import site_title
from Sankaku.Tui.Suggestions import MIN_TERM_LENGTH, NameInput, SuggestionMenu
from Sankaku.Tui.Widgets import Action, ChoiceOption, ChoiceRow
import asyncio


SORT_LABELS: dict[Sort, str] = {
    Sort.NEWEST: 'newest',
    Sort.POPULARITY: 'popular',
    Sort.QUALITY: 'quality',
    Sort.RANDOM: 'random',
    Sort.RECENTLY_FAVORITED: 'recently liked',
    Sort.RECENTLY_VOTED: 'recently voted'
}

DATE_LABELS: dict[DateRange, str] = {
    DateRange.ANY: 'any time',
    DateRange.TODAY: 'today',
    DateRange.LAST_24_HOURS: '24 hours',
    DateRange.WEEK: 'week',
    DateRange.MONTH: 'month',
    DateRange.CUSTOM: 'custom'
}

DATE_SUMMARY: dict[DateRange, str] = {
    DateRange.TODAY: 'today',
    DateRange.LAST_24_HOURS: 'last 24 hours',
    DateRange.WEEK: 'last week',
    DateRange.MONTH: 'last month'
}

STAR_LABELS: dict[int, str] = {0: 'any', 1: '1+', 2: '2+', 3: '3+', 4: '4+', 5: '5+'}

RESOLUTION_LABELS: dict[Resolution, str] = {
    Resolution.ANY: 'any',
    Resolution.HD: 'HD',
    Resolution.FULL_HD: 'Full HD',
    Resolution.QHD: '2K',
    Resolution.UHD: '4K'
}

TYPE_LABELS: dict[FileType, str] = {
    FileType.ANY: 'any',
    FileType.IMAGE: 'image',
    FileType.GIF: 'gif',
    FileType.VIDEO: 'video'
}

DURATION_LABELS: dict[Duration, str] = {
    Duration.ANY: 'any',
    Duration.UNDER_1_MIN: 'under 1 min',
    Duration.ONE_TO_FIVE_MIN: '1–5 min',
    Duration.FIVE_TO_TEN_MIN: '5–10 min',
    Duration.OVER_10_MIN: 'over 10 min'
}

USER_FIELDS: tuple[tuple[str, str], ...] = (
    ('liked-by', 'liked by'),
    ('uploaded-by', 'uploaded by'),
    ('voted-by', 'voted by')
)

SUGGEST_DEBOUNCE_SECONDS: float = 0.25
DATE_FORMAT_HINT: str = 'YYYY-MM-DD'


def summarize(filters: SearchFilters) -> list[str]:
    """Short human-readable pieces, in the order the dialog shows them."""
    parts: list[str] = []
    if filters.sort is not Sort.NEWEST:
        parts.append(SORT_LABELS[filters.sort])

    if filters.date_range is DateRange.CUSTOM and filters.date_from is not None:
        parts.append(f'{filters.date_from:%Y-%m-%d} – {(filters.date_to or date.today()):%Y-%m-%d}')
    elif filters.date_range in DATE_SUMMARY:
        parts.append(DATE_SUMMARY[filters.date_range])

    if filters.min_stars:
        parts.append(f'{STAR_LABELS[filters.min_stars]} stars')

    if filters.resolution is not Resolution.ANY:
        parts.append(f'≥ {RESOLUTION_LABELS[filters.resolution]}')

    if filters.file_type is not FileType.ANY:
        kind = TYPE_LABELS[filters.file_type]
        if filters.file_type is FileType.VIDEO and filters.duration is not Duration.ANY:
            kind = f'{kind} {DURATION_LABELS[filters.duration]}'
        parts.append(kind)

    for label, name in (('liked by', filters.liked_by), ('uploaded by', filters.uploaded_by), ('voted by', filters.voted_by)):
        if name.strip():
            parts.append(f'{label} {name.strip()}')

    return parts


def parse_day(text: str, name: str) -> date | None:
    cleaned = text.strip()
    if not cleaned:
        return None

    try:
        return date.fromisoformat(cleaned)
    except ValueError:
        raise ValueError(f'{name} must be a date like {DATE_FORMAT_HINT}') from None


class FiltersScreen(ModalScreen[SearchFilters | None], ArrowNavigation):
    """Search filters for one tab. Dismisses with the new filters, or None."""

    BINDINGS = [Binding('escape', 'close', 'Close')]


    def __init__(self, api: SankakuApi, filters: SearchFilters, query: str, anonymous: bool) -> None:
        super().__init__()
        # Suggestions for user names use this (anonymous) client.
        self.api: SankakuApi = api
        self.filters: SearchFilters = filters
        self.query_text: str = query
        self.anonymous: bool = anonymous


    def compose(self) -> ComposeResult:
        f = self.filters
        with Vertical(id='filters-dialog', classes='dialog'):
            with Horizontal(classes='line'):
                yield Static(f'[b]{site_title(self.api.site)}[/] filters', classes='fill')
                yield Action('esc', id='close')

            yield Rule()

            yield from self.choice_field('sort', 'sort', SORT_LABELS, f.sort)
            yield from self.choice_field('date', 'date', DATE_LABELS, f.date_range)
            with Horizontal(classes='field'):
                yield Label('', classes='caption')
                yield Label('from', classes='inline-caption')
                yield Input(
                    value=f'{f.date_from:%Y-%m-%d}' if f.date_from else '',
                    placeholder=DATE_FORMAT_HINT,
                    restrict=r'[0-9-]*',
                    id='date-from',
                    compact=True,
                    classes='date'
                )
                yield Label('to', classes='inline-caption')
                yield Input(
                    value=f'{f.date_to:%Y-%m-%d}' if f.date_to else '',
                    placeholder='today',
                    restrict=r'[0-9-]*',
                    id='date-to',
                    compact=True,
                    classes='date'
                )
            yield from self.choice_field('stars', 'min rating', STAR_LABELS, f.min_stars, hint='stars and up')
            yield from self.choice_field('size', 'min size', RESOLUTION_LABELS, f.resolution)
            yield from self.choice_field('type', 'file type', TYPE_LABELS, f.file_type)
            yield from self.choice_field('duration', 'duration', DURATION_LABELS, f.duration, hint='video only')

            values = {'liked-by': f.liked_by, 'uploaded-by': f.uploaded_by, 'voted-by': f.voted_by}
            for field_id, caption in USER_FIELDS:
                menu = SuggestionMenu(id=f'{field_id}-menu')
                with Vertical(classes='field-group'):
                    with Horizontal(classes='field-row'):
                        yield Label(caption, classes='caption')
                        yield NameInput(menu, value=values[field_id], placeholder='user name', id=field_id)
                    yield menu

            # Action row: the message slot keeps its place, so nothing moves.
            with Horizontal(classes='line actions'):
                yield Static('', id='filters-message', classes='fill message')
                yield Action('reset', id='reset')
                yield Action('cancel', id='cancel')
                yield Action('❯ apply', 'accent', id='apply')


    def choice_field(
        self,
        field_id: str,
        caption: str,
        labels: dict[object, str],
        value: object,
        hint: str = ''
    ) -> ComposeResult:
        with Horizontal(classes='field'):
            yield Label(caption, classes='caption')
            yield ChoiceRow(list(labels.items()), value, id=field_id)
            if hint:
                yield Static(f'[dim]{hint}[/]', classes='unit')


    def on_mount(self) -> None:
        self.sync_dependent_fields()
        self.refresh_message()
        row = self.query_one('#sort', ChoiceRow)
        for option in row.query(ChoiceOption):
            if option.selected:
                option.focus()
                break


    def on_choice_row_changed(self, event: ChoiceRow.Changed) -> None:
        self.sync_dependent_fields()
        self.refresh_message()


    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id in {field_id for field_id, _ in USER_FIELDS} and event.input.has_focus:
            self.suggest_users(event.input.id, event.value)

        self.refresh_message()


    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id in {field_id for field_id, _ in USER_FIELDS}:
            menu = self.query_one(f'#{event.input.id}-menu', SuggestionMenu)
            choice = menu.selected()
            if choice is not None:
                self.query_one(f'#{event.input.id}', NameInput).accept(choice)
                return

        self.apply()


    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        menu_id = event.option_list.id or ''
        if event.option.id is None or not menu_id.endswith('-menu'):
            return

        field = self.query_one(f'#{menu_id.removesuffix("-menu")}', NameInput)
        field.accept(event.option.id)
        field.focus()


    def on_action_pressed(self, event: Action.Pressed) -> None:
        action_id = event.action.id
        if action_id == 'apply':
            self.apply()
        elif action_id == 'reset':
            self.reset()
        elif action_id in ('cancel', 'close'):
            self.action_close()


    def action_close(self) -> None:
        self.dismiss(None)


    @work(exclusive=True, group='users', exit_on_error=False)
    async def suggest_users(self, field_id: str, value: str) -> None:
        menu = self.query_one(f'#{field_id}-menu', SuggestionMenu)
        if len(value.strip()) < MIN_TERM_LENGTH:
            menu.close()
            return

        # Exclusive: a newer keystroke cancels this worker during the sleep.
        await asyncio.sleep(SUGGEST_DEBOUNCE_SECONDS)
        names = await asyncio.to_thread(self.api.autocomplete_users, value)
        if self.query_one(f'#{field_id}', NameInput).has_focus:
            menu.show_names(value, names)


    def sync_dependent_fields(self) -> None:
        """Date inputs only for a custom range, duration only for video."""
        custom = self.query_one('#date', ChoiceRow).value is DateRange.CUSTOM
        for selector in ('#date-from', '#date-to'):
            self.query_one(selector, Input).disabled = not custom

        video = self.query_one('#type', ChoiceRow).value is FileType.VIDEO
        self.query_one('#duration', ChoiceRow).disabled = not video


    def reset(self) -> None:
        defaults = SearchFilters()
        self.query_one('#sort', ChoiceRow).select(defaults.sort)
        self.query_one('#date', ChoiceRow).select(defaults.date_range)
        self.query_one('#stars', ChoiceRow).select(defaults.min_stars)
        self.query_one('#size', ChoiceRow).select(defaults.resolution)
        self.query_one('#type', ChoiceRow).select(defaults.file_type)
        self.query_one('#duration', ChoiceRow).select(defaults.duration)
        for selector in ('#date-from', '#date-to', '#liked-by', '#uploaded-by', '#voted-by'):
            self.query_one(selector, Input).value = ''

        self.sync_dependent_fields()
        self.refresh_message()


    def read_form(self) -> SearchFilters:
        date_range = self.query_one('#date', ChoiceRow).value
        date_from = parse_day(self.query_one('#date-from', Input).value, 'from')
        date_to = parse_day(self.query_one('#date-to', Input).value, 'to')
        if date_range is DateRange.CUSTOM:
            if date_from is None:
                raise ValueError(f'a custom date range needs a start date ({DATE_FORMAT_HINT})')
            if date_to is not None and date_to < date_from:
                raise ValueError('the end date is before the start date')

        return replace(
            self.filters,
            sort=self.query_one('#sort', ChoiceRow).value,
            date_range=date_range,
            date_from=date_from if date_range is DateRange.CUSTOM else None,
            date_to=date_to if date_range is DateRange.CUSTOM else None,
            min_stars=self.query_one('#stars', ChoiceRow).value,
            resolution=self.query_one('#size', ChoiceRow).value,
            file_type=self.query_one('#type', ChoiceRow).value,
            duration=self.query_one('#duration', ChoiceRow).value,
            liked_by=self.query_one('#liked-by', Input).value.strip(),
            uploaded_by=self.query_one('#uploaded-by', Input).value.strip(),
            voted_by=self.query_one('#voted-by', Input).value.strip()
        )


    def operator_count(self, filters: SearchFilters) -> int:
        return count_operators(self.query_text) + count_operators(' '.join(filters.to_tags()))


    def refresh_message(self) -> None:
        """Keeps the anonymous operator-tag budget visible while filters change."""
        message = self.query_one('#filters-message', Static)
        try:
            filters = self.read_form()
        except ValueError:
            message.update('')
            return

        used = self.operator_count(filters)
        if not self.anonymous:
            message.update(f'[dim]{used} advanced filter(s)[/]' if used else '')
            return

        if used > ANONYMOUS_OPERATOR_LIMIT:
            message.update(
                f'[$error]{used} advanced filters · {ANONYMOUS_OPERATOR_LIMIT} allowed without sign-in[/]'
            )
            return

        message.update(f'[dim]advanced filters {used}/{ANONYMOUS_OPERATOR_LIMIT} without sign-in[/]')


    def apply(self) -> None:
        message = self.query_one('#filters-message', Static)
        try:
            filters = self.read_form()
        except ValueError as err:
            message.update(f'[$error]{escape(str(err))}[/]')
            return

        if self.anonymous and self.operator_count(filters) > ANONYMOUS_OPERATOR_LIMIT:
            message.update(
                f'[$error]Sankaku allows {ANONYMOUS_OPERATOR_LIMIT} advanced filters without sign-in · '
                'remove some or sign in[/]'
            )
            return

        self.dismiss(filters)
