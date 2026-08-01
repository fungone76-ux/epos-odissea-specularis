"""Intro canonica e deterministica per Seven Nights at Azure Crown.

Le quattro presentazioni iniziali non dipendono dalla LLM: Python governa
contenuto, ordine, NPC visibile e avanzamento. Dopo Stella il servizio torna
al normale gameplay LLM del Resort.
"""

from __future__ import annotations

from .contract import FinalScene
from .resort_intro import (
    advance_resort_intro,
    current_intro_step,
    initialise_resort_intro,
)
from .resort_turn_service import ResortTurnService, _merge_reports, _speaker_id
from .validators import ValidationErrorDetail, ValidationReport


_LOBBY_VISUAL = (
    "inside the grand Azure Crown luxury resort lobby, polished white marble floor, "
    "marble reception desk, floor-to-ceiling glass walls, visible Mediterranean sea, "
    "warm natural daylight, elegant brass details, luxury interior clearly visible, "
    "detailed environmental background, no studio backdrop"
)

_LOBBY_TAGS = [
    "NPC introduction",
    "grand luxury resort lobby interior",
    "polished marble floor",
    "marble reception desk",
    "floor-to-ceiling glass walls",
    "Mediterranean sea view",
    "detailed environmental background",
]

_INTRO_COPY = {
    "victoria": {
        "narration": (
            "Victoria Hale ti accoglie nella lobby dell'Azure Crown con la calma "
            "autorevole di chi dirige ogni dettaglio del resort. Si presenta come "
            "direttrice e ti informa che sarà lei ad accompagnarti nelle presentazioni "
            "di Luna, Maria e Stella."
        ),
        "dialogue": (
            "Benvenuto all'Azure Crown. Sono Victoria Hale, la direttrice del resort. "
            "Durante il soggiorno sarò il tuo riferimento personale. Prima di lasciarti "
            "esplorare liberamente, desidero presentarti Luna, Maria e Stella, una alla volta."
        ),
        "visual": (
            "Victoria Hale formally welcomes the unseen VIP guest, poised authoritative "
            "posture, elegant cinematic composition, " + _LOBBY_VISUAL
        ),
        "summary": "Victoria Hale si presenta come direttrice e annuncia le altre collaboratrici.",
    },
    "luna": {
        "narration": (
            "Victoria lascia spazio a Luna. La giovane donna si presenta con modi misurati "
            "e uno sguardo attento, spiegando che seguirà personalmente gli aspetti più "
            "riservati e discreti del soggiorno."
        ),
        "dialogue": (
            "Piacere, sono Luna. Mi occupo dell'assistenza privata e discreta degli ospiti. "
            "Preferisco osservare e capire ciò che serve davvero, prima di intervenire."
        ),
        "visual": (
            "Luna introduces herself to the unseen VIP guest, reserved attentive posture, "
            "elegant cinematic composition, " + _LOBBY_VISUAL
        ),
        "summary": "Luna si presenta e descrive il proprio ruolo di assistente privata.",
    },
    "maria": {
        "narration": (
            "È quindi il turno di Maria, composta e professionale. Si presenta come la "
            "responsabile dell'assistenza nella suite presidenziale e dei servizi personali "
            "durante il soggiorno."
        ),
        "dialogue": (
            "Sono Maria. Mi occuperò della suite presidenziale e di tutto ciò che riguarda "
            "il tuo comfort personale. Puoi rivolgerti direttamente a me per qualsiasi necessità."
        ),
        "visual": (
            "Maria introduces herself to the unseen VIP guest, calm professional posture, "
            "elegant cinematic composition, " + _LOBBY_VISUAL
        ),
        "summary": "Maria si presenta come responsabile della suite e del servizio personale.",
    },
    "stella": {
        "narration": (
            "Per ultima si presenta Stella, vivace e sicura di sé. Spiega di occuparsi "
            "dell'intrattenimento VIP, degli eventi e delle esperienze speciali organizzate "
            "all'interno del resort."
        ),
        "dialogue": (
            "Io sono Stella. Organizzo gli eventi VIP, l'intrattenimento e le esperienze "
            "speciali dell'Azure Crown. Farò in modo che qui non ci sia spazio per la noia."
        ),
        "visual": (
            "Stella introduces herself to the unseen VIP guest, confident lively posture, "
            "elegant cinematic composition, " + _LOBBY_VISUAL
        ),
        "summary": "Stella si presenta come responsabile dell'intrattenimento VIP.",
    },
}


