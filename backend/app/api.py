import asyncio
import io
import logging
import re
import time
from collections import defaultdict
from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from langgraph.types import Command
from PIL import Image, ImageOps, UnidentifiedImageError

from app import schemas
from app.agent.state import Item, TastingState
from app.config import Settings
from app.db import Database
from app.voice import Voice

MAX_UPLOAD_BYTES = 15 * 1024 * 1024

log = logging.getLogger("app.api")
client_log = logging.getLogger("app.client")

router = APIRouter(prefix="/api")
_session_locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


def get_db(request: Request) -> Database:
    return request.app.state.db


def get_voice(request: Request) -> Voice:
    return request.app.state.voice


DB = Annotated[Database, Depends(get_db)]
VoiceDep = Annotated[Voice, Depends(get_voice)]


def media_url(path: str | None) -> str | None:
    return f"/media/{path}" if path else None


def shop_out(shop: dict[str, Any]) -> schemas.ShopOut:
    return schemas.ShopOut(
        slug=shop["slug"],
        name=shop["name"],
        tagline=shop["tagline"],
        logo_url=media_url(shop["logo_path"]),
    )


def product_out(p: dict[str, Any]) -> schemas.ProductOut:
    return schemas.ProductOut(
        code=p["code"],
        name=p["name"],
        description=p["description"],
        chocolate=p["chocolate"],
        flavors=p["flavors"],
        allergens=p["allergens"],
        tasting_notes=p["tasting_notes"],
        image_url=media_url(p["image_path"]),
    )


async def require_session(db: Database, session_id: str) -> dict[str, Any]:
    session = await db.get_session(session_id)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sessione non trovata")
    return session


def keyterms(values: TastingState) -> list[str]:
    """Bias Scribe towards the words of this box (realtime: ≤ 50 terms, ≤ 20 chars each)."""
    terms: dict[str, None] = {}
    for p in values.get("participants", []):
        terms[p["name"]] = None
    for item in values.get("items", []):
        for word in re.findall(r"[\wàèéìòù']+", " ".join([item["name"], *item["flavors"]])):
            if len(word) >= 4:
                terms[word.lower()] = None
    return [t for t in terms if len(t) <= 20][:50]


def profile_update(before: TastingState, after: TastingState) -> schemas.ProfileUpdateOut | None:
    """Which taste profile the last turn created or changed, if any."""
    old = {p["idx"]: p for p in before.get("participants", [])}
    for p in after.get("participants", []):
        prev = old.get(p["idx"])
        if prev is not None and prev["profile"] == p["profile"] and prev["history"] == p["history"]:
            continue
        reviewed = [t for t in p["history"] if t["rating"] is not None]
        return schemas.ProfileUpdateOut(
            name=p["name"],
            kind="created" if prev is None else "updated",
            profile=p["profile"],
            likes=p["likes"],
            rating=reviewed[-1]["rating"] if prev is not None and reviewed else None,
        )
    return None


def conversation_out(
    values: TastingState, voice: Voice, before: TastingState | None = None
) -> schemas.ConversationOut:
    participants = values.get("participants", [])
    names = {p["idx"]: p["name"] for p in participants}
    phase = values["phase"]
    speaking_to = None
    if phase == "feedback" and participants:
        speaking_to = names.get(values["turn"])
    return schemas.ConversationOut(
        reply=values["reply"],
        speech_url=f"/api/speech/{voice.register(values['reply'])}",
        phase=phase,
        speaking_to=speaking_to,
        participants=[
            schemas.ParticipantOut(
                name=p["name"],
                profile=p["profile"],
                likes=p["likes"],
                dislikes=p["dislikes"],
                allergies=p["allergies"],
                pending_item=p["pending_item"],
                tasted=[t["item_id"] for t in p["history"] if t["item_id"] != p["pending_item"]],
                history=[
                    schemas.TastingOut(
                        item_id=t["item_id"],
                        name=t["name"],
                        rating=t["rating"],
                        comment=t["comment"],
                    )
                    for t in p["history"]
                    if t["item_id"] != p["pending_item"]
                ],
            )
            for p in participants
        ],
        items=[
            schemas.ItemStateOut(
                item_id=i["item_id"],
                code=i["code"],
                name=i["name"],
                status=i["status"],
                assigned_to=names.get(i["assigned_to"]) if i["assigned_to"] is not None else None,
            )
            for i in values["items"]
        ],
        keyterms=keyterms(values),
        profile_update=profile_update(before, values) if before is not None else None,
    )


# --- shops & sessions -------------------------------------------------------------------------


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/shops/{slug}", response_model=schemas.ShopOut)
async def get_shop(slug: str, db: DB) -> schemas.ShopOut:
    shop = await db.get_shop(slug)
    if shop is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Negozio non trovato")
    return shop_out(shop)


