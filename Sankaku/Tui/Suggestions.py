from pathlib import Path
from textual.binding import Binding
from textual.widgets import Input, OptionList
from textual.widgets.option_list import Option
from rich.markup import escape
from Sankaku.Api.Models import TagSuggestion


MENU_SIZE: int = 6
EXCLUDE_PREFIX: str = '-'
# Suggest from the first letter; the input debounce keeps requests in check.
MIN_TERM_LENGTH: int = 1
PATH_SEPARATORS: tuple[str, ...] = ('/', '\\')


def format_count(count: int) -> str:
    return f'{count:,}'.replace(',', ' ')


# ---- tags -------------------------------------------------------------------

def split_last_tag(query: str) -> tuple[str, str, str]:
    """Splits a query into (everything before the last tag, '-' or '', the tag)."""
    head, separator, word = query.rpartition(' ')
    prefix = EXCLUDE_PREFIX if word.startswith(EXCLUDE_PREFIX) else ''

    return f'{head}{separator}', prefix, word[len(prefix):]


def completable_term(query: str) -> str | None:
    """The tag under completion, or None when there is nothing to suggest for."""
    _, _, term = split_last_tag(query)
    if len(term) < MIN_TERM_LENGTH or ':' in term:
        return None

    return term


# ---- folders ----------------------------------------------------------------

def split_path(value: str) -> tuple[str, str]:
    """Splits a typed path into (the folder part incl. separator, the partial name)."""
    cut = max(value.rfind(separator) for separator in PATH_SEPARATORS)

    return value[:cut + 1], value[cut + 1:]


def folder_suggestions(root: Path, value: str) -> list[str]:
    """Existing sub-folders matching what is typed, as complete new field values.

    Relative input is resolved against the project root, absolute input as is.
    Hidden folders only show up once the typed name starts with a dot.
    """
    head, partial = split_path(value)
    base = Path(head).expanduser() if head else Path('.')
    if not base.is_absolute():
        base = root / base

    try:
        entries = sorted(entry.name for entry in base.iterdir() if entry.is_dir())
    except OSError:
        return []

    separator = '\\' if '\\' in head and '/' not in head else '/'
    lowered = partial.lower()
    matches: list[str] = []
    for name in entries:
        if name.startswith('.') and not partial.startswith('.'):
            continue

        if name.lower().startswith(lowered) and name != partial:
            matches.append(f'{head}{name}{separator}')

    return matches[:MENU_SIZE]


# ---- widgets ----------------------------------------------------------------

class SuggestionMenu(OptionList):
    """Dropdown of suggestions floating under an input, like Select's list."""

    # Keep keyboard focus in the input while the menu is used with the mouse.
    FOCUS_ON_CLICK = False

    DEFAULT_CSS = '''
    /* overlay takes it out of the layout (nothing below moves), constrain
       keeps it on screen. */
    SuggestionMenu {
        display: none;
        overlay: screen;
        constrain: none inside;
        height: auto;
        max-height: 10;
        width: 50;
        margin-left: 11;
        border: round $foreground 25%;
        padding: 0;
        background: ansi_default;
    }

    SuggestionMenu > .option-list--option {
        padding: 0 1;
    }

    SuggestionMenu:focus {
        border: round $foreground 25%;
    }

    SuggestionMenu > .option-list--option-highlighted {
        background: $accent;
        color: #141414;
        text-style: bold;
    }

    SuggestionMenu > .option-list--option-hover {
        background: $accent 30%;
    }
    '''


    def __init__(self, id: str) -> None:
        # Not compact: compact OptionList forces 'border: none !important',
        # and the floating menu needs its frame.
        super().__init__(id=id)
        self.can_focus = False


    @property
    def is_open(self) -> bool:
        return self.display and self.option_count > 0


    def show_rows(self, rows: list[tuple[str, str]]) -> None:
        """Shows (value, markup) rows; an empty list closes the menu."""
        self.clear_options()
        if not rows:
            self.close()
            return

        self.add_options([Option(markup, id=value) for value, markup in rows])
        self.highlighted = 0
        self.display = True


    def show_tags(self, term: str, suggestions: list[TagSuggestion]) -> None:
        items = [item for item in suggestions if item.name != term][:MENU_SIZE]
        if not items:
            self.close()
            return

        width = max(len(item.name) for item in items)
        self.show_rows([
            (item.name, f'{escape(item.name.ljust(width))}   [dim]{format_count(item.post_count)}[/]')
            for item in items
        ])


    def show_folders(self, values: list[str]) -> None:
        rows: list[tuple[str, str]] = []
        for value in values:
            _, name = split_path(value.rstrip('/\\'))
            rows.append((value, f'{escape(name)}[dim]/[/]'))

        self.show_rows(rows)


    def show_names(self, typed: str, names: list[str]) -> None:
        rows = [(name, escape(name)) for name in names if name.lower() != typed.strip().lower()]
        self.show_rows(rows[:MENU_SIZE])


    def close(self) -> None:
        self.display = False
        self.clear_options()


    def selected(self) -> str | None:
        if not self.is_open or self.highlighted is None:
            return None

        return self.get_option_at_index(self.highlighted).id


class MenuInput(Input):
    """An input that drives its SuggestionMenu from the keyboard.

    ↑/↓ move through the menu, Tab/Enter take the highlighted suggestion,
    Esc closes it. With the menu closed, Tab moves focus as usual.
    """

    BINDINGS = [
        Binding('down', 'menu_down', show=False),
        Binding('up', 'menu_up', show=False),
        Binding('tab', 'menu_accept', show=False),
        Binding('escape', 'menu_close', show=False)
    ]


    def __init__(
        self,
        menu: SuggestionMenu,
        value: str = '',
        placeholder: str = '',
        id: str | None = None
    ) -> None:
        # No select-all on focus: clicking in should place the cursor, not
        # highlight the whole value.
        super().__init__(value=value, placeholder=placeholder, id=id, compact=True, select_on_focus=False)
        self.menu: SuggestionMenu = menu


    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action in ('menu_down', 'menu_up', 'menu_accept', 'menu_close'):
            return self.menu.is_open

        return True


    def action_menu_down(self) -> None:
        if self.menu.is_open:
            self.menu.action_cursor_down()


    def action_menu_up(self) -> None:
        if self.menu.is_open:
            self.menu.action_cursor_up()


    def action_menu_accept(self) -> None:
        choice = self.menu.selected()
        if choice is None:
            self.screen.focus_next()
            return

        self.accept(choice)


    def action_menu_close(self) -> None:
        self.menu.close()


    def accept(self, choice: str) -> None:
        self.value = self.completed(choice)
        self.cursor_position = len(self.value)
        self.menu.close()


    def completed(self, choice: str) -> str:
        """The field's new value once `choice` is taken."""
        return choice


class QueryInput(MenuInput):
    """Search field: a suggestion replaces the tag being typed."""

    def completed(self, choice: str) -> str:
        head, prefix, _ = split_last_tag(self.value)

        return f'{head}{prefix}{choice} '


class PathInput(MenuInput):
    """Folder field: a suggestion is already the complete new path."""


class NameInput(MenuInput):
    """User-name field: a suggestion replaces the whole value."""