def _canonical_intro_scene(npc_id: str, name: str) -> FinalScene:
    copy = _INTRO_COPY[npc_id]
    return FinalScene.from_dict(
        {
            "narration": copy["narration"],
            "dialogue": [
                {
                    "speaker": name,
                    "text": copy["dialogue"],
                    "to": "player",
                }
            ],
            "npc_actions": [
                {"npc_id": npc_id, "action": "si presenta personalmente al cliente VIP"}
            ],
            "intentions": [],
            "initiatives": [],
            "disclosure_events": [],
            "mutations": [],
            "memory_events": [],
            "visual": {
                "summary": copy["summary"],
                "focus_character": npc_id,
                "visible_characters": [npc_id],
                "shared_action": False,
                "visual_en": copy["visual"],
                "tags_en": list(_LOBBY_TAGS),
                "moment_type": "speech",
                "speaker_character": npc_id,
                "actor_character": npc_id,
                "reactor_character": npc_id,
                "intimate_shared_moment": False,
                "multi_character_reason": "",
                "multi_character_participants": [npc_id],
            },
        }
    )


class ResortIntroTurnService(ResortTurnService):
    """Resort service con intro canonica, senza chiamate LLM."""

    def play(self, state, player_text: str):
        initialise_resort_intro(state)
        step = current_intro_step(state)
        if step is None:
            return super().play(state, player_text)

        presence = {
            npc_id: (npc.present, npc.location_id)
            for npc_id, npc in state.npcs.items()
        }
        try:
            for npc_id, npc in state.npcs.items():
                npc.present = npc_id == step.npc_id
                if npc_id == step.npc_id:
                    npc.location_id = state.location_id

            scene = _canonical_intro_scene(step.npc_id, state.npcs[step.npc_id].name)
            result = self._commit_turn(
                state,
                state.turn,
                "no_check",
                scene,
                player_text=player_text,
            )
            advance_resort_intro(state, result)
            self.store.save_state(state)
            return result
        finally:
            for npc_id, (present, location_id) in presence.items():
                npc = state.npcs[npc_id]
                npc.present = present
                npc.location_id = location_id
            self.store.save_state(state)

    def _strict_intro_report(self, state, scene) -> ValidationReport:
        step = current_intro_step(state)
        if step is None:
            return ValidationReport()

        target = step.npc_id
        other_ids = set(state.npcs) - {target}
        problems: list[str] = []
        errors: list[ValidationErrorDetail] = []

        wrong_speakers = []
        for line in scene.dialogue:
            speaker_id = _speaker_id(state, getattr(line, "speaker", ""))
            if speaker_id in other_ids:
                wrong_speakers.append(speaker_id)
        wrong_actions = [
            str(getattr(action, "npc_id", ""))
            for action in scene.npc_actions
            if str(getattr(action, "npc_id", "")) in other_ids
        ]
        wrong_intentions = [
            str(item.get("npc_id", ""))
            for item in scene.intentions
            if str(item.get("npc_id", "")) in other_ids
        ]

        forbidden = sorted(set(wrong_speakers + wrong_actions + wrong_intentions))
        if forbidden:
            message = (
                f"Intro Resort: nello step {target} nessun'altra NPC può parlare, "
                f"agire o ricevere intenzioni: {', '.join(forbidden)}"
            )
            problems.append(message)
            errors.append(
                ValidationErrorDetail(
                    code="resort_intro_other_npc_forbidden",
                    path="dialogue|npc_actions|intentions",
                    message=message,
                    details={"target_npc_id": target, "forbidden_npcs": forbidden},
                )
            )

        if scene.visual is not None:
            if scene.visual.focus_character != target or scene.visual.visible_characters != [target]:
                message = f"Intro Resort: il visual deve contenere soltanto {target}"
                problems.append(message)
                errors.append(
                    ValidationErrorDetail(
                        code="resort_intro_single_visual_required",
                        path="visual.focus_character|visual.visible_characters",
                        message=message,
                        details={
                            "target_npc_id": target,
                            "focus_character": scene.visual.focus_character,
                            "visible_characters": list(scene.visual.visible_characters),
                        },
                    )
                )

        return ValidationReport(problems=problems, errors=errors)

    def _validate_phase1_response_after_outfit_normalization(
        self, response, state, player_text: str
    ):
        base = super()._validate_phase1_response_after_outfit_normalization(
            response, state, player_text
        )
        if response.mode != "no_check" or response.scene is None:
            return base
        return _merge_reports(base, self._strict_intro_report(state, response.scene))

    def _validate_scene_after_outfit_normalization(
        self, scene, state, player_text: str
    ):
        base = super()._validate_scene_after_outfit_normalization(
            scene, state, player_text
        )
        return _merge_reports(base, self._strict_intro_report(state, scene))