@router.post("/sessions", response_model=schemas.SessionOut, status_code=201)
async def create_session(body: schemas.SessionCreate, db: DB) -> schemas.SessionOut:
    shop = await db.get_shop(body.shop_slug)
    if shop is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Negozio non trovato")
    session_id = uuid4().hex
    await db.create_session(session_id, shop["id"])
    return schemas.SessionOut(session_id=session_id, shop=shop_out(shop))


# --- vision -----------------------------------------------------------------------------------


@router.post("/sessions/{session_id}/photo", response_model=schemas.RecognitionOut)
async def upload_photo(
    session_id: str, request: Request, db: DB, photo: Annotated[UploadFile, File()]
) -> schemas.RecognitionOut:
    session = await require_session(db, session_id)
    data = await photo.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Foto troppo grande")
    try:
        image = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
    except (UnidentifiedImageError, OSError) as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "File non valido") from e

    settings: Settings = request.app.state.settings
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    photo_path = settings.uploads_dir / f"{session_id}.jpg"
    await asyncio.to_thread(image.save, photo_path, quality=90)

    started = time.perf_counter()
    sweets = await request.app.state.recognizer.recognize(image, session["shop_id"])
    await db.replace_box_items(
        session_id,
        str(photo_path),
        [
            {
                "product_id": s.product_id,
                "bbox": s.bbox,
                "det_conf": s.det_conf,
                "match_score": s.match_score,
            }
            for s in sweets
        ],
    )
    items = await db.list_box_items(session_id)
    elapsed_ms = round((time.perf_counter() - started) * 1000)
    log.info(
        "photo[%s] %dx%d → %d sweets in %d ms: %s",
        session_id[:8],
        image.width,
        image.height,
        len(items),
        elapsed_ms,
        ", ".join(f"{i['code']}({i['match_score']:.2f})" for i in items),
    )
    return schemas.RecognitionOut(
        count=len(items),
        image_width=image.width,
        image_height=image.height,
        elapsed_ms=elapsed_ms,
        items=[
            schemas.RecognizedItemOut(
                item_id=i["item_id"],
                bbox=(i["x1"], i["y1"], i["x2"], i["y2"]),
                det_conf=round(i["det_conf"], 3),
                match_score=round(i["match_score"], 3),
                product=product_out(i),
            )
            for i in items
        ],
    )


# --- conversation -----------------------------------------------------------------------------


def graph_config(session_id: str) -> dict:
    return {"configurable": {"thread_id": session_id}}


@router.post("/sessions/{session_id}/conversation/start", response_model=schemas.ConversationOut)
async def start_conversation(
    session_id: str, body: schemas.StartIn, request: Request, db: DB, voice: VoiceDep
) -> schemas.ConversationOut:
    session = await require_session(db, session_id)
    rows = await db.list_box_items(session_id)
    if not rows:
        raise HTTPException(status.HTTP_409_CONFLICT, "Prima scatta la foto della scatola")
    if body.group_size > len(rows):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"La scatola ha {len(rows)} dolcetti: al massimo {len(rows)} persone",
        )
    shop = await db.get_shop_by_id(session["shop_id"])
    graph = request.app.state.graph
    config = graph_config(session_id)
    items: list[Item] = [
        {
            "item_id": r["item_id"],
            "code": r["code"],
            "name": r["name"],
            "chocolate": r["chocolate"],
            "flavors": r["flavors"],
            "allergens": r["allergens"],
            "tasting_notes": r["tasting_notes"],
            "status": "available",
            "assigned_to": None,
        }
        for r in rows
    ]
    async with _session_locks[session_id]:
        snapshot = await graph.aget_state(config)
        if not snapshot.values:  # idempotent: a reload resumes the same conversation
            log.info("start[%s] %d people, %d sweets", session_id[:8], body.group_size, len(rows))
            await graph.ainvoke(
                {
                    "session_id": session_id,
                    "shop_name": shop["name"],
                    "phase": "intro",
                    "group_size": body.group_size,
                    "turn": 0,
                    "participants": [],
                    "items": items,
                    "user_text": "",
                    "notes": [],
                    "attempts": 0,
                    "reply": "",
                    "transcript": [],
                },
                config,
            )
            snapshot = await graph.aget_state(config)
            log.info("agent[%s] «%s»", session_id[:8], snapshot.values["reply"])
        else:
            log.info("start[%s] resumed existing conversation", session_id[:8])
    return conversation_out(snapshot.values, voice)


