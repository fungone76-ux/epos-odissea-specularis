"""Game Master: protocollo, GM demo offline, GM live OpenAI-compatible.

Una sola chiamata per fase:
- fase 1 (propose): no_check con scena, oppure check_proposal;
- fase 2 (narrate): solo dopo la risoluzione Python, narra l'esito noto.

Retry tecnici: uno per fase, solo per fallimenti di trasporto o JSON
invalido. Mai re-tiri di dado, mai riscritture semantiche automatiche.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Protocol

from .contract import (
    CheckProposal,
    ConfrontProposal,
    ContractError,
    FinalScene,
    GmPhaseResponse,
)
from .llm import LlmCallResult, LlmProviderChain, LlmProviderError, provider_chain_from_env
from .models import WorldState
from .prompt import phase1_messages, phase2_messages
from .rules import ConfrontResult, Roll
from .worldpack import WorldPack


class GameMasterError(RuntimeError):
    """Il Game Master non ha prodotto un contratto valido."""

    def __init__(self, message: str, diagnostics: dict[str, Any] | None = None):
        super().__init__(message)
        self.diagnostics = diagnostics or {}


class SceneValidationError(GameMasterError):
    """La scena finale del provider non rispetta il contratto (campi mancanti
    o invalidi). Diversa dagli errori di trasporto: il TurnService può
    ritentare la narrazione una volta invece di buttare via il turno."""


class GameMaster(Protocol):
    """Confine tra il runtime e l'autorità narrativa."""

    def propose(self, state: WorldState, pack: WorldPack, player_text: str) -> GmPhaseResponse: ...

    def revise(
        self,
        state: WorldState,
        pack: WorldPack,
        player_text: str,
        problems: list[str],
    ) -> GmPhaseResponse:
        """Revisione semantica: la proposta è stata rifiutata da Python.

        Il GM ripensa la scena e risponde con no_check. Non è un retry
        tecnico: il giudizio drammatico è cambiato, il trasporto no."""
        ...

    def narrate(
        self,
        state: WorldState,
        pack: WorldPack,
        player_text: str,
        proposal: CheckProposal,
        roll: Roll,
        stake: str,
        extras: dict[str, Any] | None = None,
    ) -> FinalScene:
        """extras può contenere: player_narration (successo pieno),
        temerario_price (prezzo da onorare), confront (esito confronto)."""
        ...

    def narrate_confront(
        self,
        state: WorldState,
        pack: WorldPack,
        player_text: str,
        proposal: "ConfrontProposal",
        result: "ConfrontResult",
        stake: str,
        extras: dict[str, Any] | None = None,
    ) -> FinalScene: ...

    def evaluate_trigger(
        self,
        state: WorldState,
        pack: WorldPack,
        proposal: CheckProposal,
        trigger: str,
    ) -> int:
        """Valuta l'innesco come da manuale: 0-3 dadi bonus."""
        ...


# ---------------------------------------------------------------------------
# GM demo offline
# ---------------------------------------------------------------------------

# Parole che suggeriscono un'azione a esito incerto nel GM dimostrativo.
_RISKY_HINTS = (
    "tento",
    "provo",
    "cerco di",
    "cerco di",
    "mi avvicino",
    "mi intrufolo",
    "sgattaiolo",
    "forzo",
    "scasso",
    "inseguo",
    "attacco",
    "colpisco",
    "rubo",
    "nascondo",
    "mi nascondo",
    "seduco",
    "minaccio",
    "inganno",
    "mento",
    "uso il potere",
    "uso la reliquia",
    "mi concentro",
)

_SKILL_HINTS = {
    "social": ("parlo", "dico", "chiedo", "persuad", "seduc", "minacc", "ingann", "mentisco"),
    "stealth": ("nascond", "intrufol", "sgattaiol", "furtiv", "rub", "scasso"),
    "investigate": ("cerco", "esamin", "ispezion", "osservo", "indag", "leggo"),
    "physical": ("attacco", "colpisco", "forzo", "inseguo", "sollevo", "spingo"),
}


