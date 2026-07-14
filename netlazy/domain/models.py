from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

@dataclass
class User:
    user_id: str
    public_key_pem: str
    created_at: datetime
    known_ips: List[str] = field(default_factory=list)
    known_fingerprints: List[str] = field(default_factory=list)
    is_banned: bool = False

class UserAlreadyExistsError(Exception):
    pass

@dataclass
class Tag:
    name: str
    aliases: List[str] = field(default_factory=list)
    hidden: bool = False

@dataclass
class MediaItem:
    url: str
    media_type: str
    blur: bool = False
    file_hash: str = ""
    public_id: Optional[str] = None
    resource_type: Optional[str] = None

@dataclass
class Contact:
    type: str
    value: str
    is_private: bool = True

@dataclass
class Profile:
    user_id: str
    bio: str = ""
    tags: List[str] = field(default_factory=list)
    media: List[MediaItem] = field(default_factory=list)
    audio: Optional[MediaItem] = None
    contacts: List[Contact] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None

@dataclass
class Handshake:
    id: str
    sender_id: str
    receiver_id: str
    handshake_type: str
    status: str
    offered_contact: Optional[str] = None
    returned_contact: Optional[str] = None
    sender_deleted: bool = False
    receiver_deleted: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None

@dataclass
class PoWChallenge:
    id: str
    difficulty: int
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

@dataclass
class Ban:
    type: str
    value: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))