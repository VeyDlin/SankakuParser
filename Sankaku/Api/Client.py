from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urlparse
from Sankaku.Api.Endpoints import (
    AUTH_HOSTS,
    BROWSER_USER_AGENT,
    DEFAULT_PAGE_SIZE,
    DOWNLOAD_CHUNK_SIZE,
    REQUEST_TIMEOUT,
    SankakuSite,
    SiteEndpoints,
    endpoints_for
)
from Sankaku.Api.Errors import AuthError, SankakuError
from Sankaku.Api.Models import MediaItem, SessionCheck, SessionStatus, TagSuggestion, TypedTag
from Sankaku.Auth.TokenStore import Tokens, TokenStore
import requests
import threading


class SankakuApi:
    """Pure-HTTP Sankaku client.

    Authenticates via POST /auth/token and carries the resulting bearer token —
    no browser and no cookie scraping involved.
    """

    def __init__(
        self,
        site: SankakuSite,
        token_store: TokenStore | None = None,
        page_size: int = DEFAULT_PAGE_SIZE
    ) -> None:
        self.site: SankakuSite = site
        self.endpoints: SiteEndpoints = endpoints_for(site)
        self.page_size: int = page_size
        self.tokens: Tokens | None = None
        self.refresh_lock: threading.Lock = threading.Lock()
        self.token_store: TokenStore | None = token_store
        self.search_tags: str = ''
        self.next_cursor: str | None = None
        self.exhausted: bool = False
        self.session: requests.Session = requests.Session()
        self.session.headers.update({'User-Agent': BROWSER_USER_AGENT})


    def __enter__(self) -> 'SankakuApi':
        return self


    def __exit__(self, *exc_info: Any) -> None:
        self.close()


    def close(self) -> None:
        self.session.close()


    @property
    def is_authorized(self) -> bool:
        return self.tokens is not None


    def login(self, username: str, password: str) -> str:
        """Exchanges credentials for tokens. Returns the authenticated user name."""
        try:
            data = self.request_json(
                'POST',
                f'{self.endpoints.api_base}/auth/token',
                body={'login': username, 'password': password},
                authorized=False
            )
        except requests.HTTPError as err:
            raise AuthError(self.server_error_of(err.response) or 'login rejected') from err
        except (SankakuError, requests.RequestException) as err:
            raise AuthError(f'login failed: {err}') from err

        access = data.get('access_token') if isinstance(data, dict) else None
        if not isinstance(access, str) or not access:
            raise AuthError('Wrong username or password')

        current_user = data.get('current_user')
        name = current_user.get('name') if isinstance(current_user, dict) else None
        refresh = data.get('refresh_token')

        self.tokens = Tokens(
            access=access,
            refresh=refresh if isinstance(refresh, str) else '',
            username=name if isinstance(name, str) and name else username
        )
        self.persist_tokens()

        return self.tokens.username


    def logout(self) -> None:
        """Forgets the session here and on disk (the user name stays remembered)."""
        self.tokens = None
        if self.token_store is not None:
            self.token_store.clear(self.site.value)


    def remembered_username(self) -> str:
        if self.token_store is None:
            return ''

        return self.token_store.remembered_username(self.site.value)


    def restore_session(self) -> SessionCheck:
        """Loads the stored session and verifies it against the API.

        Only a session the server actually rejects is dropped. When the server
        cannot be reached the tokens are kept: being offline says nothing about
        whether the session is still good.
        """
        if self.token_store is None:
            return SessionCheck(SessionStatus.NONE)

        tokens = self.token_store.load(self.site.value)
        if tokens is None:
            return SessionCheck(SessionStatus.NONE)

        self.tokens = tokens

        try:
            data = self.request_json('GET', f'{self.endpoints.api_base}/users/me?lang=en')
        except AuthError as err:
            self.logout()
            return SessionCheck(SessionStatus.INVALID, error=f'session expired: {err}')
        except requests.HTTPError as err:
            status = err.response.status_code if err.response is not None else 0
            if status in (401, 403):
                self.logout()
                return SessionCheck(SessionStatus.INVALID, error='session expired, please sign in again')

            return SessionCheck(SessionStatus.UNREACHABLE, error=f'server error {status}')
        except requests.RequestException as err:
            return SessionCheck(SessionStatus.UNREACHABLE, error=f'cannot reach Sankaku: {type(err).__name__}')
        except SankakuError as err:
            return SessionCheck(SessionStatus.UNREACHABLE, error=str(err))

        user = data.get('user') if isinstance(data, dict) else None
        name = user.get('name') if isinstance(user, dict) else None
        if not isinstance(name, str) or not name:
            name = tokens.username

        return SessionCheck(SessionStatus.VALID, username=name)


    def search(self, tags: str) -> list[MediaItem]:
        self.search_tags = quote_plus(tags)
        self.next_cursor = None
        self.exhausted = False

        return self.load_page()


    def next_page(self) -> list[MediaItem]:
        if self.exhausted:
            return []

        return self.load_page()


    def autocomplete(self, term: str) -> list[TagSuggestion]:
        cleaned = term.strip()
        if not cleaned:
            return []

        url = (
            f'{self.endpoints.api_base}/tags/autosuggestCreating'
            f'?tag={quote_plus(cleaned)}&show_meta=0&target=post'
        )
        try:
            data = self.request_json('GET', url, authorized=False)
        except (SankakuError, requests.RequestException):
            return []

        if not isinstance(data, list):
            return []

        suggestions: list[TagSuggestion] = []
        for row in data:
            if not isinstance(row, dict):
                continue

            suggestion = TagSuggestion.from_row(row)
            if suggestion is not None:
                suggestions.append(suggestion)

        return suggestions


    def autocomplete_users(self, term: str) -> list[str]:
        """User names matching `term`, for the liked/uploaded/voted-by filters."""
        cleaned = term.strip()
        if not cleaned:
            return []

        url = f'{self.endpoints.api_base}/users/autosuggest?name={quote_plus(cleaned)}&public_favs=false&include_avatar=false'
        try:
            data = self.request_json('GET', url, authorized=False)
        except (SankakuError, requests.RequestException):
            return []

        if not isinstance(data, list):
            return []

        names: list[str] = []
        for row in data:
            name = row.get('name') if isinstance(row, dict) else None
            if isinstance(name, str) and name:
                names.append(name)

        return names


    def post_tags(self, post_id: str) -> list[TypedTag]:
        """Every tag of a post with its category (search results carry only a few)."""
        data = self.request_json('GET', f'{self.endpoints.api_base}/posts/{quote_plus(post_id)}?lang=en')
        rows = data.get('tags') if isinstance(data, dict) else None
        if not isinstance(rows, list):
            return []

        tags: list[TypedTag] = []
        for row in rows:
            tag = TypedTag.from_row(row) if isinstance(row, dict) else None
            if tag is not None:
                tags.append(tag)

        return tags


    def resolve_file_url(self, item: MediaItem) -> str:
        """Resolves the real file_url of a gated post. Requires authorization."""
        url = f'{self.endpoints.api_base}/posts/{quote_plus(item.id)}/fu'
        data = self.request_json('GET', url)

        file_url = data.get('file_url') if isinstance(data, dict) else None
        if not isinstance(file_url, str) or not file_url:
            raise SankakuError(f'post {item.id} has no file url (login or premium required)')

        return file_url


    def download_file(
        self,
        url: str,
        destination: Path,
        should_abort: Callable[[], bool] | None = None,
        on_progress: Callable[[int, int | None], None] | None = None
    ) -> bool:
        """Streams a file to disk, reporting (received, total) bytes as it goes.

        Returns False when should_abort asked to stop mid-transfer; the partial
        file is removed so a half-written media file never survives.
        """
        aborted = False
        received = 0

        response = self.request('GET', url, stream=True)
        with response:
            total = self.content_length_of(response)
            if on_progress is not None:
                on_progress(0, total)

            with destination.open('wb') as file:
                for chunk in response.iter_content(chunk_size=DOWNLOAD_CHUNK_SIZE):
                    if should_abort is not None and should_abort():
                        aborted = True
                        break

                    if not chunk:
                        continue

                    file.write(chunk)
                    received += len(chunk)
                    if on_progress is not None:
                        on_progress(received, total)

        if aborted:
            destination.unlink(missing_ok=True)
            return False

        return True


    def post_url(self, item: MediaItem) -> str:
        return f'{self.endpoints.site_base}/post/show/{item.id}'


    def load_page(self) -> list[MediaItem]:
        url = (
            f'{self.endpoints.api_base}/v2/posts/keyset'
            f'?{self.endpoints.search_extra}'
            f'&limit={self.page_size}'
            f'&tags={self.search_tags}'
        )
        if self.next_cursor:
            url += f'&next={self.next_cursor}'

        data = self.request_json('GET', url)
        if not isinstance(data, dict):
            raise SankakuError('unexpected search response')

        meta = data.get('meta')
        cursor = meta.get('next') if isinstance(meta, dict) else None
        self.next_cursor = cursor if isinstance(cursor, str) and cursor else None
        self.exhausted = self.next_cursor is None

        posts = data.get('data')
        if not isinstance(posts, list):
            return []

        items: list[MediaItem] = []
        for post in posts:
            if not isinstance(post, dict):
                continue

            item = MediaItem.from_post(post)
            if item is not None:
                items.append(item)

        return items


    def refresh(self) -> bool:
        """Exchanges the refresh token for a new access token.

        The /auth/token/refresh path is reverse-engineered and unverified against
        the live API; failing here simply falls back to a full re-login.
        """
        if self.tokens is None or not self.tokens.refresh:
            return False

        try:
            response = self.session.post(
                f'{self.endpoints.api_base}/auth/token/refresh',
                json={'refresh_token': self.tokens.refresh},
                timeout=REQUEST_TIMEOUT
            )
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, ValueError):
            return False

        access = data.get('access_token') if isinstance(data, dict) else None
        if not isinstance(access, str) or not access:
            return False

        refresh = data.get('refresh_token')
        self.tokens = Tokens(
            access=access,
            refresh=refresh if isinstance(refresh, str) and refresh else self.tokens.refresh,
            username=self.tokens.username
        )
        self.persist_tokens()

        return True


    def request_json(
        self,
        method: str,
        url: str,
        body: dict[str, str] | None = None,
        authorized: bool = True
    ) -> Any:
        response = self.request(method, url, body=body, authorized=authorized)
        with response:
            try:
                data = response.json()
            except ValueError as err:
                raise SankakuError(f'malformed response from {url}') from err

        if isinstance(data, dict) and data.get('success') is False:
            raise SankakuError(str(data.get('code') or 'request failed'))

        return data


    def request(
        self,
        method: str,
        url: str,
        body: dict[str, str] | None = None,
        authorized: bool = True,
        stream: bool = False,
        allow_refresh: bool = True
    ) -> requests.Response:
        headers: dict[str, str] = {}
        if authorized:
            authorization = self.authorization_for(url)
            if authorization is not None:
                headers['Authorization'] = authorization

        response = self.session.request(
            method,
            url,
            json=body,
            headers=headers,
            stream=stream,
            timeout=REQUEST_TIMEOUT
        )

        # Anonymous browsing has nothing to refresh — let such a 401 surface as-is.
        if response.status_code == 401 and authorized and allow_refresh and self.tokens is not None:
            response.close()
            sent_token = headers.get('Authorization')
            # Parallel downloads can hit the expiry together: one refreshes,
            # the others see a new token and just retry with it.
            with self.refresh_lock:
                if self.authorization_for(url) == sent_token and not self.refresh():
                    raise AuthError('session expired and could not be refreshed')

            return self.request(
                method,
                url,
                body=body,
                authorized=authorized,
                stream=stream,
                allow_refresh=False
            )

        if response.status_code >= 400:
            message = self.readable_error(response)
            if message is not None:
                response.close()
                raise SankakuError(message)

        response.raise_for_status()

        return response


    def authorization_for(self, url: str) -> str | None:
        if self.tokens is None:
            return None

        host = (urlparse(url).hostname or '').lower()
        if not self.is_auth_host(host):
            return None

        return f'Bearer {self.tokens.access}'


    def persist_tokens(self) -> None:
        if self.token_store is None or self.tokens is None:
            return

        self.token_store.save(self.site.value, self.tokens)


    @staticmethod
    def readable_error(response: requests.Response) -> str | None:
        """Plain-language text for the API's own error codes, when it sent one."""
        try:
            data = response.json()
        except ValueError:
            return None

        code = data.get('code') if isinstance(data, dict) else None
        if not isinstance(code, str):
            return None

        if 'operator-tags-limit' in code:
            limit = data.get('param') or 'a few'
            return (
                f'Sankaku allows only {limit} advanced filters (date, type, duration, size, age rating, users) '
                'per search without signing in'
            )

        if 'account_is_private' in code:
            return 'That user keeps their likes or votes private, or there is no such user'

        if 'search-query-timeout' in code:
            return 'The search took too long on the Sankaku side; narrow it down'

        if code == 'invalid-parameters' or code == 'invalid':
            return 'Sankaku rejected the search as invalid'

        return None


    @staticmethod
    def content_length_of(response: requests.Response) -> int | None:
        header = response.headers.get('Content-Length')
        if header is None or not header.isdigit():
            return None

        return int(header)


    @staticmethod
    def server_error_of(response: requests.Response | None) -> str | None:
        """Extracts the API's own error text, e.g. 'invalid login or password'."""
        if response is None:
            return None

        try:
            data = response.json()
        except ValueError:
            return None

        if not isinstance(data, dict):
            return None

        message = data.get('error') or data.get('code')

        return str(message) if message else None


    @staticmethod
    def is_auth_host(host: str) -> bool:
        for domain in AUTH_HOSTS:
            if host == domain or host.endswith(f'.{domain}'):
                return True

        return False
