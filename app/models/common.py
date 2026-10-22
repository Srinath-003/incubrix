from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ConnectorTier(str, Enum):
    """Execution tiers for IncuBrix connectors."""

    AUTOMATED = "automated"
    ASSISTED = "assisted"


class Rendition(BaseModel):
    """Media rendition metadata and asset references."""

    asset_id: Optional[str] = Field(default=None, description="Unique asset ID")
    url: Optional[str] = Field(default=None, description="URL or URI of the rendered media file")
    media_type: str = Field(default="video", description="Type of media (e.g. video, image)")
    title: Optional[str] = Field(default=None, description="Title of the content")
    caption: Optional[str] = Field(default=None, description="Text caption or post copy")
    tags: List[str] = Field(default_factory=list, description="Tags/hashtags for the rendition")
    duration_sec: Optional[float] = Field(default=None, description="Duration in seconds for video/audio")
    aspect_ratio: Optional[str] = Field(default=None, description="Aspect ratio (e.g. 16:9, 9:16, 1:1)")
    file_size_bytes: Optional[int] = Field(default=None, description="File size in bytes")
    extra: Dict[str, Any] = Field(default_factory=dict, description="Additional rendition properties")


class Destination(BaseModel):
    """Target platform destination settings."""

    destination_id: Optional[str] = Field(default=None, description="Unique destination ID in IncuBrix")
    platform: str = Field(..., description="Platform identifier (e.g. bluesky, mastodon)")
    account_id: Optional[str] = Field(default=None, description="Account or channel identifier on platform")
    settings: Dict[str, Any] = Field(default_factory=dict, description="Platform-specific publishing settings")


class Connection(BaseModel):
    """Platform authentication and connection credentials."""

    connection_id: Optional[str] = Field(default=None, description="Unique connection ID")
    auth_type: str = Field(default="oauth2", description="Authentication mechanism")
    credentials: Dict[str, Any] = Field(default_factory=dict, description="Platform-specific credential tokens/keys")
    expires_at: Optional[str] = Field(default=None, description="Token expiration ISO timestamp")
