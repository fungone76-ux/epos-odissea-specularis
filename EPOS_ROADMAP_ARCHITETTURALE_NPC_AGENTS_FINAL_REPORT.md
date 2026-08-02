# EPOS Roadmap Architetturale NPC Agents - Final Report

Data chiusura: 2026-08-02

Branch: `agent/resort-world-design-v1`

HEAD verificato: `05074704e755a1c3132d75055907fd4d98d0ebbb`

Baseline iniziale Fase 14: `746 passed in 26.92s`

## 1. Obiettivo Del Programma

Il programma di fasi 0-14 ha trasformato il progetto in una architettura modulare, testata e compatibile, preparando gli NPC agentici senza cambiare il ciclo autorevole del turno.

Principio architetturale invariato:

```text
LIA interpreta e narra; Python governa il mondo.
```

## 2. Stato Iniziale E Finale

Stato iniziale Fase 14:

- repository locale pulito;
- branch corretto;
- HEAD locale e remoto allineati;
- nessun commit left-right;
- suite iniziale verde: `746 passed`;
- `compileall src tools tests` verde;
- import headless `epos`, `epos.llm`, `epos.validators` verde;
- `PySide6` non caricato in import headless.

Stato finale:

- nessuna ottimizzazione runtime applicata;
- report finale creato;
- roadmap aggiornata solo con blocco di chiusura;
- nessuna modifica a gameplay, prompt, provider, retry, fallback, checkpoint, RNG, state.json, TurnService, validators o llm runtime.

## 3. Matrice Fasi 0-14

| Fase | Obiettivo | Commit riferimento | Baseline fase | Stato | Debito residuo |
|---|---|---:|---:|---|---|
| 0 | Baseline, inventario e CI | storico precedente | n/d | completata | nessuno critico rilevato |
| 1 | Modularizzazione visual.py | `e1d9664`, `bec2917` | n/d | completata | `visual.py` resta facade ampia |
| 2 | Modularizzazione renderers.py | `66ff1e0` | n/d | completata | provider renderer reali restano isolati |
| 3 | Modularizzazione prompt.py | `63bca46` | n/d | completata | prompt statici invariati |
| 4 | Context Selector deterministico | `66ed25b` | 614 passed | completata | flag default false |
| 5 | Modularizzazione prudente turn_service.py | `75018d8` | 622 passed | completata | checkpoint/resolution completa non ulteriormente estratti |
| 6 | Modello agente NPC V1 | `cdf01d9` | 640 passed | completata | runtime non collegato |
| 7 | Memoria breve NPC | `337aa02` | 656 passed | completata | solo eventi osservati, persistence companion opzionale |
| 8 | Memoria lunga NPC | `a0583d2` | 682 passed | completata | retrieval non attivo nel runtime |
| 9 | Retrieval deterministico | `a9f75b5` | 699 passed | completata | integrazione Context Selector deferred |
| 10 | Coordinator NPC passivo | `08224ac` | 709 passed | completata | integrazione runtime deferred |
| 11 | Chiamata NPC opzionale isolata | `e16933c` | 735 passed | completata | flag default false, nessun provider reale nuovo |
| 12 | Modularizzazione validators.py | `81393e5` | 740 passed | completata | facade preservata |
| 13 | Modularizzazione prudente llm.py | `0507470` | 746 passed | completata | provider reali non ampliati |
| 14 | Misurazione finale e chiusura | non ancora committata | 746 passed iniziale | completata se validazioni finali verdi | nessuna ottimizzazione runtime applicata |

## 4. Architettura Finale

Facade principali:

- `src/epos/visual.py`: facade visuale e contratti visuali.
- `src/epos/renderers.py`: facade backend renderer.
- `src/epos/prompt.py`: facade prompt.
- `src/epos/turn_service.py`: facade e orchestratore del turno.
- `src/epos/validators.py`: facade validatori.
- `src/epos/llm.py`: facade provider chain.

Moduli principali:

