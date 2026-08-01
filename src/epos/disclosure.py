"""Disclosure: come gli NPC gestiscono segreti e conoscenze.

Regole:
- un NPC può rivelare solo ciò che possiede (segreti del canone o knowledge);
- mentire su un fatto richiede di conoscerlo;
- revealed / partial_truth trasferiscono il fatto al giocatore;
- withheld / deflected / refused / bargained non trasferiscono nulla ma
  restano tracciati: il gioco ricorda che l'NPC si è sottratto.

Il confronto sul fatto è NORMALIZZATO (``_normalize_fact``): minuscole,
spazi compattati, punteggiatura finale ignorata. Un fatto davvero
posseduto non viene più rifiutato per un punto o una maiuscola di
troppo nel testo proposto dalla LLM.
"""

from __future__ import annotations

from .contract import TRUTHFUL_DISCLOSURE_ACTIONS, DisclosureEvent
from .models import WorldState, add_knowledge
from .worldpack import WorldPack


def _normalize_fact(text: str) -> str:
    """Forma canonica per i confronti: minuscole, spazi compattati, senza
    punteggiatura finale. Un punto non decide mai se un NPC sa qualcosa."""

    return " ".join(str(text).casefold().split()).rstrip(".!?…;:").strip()


def possessed_facts(state: WorldState, pack: WorldPack, npc_id: str) -> list[str]:
    """Fatti che un NPC può rivelare/nascondere: knowledge + segreti di canone."""

    npc = state.npcs.get(npc_id)
    if npc is None:
        return []
    canon = pack.npc_canon.get(npc_id)
    facts = list(npc.knowledge)
    if canon is not None:
        facts.extend(canon.secrets)
    return facts


def fact_is_possessed(
    state: WorldState, pack: WorldPack, npc_id: str, fact: str
) -> bool:
    target = _normalize_fact(fact)
    return any(
        _normalize_fact(known) == target
        for known in possessed_facts(state, pack, npc_id)
    )


def validate_disclosure(
    state: WorldState, pack: WorldPack, event: DisclosureEvent
) -> list[str]:
    problems: list[str] = []

    npc = state.npcs.get(event.npc_id)
    if npc is None:
        return [f"disclosure di NPC inesistente: {event.npc_id!r}"]
    if not npc.present:
        problems.append(f"disclosure di NPC assente: {event.npc_id!r}")

    if not fact_is_possessed(state, pack, event.npc_id, event.fact):
        available = possessed_facts(state, pack, event.npc_id)
        hint = ""
        if available:
            hint = " — fatti che può usare: " + "; ".join(
                fact[:60] for fact in available[:4]
            )
        problems.append(
            f"{event.npc_id} non possiede il fatto {event.fact[:50]!r}: "
            "non può rivelare, nascondere o mentire su ciò che non sa" + hint
        )

    return problems


def apply_disclosure(state: WorldState, event: DisclosureEvent) -> None:
    """Applica gli effetti fattuali della divulgazione. Chiamato dal commit."""

    npc = state.npcs.get(event.npc_id)
    if npc is None:
        return

    if event.action in TRUTHFUL_DISCLOSURE_ACTIONS:
        if event.fact not in npc.disclosed_facts:
            npc.disclosed_facts.append(event.fact)
        add_knowledge(
            state.player,
            event.fact,
            source="told",
            turn=state.turn,
            credibility=1.0 if event.action == "revealed" else 0.75,
            origin=event.npc_id,
        )


def disclosure_context(state: WorldState, pack: WorldPack, npc_id: str) -> dict:
    """Contesto di divulgazione di un NPC per lo snapshot del GM."""

    canon = pack.npc_canon.get(npc_id)
    npc = state.npcs[npc_id]
    return {
        "secrets": canon.secrets if canon else [],
        "disclosure_policy": canon.disclosure_policy if canon else "",
        "red_lines": canon.red_lines if canon else [],
        "already_disclosed": list(npc.disclosed_facts),
    }
