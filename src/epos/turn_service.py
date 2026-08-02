"""TurnService: il ciclo canonico del turno.

    input libero
      → fase 1 GM (no_check | check_proposal | confront_proposal)
      → validazione Python della proposta (revisione semantica con limite)
      → decisione del giocatore: roll/safe, riserva, dado temerario, trigger
      → risoluzione autorevole (persistita subito) + eventuale tiro temerario
      → successo pieno / narratore giocatore: il giocatore descrive l'esito
      → fase 2 GM: scena finale coerente con l'esito autorevole
      → validazione della scena
      → commit → visual contract → rendering (mai bloccante)

Autorità narrativa del successo pieno (manuale EVENT): il giocatore
descrive i dettagli; il GM li incorpora rispettando adeguatezza,
integrità e pertinenza.
"""

from __future__ import annotations

import random
from copy import deepcopy
from collections.abc import Callable
from dataclasses import replace
from typing import Any

from .commit import apply_scene
from .contract import (
    CheckProposal,
    ConfrontProposal,
    FinalScene,
    GmPhaseResponse,
    outcome_stake,
)
from .gm import GameMaster, GameMasterError, SceneValidationError
from .entity_ids import (
    normalize_phase_response_entity_ids,
    normalize_scene_entity_ids,
)
from .models import WorldState, outfit_state
from .narrative_policy import derive_narrative_policy
from .outfit import (
    format_current_outfit_for_ui,
    normalize_player_outfit_phase_response,
    normalize_player_outfit_scene,
)
from .prompt import build_snapshot
from .player_agency import (
    player_agency_diagnostics,
    validate_check_proposal_player_agency,
    validate_scene_player_agency,
)
from .renderers import PendingRenderer, RenderRecord, Renderer
from .scene_normalize import repair_scene
from .rules import (
    ConfrontResult,
    Roll,
    choice_is_meaningful,
    confront,
    pool_size_for,
    reckless_reroll,
    resolve_check,
)
from .state_store import StateStore
from .turn_diagnostics import _phase_response_to_dict, _scene_to_dict
from .validators import ValidationReport, validate_check_proposal, validate_confront_proposal, validate_scene
from .turn_resolution import NPC_SKILL_ALIASES, npc_confront_rating
from .turn_types import (
    DecisionProvider,
    NarrationProvider,
    PlayerDecision,
    PostTurnProcessor,
    SplitProvider,
    TemerarioProvider,
    TurnResult,
    default_decision,
    default_narration,
    default_post_turn_processor,
    default_split,
    default_temerario,
)
from .visual import VisualContract, build_visual_contract
from .worldpack import WorldPack


# ---------------------------------------------------------------------------
# Facciata compatibile: tipi/provider e helper risoluzione sono re-export importati.
# ---------------------------------------------------------------------------

