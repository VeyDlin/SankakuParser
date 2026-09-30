from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from Sankaku.Tui.Navigation import ArrowNavigation
from Sankaku.Tui.Widgets import Action


class AccountMenu(ModalScreen[bool], ArrowNavigation):
    """Small dropdown under the account status for a signed-in user.

    Dismisses with True when the user chose to sign out. A click anywhere
    outside the menu closes it, like any dropdown.
    """

    BINDINGS = [Binding('escape', 'close', 'Close')]


    def compose(self) -> ComposeResult:
        # Who is signed in is already on the status the user just clicked, so
        # the menu holds only the action.
        with Vertical(id='account-menu'):
            yield Action('sign out', 'error', id='sign-out')


    def on_mount(self) -> None:
        # Opened from the keyboard, the only action should be ready for Enter.
        self.query_one('#sign-out', Action).focus()


    def on_action_pressed(self, event: Action.Pressed) -> None:
        if event.action.id == 'sign-out':
            self.dismiss(True)


    def on_click(self, event: events.Click) -> None:
        if event.widget is self:
            self.dismiss(False)


    def action_close(self) -> None:
        self.dismiss(False)
