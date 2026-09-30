class SankakuError(Exception):
    """Any failure while talking to the Sankaku API."""


class AuthError(SankakuError):
    """Credentials were rejected, or the session could not be restored."""