class TurnService:
    def __init__(
        self,
        gm: GameMaster,
        pack: WorldPack,
        store: StateStore | None = None,
        renderer: Renderer | None = None,
        rng: random.Random | None = None,
        decision_provider: DecisionProvider = default_decision,
        narration_provider: NarrationProvider = default_narration,
        split_provider: SplitProvider = default_split,
        temerario_provider: TemerarioProvider = default_temerario,
        post_turn_processor: PostTurnProcessor = default_post_turn_processor,
        progress: Callable[[str], None] | None = None,
    ):
        self.gm = gm
        self.pack = pack
        self.store = store or StateStore()
        self.renderer = renderer or PendingRenderer()
        self.rng = rng or random.Random()
        self.decision_provider = decision_provider
        self.narration_provider = narration_provider
        self.split_provider = split_provider
        self.temerario_provider = temerario_provider
        self.post_turn_processor = post_turn_processor
        # callback opzionale per mostrare l'avanzamento del turno (GUI/CLI)
        self.progress = progress
        self._outfit_normalization_diagnostics: dict[tuple[str, int], dict[str, Any]] = {}
        self._entity_id_normalization_diagnostics: dict[tuple[str, int], list[dict[str, Any]]] = {}

    def _report(self, message: str) -> None:
        if self.progress is not None:
            try:
                self.progress(message)
            except Exception:
                pass  # il feedback non blocca mai il turno

    def _narrate_with_retry(
        self,
        state: WorldState,
        turn: int,
        player_text: str,
        narrate_fn: Callable[[], FinalScene],
    ) -> FinalScene:
        """Narrazione con un secondo tentativo se la scena non è valida.

        Col GM live può capitare una scena JSON senza campi obbligatori:
        invece di buttare via il turno (proposta + tiro già risolti), si
        riprova una volta. Se anche il secondo tentativo fallisce, l'errore
        risale e il turno resta intatto come sempre.
        """
        try:
            self._save_gm_snapshot(state, turn, "final_scene", player_text)
            scene = self._normalize_scene_pipeline(
                state, turn, player_text, narrate_fn(), phase="final_scene"
            )
            _require_scene_obj(scene, state, self.pack, self.store, turn, player_text)
            self._save_llm_diagnostics(state, turn)
            return scene
        except SceneValidationError:
            # Solo scene invalide: un secondo tentativo prima di buttare via
            # proposta e tiro già risolti. Gli errori di trasporto/crash
            # risalgono subito e il turno resta ripristinabile dal checkpoint.
            self._report("Scena non valida: secondo tentativo di narrazione…")
            scene = self._normalize_scene_pipeline(
                state, turn, player_text, narrate_fn(), phase="final_scene_retry"
            )
            _require_scene_obj(scene, state, self.pack, self.store, turn, player_text)
            self._save_llm_diagnostics(state, turn)
            return scene

    # -- sessioni ----------------------------------------------------------------

    def new_session(
        self,
        session_id: str | None = None,
        creation_answers: "CreationAnswers | None" = None,
    ) -> WorldState:
        state = self.pack.new_world(session_id)
        if creation_answers is not None:
            from .creation import CreationService

            player, sheet = CreationService(self.pack).create(creation_answers)
            state.player = player
            # il visual canonico del pack (protagonista fissa) prevale sempre
            if "player" not in self.pack.visual_sheets:
                state.flags.setdefault("visual_overrides", {})["player"] = sheet.base_prompt
        self.store.save_state(state)
        return state

    def load_session(self, session_id: str) -> WorldState:
        return self.store.load_state(session_id)

    def has_pending_checkpoint(self, session_id: str) -> bool:
        return self.store.load_checkpoint(session_id) is not None

    # -- ciclo del turno -----------------------------------------------------------

    def play(self, state: WorldState, player_text: str) -> TurnResult:
        turn = state.turn
        self._prepare_llm_attempt_diagnostics(state, turn)

        self._save_gm_snapshot(state, turn, "proposal", player_text)
        propose_validated = getattr(self.gm, "propose_validated", None)
        try:
            if propose_validated is not None:
                phase1 = propose_validated(
                    state,
                    self.pack,
                    player_text,
                    lambda response: self._validate_phase1_response_after_outfit_normalization(
                        response, state, player_text
                    ),
                )
            else:
                phase1 = self.gm.propose(state, self.pack, player_text)
        except GameMasterError as exc:
            if exc.diagnostics:
                self.store.save_turn_artifact(
                    state.session_id, turn, "llm_diagnostics", exc.diagnostics
                )
            raise
        phase1 = self._normalize_phase1_pipeline(
            state, turn, player_text, phase1, phase="proposal"
        )
        self.store.save_turn_artifact(
            state.session_id, turn, "gm_phase1", _phase_response_to_dict(phase1)
        )
        self._save_llm_diagnostics(state, turn)

        if phase1.mode == "clarification":
            return TurnResult(
                turn=turn,
                mode="clarification",
                narration=phase1.clarification,
            )

        if phase1.mode == "no_check":
            scene = _require_scene(phase1, state, self.pack, player_text)
            return self._commit_turn(state, turn, "no_check", scene, player_text=player_text)

        if phase1.mode == "confront_proposal":
            return self._play_confront(state, turn, player_text, phase1.confront)

        return self._play_check(state, turn, player_text, phase1.check)

    # -- prova -----------------------------------------------------------------

    def _play_check(
        self, state: WorldState, turn: int, player_text: str, proposal: CheckProposal
    ) -> TurnResult:
        report = _combine_reports(
            validate_check_proposal(state, self.pack, proposal),
            validate_check_proposal_player_agency(state, self.pack, proposal, player_text),
        )
        if not report.ok:
            # revisione semantica con limite: una sola, tracciata, poi strict
            self._save_diagnostics(state, turn, "invalid_check_proposal", report.problems)
            self._metric(state, "semantic_revisions")
            self._save_gm_snapshot(
                state, turn, "semantic_revision", player_text, {"problems": report.problems}
            )
            revision = self.gm.revise(state, self.pack, player_text, report.problems)
            revision = self._normalize_phase1_pipeline(
                state, turn, player_text, revision, phase="semantic_revision"
            )
            self.store.save_turn_artifact(
                state.session_id, turn, "gm_revision", _phase_response_to_dict(revision)
            )
            if revision.mode != "no_check" or revision.scene is None:
                raise GameMasterError(
                    "La revisione semantica non ha prodotto una scena senza prova",
                    diagnostics={"phase": "semantic_revision"},
                )
            scene = _require_scene(revision, state, self.pack, player_text)
            return self._commit_turn(state, turn, "no_check", scene, player_text=player_text)

        rating = state.player.skill_rating(proposal.skill)
        decision = self.decision_provider(proposal, rating, proposal.difficulty, state)

        boosts = 0
        if decision.use_riserva and state.riserva > 0:
            boosts += 1
        if decision.dado_temerario_price:
            boosts += 1
        if decision.use_trigger and state.player.trigger:
            boosts += self._evaluate_trigger(state, proposal)

        pool = pool_size_for(rating, boosts)
        if choice_is_meaningful(pool, proposal.difficulty):
            choice = decision.choice
        else:
            choice = "safe"  # pool > difficoltà: successo pieno automatico

        talent = state.player.talent == proposal.skill
        roll = resolve_check(
            pool, proposal.difficulty, choice, self.rng,
            open_end=self.pack.open_end, talent=talent,
        )

        # applicazione dei consumabili solo a tiro avvenuto
        if decision.use_riserva and state.riserva > 0:
            state.riserva -= 1
        if decision.use_trigger and state.player.trigger:
            state.player.trigger = None  # l'innesco si consuma

        temerario_price = decision.dado_temerario_price
        if roll.dice and roll.outcome.value in ("failure", "critical_failure"):
            reroll_price = self.temerario_provider(roll)
            if reroll_price:
                roll = reckless_reroll(roll, self.rng)
                temerario_price = reroll_price

        self.store.save_turn_artifact(state.session_id, turn, "roll", roll.to_dict())
        # il tiro esiste PRIMA della narrazione: un crash qui non lo ripete
        self.store.save_checkpoint(
            state.session_id, turn, "check_resolved", proposal.to_dict(), roll
        )

        stake = outcome_stake(proposal, roll.outcome)
        extras: dict[str, Any] = {"choice": choice}
        if roll.outcome.value == "full_success" and roll.dice:
            # autorità narrativa del successo pieno: il giocatore descrive
            player_narration = self.narration_provider(
                f"Successo pieno. Posta: {stake}\nDescrivi come accade:"
            )
            if player_narration.strip():
                extras["player_narration"] = player_narration.strip()
        if temerario_price and roll.outcome.value in ("failure", "critical_failure"):
            extras["temerario_price"] = temerario_price

        self._report("Fase 2/3 — Il GM narra la scena (può richiedere 1-2 minuti)…")
        scene = self._narrate_with_retry(
            state,
            turn,
            player_text,
            lambda: self._narrate_validated_or_plain(
                state, player_text, proposal, roll, stake, extras
            ),
        )

        result = self._commit_turn(
            state, turn, "check", scene, proposal, roll, stake,
            player_text=player_text,
            player_narration=extras.get("player_narration", ""),
            temerario_price=temerario_price,
        )
        return result

    # -- confronto ----------------------------------------------------------------

    def _play_confront(
        self, state: WorldState, turn: int, player_text: str, proposal: ConfrontProposal
    ) -> TurnResult:
        report = validate_confront_proposal(state, self.pack, proposal)
        if not report.ok:
            self._save_diagnostics(state, turn, "invalid_confront_proposal", report.problems)
            self._metric(state, "semantic_revisions")
            self._save_gm_snapshot(
                state, turn, "semantic_revision", player_text, {"problems": report.problems}
            )
            revision = self.gm.revise(state, self.pack, player_text, report.problems)
            revision = self._normalize_phase1_pipeline(
                state, turn, player_text, revision, phase="semantic_revision"
            )
            if revision.mode != "no_check" or revision.scene is None:
                raise GameMasterError(
                    "La revisione semantica non ha prodotto una scena senza confronto",
                    diagnostics={"phase": "semantic_revision"},
                )
            scene = _require_scene(revision, state, self.pack, player_text)
            return self._commit_turn(state, turn, "no_check", scene, player_text=player_text)

        player_rating = state.player.skill_rating(proposal.skill)
        player_pool = pool_size_for(player_rating)
        canon = self.pack.npc_canon.get(proposal.target_id)
        npc_rating = npc_confront_rating(canon.skills, proposal.skill) if canon else 0
        npc_pool = pool_size_for(npc_rating)

        player_left = self.split_provider(proposal, player_pool, npc_pool)
        result = confront(player_pool, npc_pool, player_left, self.rng)
        self.store.save_turn_artifact(
            state.session_id, turn, "confront", result.to_dict()
        )
        self.store.save_checkpoint(
            state.session_id, turn, "confront_resolved", proposal.to_dict(), None
        )

        stake = proposal.stakes[
            {"player": "win", "npc": "lose", "stall": "stall"}[result.winner]
        ]
        extras: dict[str, Any] = {"confront": result.to_dict()}
        if result.narrator in ("player", "shared"):
            context = (
                "Hai vinto il confronto e la narrazione ti spetta."
                if result.narrator == "player"
                else "Stallo narrativo: la narrazione è condivisa col GM."
            )
            player_narration = self.narration_provider(
                f"{context} Posta: {stake}\nDescrivi come accade:"
            )
            if player_narration.strip():
                extras["player_narration"] = player_narration.strip()

        self._report("Fase 2/3 — Il GM narra l'esito del confronto…")
        scene = self._narrate_with_retry(
            state,
            turn,
            player_text,
            lambda: self._narrate_confront_validated_or_plain(
                state, player_text, proposal, result, stake, extras
            ),
        )

        return self._commit_turn(
            state, turn, "confront", scene, stake=stake,
            confront_result=result,
            player_text=player_text,
            player_narration=extras.get("player_narration", ""),
        )

    def _narrate_validated_or_plain(
        self,
        state: WorldState,
        player_text: str,
        proposal: CheckProposal,
        roll: Roll,
        stake: str,
        extras: dict[str, Any] | None,
    ) -> FinalScene:
        narrate_validated = getattr(self.gm, "narrate_validated", None)
        if narrate_validated is not None:
            return narrate_validated(
                state,
                self.pack,
                player_text,
                proposal,
                roll,
                stake,
                lambda scene: self._validate_scene_after_outfit_normalization(
                    scene, state, player_text
                ),
                extras=extras,
            )
        return self.gm.narrate(
            state, self.pack, player_text, proposal, roll, stake, extras=extras
        )

    def _narrate_confront_validated_or_plain(
        self,
        state: WorldState,
        player_text: str,
        proposal: ConfrontProposal,
        result: ConfrontResult,
        stake: str,
        extras: dict[str, Any] | None,
    ) -> FinalScene:
        narrate_confront_validated = getattr(self.gm, "narrate_confront_validated", None)
        if narrate_confront_validated is not None:
            return narrate_confront_validated(
                state,
                self.pack,
                player_text,
                proposal,
                result,
                stake,
                lambda scene: self._validate_scene_after_outfit_normalization(
                    scene, state, player_text
                ),
                extras=extras,
            )
        return self.gm.narrate_confront(
            state, self.pack, player_text, proposal, result, stake, extras=extras
        )

    # -- trigger -----------------------------------------------------------------

    def _evaluate_trigger(
        self, state: WorldState, proposal: CheckProposal
    ) -> int:
        """Il GM valuta l'innesco (0-3 dadi) come da manuale."""

        evaluate = getattr(self.gm, "evaluate_trigger", None)
        if evaluate is None:
            return 0
        value = int(evaluate(state, self.pack, proposal, state.player.trigger or ""))
        return max(0, min(3, value))

    # -- ripresa -----------------------------------------------------------------

    def resume_pending(self, state: WorldState, player_text: str) -> TurnResult | None:
        """Riprende un turno interrotto dopo il tiro: riusa lo STESSO roll."""

        checkpoint = self.store.load_checkpoint(state.session_id)
        if checkpoint is None:
            return None
        if checkpoint["turn"] != state.turn:
            return None

        if checkpoint["phase"] == "check_resolved":
            proposal = CheckProposal.from_dict(checkpoint["proposal"])
            roll = Roll.from_dict(checkpoint["roll"])
            stake = outcome_stake(proposal, roll.outcome)
            turn = state.turn
            self._prepare_llm_attempt_diagnostics(state, turn)
            self._report("Ripresa turno — Il GM narra la scena…")
            scene = self._narrate_with_retry(
                state,
                turn,
                player_text,
                lambda: self._narrate_validated_or_plain(
                    state, player_text, proposal, roll, stake, {}
                ),
            )
            result = self._commit_turn(
                state, turn, "check", scene, proposal, roll, stake, player_text=player_text
            )
            result.resumed = True
            return result
        return None

    # -- commit ------------------------------------------------------------------

    def _commit_turn(
        self,
        state: WorldState,
        turn: int,
        mode: str,
        scene: FinalScene,
        proposal: CheckProposal | None = None,
        roll: Roll | None = None,
        stake: str = "",
        confront_result: ConfrontResult | None = None,
        player_text: str = "",
        player_narration: str = "",
        temerario_price: str | None = None,
    ) -> TurnResult:
        outfit_before = self._outfit_state_snapshot(state)
        normalization_diag = self._outfit_normalization_diagnostics.pop(
            (state.session_id, turn),
            {},
        )
        entity_id_diag = self._entity_id_normalization_diagnostics.pop(
            (state.session_id, turn),
            [],
        )
        narrative_policy = derive_narrative_policy(
            state,
            self.pack,
            player_text,
            scene=scene,
            proposal=proposal,
            roll=roll,
            phase="commit",
        )
        agency_diagnostics = player_agency_diagnostics(
            state,
            player_text,
            proposal=proposal,
            scene=scene,
        ).to_dict()
        committed_state = deepcopy(state)
        apply_scene(committed_state, scene, pack=self.pack)
        outfit_after = self._outfit_state_snapshot(committed_state)
        committed_state.turn = turn + 1

        visual_contract = None
        if scene.visual is not None:
            visual_contract = build_visual_contract(committed_state, self.pack, scene.visual, turn)
            self.store.save_turn_artifact(
                committed_state.session_id, turn, "visual_contract", visual_contract.to_dict()
            )

        self.store.save_turn_artifact(
            committed_state.session_id, turn, "scene", _scene_to_dict(scene)
        )
        result = TurnResult(
            turn=turn,
            mode=mode,
            narration=scene.narration,
            dialogue=[{"speaker": d.speaker, "text": d.text, "to": d.to} for d in scene.dialogue],
            proposal=proposal,
            roll=roll,
            confront_result=confront_result,
            player_narration=player_narration,
            temerario_price=temerario_price,
            stake=stake,
            visual_contract=visual_contract,
            scene_mutations=[
                {"type": m.type, "target": m.target, "payload": dict(m.payload), "reason": m.reason}
                for m in scene.mutations
            ],
        )
        campaign_changes = self.post_turn_processor(committed_state, result) or {}
        result.campaign_changes = dict(campaign_changes)
        if result.campaign_changes:
            self.store.save_turn_artifact(
                committed_state.session_id, turn, "campaign_changes", result.campaign_changes
            )
        self.store.save_state(committed_state)
        state.__dict__.clear()
        state.__dict__.update(deepcopy(committed_state).__dict__)
        outfit_saved = self._outfit_state_snapshot(state)
        ui_state = format_current_outfit_for_ui(state.player)
        self.store.save_turn_artifact(
            state.session_id,
            turn,
            "outfit_diagnostics",
            {
                "source_of_truth": "WorldState.player.outfit",
                "outfit_state_before_turn": outfit_before,
                "outfit_intent_detected": normalization_diag.get("outfit_intent_detected", "none"),
                "outfit_mutations_requested": [
                    {"type": m.type, "target": m.target, "payload": dict(m.payload), "reason": m.reason}
                    for m in scene.mutations
                    if m.type in ("outfit_wear", "outfit_remove")
                ],
                "outfit_mutations_normalized": normalization_diag.get(
                    "outfit_mutations_normalized", []
                ),
                "outfit_mutations_applied": [
                    {"type": m.type, "target": m.target, "payload": dict(m.payload), "reason": m.reason}
                    for m in scene.mutations
                    if m.type in ("outfit_wear", "outfit_remove")
                ],
                "outfit_state_after_turn": outfit_after,
                "outfit_state_saved": outfit_saved,
                "outfit_state_loaded_next_turn": outfit_saved,
                "outfit_ui_value": ui_state.value,
                "outfit_ui_items": list(ui_state.items),
                "nudity_mode": outfit_saved["nudity_mode"],
                "outfit_revision": outfit_saved["revision"],
                "outfit_normalization_problems": normalization_diag.get(
                    "outfit_normalization_problems", []
                ),
            },
        )
        self.store.save_turn_artifact(
            state.session_id,
            turn,
            "entity_id_diagnostics",
            {
                "source_of_truth": "WorldState character ids",
                "normalizations": entity_id_diag,
            },
        )
        self.store.save_turn_artifact(
            state.session_id,
            turn,
            "narrative_diagnostics",
            narrative_policy.to_dict(),
        )
        self.store.save_turn_artifact(
            state.session_id,
            turn,
            "player_agency_diagnostics",
            agency_diagnostics,
        )
        self.store.clear_checkpoint(state.session_id)

        if visual_contract is not None:
            self._report("Fase 3/3 — Generazione immagine…")
        render_record = self._render(state, turn, visual_contract)

        self._write_turn_debug(
            state, turn, mode, player_text, proposal, roll, stake,
            scene, visual_contract, render_record,
        )

        result.render_record = render_record
        return result

    def _render(
        self, state: WorldState, turn: int, visual_contract: VisualContract | None
    ) -> RenderRecord | None:
        if visual_contract is None:
            return None
        record = self.renderer.render(
            visual_contract.prompt_package,
            self.store.turn_dir(state.session_id, turn),
        )
        self.store.save_turn_artifact(
            state.session_id, turn, "render_record", record.to_dict()
        )
        return record

    # -- debug leggibile per turno --------------------------------------------

    def _write_turn_debug(
        self,
        state: WorldState,
        turn: int,
        mode: str,
        player_text: str,
        proposal: CheckProposal | None,
        roll: Roll | None,
        stake: str,
        scene: FinalScene,
        visual_contract: VisualContract | None,
        render_record: RenderRecord | None,
    ) -> None:
        """Scrive debug_turno.txt nella cartella del turno: cosa e stato
        scritto, cosa e stato deciso, cosa e stato generato. Mai bloccante."""
        try:
            lines = [
                "=" * 64,
                f"DEBUG TURNO {turn} — modalità: {mode}",
                f"sessione: {state.session_id} | location: {state.location_id}",
                "=" * 64,
                "",
                "[INPUT GIOCATORE]",
                player_text or "(vuoto)",
                "",
            ]
            if proposal is not None:
                lines += [
                    "[PROPOSTA DEL GM]",
                    f"azione: {proposal.action_kind} | skill: {proposal.skill} | "
                    f"difficoltà: {proposal.difficulty}",
                    f"motivo: {proposal.reason}",
                    "",
                ]
            if roll is not None:
                lines += [
                    "[TIRO]",
                    f"pool: {roll.pool_size}d6 | difficoltà: {roll.difficulty} | "
                    f"dadi: {list(roll.dice) or '(nessun tiro — esito sicuro)'}",
                    f"esito: {roll.outcome.value}",
                    f"posta: {stake}",
                    "",
                ]
            lines += ["[NARRAZIONE]", scene.narration, ""]
            if scene.dialogue:
                lines.append("[DIALOGHI]")
                for d in scene.dialogue:
                    lines.append(f"- {d.speaker}: {d.text}")
                lines.append("")
            if visual_contract is not None:
                lines += [
                    "[PROMPT POSITIVO]",
                    visual_contract.prompt_package.get("positive", ""),
                    "",
                    "[PROMPT NEGATIVO]",
                    visual_contract.prompt_package.get("negative", ""),
                    "",
                    "[PROSA DI SCENA (visual_en)]",
                    visual_contract.visual_en,
                    "",
                ]
            if render_record is not None:
                lines += [
                    "[RENDER]",
                    f"status: {render_record.status} | backend: {render_record.backend}",
                    f"immagine: {render_record.image_path or '-'}",
                ]
                if render_record.error:
                    lines.append(f"errore: {render_record.error}")
                warning = getattr(render_record, "warning", None)
                if warning:
                    lines.append(f"⚠ {warning}")
                lines.append("")
            debug_path = self.store.turn_dir(state.session_id, turn) / "debug_turno.txt"
            debug_path.parent.mkdir(parents=True, exist_ok=True)
            debug_path.write_text("\n".join(lines), encoding="utf-8")
        except Exception:
            pass  # il debug non blocca mai il turno

    # -- rerender senza ripetere il turno -------------------------------------------

    def rerender(self, state: WorldState, turn: int | None = None) -> RenderRecord:
        turn = turn if turn is not None else state.turn - 1
        if turn < 0:
            raise GameMasterError("nessun turno da rigenerare")
        data = self.store.load_turn_artifact(state.session_id, turn, "visual_contract")
        if data is None:
            raise GameMasterError(f"nessun visual contract salvato per il turno {turn}")
        visual_contract = VisualContract.from_dict(data)
        record = self.renderer.render(
            visual_contract.prompt_package,
            self.store.turn_dir(state.session_id, turn),
        )
        self.store.save_turn_artifact(
            state.session_id, turn, "render_record", record.to_dict()
        )
        return record

    # -- diagnostica -----------------------------------------------------------------

    @staticmethod
    def _metric(state: WorldState, name: str) -> None:
        metrics = state.flags.setdefault("metrics", {})
        metrics[name] = metrics.get(name, 0) + 1

    @staticmethod
    def _outfit_state_snapshot(state: WorldState) -> dict[str, Any]:
        return outfit_state(state.player.outfit)

    def _normalize_phase1_pipeline(
        self,
        state: WorldState,
        turn: int,
        player_text: str,
        response,
        *,
        phase: str,
    ):
        entity_result = normalize_phase_response_entity_ids(
            state,
            response,
            phase=phase,
            source_payload="gm_phase1",
        )
        self._remember_entity_id_normalization(state, turn, entity_result.to_dict())
        response = entity_result.value
        normalized, diagnostics = normalize_player_outfit_phase_response(
            state, player_text, response
        )
        self._remember_outfit_normalization(state, turn, diagnostics.to_dict())
        return normalized

    def _normalize_scene_pipeline(
        self,
        state: WorldState,
        turn: int,
        player_text: str,
        scene: FinalScene,
        *,
        phase: str,
    ) -> FinalScene:
        entity_result = normalize_scene_entity_ids(
            state,
            scene,
            phase=phase,
            source_payload="final_scene",
        )
        self._remember_entity_id_normalization(state, turn, entity_result.to_dict())
        diagnostics = normalize_player_outfit_scene(state, player_text, entity_result.value)
        self._remember_outfit_normalization(state, turn, diagnostics.to_dict())
        repaired, _repair_notes = repair_scene(state, self.pack, diagnostics.scene)
        return repaired

    def _remember_outfit_normalization(
        self,
        state: WorldState,
        turn: int,
        diagnostics: dict[str, Any],
    ) -> None:
        current = self._outfit_normalization_diagnostics.setdefault(
            (state.session_id, turn),
            {
                "outfit_intent_detected": "none",
                "outfit_mutations_requested": [],
                "outfit_mutations_normalized": [],
                "outfit_normalization_problems": [],
            },
        )
        if diagnostics.get("outfit_intent_detected") != "none":
            current["outfit_intent_detected"] = diagnostics.get("outfit_intent_detected")
        for field_name in (
            "outfit_mutations_requested",
            "outfit_mutations_normalized",
            "outfit_normalization_problems",
        ):
            current[field_name].extend(diagnostics.get(field_name, []))

    def _remember_entity_id_normalization(
        self,
        state: WorldState,
        turn: int,
        diagnostics: dict[str, Any],
    ) -> None:
        current = self._entity_id_normalization_diagnostics.setdefault(
            (state.session_id, turn),
            [],
        )
        current.extend(diagnostics.get("normalizations", []))

    def _validate_scene_after_outfit_normalization(
        self,
        scene: FinalScene,
        state: WorldState,
        player_text: str,
    ):
        entity_result = normalize_scene_entity_ids(
            state,
            scene,
            phase="semantic_validation",
            source_payload="provider_parsed_scene",
        )
        normalized = normalize_player_outfit_scene(state, player_text, entity_result.value)
        repaired, _repair_notes = repair_scene(state, self.pack, normalized.scene)
        return _combine_reports(
            validate_scene(state, self.pack, repaired),
            validate_scene_player_agency(state, self.pack, repaired, player_text),
        )

    def _validate_phase1_response_after_outfit_normalization(
        self,
        response,
        state: WorldState,
        player_text: str,
    ):
        if response.mode == "no_check" and response.scene is not None:
            entity_result = normalize_phase_response_entity_ids(
                state,
                response,
                phase="semantic_validation",
                source_payload="provider_parsed_phase1",
            )
            response = entity_result.value
            response, _diagnostics = normalize_player_outfit_phase_response(
                state, player_text, response
            )
            if response.scene is not None:
                repaired, _repair_notes = repair_scene(
                    state, self.pack, response.scene
                )
                response = replace(response, scene=repaired)
        else:
            entity_result = normalize_phase_response_entity_ids(
                state,
                response,
                phase="semantic_validation",
                source_payload="provider_parsed_phase1",
            )
            response = entity_result.value
        return _validate_phase1_response(response, state, self.pack, player_text)

    def _save_diagnostics(self, state: WorldState, turn: int, kind: str, problems: list[str]):
        self.store.save_turn_artifact(
            state.session_id,
            turn,
            "diagnostics",
            {"kind": kind, "problems": problems},
        )

    def _save_gm_snapshot(
        self,
        state: WorldState,
        turn: int,
        phase: str,
        player_text: str,
        extra: dict[str, Any] | None = None,
    ) -> None:
        payload = {
            "phase": phase,
            "snapshot": build_snapshot(state, self.pack, player_text),
        }
        if extra:
            payload.update(extra)
        self.store.save_turn_artifact(
            state.session_id, turn, f"gm_snapshot_{phase}", payload
        )

    def _save_llm_diagnostics(self, state: WorldState, turn: int) -> None:
        diagnostics = getattr(self.gm, "last_llm_diagnostics", None)
        if diagnostics:
            self.store.save_turn_artifact(
                state.session_id,
                turn,
                "llm_diagnostics",
                diagnostics,
            )

    def _prepare_llm_attempt_diagnostics(self, state: WorldState, turn: int) -> None:
        if hasattr(self.gm, "llm_diagnostics_dir"):
            setattr(
                self.gm,
                "llm_diagnostics_dir",
                self.store.turn_dir(state.session_id, turn) / "llm_attempts",
            )


