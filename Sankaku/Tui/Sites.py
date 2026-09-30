from Sankaku.Api.Endpoints import SankakuSite


SITE_TITLES: dict[SankakuSite, str] = {
    SankakuSite.CHAN: 'Chan',
    SankakuSite.IDOL: 'Idol'
}


def site_title(site: SankakuSite) -> str:
    return SITE_TITLES.get(site, site.value)