- Prompt/context: `prompt_snapshot.py`, `prompt_phase1.py`, `prompt_phase2.py`, `context_budget.py`, `context_selector.py`, `context_diagnostics.py`.
- Turn service: `turn_types.py`, `turn_resolution.py`, `turn_diagnostics.py`.
- Validators: `validator_common.py`, `validator_mutations.py`, `validator_proposals.py`, `validator_scene.py`, `validator_scene_visual.py`.
- LLM: `llm_contracts.py`, `llm_errors.py`, `llm_parsing.py`, `llm_retry.py`, `llm_diagnostics.py`.
- NPC agents: `npc_agent_models.py`, `npc_agent_registry.py`, `npc_agent_selector.py`, `npc_agent_context.py`, `npc_agent_coordinator.py`, `npc_agent_coordinator_diagnostics.py`, `npc_agent_persistence.py`.
- NPC memory: `npc_memory_short.py`, `npc_memory_policy.py`, `npc_memory_long.py`, `npc_memory_long_policy.py`, `npc_memory_promotion.py`, `npc_memory_retrieval.py`, `npc_memory_retrieval_policy.py`, `npc_memory_retrieval_diagnostics.py`.
- Optional NPC LLM: `npc_agent_llm_contract.py`, `npc_agent_llm_runner.py`, `npc_agent_llm_validator.py`, `npc_agent_llm_diagnostics.py`.

Runtime attivo:

- TurnService legacy;
- prompt phase1/phase2 legacy;
- validatori Python;
- commit atomico;
- checkpoint/recovery;
- renderer non bloccante;
- provider chain principale.

Runtime isolato o feature-flagged:

- Context Selector: disponibile via `EPOS_CONTEXT_SELECTOR_ENABLED`, default false.
- NPC Agent model/registry/selector/memorie/retrieval/coordinator: isolati, non invocati da TurnService.
- Optional NPC LLM: disponibile tramite runner isolato, flag `EPOS_NPC_DEDICATED_LLM_ENABLED`, default false.

Deferred:

- integrazione runtime del coordinator;
- inserimento memorie NPC nei prompt di turno;
- uso della optional NPC LLM nel ciclo gioco;
- qualsiasi ulteriore fase post-roadmap.

## 5. Misure Prompt E Snapshot

Metriche locali riproducibili, nessuna richiesta reale inviata.

| Scenario | Snapshot chars | Snapshot bytes | Est. tokens | Phase1 chars | Phase2 chars | Snapshot ms | Phase1 ms | Phase2 ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| turno_minimo | 12423 | 12474 | 3106 | 36176 | 35468 | 0.545 | 0.726 | 0.575 |
| turno_medio | 12649 | 12700 | 3163 | 36502 | 35794 | 0.157 | 0.596 | 0.597 |
| stato_grande_multi_npc | 30042 | 30140 | 7511 | 60531 | 59823 | 0.432 | 1.267 | 1.505 |

Conteggi snapshot:

- turno minimo: 20 sezioni, 10 NPC totali, 1 NPC presente, 0 thread, 2 missioni selezionate, 30 knowledge entries.
- turno medio: 20 sezioni, 10 NPC totali, 1 NPC presente, 1 thread, 2 missioni selezionate, 30 knowledge entries.
- stato grande: 20 sezioni, 10 NPC totali, 10 NPC presenti, 10 thread, 2 missioni selezionate, 90 knowledge entries.

## 6. Misure Context Selector

| Scenario | Chars prima | Chars dopo | Tokens prima | Tokens dopo | Riduzione | Inclusi | Esclusi | Tempo ms |
|---|---:|---:|---:|---:|---:|---|---|---:|
| piccolo | 15226 | 13344 | 3807 | 3336 | 12.36% | polifemo | nessuno | 1.466 |
| medio | 15512 | 13630 | 3878 | 3408 | 12.13% | polifemo | nessuno | 0.943 |
| grande | 37146 | 19041 | 9287 | 4761 | 48.74% | penelope, polifemo, circe | 7 NPC | 1.271 |