# ---------------------------------------------------------------------------
# helper
# ---------------------------------------------------------------------------


def _require_scene(
    phase1: GmPhaseResponse,
    state: WorldState,
    pack: WorldPack,
    player_text: str = "",
) -> FinalScene:
    scene = phase1.scene
    repaired, _repair_notes = repair_scene(state, pack, scene)
    report = _combine_reports(
        validate_scene(state, pack, repaired),
        validate_scene_player_agency(state, pack, repaired, player_text),
    )
    if not report.ok:
        raise GameMasterError(
            "Scena non valida: " + "; ".join(report.problems),
            diagnostics={"phase": "scene_validation", "problems": report.problems},
        )
    return repaired


def _validate_phase1_response(
    response: GmPhaseResponse,
    state: WorldState,
    pack: WorldPack,
    player_text: str = "",
):
    if response.mode == "no_check":
        if response.scene is None:
            return ["mode no_check senza scena"]
        return _combine_reports(
            validate_scene(state, pack, response.scene),
            validate_scene_player_agency(state, pack, response.scene, player_text),
        )
    if response.mode == "check_proposal":
        if response.check is None:
            return ["mode check_proposal senza check"]
        return _combine_reports(
            validate_check_proposal(state, pack, response.check),
            validate_check_proposal_player_agency(state, pack, response.check, player_text),
        )
    if response.mode == "confront_proposal":
        if response.confront is None:
            return ["mode confront_proposal senza confront"]
        return validate_confront_proposal(state, pack, response.confront)
    if response.mode == "clarification":
        if not response.clarification.strip():
            return ["mode clarification senza domanda"]
        return ValidationReport()
    return [f"mode non valido: {response.mode}"]


def _require_scene_obj(
    scene: FinalScene,
    state: WorldState,
    pack: WorldPack,
    store: StateStore,
    turn: int,
    player_text: str = "",
) -> None:
    report = _combine_reports(
        validate_scene(state, pack, scene),
        validate_scene_player_agency(state, pack, scene, player_text),
    )
    if not report.ok:
        store.save_turn_artifact(
            state.session_id,
            turn,
            "diagnostics",
            {"kind": "invalid_scene", "problems": report.problems},
        )
        raise SceneValidationError(
            "Scena finale non valida: " + "; ".join(report.problems),
            diagnostics={"phase": "scene_validation", "problems": report.problems},
        )


def _combine_reports(*reports: ValidationReport) -> ValidationReport:
    problems: list[str] = []
    errors = []
    warnings = []
    for report in reports:
        problems.extend(report.problems)
        errors.extend(report.errors)
        warnings.extend(report.warnings)
    return ValidationReport(problems, errors, warnings)
