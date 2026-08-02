# EPOS / Odissea Specularis â€” Roadmap Architetturale e NPC Agent Runtime

**Repository:** `fungone76-ux/epos-odissea-specularis`
**Branch di lavoro:** `agent/resort-world-design-v1`
**Cartella locale:** `D:\epos_odissea_specularis`
**Baseline corrente:** `578 passed`
**Principio architetturale inviolabile:**

> **Lâ€™IA interpreta e narra; Python governa il mondo.**

---

# 1. Obiettivo generale

Questa roadmap definisce il percorso per:

1. ridurre la complessitÃ  dei file Python piÃ¹ grandi;
2. separare responsabilitÃ  senza cambiare il comportamento del gioco;
3. rendere i prompt piÃ¹ modulari e piÃ¹ economici in termini di token;
4. introdurre agenti NPC separati ma coordinati;
5. dotare ogni NPC di memoria breve e lunga;
6. mantenere una sola chiamata LLM nella maggior parte dei turni;
7. preservare validazione, commit atomico, checkpoint, player agency e canone.

La roadmap non prevede una riscrittura totale del progetto.

Il metodo richiesto Ã¨ sempre:

```text
audit
â†’ baseline
â†’ modifica piccola
â†’ test mirati
â†’ suite completa
â†’ commit
â†’ push
â†’ nuova baseline
```

---

# 2. Stato architetturale giÃ  raggiunto

Sono giÃ  stati completati questi interventi:

- `epos/__init__.py` privo di effetti collaterali;
- import headless senza caricamento di PySide6;
- bootstrap Resort espliciti;
- eliminazione dei monkey-patch runtime Resort;
- eliminazione dei file `*_patch.py` Resort;
- gestione canonica della presenza NPC;
- gestione canonica degli intent Resort;
- integrazione diretta del tempo manuale nella GUI;
- normalizzazione canonica del placeholder `npc_id`;
- nomi display-facing mantenuti leggibili;
- ID machine-facing normalizzati;
- vocabolari outfit canonici e immutabili;
- gestione outfit hosiery corretta tramite `outfit_state`;
- rimozione del bootstrap globale Resort da `tests/conftest.py`;
- suite completa verificata a `578 passed`.

Questa baseline deve essere considerata il punto di partenza ufficiale.

---

# 3. Principi da non violare

## 3.1 Python governa

La LLM non deve:

- tirare dadi;
- modificare direttamente lo stato;
- decidere esiti autorevoli;
- inventare conoscenze;
- modificare relazioni senza validazione;
- applicare mutazioni;
- decidere chi Ã¨ presente;
- scrivere direttamente nei salvataggi.

La LLM puÃ²:

- interpretare input libero;
- proporre intenzioni;
- proporre dialoghi;
- proporre scene;
- narrare esiti giÃ  decisi;
- proporre azioni soggette a validazione.

## 3.2 CompatibilitÃ

Durante ogni rifattorizzazione devono restare compatibili:

- API pubbliche;
- contratti JSON;
- struttura dei salvataggi;
- output visuali;
- ordine dei tag;
- prompt finali, salvo fase specifica di ottimizzazione;
- checkpoint;
- commit atomico;
- diagnostica;
- player agency;
- regole di presenza, conoscenza e outfit.

## 3.3 ModularitÃ  incrementale

Ãˆ vietato:

- riscrivere grandi moduli in un solo passaggio;
- cambiare comportamento e struttura insieme;
- spostare codice senza test;
- introdurre framework pesanti solo per â€œmodernizzareâ€;
- aggiungere agenti NPC con una chiamata LLM per personaggio a ogni turno.

---

# 4. Sequenza completa delle fasi

## FASE 0 â€” Baseline, allineamento e inventario

### 0A. Verifica locale e remoto

```powershell
git status --short
git branch --show-current
git log -5 --oneline
git remote -v
git fetch origin
git status -sb
git rev-parse HEAD
git rev-parse origin/agent/resort-world-design-v1
git log --oneline --left-right --graph HEAD...origin/agent/resort-world-design-v1
```

Verificare:

