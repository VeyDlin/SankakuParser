from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import ProgressBar, Static


class Action(Static, can_focus=True):
    """Flat clickable text — a borderless button that takes exactly one row.

    Reachable from the keyboard: Tab/arrows focus it (shown exactly like the
    mouse hover), Enter or Space presses it.

    Only text glyphs are used for icons: characters like ⏸ or ⬇ render as
    colour emoji in Windows Terminal and break the alignment.
    """

    DEFAULT_CSS = '''
    Action {
        width: auto;
        height: 1;
        padding: 0 1;
        color: $text-muted;
        pointer: pointer;
    }

    Action:hover,
    Action:focus {
        color: #141414;
        background: $accent;
        text-style: bold;
    }

    Action:disabled {
        color: $text-disabled;
        pointer: not-allowed;
    }

    Action:disabled:hover {
        background: transparent;
        text-style: none;
    }

    Action.-accent {
        color: $accent;
    }

    Action.-success {
        color: $success;
    }

    Action.-warning {
        color: $warning;
    }

    Action.-error {
        color: $error;
    }

    Action.-accent:hover,
    Action.-success:hover,
    Action.-warning:hover,
    Action.-error:hover,
    Action.-accent:focus,
    Action.-success:focus,
    Action.-warning:focus,
    Action.-error:focus {
        color: #141414;
    }

    Action.-success:hover,
    Action.-success:focus {
        background: $success;
    }

    Action.-warning:hover,
    Action.-warning:focus {
        background: $warning;
    }

    Action.-error:hover,
    Action.-error:focus {
        background: $error;
    }

    Action:disabled.-accent,
    Action:disabled.-success,
    Action:disabled.-warning,
    Action:disabled.-error {
        color: $text-disabled;
    }
    '''

    BINDINGS = [
        Binding('enter', 'press', show=False),
        Binding('space', 'press', show=False)
    ]

    TONES: tuple[str, ...] = ('accent', 'success', 'warning', 'error')

    # layout=True: the width is 'auto', so a new label must trigger a relayout.
    label: reactive[str] = reactive('', layout=True)


    class Pressed(Message):
        def __init__(self, action: 'Action') -> None:
            super().__init__()
            self.action: Action = action


        @property
        def control(self) -> 'Action':
            return self.action


    def __init__(
        self,
        label: str,
        tone: str = '',
        id: str | None = None,
        disabled: bool = False,
        classes: str | None = None
    ) -> None:
        super().__init__(id=id, disabled=disabled, classes=classes)
        self.label = label
        self.tone: str = ''
        self.set_tone(tone)


    def render(self) -> str:
        return self.label


    def set_tone(self, tone: str) -> None:
        for name in self.TONES:
            self.remove_class(f'-{name}')

        self.tone = tone
        if tone:
            self.add_class(f'-{tone}')


    def on_click(self, event: events.Click) -> None:
        event.stop()
        self.action_press()


    def action_press(self) -> None:
        if self.disabled:
            return

        self.post_message(self.Pressed(self))


class SiteTab(Action):
    """A site tab in the top bar. `current` marks the tab whose page is shown.

    It is a plain focusable action on purpose: arrows only move focus along the
    top bar, and Enter/Space (or a click) switches the page.
    """

    DEFAULT_CSS = '''
    SiteTab.-current {
        color: $accent;
        text-style: bold;
    }

    /* The fill is the accent: the current tab's accent text would vanish on it. */
    SiteTab.-current:hover,
    SiteTab.-current:focus {
        color: #141414;
    }
    '''

    current: reactive[bool] = reactive(False)


    def watch_current(self, current: bool) -> None:
        self.set_class(current, '-current')


class ChoiceOption(Action):
    """One option of a ChoiceRow; the selected one is accented."""

    DEFAULT_CSS = '''
    ChoiceOption {
        margin-right: 1;
    }

    ChoiceOption.-selected {
        color: $accent;
        text-style: bold;
    }

    ChoiceOption.-selected:hover,
    ChoiceOption.-selected:focus {
        color: #141414;
    }
    '''

    selected: reactive[bool] = reactive(False)


    def __init__(self, label: str, value: object, id: str | None = None) -> None:
        super().__init__(label, id=id)
        self.value: object = value


    def watch_selected(self, selected: bool) -> None:
        self.set_class(selected, '-selected')


