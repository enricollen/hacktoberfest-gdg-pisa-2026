"""Tasting conversation as a LangGraph state machine.

Turn-taking and bookkeeping (who speaks next, which sweet is free, when the box is empty) are
deterministic; Gemma only understands answers and phrases recommendations. Each user turn is a
`listen` interrupt: the REST layer resumes the graph with the transcript.

The group size is chosen in the UI before the conversation starts.

    welcome → listen ─┬─ intro ──────→ listen        (one person at a time: name, tastes, tip)
                      └─ feedback ─┬─→ listen        (round robin: comment, profile, next tip)
                                   └─→ closing → END
"""

import logging
import random
from dataclasses import dataclass

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import interrupt

from app.agent import prompts, rules
from app.agent.llm import LLM
from app.agent.state import Item, Participant, TastingState
from app.db import Database

log = logging.getLogger(__name__)

MAX_PEOPLE = 10

# Jovial lines for the deterministic parts of the conversation (picked at random, so the agent
# does not sound like a recording). Gemma writes the rest with the same tone (see prompts.SYSTEM).
OPENERS = (
    "Che bella scatola, ottima scelta!",
    "Ah, ma che meraviglia di scatola: avete gusto!",
    "Che spettacolo! Questa sì che è una scatola come si deve.",
    "Ottima scelta, davvero: qui dentro c'è da divertirsi!",
)
NEXT_PERSON = (
    "E ora sotto con la prossima persona: dimmi il tuo nome e i tuoi gusti!",
    "Bene, avanti il prossimo goloso: come ti chiami e cosa ti piace?",
    "Passiamo alla prossima persona: presentati e raccontami i tuoi gusti!",
)
START_TASTING = (
    "E adesso, mani alla scatola: assaggiate con calma, senza fretta!",
    "Ora il momento più bello: assaggiate pure, con calma!",
    "Via all'assaggio, gustatevelo con calma!",
)
NEXT_REVIEW = (
    "{name}, tocca a te: com'era {sweet}?",
    "E tu, {name}? Raccontami un po' com'era {sweet}!",
    "{name}, sono curioso: com'era {sweet}?",
)
SAME_PERSON = (
    "Assaggialo con calma e poi raccontami!",
    "Gustatelo con calma, poi dimmi tutto!",
)

# Declared allergy keyword → allergen label used in the catalog.
ALLERGY_KEYWORDS = {
    "frutta a guscio": (
        "frutta a guscio",
        "frutta secca",
        "nocciol",
        "mandorl",
        "pistacch",
        "noci",
        "pecan",
        "arachid",
    ),
    "latte": ("latte", "lattosio", "latticini"),
    "soia": ("soia",),
}


@dataclass(slots=True)
class Deps:
    llm: LLM
    db: Database


# --- pure helpers ---------------------------------------------------------------------------


def available_items(items: list[Item]) -> list[Item]:
    return [i for i in items if i["status"] == "available"]


def item_by_id(items: list[Item], item_id: int) -> Item:
    return next(i for i in items if i["item_id"] == item_id)


def is_safe(item: Item, allergies: list[str]) -> bool:
    declared = " ".join(allergies).lower()
    for allergen, keywords in ALLERGY_KEYWORDS.items():
        if any(k in declared for k in keywords) and any(
            a.startswith(allergen) and "tracce" not in a for a in item["allergens"]
        ):
            return False
    return True


def fallback_pick(p: Participant, items: list[Item]) -> Item | None:
    """Deterministic recommendation used when the LLM picks an invalid or unsafe sweet."""
    likes = " ".join(p["likes"] + [p["profile"]]).lower()
    dislikes = " ".join(p["dislikes"]).lower()

    def score(i: Item) -> int:
        terms = [i["chocolate"], *i["flavors"]]
        return sum(t.lower() in likes for t in terms) - 2 * sum(
            t.lower() in dislikes for t in terms
        )

    safe = [i for i in items if is_safe(i, p["allergies"])]
    return max(safe, key=score, default=None)