- branch corretto;
- working tree pulito;
- locale allineato al remoto;
- ultimi commit presenti;
- vecchi patch assenti;
- nuovi moduli canonici presenti.

### 0B. Baseline tecnica

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall src tools tests
.\.venv\Scripts\python.exe -c "import sys; import epos; import epos.visual; assert 'PySide6' not in sys.modules"
```

Baseline attesa:

```text
578 passed
```

### 0C. Inventario dei monoliti

Misurare e classificare:

- `visual.py`
- `turn_service.py`
- `prompt.py`
- `renderers.py`
- `validators.py`
- `llm.py`
- `gui.py`
- `odyssey_mission_tracker.py`

Produrre per ogni file:

- righe;
- responsabilitÃ ;
- simboli pubblici;
- simboli privati rilevanti;
- dipendenze;
- test collegati;
- rischio di estrazione;
- ordine consigliato.

### 0D. CI minima

Aggiungere o verificare `.github/workflows/ci.yml` con:

- Python 3.12;
- installazione progetto;
- installazione dipendenze test;
- `pytest -q`;
- `python -m compileall src tools tests`.

Ruff va aggiunto solo se sostenibile senza rendere rossa la CI per debito tecnico preesistente.

### Criteri di chiusura Fase 0

- locale e remoto allineati;
- working tree pulito prima delle modifiche;
- suite verde;
- compileall verde;
- import headless verde;
- inventario completato;
- CI minima presente.

---

## FASE 1 â€” Suddivisione di `visual.py`

### Obiettivo

Ridurre la responsabilitÃ  di `visual.py` senza cambiare il comportamento visuale.

### Struttura orientativa

```text
src/epos/
â”œâ”€â”€ visual.py
â”œâ”€â”€ visual_policy.py
â”œâ”€â”€ visual_sanitizer.py
â”œâ”€â”€ visual_subjects.py
â”œâ”€â”€ visual_composition.py
â””â”€â”€ visual_prompt_builder.py
```

Non Ã¨ obbligatorio creare tutti i file subito.

### Ordine di estrazione

1. sanitizzazione pura;
2. deduplicazione e normalizzazione tag;
3. gestione soggetti e identitÃ ;
4. composizione multi-character;
5. compilazione del prompt finale;
6. policy e configurazione.

### ResponsabilitÃ

- `visual_sanitizer.py`: pulizia stringhe, deduplicazione, normalizzazione tag e layer;
- `visual_subjects.py`: soggetti, identitÃ , outfit, LoRA, speaker/actor/reactor;
- `visual_composition.py`: multi-character, camera, framing, pose e gerarchia visiva;
- `visual_prompt_builder.py`: assemblaggio finale del prompt;
- `visual_policy.py`: limiti, policy worldpack e regole applicabili;
- `visual.py`: facciata pubblica con re-export espliciti.

### Test obbligatori

- singolo personaggio;
- speaker focus;
- actor/reactor;
- multi-character;
- outfit completo;
- outfit rimosso;
- nudity mode;
- deduplicazione;
- ordine layer;
- identitÃ ;
- LoRA;
- location;
- camera;
- framing;
- prompt finale;
- nomi display-facing;
- ID machine-facing.

### Criteri di chiusura Fase 1

- API pubbliche compatibili;
- output golden invariati;
- nessun import circolare;
- test visuali verdi;
- test renderer correlati verdi;
- suite completa verde;
- `visual.py` ridotto senza wrapper inutili.

---

## FASE 2 â€” Suddivisione di `renderers.py`

### Struttura prevista

```text
src/epos/renderers/
â”œâ”€â”€ __init__.py
â”œâ”€â”€ base.py
â”œâ”€â”€ pending.py
â”œâ”€â”€ comfyui.py
â”œâ”€â”€ a1111.py
â”œâ”€â”€ novelai.py
â””â”€â”€ diagnostics.py
```

### Criteri di chiusura

- API pubblica compatibile;
- selezione renderer invariata;
- fallimento rendering non blocca il turno;
- test mock per backend;
- suite completa verde.

---

## FASE 3 â€” Suddivisione di `prompt.py`

### Struttura prevista

```text
src/epos/
â”œâ”€â”€ prompt.py
â”œâ”€â”€ prompt_snapshot.py
â”œâ”€â”€ prompt_phase1.py
â”œâ”€â”€ prompt_phase2.py
â”œâ”€â”€ prompt_rules.py
â”œâ”€â”€ prompt_context_selector.py
â””â”€â”€ prompt_budget.py
```

### Criteri di chiusura

- prompt modulari;
- API compatibile;
- output invariato prima dellâ€™ottimizzazione;
- test snapshot;
- test fase 1 e fase 2;
- suite completa verde.

---

## FASE 4 â€” Context Selector e riduzione token V1

### Obiettivo

Evitare di inviare tutto il mondo alla LLM a ogni turno.

### Selezione deterministica

Python seleziona:

- NPC presenti;
- NPC nominati;
- NPC coinvolti in thread;
- NPC influenzati da azioni;
- NPC con iniziativa urgente;
- location corrente;
- missioni pertinenti;
- outfit dei soli soggetti visibili;
- memorie brevi rilevanti;
- memorie lunghe pertinenti;
- regole applicabili al turno.

### Budget iniziale

```python
ContextBudget(
    max_active_npcs=3,
    max_short_memories_per_npc=4,
    max_long_memories_per_npc=3,
    max_threads_per_npc=3,
    max_relevant_missions=2,
    max_recent_events=6,
)
```

### Diagnostica

```json
{
  "included_npcs": ["luna", "maria"],
  "excluded_npcs": ["stella", "victoria"],
  "included_memories": 5,
  "included_threads": 2,
  "estimated_tokens_before": 8200,
  "estimated_tokens_after": 4100,
  "reasons": {
    "luna": ["present", "mentioned"],
    "maria": ["open_thread"]
  }
}
```

### Criteri di chiusura Fase 4

- riduzione token misurabile;
- nessuna informazione canonica necessaria esclusa;
- diagnostica completa;
- test di inclusione/esclusione;
- suite completa verde.

---

## FASE 5 â€” Suddivisione di `turn_service.py`

### Struttura prevista

```text
src/epos/
â”œâ”€â”€ turn_service.py
â”œâ”€â”€ turn_phase1.py
â”œâ”€â”€ turn_resolution.py
â”œâ”€â”€ turn_checkpoint.py
â”œâ”€â”€ turn_phase2.py
â”œâ”€â”€ turn_commit_flow.py
â””â”€â”€ turn_diagnostics.py
```

### Criteri di chiusura

- API pubblica invariata;
- nessun doppio tiro;
- checkpoint recuperabile;
- commit atomico;
- rendering disaccoppiato;
- suite completa verde.

---

## FASE 6 â€” Modello agente NPC V1

### Obiettivo

Rappresentare ogni NPC come agente logico separato, senza aggiungere chiamate LLM per personaggio.

### Struttura prevista

```text
src/epos/npc_agents/
â”œâ”€â”€ __init__.py
â”œâ”€â”€ models.py
â”œâ”€â”€ selector.py
â”œâ”€â”€ coordinator.py
â”œâ”€â”€ context.py
â”œâ”€â”€ memory_short.py
â”œâ”€â”€ memory_long.py
â”œâ”€â”€ initiative.py
â””â”€â”€ persistence.py
```

### Stato agente

Ogni NPC deve avere:

```text
identitÃ
personalitÃ  sintetica
obiettivi
intenzione corrente
emozioni
relazioni
conoscenze
thread aperti
memoria breve
memoria lunga
prioritÃ  dâ€™iniziativa
next_evaluation_turn
```

### Esempio

```json
{
  "npc_id": "luna",
  "persona_summary": "curiosa, prudente, sensibile alla fiducia",
  "current_goal": "capire se il giocatore Ã¨ sincero",
  "current_intention": "fare una domanda indiretta",
  "emotion": "sospettosa ma interessata",
  "next_evaluation_turn": 44
}
```

### Criteri di chiusura Fase 6

- nessuna chiamata LLM aggiuntiva;
- stato agente separato;
- isolamento conoscenze;
- persistenza;
- test per NPC distinti;
- suite completa verde.

---

## FASE 7 â€” Memoria breve NPC

### Tipi di memoria breve

- ultima battuta rilevante;
- domanda aperta;
- promessa recente;
- offesa;
- emozione;
- azione osservata;
- cambio outfit;
- presenza;
- iniziativa tentata;
- richiesta non risolta.

### Struttura

```json
{
  "npc_id": "luna",
  "short_term": [
    {
      "turn": 42,
      "type": "unanswered_question",
      "summary": "Il giocatore non ha risposto alla domanda sulla lettera.",
      "source_event_id": "event_42_03",
      "importance": 0.62
    }
  ]
}
```

### Politica

```text
massimo 8â€“12 eventi rilevanti
deduplicazione
decadimento
compattazione
nessuna memoria da evento non osservato
```

### Criteri di chiusura Fase 7

- memoria aggiornata solo da eventi osservabili;
- isolamento tra NPC;
- limite dimensione;
- compattazione;
- test decadimento;
- persistenza;
- suite verde.

---

## FASE 8 â€” Memoria lunga NPC

### Tipi

```text
promise
betrayal
trust_event
fear_event
relationship_milestone
secret
debt
trauma
mission_event
preference
major_decision
```

### Struttura

```json
{
  "id": "memory_luna_0018",
  "npc_id": "luna",
  "type": "promise",
  "summary": "Il giocatore ha promesso di proteggere il suo segreto.",
  "turn": 18,
  "importance": 0.92,
  "tags": ["secret", "trust"],
  "source_event_id": "event_18_04",
  "status": "active"
}
```

### Regola

Python decide la promozione da memoria breve a memoria lunga. La LLM non puÃ² creare autonomamente una memoria lunga canonica.

### Criteri di chiusura Fase 8

- memoria persistente;
- origine verificabile;
- nessuna memoria inventata;
- promozione governata da Python;
- test serializzazione;
- suite verde.

---

## FASE 9 â€” Retrieval memoria deterministico

### Punteggio

```text
rilevanza argomento
+ importanza
+ recenza
+ thread collegato
+ relazione coinvolta
+ location
+ missione
```

### Limiti

```text
massimo 4 memorie brevi per NPC
massimo 3 memorie lunghe per NPC
massimo 3 thread aperti per NPC
```

### Diagnostica

```json
{
  "memory_id": "memory_luna_0018",
  "score": 0.87,
  "reasons": ["topic_match", "high_importance", "open_thread"]
}
```

### Criteri di chiusura Fase 9

- retrieval deterministico;
- spiegabilitÃ ;
- riduzione token;
- nessun vector DB necessario;
- test selezione;
- suite verde.

---

## FASE 10 â€” Coordinatore agenti NPC

### Obiettivo

Costruire una singola rappresentazione multi-agente per una sola chiamata LLM.

### Input LLM

```json
{
  "active_agents": [
    {
      "id": "luna",
      "goal": "capire se il giocatore Ã¨ sincero",
      "emotion": "sospettosa",
      "short_memory": [],
      "long_memory": [],
      "open_threads": []
    },
    {
      "id": "maria",
      "goal": "evitare un conflitto",
      "emotion": "preoccupata",
      "short_memory": [],
      "long_memory": [],
      "open_threads": []
    }
  ]
}
```

### Output LLM proposto

```json
{
  "npc_decisions": [
    {
      "npc_id": "luna",
      "proposed_intention": "porre una domanda indiretta",
      "proposed_action": "osserva la reazione del giocatore",
      "dialogue": "..."
    }
  ]
}
```

### Validazione Python

Python verifica:

- presenza;
- conoscenza;
- autonomia;
- intenzione;
- relazione;
- azione possibile;
- compatibilitÃ  missione;
- mutazioni;
- conflitti tra NPC.

### Criteri di chiusura Fase 10

- una sola chiamata LLM;
- agenti logicamente separati;
- nessuna contaminazione conoscenze;
- prioritÃ  deterministiche;
- NPC non rilevanti esclusi;
- suite verde.

---

## FASE 11 â€” Chiamate NPC dedicate opzionali

### Casi ammessi

- conflitto importante;
- decisione irreversibile;
- evento personale fuori scena;
- riflessione privata;
- svolta missione personale;
- soglia emotiva critica.

### Limiti

```text
massimo 1 chiamata NPC dedicata per turno
disattivata di default
budget separato
risultato sempre validato da Python
```

### Configurazione

```text
EPOS_NPC_DEDICATED_CALLS_ENABLED=false
EPOS_NPC_DEDICATED_CALLS_MAX_PER_TURN=1
```

### Criteri di chiusura Fase 11

- nessun aumento incontrollato costi;
- chiamate tracciate;
- budget misurato;
- fallback a coordinatore unico;
- suite verde.

---

## FASE 12 â€” Suddivisione di `validators.py`

```text
src/epos/validators/
â”œâ”€â”€ __init__.py
â”œâ”€â”€ scene.py
â”œâ”€â”€ outfit.py
â”œâ”€â”€ mutations.py
â”œâ”€â”€ dialogue.py
â”œâ”€â”€ memory.py
â”œâ”€â”€ knowledge.py
â””â”€â”€ resort.py
```

### Criteri di chiusura

- API compatibile;
- error code invariati;
- messaggi retry invariati;
- test validator completi;
- suite verde.

---

## FASE 13 â€” Suddivisione di `llm.py`

```text
src/epos/llm/
â”œâ”€â”€ __init__.py
â”œâ”€â”€ base.py
â”œâ”€â”€ providers.py
â”œâ”€â”€ fallback.py
â”œâ”€â”€ retries.py
â”œâ”€â”€ diagnostics.py
â””â”€â”€ token_usage.py
```

### Criteri di chiusura

- provider compatibili;
- fallback invariato;
- nessuna nuova dipendenza obbligatoria;
- metriche token disponibili;
- suite verde.

---

## FASE 14 â€” Ottimizzazione misurata

### Metriche per turno

- token fase 1;
- token fase 2;
- costo stimato;
- latenza;
- retry;
- NPC inclusi;
- memorie incluse;
- thread inclusi;
- dimensione snapshot;
- prompt prima/dopo;
- violazioni di conoscenza;
- errori visuali;
- errori validazione.

### Esempio diagnostico

```json
{
  "turn": 52,
  "phase1_tokens": 3120,
  "phase2_tokens": 1840,
  "total_tokens": 4960,
  "baseline_estimate": 9100,
  "reduction_percent": 45.49,
  "active_npcs": ["luna"],
  "short_memories": 3,
  "long_memories": 2
}
```

### Criteri di chiusura Fase 14

- riduzione token reale;
- nessuna perdita di coerenza;
- costi misurabili;
- latenza misurabile;
- prompt piÃ¹ piccoli;
- qualitÃ  narrativa verificata.

---

# 5. Ordine operativo definitivo

```text
0. Baseline, allineamento, inventario e CI
1. visual.py
2. renderers.py
3. prompt.py
4. Context Selector e token budget
5. turn_service.py
6. NPC Agent State
7. Memoria breve
8. Memoria lunga
9. Retrieval deterministico
10. Coordinatore NPC
11. Chiamate dedicate opzionali
12. validators.py
13. llm.py
14. Ottimizzazione finale
```

---

# 6. Strategia agenti NPC

Non usare:

```text
1 chiamata LLM per ogni NPC a ogni turno
```

Usare invece:

```text
Python seleziona NPC attivi
â†’ Python costruisce contesti separati
â†’ una sola chiamata LLM multi-agente
â†’ Python valida ogni decisione NPC
```

Vantaggi:

- memoria separata;
- obiettivi distinti;
- emozioni distinte;
- conoscenze isolate;
- meno token;
- meno costi;
- meno contraddizioni;
- controllo canonico;
- diagnostica piÃ¹ chiara.

---

# 7. Strategia memoria NPC

## Memoria breve

Serve per eventi recenti, domande, tensioni, promesse, outfit, presenza e iniziative.

## Memoria lunga

Serve per segreti, tradimenti, fiducia, traumi, debiti, traguardi relazionali ed eventi missione.

## Regola fondamentale

La LLM puÃ² proporre un ricordo, ma Python deve:

- verificare lâ€™evento;
- verificarne lâ€™osservabilitÃ ;
- classificarlo;
- assegnare importanza;
- decidere se persisterlo;
- controllarne la promozione.

---

# 8. Strategia token

Riduzioni principali:

- inviare solo NPC attivi;
- limitare memorie;
- limitare thread;
- limitare missioni;
- includere solo location corrente;
- includere solo outfit visibili;
- includere solo regole applicabili;
- separare prompt fase 1 e fase 2;
- evitare ripetizioni;
- deduplicare istruzioni.

---

# 9. Regole di test per ogni fase

Ogni fase deve includere:

1. test baseline;
2. test mirati;
3. test regressione;
4. suite completa;
5. compileall;
6. import headless;
7. `git diff --check`;
8. verifica working tree;
9. rapporto finale;
10. nessun commit prima della verifica.

Comandi standard:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall src tools tests
.\.venv\Scripts\python.exe -c "import sys; import epos; assert 'PySide6' not in sys.modules"
git diff --check
git status --short
git diff --stat
```

