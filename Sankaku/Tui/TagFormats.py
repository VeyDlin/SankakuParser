from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.geometry import Region
from textual.message import Message
from textual.screen import ModalScreen
from Sankaku.Config import TAG_FORMATS
from Sankaku.Tui.Navigation import ArrowNavigation
from Sankaku.Tui.Widgets import Action, Toggle


FORMAT_HINTS: dict[str, str] = {
    'txt': 'txt   tags in one line',
    'json': 'json  tags by category + post info · 1 extra request per file'
}


def formats_label(formats: tuple[str, ...]) -> str:
    chosen = ', '.join(formats) if formats else 'not saved'

    return f'tags: {chosen} ▾'


class TagFormatsMenu(ModalScreen[tuple[str, ...]], ArrowNavigation):
    """Dropdown of tag sidecar formats; any number may be ticked.

    Hangs under the button that opened it. Closes on Esc or a click outside,
    returning whatever is ticked at that moment.
    """

    BINDINGS = [Binding('escape', 'close', 'Close')]


    def __init__(self, picker: 'TagFormatPicker') -> None:
        super().__init__()
        self.picker: TagFormatPicker = picker
        self.formats: tuple[str, ...] = picker.formats
        self.anchor: Region = picker.region


    def compose(self) -> ComposeResult:
        with Vertical(id='tag-formats-menu'):
            for name in TAG_FORMATS:
                yield Toggle(FORMAT_HINTS[name], name in self.formats, id=f'format-{name}')


    def on_mount(self) -> None:
        menu = self.query_one('#tag-formats-menu', Vertical)
        menu.styles.margin = (self.anchor.bottom, 0, 0, self.anchor.x)
        self.query_one(f'#format-{TAG_FORMATS[0]}', Toggle).focus()


    def on_toggle_changed(self, event: Toggle.Changed) -> None:
        # Live: the button shows the choice as it is made, not only on close.
        self.picker.choose(self.chosen())


    def chosen(self) -> tuple[str, ...]:
        return tuple(name for name in TAG_FORMATS if self.query_one(f'#format-{name}', Toggle).value)


    def on_click(self, event: events.Click) -> None:
        if event.widget is self:
            self.action_close()


    def action_close(self) -> None:
        self.dismiss(self.chosen())


class TagFormatPicker(Action):
    """`tags: txt, json ▾` — opens TagFormatsMenu under itself."""

    class Changed(Message):
        def __init__(self, picker: 'TagFormatPicker', formats: tuple[str, ...]) -> None:
            super().__init__()
            self.picker: TagFormatPicker = picker
            self.formats: tuple[str, ...] = formats


        @property
        def control(self) -> 'TagFormatPicker':
            return self.picker


    def __init__(self, formats: tuple[str, ...], id: str) -> None:
        super().__init__(formats_label(formats), id=id)
        self.formats: tuple[str, ...] = formats


    def set_formats(self, formats: tuple[str, ...]) -> None:
        self.formats = formats
        self.label = formats_label(formats)


    def action_press(self) -> None:
        if self.disabled:
            return

        self.app.push_screen(TagFormatsMenu(self), self.menu_closed)


    def menu_closed(self, formats: tuple[str, ...] | None) -> None:
        if formats is not None:
            self.choose(formats)


    def choose(self, formats: tuple[str, ...]) -> None:
        """A user choice: update the label and tell the pane."""
        if formats == self.formats:
            return

        self.set_formats(formats)
        self.post_message(self.Changed(self, formats))