def choose(code: str | None, p: Participant, items: list[Item]) -> tuple[Item | None, bool]:
    """Validate the LLM choice. Returns (item, llm_choice_was_valid)."""
    available = available_items(items)
    picked = next((i for i in available if i["code"] == code), None)
    if picked and is_safe(picked, p["allergies"]):
        return picked, True
    return fallback_pick(p, available), False


def assign(items: list[Item], item: Item, participant_idx: int) -> list[Item]:
    return [
        {**i, "status": "assigned", "assigned_to": participant_idx}
        if i["item_id"] == item["item_id"]
        else i
        for i in items
    ]


def next_reviewer(participants: list[Participant], after: int) -> int | None:
    """Next participant (round robin) who still has a suggested sweet to comment on."""
    n = len(participants)
    for step in range(1, n + 1):
        idx = (after + step) % n
        if participants[idx]["pending_item"] is not None:
            return idx
    return None


def tip_sentence(p: Participant, item: Item) -> str:
    return f"{p['name']}, per te ho scelto {item['name']}: {item['tasting_notes']}"


# --- graph ------------------------------------------------------------------------------------

MAX_NAME_ATTEMPTS = 3  # then the guest gets a placeholder name: the tasting must go on
MAX_FEEDBACK_ATTEMPTS = 2  # then the comment is taken as is