class DemoGameMaster:
    """GM deterministico offline: euristiche semplici, nessuna rete.

    Serve a giocare e testare il ciclo completo senza provider. Non è un
    fallback narrativo per il live: è un provider a sé.
    """

    @staticmethod
    def _mentions(text: str, hints) -> bool:
        return any(re.search(rf"\b{re.escape(h)}", text) for h in hints)

    def propose(self, state: WorldState, pack: WorldPack, player_text: str) -> GmPhaseResponse:
        text = player_text.lower()
        if self._mentions(text, _RISKY_HINTS):
            action_kind = "physical"
            for kind, hints in _SKILL_HINTS.items():
                if self._mentions(text, hints):
                    action_kind = kind
                    break
            present = state.present_npc_ids()
            proposal = CheckProposal(
                action_kind=action_kind,
                skill=action_kind,
                difficulty=3,
                target_ids=present[:1],
                opposition="npc_resistance" if present else "environment",
                reason="Azione a esito incerto (demo).",
                stakes={
                    "full_success": "L'azione riesce pienamente.",
                    "partial_success": "L'azione riesce con un costo o una complicazione.",
                    "failure": "L'azione non riesce.",
                    "critical_failure": "L'azione fallisce con una complicazione seria.",
                },
            )
            return GmPhaseResponse(mode="check_proposal", check=proposal)
        return GmPhaseResponse(mode="no_check", scene=self._scene(state, pack, player_text))

    def revise(
        self,
        state: WorldState,
        pack: WorldPack,
        player_text: str,
        problems: list[str],
    ) -> GmPhaseResponse:
        # il GM demo accetta il giudizio di Python e narra senza prova
        return GmPhaseResponse(mode="no_check", scene=self._scene(state, pack, player_text))

    def narrate(
        self,
        state: WorldState,
        pack: WorldPack,
        player_text: str,
        proposal: CheckProposal,
        roll: Roll,
        stake: str,
        extras: dict[str, Any] | None = None,
    ) -> FinalScene:
        outcome_text = {
            "full_success": "Tutto fila esattamente come speravi.",
            "partial_success": "Ce la fai, ma qualcosa si complica.",
            "failure": "Non funziona: la situazione ti si chiude contro.",
            "critical_failure": "Va storto tutto quello che poteva andare storto.",
        }[roll.outcome.value]
        prefix = f"{outcome_text} {stake}".strip()
        extras = extras or {}
        if extras.get("player_narration"):
            prefix = f"{prefix} {extras['player_narration']}".strip()
        if extras.get("temerario_price"):
            prefix = f"{prefix} E il prezzo si paga: {extras['temerario_price']}".strip()
        return self._scene(state, pack, player_text, prefix=prefix)

    def narrate_confront(
        self,
        state: WorldState,
        pack: WorldPack,
        player_text: str,
        proposal: ConfrontProposal,
        result: ConfrontResult,
        stake: str,
        extras: dict[str, Any] | None = None,
    ) -> FinalScene:
        outcome_text = {
            "player": "Vinci il confronto.",
            "npc": "Il confronto ti sfugge.",
            "stall": "Nessuno prevale: stallo.",
        }[result.winner]
        prefix = f"{outcome_text} {stake}".strip()
        extras = extras or {}
        if extras.get("player_narration"):
            prefix = f"{prefix} {extras['player_narration']}".strip()
        return self._scene(state, pack, player_text, prefix=prefix)

    def evaluate_trigger(
        self,
        state: WorldState,
        pack: WorldPack,
        proposal: CheckProposal,
        trigger: str,
    ) -> int:
        return 1  # valutazione dimostrativa: innesco pertinente ma generico

    # -- costruzione scena dimostrativa -------------------------------------

    def _scene(
        self,
        state: WorldState,
        pack: WorldPack,
        player_text: str,
        prefix: str = "",
    ) -> FinalScene:
        location = pack.locations.get(state.location_id)
        location_name = location.name if location else state.location_id
        present = state.present_npc_ids()

        narration_parts = []
        if prefix:
            narration_parts.append(prefix)
        narration_parts.append(f"Nella quiete di {location_name}, il tuo gesto non passa inosservato.")

        dialogue = []
        if present:
            npc = state.npcs[present[0]]
            canon = pack.npc_canon.get(npc.id)
            style = canon.speech_style if canon and canon.speech_style else "misurato"
            dialogue.append(
                {
                    "speaker": npc.name,
                    "text": f"Ti ho vista. E voglio capire che intenzioni hai. ({npc.name}, tono {style})",
                }
            )
        narration_parts.append(player_text.strip())

        scene_dict = {
            "narration": " ".join(narration_parts),
            "dialogue": dialogue,
            "npc_actions": [
                {"npc_id": npc_id, "action": "osserva il giocatore con attenzione"}
                for npc_id in present
            ],
            "intentions": [
                {"npc_id": npc_id, "intention": "valutare le intenzioni del giocatore"}
                for npc_id in present
            ],
            "mutations": [],
            "memory_events": [
                {
                    "summary": f"Il giocatore ha agito: {player_text[:60]}",
                    "witnesses": present,
                    "level": "immediate",
                    "emotional_impact": 0,
                    "public": True,
                }
            ]
            if present
            else [],
            "visual": {
                "summary": "il momento dello scambio",
                "focus_character": present[0] if present else "player",
                "visible_characters": [present[0]] if present else ["player"],
                "shared_action": False,
                "visual_en": (
                    f"inside {location_name}, a tense quiet moment, "
                    "warm ambient light, cinematic composition"
                ),
                "tags_en": ["indoor", "dialogue scene"],
            },
        }
        return FinalScene.from_dict(scene_dict)