class ChoiceRow(Horizontal):
    """Pick one of several options, laid out in a row (a segmented control).

    Arrows move focus between the options; Enter/Space or a click picks one.
    """

    DEFAULT_CSS = '''
    ChoiceRow {
        width: auto;
        height: 1;
        margin-right: 2;
    }
    '''


    class Changed(Message):
        def __init__(self, row: 'ChoiceRow', value: object) -> None:
            super().__init__()
            self.row: ChoiceRow = row
            self.value: object = value


        @property
        def control(self) -> 'ChoiceRow':
            return self.row


    def __init__(self, options: list[tuple[object, str]], value: object, id: str) -> None:
        super().__init__(id=id)
        self.options: list[tuple[object, str]] = options
        self.value: object = value


    def compose(self) -> ComposeResult:
        for index, (value, label) in enumerate(self.options):
            option = ChoiceOption(label, value, id=f'{self.id}-{index}')
            option.selected = value == self.value
            yield option


    def on_action_pressed(self, event: Action.Pressed) -> None:
        if not isinstance(event.action, ChoiceOption):
            return

        event.stop()
        self.select(event.action.value)
        self.post_message(self.Changed(self, self.value))


    def select(self, value: object) -> None:
        self.value = value
        for option in self.query(ChoiceOption):
            option.selected = option.value == value


class Toggle(Static, can_focus=True):
    """A one-row `[x] label` checkbox. Enter or Space flips it when focused."""

    DEFAULT_CSS = '''
    Toggle {
        width: auto;
        height: 1;
        padding: 0 1;
        color: $text-muted;
        pointer: pointer;
    }

    Toggle:hover,
    Toggle:focus {
        color: #141414;
        background: $accent;
    }

    Toggle:disabled {
        color: $text-disabled;
        pointer: not-allowed;
    }

    Toggle:disabled:hover {
        background: transparent;
    }
    '''

    BINDINGS = [
        Binding('enter', 'flip', show=False),
        Binding('space', 'flip', show=False)
    ]

    value: reactive[bool] = reactive(False)


    class Changed(Message):
        """Posted when the user flips the toggle (not when code sets it)."""

        def __init__(self, toggle: 'Toggle', value: bool) -> None:
            super().__init__()
            self.toggle: Toggle = toggle
            self.value: bool = value


        @property
        def control(self) -> 'Toggle':
            return self.toggle


    def __init__(self, label: str, value: bool = False, id: str | None = None) -> None:
        super().__init__(id=id)
        self.text: str = label
        self.value = value


    def render(self) -> str:
        if not self.value:
            mark = ' '
        elif self.mouse_hover or self.has_focus:
            # The hover/focus fill is the accent colour: an accent mark would
            # vanish, so there the mark takes the (dark) text colour instead.
            mark = '[b]x[/]'
        else:
            mark = '[$accent]x[/]'

        return f'\\[{mark}] {self.text}'


    def on_enter(self, event: events.Enter) -> None:
        self.refresh()


    def on_leave(self, event: events.Leave) -> None:
        self.refresh()


    def on_focus(self, event: events.Focus) -> None:
        self.refresh()


    def on_blur(self, event: events.Blur) -> None:
        self.refresh()


    def on_click(self, event: events.Click) -> None:
        event.stop()
        self.action_flip()


    def action_flip(self) -> None:
        if self.disabled:
            return

        self.value = not self.value
        self.post_message(self.Changed(self, self.value))


def format_size(size: float) -> str:
    value = float(size)
    for unit in ('B', 'KB', 'MB', 'GB'):
        if value < 1024 or unit == 'GB':
            return f'{value:.0f} {unit}' if unit == 'B' else f'{value:.1f} {unit}'

        value /= 1024

    return f'{value:.1f} GB'
