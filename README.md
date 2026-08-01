# EPOS - Odissea Specularis

Gioco narrativo single player in italiano con input libero, LLM Game Master, GUI e immagini. Questa cartella e dedicata solo alla campagna **Odissea Specularis**.

Principio vincolante:

> LIA interpreta e narra; Python governa il mondo.

La LLM non tira dadi, non applica mutazioni, non salva stato e non decide fatti canonici persistenti. Ogni proposta LLM passa da contratto JSON, normalizzazione, validazione Python, risoluzione Python e commit persistente.

## Requisiti

- Python 3.12+
- Dipendenze runtime: `PyYAML`, `Pillow`
- GUI: `PySide6`
- Opzionale: endpoint LLM OpenAI-compatible
- Opzionale: renderer immagini `pending`, `comfy`, `a1111`, `novelai`

Installazione locale consigliata:

```powershell
cd /d D:\epos_odissea_specularis
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install -e .[gui]
```

## Avvio consigliato

```powershell
cd /d D:\epos_odissea_specularis
.\avvia_odissea.bat
```

Il launcher avvia:

```powershell
python tools\play_odyssey_gui.py --live
```

Modalita alternative:

```powershell
python tools\play_odyssey_gui.py          # GM demo offline
python tools\play_odyssey_gui.py --live   # GM live da .env
python tools\play_odyssey_gui.py --live --pack worlds\odyssey_specularis
```

Copia `.env.example` in `.env` e imposta almeno `EPOS_LLM_BASE_URL`, `EPOS_LLM_MODEL`, `EPOS_LLM_API_KEY` oppure `EPOS_LLM_KEY_ENV`.

## Campagna canonica

La sola campagna runtime e:

```text
worlds/odyssey_specularis/
```

I pack `demo_pack` e `acque_chiuse` sono sotto `tests/fixtures/` e servono solo per regression test del motore. Non sono campagne del nuovo progetto.

## Struttura essenziale

```text
src/epos/
  models.py                  stato canonico persistente
  contract.py                contratti JSON LLM -> runtime
  validators.py              validazione semantica
  rules.py                   dadi e risoluzione prove Python
  commit.py                  applicazione mutazioni validate
  turn_service.py            ciclo autorevole del turno
  prompt.py                  snapshot compatto e prompt phase 1/2
  llm.py                     provider chain e diagnostica LLM
  worldpack.py               loader dati Odissea
  odyssey_mission_tracker.py missioni data-driven
  visual.py                  visual contract autorevole
  visual_director.py         regia deterministica camera/posa
  renderers.py               adapter pending/ComfyUI/A1111/NovelAI
  application.py             facciata applicativa non-Qt per GUI
  gui.py                     GUI generica PySide6
  odyssey_gui.py             estensione GUI specifica Odissea
```

## Ciclo turno reale

```text
input libero
  -> fase 1 LLM: no_check | check_proposal | confront_proposal | clarification
  -> normalizzazione e validazione Python
  -> tiro/scelta sicura/confronto risolti da Python se serve
  -> checkpoint del risultato autorevole
  -> fase 2 LLM: narrazione dell'esito gia deciso
  -> validazione scena finale
  -> commit su copia dello stato
  -> salvataggio atomico dello stato
  -> visual contract autorevole
  -> rendering disaccoppiato e retryable
```

Il rendering non annulla mai il turno narrativo: se fallisce, resta un `render_record` retryable e il comando `Rerender` usa il `visual_contract` salvato senza richiamare il GM.

## Artefatti diagnostici per turno

Per ogni turno significativo il runtime salva sotto `saves/<session_id>/turns/<NNNN>/` gli artefatti disponibili, fra cui:

- `gm_snapshot_proposal.json`
- `gm_snapshot_final_scene.json`
- `gm_phase1.json`
- `scene.json`
- `visual_contract.json`
- `render_record.json`
- `outfit_diagnostics.json`
- `entity_id_diagnostics.json`
- `narrative_diagnostics.json`
- `player_agency_diagnostics.json`
- `llm_diagnostics.json`, quando il GM live lo produce
- `debug_turno.txt`

Questi file sono diagnostica e audit trail: lo stato autorevole resta `saves/<session_id>/state.json`.

## Criteri di accettazione coperti

- Input libero giocabile: `TurnService.play()` e GUI `EposGameWindow`.
- Autonomia giocatore: test in `tests/test_player_agency_regression.py`.
- NPC con iniziativa/memoria: test in `tests/test_npc_features.py`, `tests/test_thread_domain.py`, `tests/test_knowledge_provenance.py`.
- Prove risolte da Python: test in `tests/test_rules.py`, `tests/test_turn_service.py`.
- Stato non corrotto dopo errori: test strictness e checkpoint in `tests/test_turn_service.py`.
- Outfit, luogo, condizioni, conoscenze coerenti: test in `tests/test_outfit_continuity.py`, `tests/test_entity_id_normalization.py`, `tests/test_knowledge_provenance.py`.
- Missioni Odissea data-driven: test in `tests/test_odyssey_worldpack_missions.py`, `tests/test_odyssey_turn_service_campaign.py`.
- Diagnostica per turno: test in `tests/test_turn_service.py`, `tests/test_llm_diagnostics.py`.
- Rendering disaccoppiato: test in `tests/test_turn_service.py`, `tests/test_comfy_renderer.py`, `tests/test_a1111_renderer.py`.
- GUI separata dal dominio: facciata `epos.application.GameApplicationService`, test in `tests/test_application_service.py`, `tests/test_gui.py`.

## Verifica

```powershell
python -m pytest -q
```

Ultima verifica eseguita durante la migrazione finale:

```text
473 passed, 2 warnings
```

Le due warning note sono legacy in `tests/test_odyssey.py`: due test restituiscono valori invece di usare `assert`. Non bloccano la suite.

## Note operative

- I salvataggi legacy non sono compatibili e non devono esserlo.
- La directory originale `D:\gioco_k3_extract` resta intatta.
- Il progetto corrente vive in `D:\epos_odissea_specularis`.