# ---------------------------------------------------------------------------
# GM live OpenAI-compatible
# ---------------------------------------------------------------------------


class OpenAICompatibleGameMaster:
    """GM live verso endpoint POST /chat/completions.

    Configurazione via env:
        EPOS_LLM_BASE_URL  — es. https://api.openai.com/v1
        EPOS_LLM_MODEL     — nome del modello
        EPOS_LLM_API_KEY   — chiave (o EPOS_LLM_KEY_ENV per puntare ad altra env)
    """

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        timeout_seconds: int | None = None,
        omit_temperature: bool = False,
        provider_chain: LlmProviderChain | None = None,
    ):
        try:
            self.provider_chain = provider_chain or provider_chain_from_env(
                base_url=base_url,
                model=model,
                api_key=api_key,
                timeout_seconds=timeout_seconds,
                omit_temperature=omit_temperature,
        )
        except LlmProviderError as exc:
            raise GameMasterError(
                str(exc),
                diagnostics={},
            ) from exc
        self.last_llm_diagnostics: dict[str, Any] = {}
        self.llm_diagnostics_dir: str | os.PathLike[str] | None = None

    def _compact_prompt(self) -> bool:
        providers = os.environ.get("EPOS_PROMPT_COMPACT_PROVIDERS", "zai").lower().split(",")
        providers = [p.strip() for p in providers if p.strip()]
        return self.provider_chain.primary.provider_id.lower() in providers

    # -- fasi ----------------------------------------------------------------

    def propose(self, state: WorldState, pack: WorldPack, player_text: str) -> GmPhaseResponse:
        messages = phase1_messages(state, pack, player_text, compact=self._compact_prompt())
        return self._call_contract(
            messages,
            phase="proposal",
            parse=GmPhaseResponse.from_dict,
        ).value

    def propose_validated(
        self,
        state: WorldState,
        pack: WorldPack,
        player_text: str,
        validate: Any,
    ) -> GmPhaseResponse:
        messages = phase1_messages(state, pack, player_text, compact=self._compact_prompt())
        return self._call_contract(
            messages,
            phase="proposal",
            parse=GmPhaseResponse.from_dict,
            validate=validate,
        ).value

    def revise(
        self,
        state: WorldState,
        pack: WorldPack,
        player_text: str,
        problems: list[str],
    ) -> GmPhaseResponse:
        messages = phase1_messages(state, pack, player_text, compact=self._compact_prompt())
        revision_note = (
            "\n\nREVISIONE SEMANTICA RICHIESTA DAL RUNTIME:\n"
            "La tua proposta di prova è stata rifiutata dall'arbitro Python "
            "per questi motivi:\n- "
            + "\n- ".join(problems)
            + "\nRipensa la scena: rispondi con mode no_check e la scena "
            "finale completa, senza proporre una nuova prova."
        )
        messages[-1] = {"role": "user", "content": messages[-1]["content"] + revision_note}
        return self._call_contract(
            messages,
            phase="semantic_revision",
            parse=GmPhaseResponse.from_dict,
        ).value

    def narrate(
        self,
        state: WorldState,
        pack: WorldPack,
        player_text: str,
        proposal: CheckProposal,
        roll: Roll,
        stake: str,
        extras: dict[str, Any] | None = None,
    ) -> FinalScene:
        messages = phase2_messages(
            state, pack, player_text, proposal.to_dict(), roll.to_dict(), stake,
            extras=extras, compact=self._compact_prompt(),
        )
        return self._call_contract(
            messages,
            phase="final_scene",
            parse=FinalScene.from_dict,
            scene_error=True,
        ).value

    def narrate_validated(
        self,
        state: WorldState,
        pack: WorldPack,
        player_text: str,
        proposal: CheckProposal,
        roll: Roll,
        stake: str,
        validate: Any,
        extras: dict[str, Any] | None = None,
    ) -> FinalScene:
        messages = phase2_messages(
            state, pack, player_text, proposal.to_dict(), roll.to_dict(), stake,
            extras=extras, compact=self._compact_prompt(),
        )
        return self._call_contract(
            messages,
            phase="final_scene",
            parse=FinalScene.from_dict,
            validate=validate,
            scene_error=True,
        ).value

    def narrate_confront(
        self,
        state: WorldState,
        pack: WorldPack,
        player_text: str,
        proposal: ConfrontProposal,
        result: ConfrontResult,
        stake: str,
        extras: dict[str, Any] | None = None,
    ) -> FinalScene:
        messages = phase2_messages(
            state,
            pack,
            player_text,
            proposal.to_dict(),
            {"winner": result.winner, "narrator": result.narrator, **result.to_dict()},
            stake,
            extras={**(extras or {}), "is_confront": True},
            compact=self._compact_prompt(),
        )
        return self._call_contract(
            messages,
            phase="confront_scene",
            parse=FinalScene.from_dict,
            scene_error=True,
        ).value

    def narrate_confront_validated(
        self,
        state: WorldState,
        pack: WorldPack,
        player_text: str,
        proposal: ConfrontProposal,
        result: ConfrontResult,
        stake: str,
        validate: Any,
        extras: dict[str, Any] | None = None,
    ) -> FinalScene:
        messages = phase2_messages(
            state,
            pack,
            player_text,
            proposal.to_dict(),
            {"winner": result.winner, "narrator": result.narrator, **result.to_dict()},
            stake,
            extras={**(extras or {}), "is_confront": True},
            compact=self._compact_prompt(),
        )
        return self._call_contract(
            messages,
            phase="confront_scene",
            parse=FinalScene.from_dict,
            validate=validate,
            scene_error=True,
        ).value

    def evaluate_trigger(
        self,
        state: WorldState,
        pack: WorldPack,
        proposal: CheckProposal,
        trigger: str,
    ) -> int:
        messages = [
            {"role": "system", "content": "Valuta un innesco per un GDR. Rispondi SOLO con JSON."},
            {
                "role": "user",
                "content": (
                    f"Innesco dichiarato dal giocatore: {trigger!r}\n"
                    f"Proposta di prova: {proposal.to_dict()}\n"
                    "Valuta l'innesco da 0 a 3 secondo pertinenza e specificità: "
                    "0 = generico, 1 = contesto ampio, 2 = specifico, 3 = precisissimo. "
                    'Rispondi {"value": N}.'
                ),
            },
        ]
        result = self._call_contract(
            messages,
            phase="trigger_evaluation",
            parse=lambda payload: payload,
        )
        return max(0, min(3, int(result.raw_payload.get("value", 0))))

    # -- trasporto -------------------------------------------------------------

    def _call_contract(
        self,
        messages: list[dict[str, str]],
        phase: str,
        parse: Any,
        validate: Any | None = None,
        scene_error: bool = False,
    ) -> LlmCallResult[Any]:
        try:
            result = self.provider_chain.complete_json(
                messages,
                phase=phase,
                parse=parse,
                validate=validate,
                diagnostics_dir=self.llm_diagnostics_dir,
            )
            self.last_llm_diagnostics = result.diagnostics
            return result
        except LlmProviderError as exc:
            diagnostics = dict(self.provider_chain.last_diagnostics)
            diagnostics["phase"] = phase
            error_cls = SceneValidationError if scene_error else GameMasterError
            raise error_cls(
                f"Provider LLM fallito nella fase {phase}: {exc}",
                diagnostics=diagnostics,
            ) from exc
