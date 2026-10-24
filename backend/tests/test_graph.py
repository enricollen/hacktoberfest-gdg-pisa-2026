"""End-to-end conversation flows with a scripted LLM (no network)."""

import re

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from app.agent import prompts
from app.agent.graph import Deps, build_graph, is_safe


def heard(prompt: str) -> str:
    """The transcripts quoted in a prompt (one answer, or several for the same person)."""
    return " ".join(re.findall(r'(?:Risposta trascritta: |^- )"(.*)"$', prompt, re.M))


class FakeLLM:
    async def structured(self, system, prompt, schema):
        if schema is prompts.ClosingOut:
            return schema(reply="Grazie a tutti, alla prossima!")
        said = heard(prompt)
        first_code = next(iter(re.findall(r"^- (P\d+):", prompt, re.M)), None)
        if schema is prompts.IntroOut:
            name = re.search(r"sono (\w+)", said, re.I)
            return schema(
                name=name.group(1) if name else None,
                likes=["fondente"] if "fondente" in said else [],
                dislikes=[],
                allergies=["nocciole"] if "nocciole" in said else [],
                profile="Ama il fondente.",
                recommended_code=first_code,
                reply="Ecco il tuo dolcetto.",
            )
        return schema(
            understood="buono" in said,
            rating=4,
            comment="Le è piaciuto.",
            profile="Ama il fondente intenso.",
            recommended_code=first_code,
            reply="Bene! Prova questo.",
        )


class DownLLM:
    """Gemma unreachable for the whole session."""

    async def structured(self, system, prompt, schema):
        raise RuntimeError("LLM unavailable")


class FakeDB:
    def __init__(self):
        self.tastings = []

    async def log_tasting(self, *args):
        self.tastings.append(args)


def make_items(n):
    return [
        {
            "item_id": i + 1,
            "code": f"P{i + 1:02d}",
            "name": f"Dolcetto {i + 1}",
            "chocolate": "fondente",
            "flavors": ["nocciola"] if i == 0 else ["cacao"],
            "allergens": ["frutta a guscio"] if i == 0 else ["latte"],
            "tasting_notes": "cacao intenso",
            "status": "available",
            "assigned_to": None,
        }
        for i in range(n)
    ]


async def start(llm, group_size=2, n_items=5):
    db = FakeDB()
    graph = build_graph(Deps(llm=llm, db=db), InMemorySaver())
    config = {"configurable": {"thread_id": "t"}}
    await graph.ainvoke(
        {
            "session_id": "session",
            "shop_name": "GemmaCacao",
            "phase": "intro",
            "group_size": group_size,
            "turn": 0,
            "participants": [],
            "items": make_items(n_items),
            "user_text": "",
            "notes": [],
            "attempts": 0,
            "reply": "",
            "transcript": [],
        },
        config,
    )

    async def say(text):
        await graph.ainvoke(Command(resume=text), config)
        return (await graph.aget_state(config)).values

    return db, (await graph.aget_state(config)).values, say


async def finish(state, say, text="era molto buono", max_turns=20):
    for _ in range(max_turns):
        if state["phase"] == "done":
            return state
        state = await say(text)
    raise AssertionError("conversation did not end")


async def test_full_tasting_until_box_is_empty():
    db, state, say = await start(FakeLLM())
    assert "come ti chiami" in state["reply"] and state["phase"] == "intro"
    assert "Dolcetto" not in state["reply"]  # short welcome: no list of sweets

    state = await say("ehm ciao")  # no name: asks again, same person
    assert state["phase"] == "intro" and state["participants"] == []

    state = await say("Sono Anna e sono allergica alle nocciole, amo il fondente")
    anna = state["participants"][0]
    assert anna["name"] == "Anna"
    # P01 contains nuts: the LLM picked it, the safety check must override it.
    assert state["items"][0]["status"] == "available"
    assert anna["pending_item"] == 2

    state = await say("Sono Luca, amo il fondente")
    assert state["phase"] == "feedback" and state["turn"] == 0
    assert "Anna" in state["reply"]

    state = await say("mah")  # not an opinion: asks once
    assert state["turn"] == 0 and not db.tastings

    state = await finish(state, say)
    assert all(i["status"] == "eaten" for i in state["items"])
    assert len(db.tastings) == 5
    assert all(p["pending_item"] is None for p in state["participants"])
    assert "Grazie a tutti" in state["reply"]


