from dataclasses import dataclass
from enum import Enum


# The Sankaku media CDN (iv./v.sankakucomplex.com) answers 403 to a bare tool
# User-Agent, so every request presents a browser agent instead.
BROWSER_USER_AGENT: str = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
)

# Registrable domains the bearer token may be sent to. A file_url can point at a
# foreign host, and the session token must never leak there.
AUTH_HOSTS: tuple[str, ...] = ('sankakucomplex.com', 'sankakuapi.com')

REQUEST_TIMEOUT: int = 30
DOWNLOAD_CHUNK_SIZE: int = 1 << 16
DEFAULT_PAGE_SIZE: int = 40


class SankakuSite(Enum):
    CHAN = 'chan'
    IDOL = 'idol'


@dataclass(frozen=True)
class SiteEndpoints:
    api_base: str
    site_base: str
    search_extra: str


SITE_ENDPOINTS: dict[SankakuSite, SiteEndpoints] = {
    SankakuSite.CHAN: SiteEndpoints(
        api_base='https://sankakuapi.com',
        site_base='https://chan.sankakucomplex.com',
        search_extra='lang=en&hide_posts_in_books=in-larger-tags'
    ),
    SankakuSite.IDOL: SiteEndpoints(
        api_base='https://i.sankakuapi.com',
        site_base='https://idol.sankakucomplex.com',
        search_extra='lang=en'
    )
}


def endpoints_for(site: SankakuSite) -> SiteEndpoints:
    return SITE_ENDPOINTS[site]
