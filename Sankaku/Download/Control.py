import threading


PAUSE_POLL_SECONDS: float = 0.2


class DownloadControl:
    """Thread-safe pause/stop flags shared between the key listener and the loop.

    Stop wins over pause: stopping always releases a paused loop so it can
    observe the stop and unwind.
    """

    def __init__(self) -> None:
        self.stop_event: threading.Event = threading.Event()
        self.resume_event: threading.Event = threading.Event()
        self.resume_event.set()


    @property
    def is_stopped(self) -> bool:
        return self.stop_event.is_set()


    @property
    def is_paused(self) -> bool:
        return not self.resume_event.is_set()


    def stop(self) -> None:
        self.stop_event.set()
        self.resume_event.set()


    def pause(self) -> None:
        if self.is_stopped:
            return

        self.resume_event.clear()


    def resume(self) -> None:
        self.resume_event.set()


    def toggle_pause(self) -> bool:
        """Flips the pause flag. Returns True when the new state is 'paused'."""
        if self.is_paused:
            self.resume()
            return False

        self.pause()

        return True


    def wait_while_paused(self) -> None:
        """Blocks while paused. Returns immediately once stopped."""
        while not self.is_stopped:
            if self.resume_event.wait(timeout=PAUSE_POLL_SECONDS):
                return


    def sleep(self, seconds: float) -> None:
        """Interruptible sleep — returns early when stopped."""
        self.stop_event.wait(timeout=seconds)
