from dataclasses import dataclass
from enum import Enum
from typing import Any


@dataclass
class MediaItem:
    id: str
    file_url: str | None
    file_format: str
    tags: list[str]
    file_size: int = 0  # bytes as reported by the API; 0 when unknown
    rating: str = ''
    width: int = 0
    height: int = 0
    created_at: int = 0  # unix seconds
    md5: str = ''
    source: str = ''
    duration: float = 0.0  # seconds, videos only

    @property
    def needs_resolve(self) -> bool:
        """A gated post (18+ / premium) arrives without a file_url."""
        return not self.file_url


    @staticmethod
    def from_post(post: dict[str, Any]) -> 'MediaItem | None':
        post_id = post.get('id')
        if post_id is None:
            return None

        file_url = post.get('file_url')
        created = post.get('created_at')
        created_at = created.get('s') if isinstance(created, dict) else None

        return MediaItem(
            id=str(post_id),
            file_url=file_url if isinstance(file_url, str) and file_url else None,
            file_format=MediaItem.format_of(post),
            tags=MediaItem.tags_of(post),
            file_size=positive_int(post.get('file_size')),
            rating=text_of(post.get('rating')),
            width=positive_int(post.get('width')),
            height=positive_int(post.get('height')),
            created_at=positive_int(created_at),
            md5=text_of(post.get('md5')),
            source=text_of(post.get('source')),
            duration=seconds_of(post.get('video_duration'))
        )


    @staticmethod
    def format_of(post: dict[str, Any]) -> str:
        extension = post.get('file_ext')
        if isinstance(extension, str) and extension:
            return extension

        file_type = post.get('file_type')
        if isinstance(file_type, str) and '/' in file_type:
            return file_type.split('/')[1]

        return 'bin'


    @staticmethod
    def tags_of(post: dict[str, Any]) -> list[str]:
        raw_tags = post.get('tag_names')
        if not isinstance(raw_tags, list):
            return []

        tags: list[str] = []
        for tag in raw_tags:
            if isinstance(tag, str):
                tags.append(tag.replace('_', ' '))

        return tags


@dataclass
class TagSuggestion:
    name: str
    post_count: int

    @staticmethod
    def from_row(row: dict[str, Any]) -> 'TagSuggestion | None':
        name = row.get('tagName') or row.get('name')
        if not isinstance(name, str) or not name:
            return None

        post_count = row.get('post_count')

        return TagSuggestion(
            name=name,
            post_count=post_count if isinstance(post_count, int) else 0
        )


class SessionStatus(Enum):
    NONE = 'none'                # nothing stored
    VALID = 'valid'              # the server accepted the stored session
    INVALID = 'invalid'          # the server rejected it; it has been dropped
    UNREACHABLE = 'unreachable'  # could not verify; the session is kept


@dataclass(frozen=True)
class SessionCheck:
    status: SessionStatus
    username: str = ''
    error: str = ''


# Sankaku's own tag categories (from the web app's tag-types table).
TAG_TYPES: dict[int, str] = {
    0: 'general',
    1: 'artist',
    2: 'studio',
    3: 'copyright',
    4: 'character',
    5: 'genre',
    8: 'medium',
    9: 'meta',
    10: 'fashion',
    11: 'anatomy',
    12: 'pose',
    13: 'activity',
    14: 'role',
    15: 'flora',
    16: 'fauna',
    17: 'entity',
    18: 'object',
    19: 'substance',
    20: 'setting',
    21: 'language',
    22: 'automatic',
    23: 'other'
}


@dataclass(frozen=True)
class TypedTag:
    name: str
    category: str

    @staticmethod
    def from_row(row: dict[str, Any]) -> 'TypedTag | None':
        name = row.get('tagName') or row.get('name')
        if not isinstance(name, str) or not name:
            return None

        kind = row.get('type')

        return TypedTag(
            name=name.replace('_', ' '),
            category=TAG_TYPES.get(kind, 'other') if isinstance(kind, int) else 'other'
        )


def positive_int(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0


def seconds_of(value: Any) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
        return float(value)

    return 0.0


def text_of(value: Any) -> str:
    return value if isinstance(value, str) else ''

