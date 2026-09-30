from rich.markup import escape
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.theme import Theme
from textual.timer import Timer
from textual.widgets import ContentSwitcher, Static
from Sankaku.Api.Endpoints import SankakuSite
from Sankaku.Auth.TokenStore import TokenStore
from Sankaku.Config import AppConfig
from Sankaku.Tui.SitePane import SPINNER_FRAMES, SPINNER_INTERVAL_SECONDS, AccountView, SitePane
from Sankaku.Tui import Palette
from Sankaku.Tui.Navigation import ARROW_BINDINGS, move_focus
from Sankaku.Tui.SettingsScreen import SettingsScreen
from Sankaku.Tui.Sites import site_title
from Sankaku.Tui.Widgets import Action, SiteTab


TAB_PREFIX: str = 'tab-'
PANE_PREFIX: str = 'pane-'

# The background is the terminal's own (see App.tcss), so only the foreground
# colours matter here; they live in Palette.
THEME: Theme = Theme(
    name='sankaku',
    primary=Palette.ACCENT,
    accent=Palette.ACCENT,
    secondary=Palette.SECONDARY,
    success=Palette.SUCCESS,
    warning=Palette.WARNING,
    error=Palette.ERROR,
    foreground=Palette.FOREGROUND,
    background=Palette.BACKGROUND,
    surface=Palette.SURFACE,
    panel=Palette.PANEL,
    dark=True
)


class SankakuApp(App[None]):
    TITLE = 'Sankaku Parser'
    CSS_PATH = 'App.tcss'
    # Tab/Shift+Tab walk every control; the arrows move focus spatially: ↑/↓ to
    # the row above/below, ←/→ along the row. Widgets that need an arrow for
    # themselves (text inputs, an open suggestion list) handle it first.
    BINDINGS = [Binding('ctrl+q', 'quit', 'Quit', priority=True), *ARROW_BINDINGS]


    def __init__(self, config: AppConfig) -> None:
        # ansi_color lets the stylesheet use ansi_default: the terminal's own
        # background instead of a painted one.
        super().__init__(ansi_color=True)
        self.config: AppConfig = config
        self.token_store: TokenStore = TokenStore(config.session_path)
        self.register_theme(THEME)
        self.theme = THEME.name
        self.account_spinner: Timer | None = None
        self.account_frame: int = 0


    def compose(self) -> ComposeResult:
        # A hand-built top bar: site tabs, account status and settings are all
        # plain focusable actions on one row, so the arrows walk along it and
        # Enter/Space picks the focused one (arrows never switch the page).
        first = next(iter(SankakuSite))
        with Horizontal(id='topbar'):
            for site in SankakuSite:
                tab = SiteTab(site_title(site), id=f'{TAB_PREFIX}{site.value}', classes='site-tab')
                tab.current = site is first
                yield tab
            yield Static('', classes='fill')
            yield Static('', id='account-note')
            yield Action(f'checking sign-in [$accent]{SPINNER_FRAMES[0]}[/]', id='account', disabled=True)
            yield Action('settings', id='settings')

        with ContentSwitcher(initial=f'{PANE_PREFIX}{first.value}', id='panes'):
            for site in SankakuSite:
                yield SitePane(site, self.config, self.token_store, id=f'{PANE_PREFIX}{site.value}')


    def on_mount(self) -> None:
        # Start where the work starts: the search field, not the first tab.
        self.active_pane().query_one('#query').focus()


    def pane_for(self, site: SankakuSite) -> SitePane:
        return self.query_one(f'#{PANE_PREFIX}{site.value}', SitePane)


    def active_pane(self) -> SitePane:
        current = self.query_one('#panes', ContentSwitcher).current or ''
        site_value = current.removeprefix(PANE_PREFIX)

        return self.query_one(f'#{PANE_PREFIX}{site_value}', SitePane)


    def show_site(self, site: SankakuSite) -> None:
        self.query_one('#panes', ContentSwitcher).current = f'{PANE_PREFIX}{site.value}'
        for tab in self.query(SiteTab):
            tab.current = tab.id == f'{TAB_PREFIX}{site.value}'

        self.refresh_account()


    def on_action_pressed(self, event: Action.Pressed) -> None:
        action_id = event.action.id or ''
        if action_id.startswith(TAB_PREFIX):
            self.show_site(SankakuSite(action_id.removeprefix(TAB_PREFIX)))
        elif action_id == 'account':
            self.active_pane().open_account()
        elif event.action.id == 'settings':
            self.open_settings()


    def open_settings(self) -> None:
        pane = self.active_pane()
        self.push_screen(SettingsScreen(self.config, pane.site), lambda saved: self.settings_closed(pane, saved))


    def settings_closed(self, pane: SitePane, saved: bool | None) -> None:
        if not saved:
            return

        pane.apply_settings()

        self.notify('Settings saved · downloads already running keep their old settings')


    def on_site_pane_account_changed(self, message: SitePane.AccountChanged) -> None:
        self.refresh_account()


    def on_site_pane_state_changed(self, message: SitePane.StateChanged) -> None:
        """Badges the tab, so a background tab's download stays visible."""
        tab = self.query_one(f'#{TAB_PREFIX}{message.site.value}', SiteTab)
        title = site_title(message.site)
        tab.label = f'{title} {message.badge}' if message.badge else title


    def refresh_account(self) -> None:
        """Shows the active tab's sign-in state in the top bar.

        | state            | shown                             | click           |
        | checking         | checking sign-in ✻ (inert)        | —               |
        | signed in        | Fangog ●                          | sign-out menu   |
        | signed out       | not signed in · sign in           | sign-in dialog  |
        | never signed in  | sign in                           | sign-in dialog  |
        | error            | sign-in error ✕                   | dialog + reason |

        Icons trail the text: the bar is right-aligned, so a trailing icon stays
        put while only the text changes length.
        """
        pane = self.active_pane()
        view = pane.account_view()
        account = self.query_one('#account', Action)
        note = self.query_one('#account-note', Static)

        note.display = view in (AccountView.SIGNED_IN, AccountView.SIGNED_OUT)
        note.update('[dim]signed in as[/]' if view is AccountView.SIGNED_IN else '[dim]not signed in ·[/]')
        account.disabled = view is AccountView.CHECKING

        if view is AccountView.CHECKING:
            account.set_tone('')
            account.label = f'checking sign-in [$accent]{SPINNER_FRAMES[self.account_frame]}[/]'
            if self.account_spinner is None:
                self.account_spinner = self.set_interval(SPINNER_INTERVAL_SECONDS, self.tick_account)
            return

        self.stop_account_spinner()

        if view is AccountView.SIGNED_IN:
            account.set_tone('success')
            account.label = f'{escape(pane.username())} ●'
        elif view is AccountView.ERROR:
            account.set_tone('error')
            account.label = 'sign-in error ✕'
        else:
            account.set_tone('accent')
            account.label = 'sign in'


    def tick_account(self) -> None:
        self.account_frame = (self.account_frame + 1) % len(SPINNER_FRAMES)
        self.refresh_account()


    def stop_account_spinner(self) -> None:
        if self.account_spinner is None:
            return

        self.account_spinner.stop()
        self.account_spinner = None


    def action_focus_toward(self, direction: str) -> None:
        move_focus(self.screen, direction)