---

# 10. Criteri di accettazione finali

- [ ] tutti i test passano;
- [ ] nessun monkey-patch;
- [ ] nessun side effect allâ€™import;
- [ ] PySide6 non entra nel runtime headless;
- [ ] `visual.py` modulare;
- [ ] `renderers.py` modulare;
- [ ] `prompt.py` modulare;
- [ ] `turn_service.py` modulare;
- [ ] `validators.py` modulare;
- [ ] `llm.py` modulare;
- [ ] token misurati;
- [ ] token ridotti;
- [ ] NPC con stato agente separato;
- [ ] NPC con memoria breve;
- [ ] NPC con memoria lunga;
- [ ] retrieval deterministico;
- [ ] una sola chiamata LLM nella maggior parte dei turni;
- [ ] chiamate dedicate opzionali e limitate;
- [ ] conoscenze NPC isolate;
- [ ] player agency protetta;
- [ ] commit atomico;
- [ ] checkpoint recuperabile;
- [ ] rendering non bloccante;
- [ ] diagnostica completa;
- [ ] salvataggi compatibili.

---

# 11. Decisioni architetturali ufficiali

1. Gli agenti NPC sono agenti logici, non processi LLM indipendenti.
2. La memoria NPC Ã¨ canonica solo dopo validazione Python.
3. Il retrieval iniziale Ã¨ deterministico, non vettoriale.
4. Il vector DB non Ã¨ necessario nella V1.
5. LangChain e LangGraph non sono necessari.
6. La LLM non governa lo stato.
7. Le API pubbliche restano compatibili durante le estrazioni.
8. Le modifiche strutturali devono essere separate dalle modifiche di gameplay.
9. Ogni fase deve chiudersi con suite verde.
10. La baseline corrente Ã¨ `578 passed`.

---

# 12. Prossimo passo immediato

```text
FASE 0
â†’ verifica locale/remoto
â†’ inventario
â†’ CI minima
â†’ prima estrazione sicura da visual.py
```

Il lavoro sugli NPC agentici inizierÃ  solo dopo la modularizzazione di:

```text
visual.py
prompt.py
turn_service.py
```

Questo ordine riduce il rischio e rende possibile introdurre memoria, selezione contesto e agenti senza aumentare il debito tecnico.

---

# 13. Chiusura roadmap V1

Data chiusura locale: 2026-08-02.

Stato finale:

- FASI 0-13 completate;
- FASE 14 completata come misurazione finale e chiusura architetturale;
- baseline finale attesa: `746 passed`;
- report finale: `EPOS_ROADMAP_ARCHITETTURALE_NPC_AGENTS_FINAL_REPORT.md`;
- commit finale previsto: non ancora creato.

Deferred reali:

- integrazione runtime attiva del Coordinator NPC;
- uso delle memorie NPC nei prompt di turno;
- attivazione runtime della chiamata NPC LLM opzionale;
- qualsiasi evoluzione oltre la V1.

Stato roadmap: chiusa localmente, subordinata alla validazione finale verde e al futuro commit manuale.