def build_graph(deps: Deps, checkpointer: BaseCheckpointSaver) -> CompiledStateGraph:
    def system(state: TastingState) -> str:
        return prompts.SYSTEM.format(shop=state["shop_name"])

    def say(reply: str, **update) -> dict:
        return {**update, "reply": reply, "transcript": [{"role": "agent", "text": reply}]}

    async def ask_llm(state: TastingState, prompt: str, schema):
        """Gemma's answer, or None when it is unavailable (the caller falls back to rules)."""
        try:
            return await deps.llm.structured(system(state), prompt, schema)
        except RuntimeError:
            log.warning("[%s] LLM unavailable: rule-based fallback", state["session_id"][:8])
            return None

    async def welcome(state: TastingState) -> dict:
        who = "Dimmi" if state["group_size"] == 1 else "Cominciamo dalla prima persona: dimmi"
        reply = (
            f"{random.choice(OPENERS)} Benvenuti da {state['shop_name']}! "
            f"{who} come ti chiami, cosa ti piace e se hai allergie."
        )
        return say(reply, phase="intro", turn=0, notes=[], attempts=0)

    def listen(state: TastingState) -> dict:
        text = interrupt({"reply": state["reply"], "phase": state["phase"]})
        return {"user_text": text, "transcript": [{"role": "user", "text": text}]}

    def handoff_after_intro(state: TastingState, participants, items, reply: str) -> dict:
        idx = state["turn"]
        if idx + 1 < state["group_size"]:
            reply += f" {random.choice(NEXT_PERSON)}"
            return say(
                reply, participants=participants, items=items, turn=idx + 1, notes=[], attempts=0
            )
        first = next_reviewer(participants, after=len(participants) - 1)
        if first is None:
            return say(reply, participants=participants, items=items, phase="done")
        p0 = participants[first]
        sweet = item_by_id(items, p0["pending_item"])["name"]
        reply += f" {random.choice(START_TASTING)} Poi {p0['name']}, raccontami: com'era {sweet}?"
        return say(
            reply,
            participants=participants,
            items=items,
            turn=first,
            phase="feedback",
            notes=[],
            attempts=0,
        )

    async def intro(state: TastingState) -> dict:
        sid, idx = state["session_id"][:8], state["turn"]
        # Everything this person said so far: a retry ("mi chiamo Luca") adds to earlier tastes.
        notes = [*state.get("notes", []), state["user_text"]]
        attempts = state.get("attempts", 0) + 1
        heard = " ".join(notes)
        available = available_items(state["items"])

        out = await ask_llm(
            state,
            prompts.intro_prompt(notes, idx + 1, state["group_size"], available),
            prompts.IntroOut,
        )
        r_likes, r_dislikes, r_allergies = rules.extract_tastes(heard, state["items"])
        # Each answer on its own: a bare "Luca" is a name, "Luca mi piace il fondente" is not.
        rule_name = next(filter(None, map(rules.extract_name, reversed(notes))), None)
        name = (out.name if out and out.name else None) or rule_name
        likes = (out.likes if out else []) or r_likes
        dislikes = (out.dislikes if out else []) or r_dislikes
        allergies = sorted({*(out.allergies if out else []), *r_allergies})
        log.info(
            "intro[%s] person %d/%d attempt %d via %s: name=%r likes=%s dislikes=%s "
            "allergies=%s code=%s",
            sid,
            idx + 1,
            state["group_size"],
            attempts,
            "llm" if out else "rules",
            name,
            likes,
            dislikes,
            allergies,
            out.recommended_code if out else None,
        )

        prefix = ""
        if not name:
            if attempts < MAX_NAME_ATTEMPTS:
                reply = (
                    "Che bei gusti! Però non ho capito il tuo nome: come ti chiami?"
                    if likes or dislikes or allergies
                    else "Scusa, non ho capito bene! Come ti chiami e cosa ti piace?"
                )
                return say(reply, notes=notes, attempts=attempts)
            name = f"Ospite {idx + 1}"
            prefix = f"Non ho capito il tuo nome, ti chiamerò {name}!"
        elif not (likes or dislikes or allergies) and attempts == 1:
            reply = (
                f"Piacere {name.strip().title()}! E che cioccolato ti piace di più: "
                "fondente, al latte o bianco?"
            )
            return say(reply, notes=notes, attempts=attempts)

        person: Participant = {
            "idx": idx,
            "name": name.strip().title(),
            "likes": likes,
            "dislikes": dislikes,
            "allergies": allergies,
            "profile": (out.profile if out and out.profile else "")
            or f"Ama {', '.join(likes) or 'scoprire gusti nuovi'}.",
            "history": [],
            "pending_item": None,
        }
        items = state["items"]
        item, llm_ok = choose(out.recommended_code if out else None, person, items)
        if out and not llm_ok:
            log.warning(
                "intro[%s] LLM pick %s rejected → %s",
                sid,
                out.recommended_code,
                item and item["code"],
            )
        if item is None:
            reply = f"Piacere {person['name']}! Purtroppo non c'è un dolcetto adatto a te."
        else:
            # Gemma's sentence only if it understood the name itself and picked a valid sweet.
            use_llm = out is not None and bool(out.name) and llm_ok and bool(out.reply)
            reply = out.reply if use_llm else tip_sentence(person, item)
            items = assign(items, item, idx)
            person["pending_item"] = item["item_id"]
            person["history"] = [
                {
                    "item_id": item["item_id"],
                    "name": item["name"],
                    "reason": reply,
                    "rating": None,
                    "comment": None,
                }
            ]
        reply = f"{prefix} {reply}".strip()
        return handoff_after_intro(state, [*state["participants"], person], items, reply)

    async def feedback(state: TastingState) -> dict:
        sid, idx = state["session_id"][:8], state["turn"]
        participants = [dict(p) for p in state["participants"]]
        person: Participant = participants[idx]  # type: ignore[assignment]
        items = state["items"]
        tasted = item_by_id(items, person["pending_item"])
        notes = [*state.get("notes", []), state["user_text"]]
        attempts = state.get("attempts", 0) + 1
        heard = " ".join(notes)
        available = [i for i in available_items(items) if is_safe(i, person["allergies"])]

        out = await ask_llm(
            state, prompts.feedback_prompt(notes, person, tasted, available), prompts.FeedbackOut
        )
        rule_rating = rules.rating_from_text(heard)
        understood = out.understood if out else (rule_rating is not None or len(heard.split()) >= 3)
        log.info(
            "feedback[%s] %s on %s attempt %d via %s: understood=%s rating=%s next=%s",
            sid,
            person["name"],
            tasted["code"],
            attempts,
            "llm" if out else "rules",
            understood,
            out.rating if out else rule_rating,
            out.recommended_code if out else None,
        )
        if not understood and attempts < MAX_FEEDBACK_ATTEMPTS:
            reply = f"{person['name']}, non ho capito bene: ti è piaciuto {tasted['name']}?"
            return say(reply, notes=notes, attempts=attempts)

        rating = (out.rating if out else None) or rule_rating
        comment = (out.comment if out and out.understood else None) or heard
        await deps.db.log_tasting(
            state["session_id"], person["name"], tasted["item_id"], rating, comment
        )
        items = [
            {**i, "status": "eaten"} if i["item_id"] == tasted["item_id"] else i for i in items
        ]
        if out and out.profile:
            person["profile"] = out.profile
        elif rating is not None:  # rules: remember what went well or badly
            verdict = (
                "Ha apprezzato" if rating >= 4 else "Non ha amato" if rating <= 2 else "Così così"
            )
            person["profile"] = f"{person['profile']} {verdict} {tasted['name']}.".strip()
            if rating >= 4:
                person["likes"] = list(dict.fromkeys([*person["likes"], *tasted["flavors"][:1]]))
        person["history"] = [
            {**t, "rating": rating, "comment": comment} if t["item_id"] == tasted["item_id"] else t
            for t in person["history"]
        ]
        person["pending_item"] = None

        nxt, llm_ok = choose(out.recommended_code if out else None, person, items)
        if out and out.recommended_code and not llm_ok:
            log.warning(
                "feedback[%s] LLM pick %s rejected → %s",
                sid,
                out.recommended_code,
                nxt and nxt["code"],
            )
        use_llm = out is not None and out.understood and bool(out.reply) and (nxt is None or llm_ok)
        if use_llm:
            reply = out.reply
        else:
            reply = rules.reaction(rating)
            if nxt is not None:
                reply += f" {tip_sentence(person, nxt)}"
        if nxt is not None:
            items = assign(items, nxt, idx)
            person["pending_item"] = nxt["item_id"]
            person["history"] = [
                *person["history"],
                {
                    "item_id": nxt["item_id"],
                    "name": nxt["name"],
                    "reason": reply,
                    "rating": None,
                    "comment": None,
                },
            ]

        following = next_reviewer(participants, after=idx)  # type: ignore[arg-type]
        if following is None:
            return say(
                reply, participants=participants, items=items, phase="done", notes=[], attempts=0
            )
        if following == idx:
            reply += f" {random.choice(SAME_PERSON)}"
        else:
            p = participants[following]
            sweet = item_by_id(items, p["pending_item"])["name"]
            reply += " " + random.choice(NEXT_REVIEW).format(name=p["name"], sweet=sweet)
        return say(
            reply, participants=participants, items=items, turn=following, notes=[], attempts=0
        )

    async def closing(state: TastingState) -> dict:
        out = await ask_llm(
            state, prompts.closing_prompt(state["participants"]), prompts.ClosingOut
        )
        if out and out.reply:
            goodbye = out.reply
        else:
            favorites = []
            for p in state["participants"]:
                rated = [t for t in p["history"] if t["rating"]]
                if rated:
                    best = max(rated, key=lambda t: t["rating"])
                    favorites.append(f"{p['name']} ha adorato {best['name']}")
            goodbye = (
                "Che degustazione, la scatola è finita! "
                + (". ".join(favorites) + ". " if favorites else "")
                + f"Grazie a tutti, vi aspettiamo da {state['shop_name']}!"
            )
        reply = f"{state['reply']} {goodbye}".strip()
        return {"reply": reply, "transcript": [{"role": "agent", "text": goodbye}]}

    g = StateGraph(TastingState)
    g.add_node("welcome", welcome)
    g.add_node("listen", listen)
    g.add_node("intro", intro)
    g.add_node("feedback", feedback)
    g.add_node("closing", closing)

    g.add_edge(START, "welcome")
    g.add_edge("welcome", "listen")
    g.add_conditional_edges(
        "listen", lambda s: s["phase"], {"intro": "intro", "feedback": "feedback"}
    )
    g.add_conditional_edges(
        "intro", lambda s: "closing" if s["phase"] == "done" else "listen", ["closing", "listen"]
    )
    g.add_conditional_edges(
        "feedback", lambda s: "closing" if s["phase"] == "done" else "listen", ["closing", "listen"]
    )
    g.add_edge("closing", END)
    return g.compile(checkpointer=checkpointer)
