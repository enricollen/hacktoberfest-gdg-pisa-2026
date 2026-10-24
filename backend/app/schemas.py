from typing import Any, Literal

from pydantic import BaseModel, Field


class ShopOut(BaseModel):
    slug: str
    name: str
    tagline: str
    logo_url: str | None


class SessionCreate(BaseModel):
    shop_slug: str


class SessionOut(BaseModel):
    session_id: str
    shop: ShopOut


class ProductOut(BaseModel):
    code: str
    name: str
    description: str
    chocolate: str
    flavors: list[str]
    allergens: list[str]
    tasting_notes: str
    image_url: str | None


class RecognizedItemOut(BaseModel):
    item_id: int
    bbox: tuple[float, float, float, float]
    det_conf: float
    match_score: float
    product: ProductOut


class RecognitionOut(BaseModel):
    count: int
    image_width: int
    image_height: int
    items: list[RecognizedItemOut]
    elapsed_ms: int


class StartIn(BaseModel):
    group_size: int = Field(ge=1, le=10, description="People taking part, chosen in the UI")


class TurnIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class TastingOut(BaseModel):
    item_id: int
    name: str
    rating: int | None
    comment: str | None


class ParticipantOut(BaseModel):
    name: str
    profile: str
    likes: list[str]
    dislikes: list[str]
    allergies: list[str]
    pending_item: int | None
    tasted: list[int]
    history: list[TastingOut] = Field(description="Reviewed sweets, in tasting order")


class ProfileUpdateOut(BaseModel):
    """The profile saved during the last turn: drives the 'profile saved' animation."""

    name: str
    kind: Literal["created", "updated"]
    profile: str
    likes: list[str]
    rating: int | None = None


class ItemStateOut(BaseModel):
    item_id: int
    code: str
    name: str
    status: Literal["available", "assigned", "eaten"]
    assigned_to: str | None


class ConversationOut(BaseModel):
    reply: str
    speech_url: str
    phase: Literal["intro", "feedback", "done"]
    speaking_to: str | None = Field(description="Name of the person expected to answer")
    participants: list[ParticipantOut]
    items: list[ItemStateOut]
    keyterms: list[str] = Field(description="Words to bias speech recognition")
    profile_update: ProfileUpdateOut | None = None


class SttTokenOut(BaseModel):
    token: str


class ClientLogIn(BaseModel):
    level: Literal["debug", "info", "warning", "error"] = "info"
    event: str = Field(max_length=100)
    session_id: str | None = Field(default=None, max_length=64)
    data: dict[str, Any] | None = None