async def test_tastes_said_before_the_name_are_kept():
    _, state, say = await start(FakeLLM(), group_size=1)
    state = await say("adoro il fondente")  # no name yet
    assert "nome" in state["reply"] and state["participants"] == []
    state = await say("sono Marta")
    marta = state["participants"][0]
    assert marta["name"] == "Marta" and marta["likes"] == ["fondente"]


async def test_name_never_understood_becomes_guest():
    _, state, say = await start(FakeLLM(), group_size=2)
    for _ in range(3):
        state = await say("eh boh")
    assert state["participants"][0]["name"] == "Ospite 1"
    assert state["turn"] == 1  # moved on to the next person


async def test_asks_tastes_once_when_only_the_name_is_given():
    _, state, say = await start(FakeLLM(), group_size=2)
    state = await say("sono Paolo")
    assert "Piacere Paolo" in state["reply"] and state["participants"] == []
    state = await say("boh, non saprei")  # still no tastes: go on anyway
    assert state["participants"][0]["name"] == "Paolo" and state["turn"] == 1


async def test_tasting_completes_with_llm_down():
    db, state, say = await start(DownLLM(), group_size=2, n_items=4)
    state = await say("Mi chiamo Giulia e amo il fondente")
    assert state["participants"][0]["name"] == "Giulia"
    state = await say("Luca")  # name only: asks the tastes once
    assert "Piacere Luca" in state["reply"]
    state = await say("mi piace il fondente")  # merged with the name said before
    assert state["participants"][1]["name"] == "Luca"
    assert state["participants"][1]["likes"] == ["fondente"]
    assert state["phase"] == "feedback"
    state = await finish(state, say, "buonissimo davvero")
    assert len(db.tastings) == 4
    assert all(t[3] == 5 for t in db.tastings)  # ratings from keywords
    assert "Grazie a tutti" in state["reply"]


async def test_unclear_feedback_is_accepted_after_one_retry():
    db, _, say = await start(FakeLLM(), group_size=1, n_items=2)
    await say("sono Eva e amo il fondente")
    await say("uhm")
    await say("uhm")
    assert len(db.tastings) == 1  # moved on instead of looping


def test_allergy_check_ignores_traces():
    item = {"allergens": ["latte (tracce)", "frutta a guscio"]}
    assert not is_safe(item, ["allergico alle mandorle"])
    assert is_safe(item, ["intollerante al lattosio"])


async def test_end_early_keeps_what_was_gathered():
    """Same state update as POST /conversation/end: closing now, mid-tasting."""
    graph = build_graph(Deps(llm=FakeLLM(), db=FakeDB()), InMemorySaver())
    config = {"configurable": {"thread_id": "early"}}
    await graph.ainvoke(
        {
            "session_id": "s",
            "shop_name": "GemmaCacao",
            "phase": "intro",
            "group_size": 3,
            "turn": 0,
            "participants": [],
            "items": make_items(6),
            "user_text": "",
            "notes": [],
            "attempts": 0,
            "reply": "",
            "transcript": [],
        },
        config,
    )
    await graph.ainvoke(Command(resume="sono Anna e amo il fondente"), config)
    await graph.aupdate_state(
        config, {"phase": "done", "reply": "Grazie a tutti!"}, as_node="closing"
    )
    snapshot = await graph.aget_state(config)
    assert snapshot.next == ()  # nothing left to run: the conversation is over
    assert snapshot.values["phase"] == "done"
    assert [p["name"] for p in snapshot.values["participants"]] == ["Anna"]
    assert snapshot.values["participants"][0]["pending_item"] is not None
