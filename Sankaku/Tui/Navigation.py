from textual.binding import Binding
from textual.screen import Screen
from textual.widget import Widget


# ↑/↓ to the row above/below, ←/→ along the row. Widgets that need an arrow for
# themselves (text inputs, an open suggestion list) handle it before these.
ARROW_BINDINGS: list[Binding] = [
    Binding('up', 'focus_toward("up")', show=False),
    Binding('down', 'focus_toward("down")', show=False),
    Binding('left', 'focus_toward("left")', show=False),
    Binding('right', 'focus_toward("right")', show=False)
]


class ArrowNavigation(Screen[object]):
    """Base for modal screens: arrows move focus spatially inside the dialog.

    App bindings are not consulted while a modal screen is active, so every
    dialog carries the arrow bindings itself.
    """

    BINDINGS = ARROW_BINDINGS


    def action_focus_toward(self, direction: str) -> None:
        move_focus(self, direction)


def move_focus(screen: Screen[object], direction: str) -> None:
    """Moves focus to the nearest control in a direction. Nothing happens at an edge."""
    current = screen.focused
    candidates = [widget for widget in screen.focus_chain if widget is not current and widget.region.area]
    if current is None:
        if candidates:
            candidates[0].focus()
        return

    target = nearest(current, candidates, direction)
    if target is not None:
        target.focus()


def nearest(current: Widget, candidates: list[Widget], direction: str) -> Widget | None:
    """The closest candidate in a direction.

    Vertical moves take the nearest row first, then the control whose left edge
    is closest: forms here are one left-aligned column, so the left edge (not
    the centre of a wide field) says which control sits "below".
    """
    here = current.region
    best: Widget | None = None
    best_key: tuple[int, int] | None = None

    for widget in candidates:
        there = widget.region
        same_row = there.y < here.bottom and there.bottom > here.y
        if direction == 'down' and there.y >= here.bottom:
            key = (there.y - here.y, abs(there.x - here.x))
        elif direction == 'up' and there.bottom <= here.y:
            key = (here.y - there.y, abs(there.x - here.x))
        elif direction == 'right' and same_row and there.x >= here.right:
            key = (there.x - here.x, 0)
        elif direction == 'left' and same_row and there.right <= here.x:
            key = (here.x - there.x, 0)
        else:
            continue

        if best_key is None or key < best_key:
            best, best_key = widget, key

    return best