Determinismo: misure ripetute sullo stesso input hanno restituito stesso set di inclusi/esclusi e stessi reason key.

Legacy: con flag disattivato la suite dedicata mantiene comportamento legacy invariato.

## 7. Misure NPC Pipeline

Policy retrieval usata: short limit 4, long limit 3.

| Scenario | Candidati | Selezionati | Short selezionate | Long selezionate | Context chars | Est. tokens | Coordinator ms |
|---|---:|---|---:|---:|---:|---:|---:|
| registry_vuoto | 0 | nessuno | 0 | 0 | 170 | 43 | 0.011 |
| un_npc | 10 | penelope | 4 | 3 | 4738 | 1185 | 0.261 |
| tre_npc | 10 | penelope, polifemo, circe | 12 | 9 | 11985 | 2997 | 0.644 |
| molti_npc | 10 | penelope, polifemo, circe, calipso, tiresia, atena | 16 | 12 | 17137 | 4285 | 0.931 |
| budget_limitato | 10 | penelope, polifemo | 8 | 6 | 8471 | 2118 | 0.445 |

Reason codes osservati: `active_mission`, `actor`, `mentioned`, `next_evaluation_due`, `open_thread`, `over_budget`, `present`, `reactor`, `speaker`.

Retrieval per NPC:

| NPC | Short prima | Short dopo | Long prima | Long dopo | Escluse | Reason | Tempo ms |
|---|---:|---:|---:|---:|---:|---|---:|
| polifemo | 7 | 4 | 5 | 3 | 5 | over_budget | 0.172 |
| circe | 7 | 4 | 5 | 3 | 5 | over_budget | 0.170 |

## 8. Misure Provider Chain

Misure con opener finto, nessuna rete.

| Scenario | Stato | Call count | Ordine | Attempt statuses | Fallback | Reason | Tempo ms |
|---|---|---:|---|---|---|---|---:|
| success_first | success | 1 | primary | success | false | vuoto | 0.245 |
| success_after_retry | success | 2 | primary, primary | timeout, success | false | vuoto | 0.079 |
| success_fallback | success | 3 | primary, primary, secondary | timeout, timeout, success | true | primary_timeout | 0.078 |
| all_failed | dns_error | 3 | primary, primary, secondary | timeout, timeout, dns_error | true | primary_timeout | 0.056 |
| invalid_response | invalid_json | 3 | primary, primary, secondary | invalid_json x3 | true | primary_invalid_json | 0.087 |
| empty_response | invalid_json | 3 | primary, primary, secondary | invalid_json x3 | true | primary_invalid_json | 0.070 |

Provider order verificato: primary prima, secondary solo dopo fallimento primary. Retry e fallback invariati.

## 9. Misure Optional NPC LLM

Fake provider, runner isolato, nessuna integrazione runtime.

| Scenario | Status | Reason | Call count | Agenti inclusi | Esclusi budget | Proposals | Payload chars | Est. tokens | Tempo ms |
|---|---|---|---:|---|---|---:|---:|---:|---:|
| flag_false | skipped | disabled | 0 | nessuno | nessuno | 0 | 0 | 0 | 0.013 |
| budget_zero | skipped | budget_exhausted | 0 | nessuno | nessuno | 0 | 0 | 0 | 0.005 |
| valid | success | success | 1 | penelope, polifemo, circe | calipso | 1 | 9994 | 2499 | 0.058 |
| forbidden_field | fallback | forbidden_field | 1 | penelope, polifemo, circe | calipso | 0 | 9994 | 2499 | 0.043 |
| provider_error | fallback | provider_error | 1 | penelope, polifemo, circe | calipso | 0 | 9994 | 2499 | 0.031 |

Vincolo massimo chiamate: rispettato, massimo una chiamata logica nei casi enabled con agenti e budget > 0.

## 10. Feature Flag

