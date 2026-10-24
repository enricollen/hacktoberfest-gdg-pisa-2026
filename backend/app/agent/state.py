import operator
from typing import Annotated, Literal, TypedDict

Phase = Literal["intro", "feedback", "done"]
ItemStatus = Literal["available", "assigned", "eaten"]


class Item(TypedDict):
    item_id: int  # box_items.id
    code: str
    name: str
    chocolate: str
    flavors: list[str]
    allergens: list[str]
    tasting_notes: str
    status: ItemStatus
    assigned_to: int | None  # participant index


class Tasting(TypedDict):
    item_id: int
    name: str
    reason: str
    rating: int | None
    comment: str | None


class Participant(TypedDict):
    idx: int
    name: str
    likes: list[str]
    dislikes: list[str]
    allergies: list[str]
    profile: str  # evolving natural-language taste profile, rewritten after every feedback
    history: list[Tasting]
    pending_item: int | None  # suggested, not reviewed yet


class Line(TypedDict):
    role: Literal["agent", "user"]
    text: str


class TastingState(TypedDict):
    session_id: str
    shop_name: str
    phase: Phase
    group_size: int
    turn: int  # index of the participant the agent is talking to
    participants: list[Participant]
    items: list[Item]
    user_text: str
    notes: list[str]  # what the person being addressed said so far (reset when the turn passes)
    attempts: int  # tries for the current step: caps clarification loops
    reply: str
    transcript: Annotated[list[Line], operator.add]
