"""Fase 3: scenario deterministico breve di Odissea Specularis."""

from pathlib import Path

from epos.contract import CheckProposal, FinalScene, GmPhaseResponse, Mutation, VisualMoment
from epos.odyssey_mission_tracker import OdysseyMissionTracker
from epos.prompt import build_snapshot
from epos.state_store import StateStore
from epos.turn_service import PlayerDecision, TurnService
from epos.worldpack import load_pack

PACK = Path(__file__).resolve().parents[1] / "worlds" / "odyssey_specularis"


class OdysseyScenarioGM:
    """GM deterministico per verificare il ciclo reale senza provider esterni."""

    def propose(self, state, pack, player_text):
        if state.turn == 0:
            return GmPhaseResponse(
                mode="no_check",
                scene=FinalScene(
                    narration=(
                        "Ulisse si ferma sulla soglia della caverna. Polifemo respira "
                        "nel buio, e il suo nome resta una domanda pericolosa."
                    ),
                    mutations=[
                        Mutation(
                            type="thread_open",
                            target="world",
                            payload={
                                "thread_id": "thread_nome_polifemo",
                                "type": "question",
                                "participants": ["player", "polifemo"],
                                "summary": "Quale nome usera Ulisse davanti a Polifemo?",
                                "close_condition": "Ulisse pronuncia un nome falso davanti a Polifemo.",
                            },
                            reason="Il nome scelto davanti a Polifemo e una questione aperta.",
                        )
                    ],
                    visual=VisualMoment(
                        summary="Ulisse osserva la caverna",
                        focus_character="player",
                        visible_characters=["player"],
                        shared_action=False,
                        visual_en="a lone Greek heroine watching a volcanic cave entrance",
                        tags_en=["volcanic cave", "solitude"],
                    ),
                ),
            )
        if "nessuno" not in player_text.casefold():
            return GmPhaseResponse(
                mode="no_check",
                scene=FinalScene(
                    narration=(
                        "Il respiro di Polifemo muove il fumo. La domanda sul nome "
                        "resta sospesa mentre Ulisse studia ossa, latte acido e uscita."
                    ),
                    visual=VisualMoment(
                        summary="Ulisse conta le vie di fuga",
                        focus_character="player",
                        visible_characters=["player"],
                        shared_action=False,
                        visual_en="a lone Greek strategist studying bones and shadows in a cave",
                        tags_en=["cave interior", "strategy"],
                    ),
                ),
            )
        return GmPhaseResponse(
            mode="check_proposal",
            check=CheckProposal(
                action_kind="deception",
                skill="dolos",
                difficulty=3,
                target_ids=["polifemo"],
                opposition="npc_resistance",
                reason="Ulisse tenta l'inganno canonico del nome Nessuno davanti a Polifemo.",
                stakes={
                    "full_success": "Sblocca Isola di Eolo.",
                    "partial_success": "Sblocca Isola di Eolo.",
                    "failure": "Polifemo capisce la menzogna.",
                    "critical_failure": "Polifemo divora Ulisse.",
                },
            ),
        )

    def revise(self, state, pack, player_text, problems):
        raise AssertionError(problems)

    def narrate(self, state, pack, player_text, proposal, roll, stake, extras=None):
        return FinalScene(
            narration=(
                "Ulisse offre vino e dice di chiamarsi Nessuno. Polifemo ride, beve, "
                "crolla. La questione del nome si chiude nello stratagemma."
            ),
            mutations=[
                Mutation(
                    type="thread_close",
                    target="world",
                    payload={
                        "thread_id": "thread_nome_polifemo",
                        "reason": "Ulisse ha scelto e pronunciato il nome falso Nessuno.",
                    },
                    reason="Il nome falso e stato dichiarato in scena.",
                ),
                Mutation(
                    type="mission_complete",
                    target="loc_ciclopi",
                    payload={"completed_objectives": ["escape_polifemo"]},
                    reason="Polifemo e stata ingannata e la fuga verso Eolo e canonica.",
                ),
            ],
            visual=VisualMoment(
                summary="Ulisse fugge dalla caverna dopo l'inganno",
                focus_character="player",
                visible_characters=["player"],
                shared_action=False,
                visual_en="a lone Greek heroine escaping a volcanic cave after a deception",
                tags_en=["escape", "volcanic cave"],
            ),
        )


def _process_odyssey_turn(pack):
    def process(state, result):
        return OdysseyMissionTracker(state, pack=pack).process_turn(result)

    return process


def test_odyssey_deterministic_scenario_crosses_required_slice(tmp_path):
    pack = load_pack(PACK)
    store = StateStore(tmp_path / "saves")
    service = TurnService(
        gm=OdysseyScenarioGM(),
        pack=pack,
        store=store,
        decision_provider=lambda *_: PlayerDecision(choice="safe"),
        post_turn_processor=_process_odyssey_turn(pack),
    )
    state = service.new_session("odyssey-scenario")

    look = service.play(state, "Mi guardo intorno senza toccare nulla.")
    assert look.mode == "no_check"
    assert look.roll is None
    assert state.location_id == "loc_ciclopi"
    assert state.active_threads[0].id == "thread_nome_polifemo"
    assert state.active_threads[0].status == "open"
    assert look.visual_contract is not None
    assert look.visual_contract.visible_characters == ["player"]

    wait = service.play(state, "Resto immobile e ascolto il respiro di Polifemo.")
    assert wait.mode == "no_check"
    assert state.location_id == "loc_ciclopi"
    assert state.active_threads[0].status == "open"

    snapshot = build_snapshot(state, pack, "Ora scelgo quale nome dire.")
    assert snapshot["active_threads"] == [
        {
            "id": "thread_nome_polifemo",
            "type": "question",
            "summary": "Quale nome usera Ulisse davanti a Polifemo?",
            "participants": ["player", "polifemo"],
            "opened_turn": 0,
            "close_condition": "Ulisse pronuncia un nome falso davanti a Polifemo.",
        }
    ]

    escape = service.play(state, 'Offro vino a Polifemo e dico: "Mi chiamo Nessuno".')
    assert escape.mode == "check"
    assert escape.proposal.skill == "dolos"
    assert escape.roll is not None
    assert escape.campaign_changes["mission_completed"] is True
    assert escape.campaign_changes["location_changed"] is True
    assert state.location_id == "loc_eolo"
    assert state.flags["odyssey_kleos"] == 1
    assert state.active_threads[0].status == "closed"
    assert state.active_threads[0].closed_turn == 2
    assert "Nessuno" in state.active_threads[0].close_reason

    loaded = service.load_session(state.session_id)
    assert loaded.location_id == "loc_eolo"
    assert loaded.active_threads[0].status == "closed"
    assert loaded.flags["odyssey_kleos"] == 1

    scene_artifact = store.load_turn_artifact(state.session_id, 2, "scene")
    visual_artifact = store.load_turn_artifact(state.session_id, 2, "visual_contract")
    campaign_artifact = store.load_turn_artifact(state.session_id, 2, "campaign_changes")
    assert scene_artifact["mutations"][1]["type"] == "mission_complete"
    assert visual_artifact["visible_characters"] == ["player"]
    assert "cave" in visual_artifact["prompt_package"]["positive"]
    assert campaign_artifact["new_location"] == "loc_eolo"
    assert store.load_checkpoint(state.session_id) is None
