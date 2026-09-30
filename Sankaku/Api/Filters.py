from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta, timezone
from enum import Enum


# Every tag below was verified against the live API (chan and idol), and matches
# what the Sankaku web app itself sends for the same filter.

class Sort(Enum):
    NEWEST = ''                                      # the API default
    POPULARITY = 'order:popularity'
    QUALITY = 'order:quality'
    RANDOM = 'order:random'
    RECENTLY_FAVORITED = 'order:recently_favorited'
    RECENTLY_VOTED = 'order:recently_voted'


class DateRange(Enum):
    ANY = 'any'
    TODAY = 'today'
    LAST_24_HOURS = '24h'
    WEEK = 'week'
    MONTH = 'month'
    CUSTOM = 'custom'


class Resolution(Enum):
    """Minimum size in megapixels (width × height of the named format).

    One mpixels: tag instead of width: + height: — each of those counts toward
    the anonymous operator-tag limit, and two would use it up alone.
    """

    ANY = 0.0
    HD = 0.9        # 1280 × 720
    FULL_HD = 2.0   # 1920 × 1080
    QHD = 3.6       # 2560 × 1440
    UHD = 8.2       # 3840 × 2160


class FileType(Enum):
    ANY = ''
    IMAGE = 'image'
    GIF = 'gif'
    VIDEO = 'video'


class Duration(Enum):
    """Video length in seconds as (from, to); to=None means open-ended."""

    ANY = (0, 0)
    UNDER_1_MIN = (0, 60)
    ONE_TO_FIVE_MIN = (60, 300)
    FIVE_TO_TEN_MIN = (300, 600)
    OVER_10_MIN = (600, None)


MAX_STARS: int = 5

# Meta-tags the API rations: an anonymous search may use at most
# ANONYMOUS_OPERATOR_LIMIT of them (verified live; order:, threshold:, rating:
# and plain tags are free). The limit for signed-in users is not known.
OPERATOR_PREFIXES: tuple[str, ...] = (
    'date:', 'file_type:', 'duration:', 'width:', 'height:', 'mpixels:', 'fav:', 'user:', 'voted:'
)
ANONYMOUS_OPERATOR_LIMIT: int = 2
# The API's date tags are UTC, to the hour: date:2024-03-10T00:00..2024-03-17T00:00
DATE_TAG_FORMAT: str = '%Y-%m-%dT%H:00'


@dataclass(frozen=True)
class SearchFilters:
    sort: Sort = Sort.NEWEST
    date_range: DateRange = DateRange.ANY
    date_from: date | None = None      # CUSTOM only, inclusive local days
    date_to: date | None = None
    min_stars: int = 0                 # 0 = any; N = the site's "N stars and up"
    resolution: Resolution = Resolution.ANY
    file_type: FileType = FileType.ANY
    duration: Duration = Duration.ANY  # only applies to video
    liked_by: str = ''
    uploaded_by: str = ''
    voted_by: str = ''


    @property
    def is_empty(self) -> bool:
        return not self.to_tags()


    def with_liked_by(self, name: str) -> 'SearchFilters':
        return replace(self, liked_by=name)


    def to_tags(self, now: datetime | None = None) -> list[str]:
        """The search meta-tags these filters stand for, in a stable order."""
        tags: list[str] = []

        if self.sort is not Sort.NEWEST:
            tags.append(self.sort.value)

        date_tag = self.date_tag(now or datetime.now().astimezone())
        if date_tag:
            tags.append(date_tag)

        if 0 < self.min_stars <= MAX_STARS:
            tags.append(f'threshold:{self.min_stars}')

        if self.resolution is not Resolution.ANY:
            tags.append(f'mpixels:>={self.resolution.value:g}')

        if self.file_type is not FileType.ANY:
            tags.append(f'file_type:{self.file_type.value}')
            if self.file_type is FileType.VIDEO and self.duration is not Duration.ANY:
                low, high = self.duration.value
                tags.append(f'duration:>={low}' if high is None else f'duration:{low}..{high}')

        for prefix, name in (('fav', self.liked_by), ('user', self.uploaded_by), ('voted', self.voted_by)):
            cleaned = user_name(name)
            if cleaned:
                tags.append(f'{prefix}:{cleaned}')

        return tags


    def date_tag(self, now: datetime) -> str:
        start, end = self.date_bounds(now)
        if start is None or end is None:
            return ''

        return f'date:{format_utc(start)}..{format_utc(end)}'


    def date_bounds(self, now: datetime) -> tuple[datetime | None, datetime | None]:
        # The upper bound is rounded up to the next hour so the current hour counts.
        end = ceil_hour(now)
        if self.date_range is DateRange.TODAY:
            return datetime.combine(now.date(), time.min, now.tzinfo), end

        if self.date_range is DateRange.LAST_24_HOURS:
            return now - timedelta(hours=24), end

        if self.date_range is DateRange.WEEK:
            return now - timedelta(days=7), end

        if self.date_range is DateRange.MONTH:
            return now - timedelta(days=30), end

        if self.date_range is DateRange.CUSTOM and self.date_from is not None:
            last = self.date_to or now.date()
            if last < self.date_from:
                return None, None

            start = datetime.combine(self.date_from, time.min, now.tzinfo)
            return start, datetime.combine(last + timedelta(days=1), time.min, now.tzinfo)

        return None, None


def user_name(value: str) -> str:
    """A user name as the API wants it in a tag: trimmed, spaces as underscores."""
    return value.strip().replace(' ', '_')


def format_utc(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime(DATE_TAG_FORMAT)


def ceil_hour(moment: datetime) -> datetime:
    floored = moment.replace(minute=0, second=0, microsecond=0)
    if floored == moment:
        return floored

    return floored + timedelta(hours=1)


def count_operators(query: str) -> int:
    """How many rationed meta-tags a search string uses."""
    count = 0
    for tag in query.split():
        if tag.lstrip('-').startswith(OPERATOR_PREFIXES):
            count += 1

    return count


def combine_query(query: str, filters: SearchFilters, now: datetime | None = None) -> str:
    """The user's own tags followed by the filter tags."""
    parts = [query.strip(), *filters.to_tags(now)]

    return ' '.join(part for part in parts if part)