| Flag | Default | True values | False values | Modulo | Runtime |
|---|---|---|---|---|---|
| `EPOS_CONTEXT_SELECTOR_ENABLED` | false | true, 1, yes, on | false, 0, no, off, stringa vuota | `context_selector.py` | opzionale, legacy off |
| `EPOS_NPC_DEDICATED_LLM_ENABLED` | false | true, 1, yes, on | false, 0, no, off, stringa vuota | `npc_agent_llm_runner.py` | isolato, non collegato a TurnService |

Altri flag esistenti sono renderer/prompt/provider legacy e non sono stati modificati.

## 11. Persistence

Verifica architetturale:

- `state.json`: invariato;
- checkpoint: invariato;
- `npc_agents.json`: companion opzionale;
- file companion mancante: caricato come registry vuoto;
- short memories: round-trip tramite registry;
- long memories: round-trip tramite registry;
- nessuna migrazione obbligatoria;
- nessuna scrittura runtime nuova in Fase 14.

## 12. TODO, File Residui E Import

Ricerca `TODO|FIXME|HACK|monkey.patch|sys.path|EPOS_NPC|EPOS_CONTEXT_SELECTOR`:

- `sys.path.insert` in tool CLI e test legacy: valido, usato per runner locali.
- `EPOS_CONTEXT_SELECTOR_ENABLED` in codice e test: valido.
- `EPOS_NPC_DEDICATED_LLM_ENABLED` in codice e test: valido.
- Nessun `TODO`, `FIXME`, `HACK` critico nei risultati raccolti.

Ricerca file residui `patch|backup|old|copy|tmp|temp`:

- `tests/test_runtime_patch_removal.py`: valido, test dedicato alla rimozione patch runtime.
- Nessun file runtime patch/backup/tmp rilevato in `src`, `tests`, `tools`.

## 13. Ottimizzazioni

Decisione: nessuna ottimizzazione runtime applicata.

Motivazione misurata:

- snapshot/prompt build sotto 2 ms negli scenari locali misurati;
- context selector sotto 1.5 ms negli scenari misurati;
- coordinator sotto 1 ms anche con 10 candidati e memorie;
- retrieval per NPC circa 0.17 ms;
- provider chain fake dominata da simulazione locale, senza collo di bottiglia CPU.

Ottimizzazioni candidate rifiutate:

- cache globale di snapshot: vietata e non necessaria;
- token budget globale NPC: nuova architettura non richiesta;
- integrazione Context Selector/NPC nel runtime: deferred e fuori scopo;
- riduzione arbitraria di campi prompt: cambierebbe comportamento/qualita narrativa.

## 14. Rischi Residui E Debito Tecnico

- `turn_service.py` resta grande: ulteriore estrazione checkpoint/resolution completa e' stata giudicata rischiosa nella Fase 5 conclusiva.
- `visual.py` resta ampio come facade con logica storica: protetto da test, ma da non modificare senza golden.
- Context Selector e pipeline NPC sono implementati ma non collegati al runtime TurnService.
- Optional NPC LLM e' isolato e flaggato; qualsiasi attivazione runtime richiederebbe nuova fase/progetto dedicato.
- La stima token e' euristica locale `ceil(chars / 4)`, non misura API reale.

## 15. Raccomandazioni Operative

- Non attivare flag sperimentali in produzione senza golden su prompt e turno completo.
- Prima di ogni futura integrazione runtime, misurare numero chiamate LLM, dimensione prompt, ordine retry e fallback.
- Conservare la facade pubblica per `turn_service`, `validators`, `llm`, `prompt`, `visual`, `renderers`.
- Non introdurre provider, modelli, endpoint o env var senza test fake-provider e diff contrattuale.
- Non promuovere memorie o contesti NPC a input autorevole: Python deve restare il solo governo dello stato.

## 16. Stato Roadmap

La roadmap architetturale NPC Agents V1 e' chiusa sul piano implementativo locale quando le validazioni finali della Fase 14 restano verdi.

Baseline finale attesa: `746 passed`.

Commit finale: non ancora creato, come richiesto.