@router.post("/sessions/{session_id}/conversation/turn", response_model=schemas.ConversationOut)
async def conversation_turn(
    session_id: str, body: schemas.TurnIn, request: Request, db: DB, voice: VoiceDep
) -> schemas.ConversationOut:
    await require_session(db, session_id)
    graph = request.app.state.graph
    config = graph_config(session_id)
    async with _session_locks[session_id]:
        snapshot = await graph.aget_state(config)
        if not snapshot.values:
            raise HTTPException(status.HTTP_409_CONFLICT, "Conversazione non avviata")
        if snapshot.values["phase"] == "done" and not snapshot.next:
            log.info("turn[%s] ignored: conversation already finished", session_id[:8])
            return conversation_out(snapshot.values, voice)
        before = snapshot.values
        log.info(
            "user[%s] phase=%s turn=%s «%s»",
            session_id[:8],
            before["phase"],
            before["turn"],
            body.text.strip(),
        )
        started = time.perf_counter()
        try:
            if snapshot.interrupts:
                await graph.ainvoke(Command(resume=body.text.strip()), config)
            else:  # the previous turn failed mid-way (e.g. LLM outage): retry it with new text
                await graph.aupdate_state(
                    config, {"user_text": body.text.strip()}, as_node="listen"
                )
                await graph.ainvoke(None, config)
        except RuntimeError as e:
            log.error("turn[%s] failed: %s", session_id[:8], e)
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE, "Il maître è distratto, ripeti per favore"
            ) from e
        except Exception as e:  # never leave the guests stuck: log it, let them repeat
            log.exception("turn[%s] crashed", session_id[:8])
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "Scusate, ho perso il filo: ripetete per favore",
            ) from e
        snapshot = await graph.aget_state(config)
    after = snapshot.values
    out = conversation_out(after, voice, before)
    log.info(
        "agent[%s] %.2fs phase=%s→%s next=%s eaten=%d/%d «%s»",
        session_id[:8],
        time.perf_counter() - started,
        before["phase"],
        after["phase"],
        out.speaking_to or f"persona {after['turn'] + 1}",
        sum(i["status"] == "eaten" for i in after["items"]),
        len(after["items"]),
        after["reply"],
    )
    return out


@router.post("/sessions/{session_id}/conversation/end", response_model=schemas.ConversationOut)
async def end_conversation(
    session_id: str, request: Request, db: DB, voice: VoiceDep
) -> schemas.ConversationOut:
    """Demo control: wrap up now with a short thank you; the summary shows what was gathered."""
    await require_session(db, session_id)
    graph = request.app.state.graph
    config = graph_config(session_id)
    async with _session_locks[session_id]:
        snapshot = await graph.aget_state(config)
        if not snapshot.values:
            raise HTTPException(status.HTTP_409_CONFLICT, "Conversazione non avviata")
        values = snapshot.values
        if values["phase"] != "done" or snapshot.next:
            shop = values["shop_name"]
            reply = f"Grazie a tutti per questa degustazione! Vi aspettiamo presto da {shop}."
            # Recorded as the closing node: the graph moves to END, the state is kept as is.
            await graph.aupdate_state(
                config,
                {
                    "phase": "done",
                    "reply": reply,
                    "notes": [],
                    "attempts": 0,
                    "transcript": [{"role": "agent", "text": reply}],
                },
                as_node="closing",
            )
            snapshot = await graph.aget_state(config)
            eaten = sum(i["status"] == "eaten" for i in snapshot.values["items"])
            log.info(
                "end[%s] ended early: %d people, %d/%d eaten",
                session_id[:8],
                len(snapshot.values["participants"]),
                eaten,
                len(snapshot.values["items"]),
            )
    return conversation_out(snapshot.values, voice)


@router.get("/sessions/{session_id}/conversation", response_model=schemas.ConversationOut)
async def get_conversation(
    session_id: str, request: Request, db: DB, voice: VoiceDep
) -> schemas.ConversationOut:
    await require_session(db, session_id)
    snapshot = await request.app.state.graph.aget_state(graph_config(session_id))
    if not snapshot.values:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversazione non avviata")
    return conversation_out(snapshot.values, voice)


# --- voice ------------------------------------------------------------------------------------


@router.post("/voice/stt-token", response_model=schemas.SttTokenOut)
async def stt_token(voice: VoiceDep) -> schemas.SttTokenOut:
    try:
        return schemas.SttTokenOut(token=await voice.stt_token())
    except Exception as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Trascrizione non disponibile") from e


@router.get("/speech/{utterance_id}")
async def speech(utterance_id: str, voice: VoiceDep) -> StreamingResponse:
    text = voice.text_of(utterance_id)
    if text is None:
        log.warning("speech %s unknown (expired or server restarted)", utterance_id[:8])
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Audio non disponibile")
    chunks = voice.stream(text, utterance_id)
    # Pull the first chunk before answering, so an ElevenLabs error (quota, voice not allowed
    # on the plan...) becomes a clean 502 instead of an empty MP3.
    try:
        first = await anext(chunks)
    except StopAsyncIteration:
        first = b""
    except Exception as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Sintesi vocale non disponibile") from e

    async def body():
        yield first
        async for chunk in chunks:
            yield chunk

    return StreamingResponse(body(), media_type="audio/mpeg", headers={"Cache-Control": "no-store"})


@router.post("/client-log", status_code=204)
async def client_log_event(event: schemas.ClientLogIn) -> None:
    """Browser-side events (mic, transcripts, playback) land in the server log."""
    level = getattr(logging, event.level.upper())
    sid = (event.session_id or "-")[:8]
    client_log.log(level, "[%s] %s %s", sid, event.event, event.data or "")
