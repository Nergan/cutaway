from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Optional, Any
from netlazy.domain.models import Handshake, PoWChallenge, Profile, Tag, User, MediaItem

class UserRepository(ABC):
    @abstractmethod
    async def create(self, user: User, session: Any = None) -> None:
        ...

    @abstractmethod
    async def get_by_id(self, user_id: str, session: Any = None) -> Optional[User]:
        ...
        
    @abstractmethod
    async def log_footprint(self, user_id: str, ip: str, fingerprint: str) -> None:
        ...

    @abstractmethod
    async def delete(self, user_id: str, session: Any = None) -> None:
        ...

    @abstractmethod
    async def get_active_user_ids(self, user_ids: List[str]) -> List[str]:
        ...

class NonceRepository(ABC):
    @abstractmethod
    async def insert_if_not_exists(self, user_id: str, nonce: str) -> bool:
        ...

    @abstractmethod
    async def delete_for_user(self, user_id: str, session: Any = None) -> None:
        ...

class TagRepository(ABC):
    @abstractmethod
    async def sync(self, tags: List[Tag]) -> None:
        ...

    @abstractmethod
    async def list_visible(self) -> List[Tag]:
        ...
        
    @abstractmethod
    async def get_all_tags(self) -> List[Tag]:
        ...

    @abstractmethod
    async def search(self, query: str) -> List[Tag]:
        ...

    @abstractmethod
    async def get_all_names(self) -> List[str]:
        ...

class ProfileRepository(ABC):
    @abstractmethod
    async def get_by_user_id(self, user_id: str, session: Any = None) -> Optional[Profile]:
        ...
        
    @abstractmethod
    async def get_by_user_ids(self, user_ids: List[str]) -> List[Profile]:
        ...

    @abstractmethod
    async def upsert(self, profile: Profile, session: Any = None) -> None:
        ...
        
    @abstractmethod
    async def get_feed(self, viewer_id: str, exclude_ids: List[str], cursor: datetime, requires: List[str], excludes: List[str], limit: int) -> List[Profile]:
        ...

    @abstractmethod
    async def delete(self, user_id: str, session: Any = None) -> None:
        ...

    @abstractmethod
    async def count_media_usage(self, file_hash: str) -> int:
        ...

    @abstractmethod
    async def find_media_by_hash(self, file_hash: str) -> Optional[MediaItem]:
        ...

class HandshakeRepository(ABC):
    @abstractmethod
    async def create(self, handshake: Handshake) -> None:
        ...

    @abstractmethod
    async def update(self, handshake: Handshake) -> None:
        ...

    @abstractmethod
    async def delete(self, handshake_id: str) -> None:
        ...

    @abstractmethod
    async def get_by_id(self, handshake_id: str) -> Optional[Handshake]:
        ...

    @abstractmethod
    async def get_for_user(self, user_id: str) -> List[Handshake]:
        ...

    @abstractmethod
    async def get_between_users(self, user_id_1: str, user_id_2: str) -> Optional[Handshake]:
        ...

    @abstractmethod
    async def get_interacted_user_ids(self, user_id: str) -> List[str]:
        ...

    @abstractmethod
    async def delete_for_user(self, user_id: str, session: Any = None) -> None:
        ...

class MediaStorage(ABC):
    @abstractmethod
    async def upload(self, file_bytes: bytes, media_type: str, public_id_hint: str) -> dict:
        ...
        
    @abstractmethod
    async def delete(self, url: str, public_id: Optional[str] = None, resource_type: Optional[str] = None) -> None:
        ...

class SecurityRepository(ABC):
    @abstractmethod
    async def create_challenge(self, challenge: PoWChallenge) -> None:
        ...

    @abstractmethod
    async def consume_challenge(self, challenge_id: str) -> Optional[PoWChallenge]:
        ...

    @abstractmethod
    async def is_banned(self, ip: str, fingerprint: str, user_id: Optional[str] = None) -> bool:
        ...

    @abstractmethod
    async def apply_bans(self, ips: List[str], fingerprints: List[str], user_id: str) -> None:
        ...
        
    @abstractmethod
    async def remove_bans(self, ips: List[str], fingerprints: List[str], user_id: str) -> None:
        ...