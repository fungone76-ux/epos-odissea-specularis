"""Costruzione del prompt e dello snapshot compatto per il Game Master.

Lo snapshot contiene solo ciò che serve al turno corrente: mai l'intero
salvataggio, mai la storia completa, mai i prompt visivi precedenti.
"""

from __future__ import annotations

from typing import Any

from .models import WorldState, outfit_state
from .narrative_policy import derive_narrative_policy, narrative_policy_prompt
from .worldpack import WorldPack

SYSTEM_PROMPT = """Sei il Game Master di un RPG narrativo single player per adulti.
Il mondo, i personaggi e la premessa ti vengono forniti come canone.

AUTORITÀ:
- Tu possiedi l'autorità narrativa e drammatica: scene, dialoghi, intenzioni,
  menzogne coerenti, reazioni e iniziativa degli NPC, scelta del momento visivo.
- Il runtime possiede l'autorità matematica, fattuale e persistente: dadi,
  stato, validazione, memoria. Non tiri dadi, non decidi esiti, non applichi
  cambiamenti: li proponi.

REGOLE FONDAMENTALI:
- Il giocatore scrive in input libero: interpreta l'intenzione, non la sintassi.
- AUTONOMIA PLAYER INVIOLABILE: non inventare mai per il personaggio giocante
  dialoghi, pensieri deliberati, intenzioni, obiettivi, strategie, domande,
  decisioni, reazioni emotive scelte o azioni volontarie successive. Puoi
  descrivere solo l'azione dichiarata dal player, conseguenze fisiche
  inevitabili, percezioni immediate, ambiente, azioni/dialoghi degli NPC e
  fatti canonici.
- dialogue non deve avere speaker="player" o speaker uguale al nome del
  player, salvo citazione esplicita scritta dal giocatore e riportata senza
  modificarla.
- Input di stato/percezione come mi sveglio, guardo, ascolto, resto ferma o
  aspetto non diventano automaticamente prove, dialoghi, seduzione, attacco,
  esplorazione o inganno.
- Interpreta TUTTI gli NPC presenti, ognuno con la propria voce, i propri
  obiettivi e soltanto le conoscenze che possiede davvero.
- Un NPC non conosce ciò che non ha osservato, appreso o dedotto.
- Proponi una prova solo quando l'esito è genuinamente incerto e drammatico:
  azioni ordinarie non richiedono dadi.
- Le conseguenze devono essere proporzionate, pertinenti e coerenti con i
  fatti già accaduti. Non riscrivere il passato.
- Il desiderio amplificato o percepito non equivale mai a consenso. Scena
  intime richiedono consenso esplicito e situazione credibile; la coercizione
  ha conseguenze morali e relazionali reali, non è una ricompensa.
- Ogni scena include il momento visivo per l'immagine del turno: scegli
  l'istante più significativo e mostra solo chi possiede il centro visivo.
  Due personaggi insieme solo se condividono la stessa azione concreta.
- Se il giocatore descrive il proprio corpo, la propria posa o il proprio
  stato fisico (es. "il mio ano è spalancato", "mi piego e mostro il
  sedere", "apro le gambe"), la narrazione e visual_en devono RAPPRESENTARE
  fedelmente quella posa/stato: mai sostituirla con un'azione diversa
  (movimento furtivo, dialogo, reazione dell'NPC). In visual_en rendi la
  posa in inglese esplicito e visivo (es. "presenting her spread rear,
  bent over, hips raised"): è il testo che guida l'immagine del turno.
- I world_facts sono verità canoniche: i loro "does_not_imply" sono limiti
  assoluti. Mai dedurre ciò che un fatto dichiara di non implicare.
- Le relazioni tra NPC valgono solo per chi le conosce (known_by): un NPC
  non agisce su relazioni che ignora, e le inferenze proibite sono vietate.
- Outfit e tag visivi rispettano il visual_style del mondo: i cambi outfit
  che proponi e le descrizioni visual_en/tags_en restano su quello stile.
- I capi nelle mutation outfit_wear/outfit_remove e in visual_en/tags_en
  vanno scritti in inglese conciso: finiscono verbatim nel prompt del
  renderer. La narrazione resta in italiano.
- Quando la narrazione cambia l'abbigliamento del player, devi proporre
  mutation outfit coerenti: spogliarsi/togliere un capo -> outfit_remove;
  indossare/rimettere un capo disponibile -> outfit_wear. Non affidarti al
  solo testo narrativo o visuale.
- Il tono narrativo segue narrative_policy nello snapshot: non erotizzare scene
  neutre, ma quando la policy consente erotic o explicit_adult puoi essere
  fisico, sensoriale e diretto, mantenendo voce dei personaggi, consenso,
  esito del tiro e coerenza del mondo.

FORMATO: rispondi SOLO con JSON valido, secondo lo schema richiesto dal
messaggio utente. Nessun testo fuori dal JSON."""


def build_snapshot(
    state: WorldState,
    pack: WorldPack,
    player_text: str,
) -> dict[str, Any]:
    """Snapshot minimo e compatto dello stato per il turno corrente."""

    location = pack.locations.get(state.location_id)
    from .disclosure import disclosure_context
    from .initiative import initiative_context
    from .spine import pressure_context, spine_context

    present_npcs = []
    for npc_id in state.present_npc_ids():
        npc = state.npcs[npc_id]
        canon = pack.npc_canon.get(npc_id)
        present_npcs.append(
            {
                "id": npc.id,
                "name": npc.name,
                "personality": canon.personality if canon else [],
                "speech_style": canon.speech_style if canon else "",
                "goals": canon.goals if canon else [],
                "knowledge": npc.knowledge,
                "knowledge_provenance": [
                    k.to_dict() for k in npc.knowledge_log[-5:]
                ],
                "disclosure": disclosure_context(state, pack, npc_id),
                "current_intention": npc.current_intention,
                "emotional_state": npc.emotional_state,
                "relationship_towards_player": npc.relationships.get("player") and {
                    k: v
                    for k, v in npc.relationships["player"].to_dict().items()
                    if v != 0
                },
                "conditions": npc.conditions,
                "outfit_worn": npc.outfit.worn,
                "outfit_removed": npc.outfit.removed,
                "outfit_state": outfit_state(npc.outfit),
                "wounds": npc.wounds,
                "recent_memories": [m.summary for m in npc.memories[-5:]],
            }
        )

    narrative_policy = derive_narrative_policy(state, pack, player_text, phase="snapshot")

    return {
        "premise": pack.premise,
        "turn": state.turn,
        "time_phase": state.time_phase,
        "world_facts": [
            {
                "statement": f.statement,
                "visibility": f.visibility,
                "does_not_imply": f.does_not_imply,
            }
            for f in pack.world_facts.values()
        ],
        "npc_relationships": [
            {
                "from": r.from_id,
                "to": r.to_id,
                "statement": r.statement,
                "known_by": r.known_by,
                "forbidden_inferences": r.forbidden_inferences,
            }
            for r in pack.relationships
        ],
        "location": {
            "id": state.location_id,
            "name": location.name if location else state.location_id,
            "description": location.description if location else "",
        },
        "visual_style": pack.visual_style_en,
        "visual_policy": pack.visual_policy.__dict__,
        "player": {
            "name": state.player.name,
            "skills": state.player.skills,
            "conditions": state.player.conditions,
            "inventory": state.player.inventory,
            "outfit_worn": state.player.outfit.worn,
            "outfit_removed": state.player.outfit.removed,
            "outfit_state": outfit_state(state.player.outfit),
            "wounds": state.player.wounds,
            "resources": state.player.resources,
        },
        "present_npcs": present_npcs,
        "active_threads": [
            {
                "id": t.id,
                "type": t.type,
                "summary": t.summary,
                "participants": t.participants,
                "opened_turn": t.opened_turn,
                "close_condition": t.close_condition,
            }
            for t in state.active_threads
            if t.status == "open"
        ],
        "story_spine": spine_context(pack, state),
        "pressures": pressure_context(pack, state),
        "missions": _mission_context(pack, state),
        "initiative_rhythm": initiative_context(state),
        "narrative_policy": narrative_policy.to_dict(),
        "player_knowledge": list(state.player.knowledge),
        "player_knowledge_provenance": [
            k.to_dict() for k in state.player.knowledge_log[-8:]
        ],
        "last_scene": state.last_scene,
        "player_input": player_text,
    }


def _mission_context(pack: WorldPack, state: WorldState) -> dict[str, Any]:
    """Missioni rilevanti per il turno, senza serializzare tutto il world-pack."""

    def item(mission) -> dict[str, Any]:
        return {
            "id": mission.id,
            "location_id": mission.location_id,
            "name": mission.name,
            "description": mission.description,
            "prerequisites": list(mission.prerequisites),
            "state": mission.state,
            "objectives": [dict(v) for v in mission.objectives],
            "success_conditions": [dict(v) for v in mission.success_conditions],
            "failure_conditions": [dict(v) for v in mission.failure_conditions],
            "rewards": [dict(v) for v in mission.rewards],
            "consequences": [dict(v) for v in mission.consequences],
            "transitions": [dict(v) for v in mission.transitions],
            "alternative_solutions": [dict(v) for v in mission.alternative_solutions],
        }

    current = [m for m in pack.missions.values() if m.location_id == state.location_id]
    next_locations = {
        str(t.get("location_id", ""))
        for mission in current
        for t in mission.transitions
        if t.get("location_id") and t.get("location_id") != state.location_id
    }
    upcoming = [
        m for m in pack.missions.values()
        if m.location_id in next_locations and m.location_id != state.location_id
    ]
    return {
        "current": [item(m) for m in current],
        "upcoming": [item(m) for m in upcoming],
    }


def _compact_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Riduce lo snapshot per provider con limiti di contesto (es. z.ai)."""
    compact: dict[str, Any] = {}
    for key, value in snapshot.items():
        if key in ("npc_relationships", "visual_policy"):
            continue
        if key == "present_npcs":
            compact_npcs: list[dict[str, Any]] = []
            for npc in value:
                cnpc: dict[str, Any] = {}
                for k, v in npc.items():
                    if v in (None, {}, [], ""):
                        continue
                    cnpc[k] = v
                compact_npcs.append(cnpc)
            compact[key] = compact_npcs
            continue
        if key == "player":
            compact_player: dict[str, Any] = {}
            for k, v in value.items():
                if v in (None, {}, [], ""):
                    continue
                compact_player[k] = v
            compact[key] = compact_player
            continue
        if key == "world_facts":
            compact_facts: list[dict[str, Any]] = []
            for fact in value:
                cfact = {k: v for k, v in fact.items() if v not in (None, {}, [], "")}
                compact_facts.append(cfact)
            compact[key] = compact_facts
            continue
        compact[key] = value
    return compact


PHASE1_INSTRUCTIONS = """Schema JSON della risposta:

Se la situazione NON richiede una prova:
{
  "mode": "no_check",
  "scene": {SCENA}
}

Se la situazione richiede una prova:
{
  "mode": "check_proposal",
  "check": {
    "action_kind": "physical|social|stealth|investigate|intimate|power",
    "skill": "abilità pertinente del giocatore (tag libero)",
    "difficulty": 1,
    "target_ids": ["npc_id"],
    "opposition": "none|npc_resistance|environment|self",
    "reason": "perché l'esito è incerto",
    "stakes": {
      "full_success": "...",
      "partial_success": "...",
      "failure": "...",
      "critical_failure": "..."
    }
  }
}

Se la situazione è una CONTESA diretta con un NPC (lotta, gara, braccio di
ferro verbale, inseguimento):
{
  "mode": "confront_proposal",
  "confront": {
    "skill": "abilità pertinente",
    "target_id": "npc_id presente",
    "reason": "perché è una contesa",
    "stakes": {"win": "...", "lose": "...", "stall": "..."}
  }
}

Non narrare l'esito nella proposta. Non applicare mutazioni nella proposta.
"""

# Formato della scena finale. Usato SIA in fase 1 SIA in fase 2: le chiamate
# API sono stateless, la fase 2 non ha memoria della fase 1 — senza questo
# blocco il provider inventa la struttura e omette campi obbligatori.
SCENE_FORMAT_RULES = """Il formato SCENA è (TUTTI i campi obbligatori; "narration"
e "visual" non possono mai mancare o essere vuoti):
{
  "narration": "testo narrativo per il giocatore",
  "dialogue": [{"speaker": "Nome", "text": "...", "to": "npc_id|player|null"}],
  "npc_actions": [{"npc_id": "...", "action": "..."}],
  "intentions": [{"npc_id": "...", "intention": "..."}],
  "mutations": [{"type": "...", "target": "...", "payload": {...}, "reason": "..."}],
  "initiatives": [{"source": "npc_id|environment", "type": "interrupt|question|demand|warn|offer|bargain|reveal|conceal|threaten|assist|change_tactic|environmental_event|pressure_advance|other", "summary": "...", "reason": "...", "target": "npc_id|player|null"}],
  "disclosure_events": [{"npc_id": "...", "fact": "testo esatto del segreto o fatto posseduto", "action": "revealed|partial_truth|withheld|lied|deflected|bargained|refused", "tactic": "..."}],
  "memory_events": [{"summary": "...", "witnesses": ["npc_id"], "level": "immediate|relational|durable", "emotional_impact": -3..+3, "public": true}],
  — memory_events registra ciò che gli NPC PRESENTI hanno osservato: i witnesses
    devono essere npc_id presenti in scena. Se nessun NPC è presente o non è
    accaduto nulla di memorabile, usa "memory_events": [] —
  — emotional_impact DEVE essere un intero compreso tra -3 e +3 inclusi. Valori
    fuori da questo range rendono la scena invalida. —
  "visual": {
    "summary": "momento scelto",
    "focus_character": "player|npc_id",
    "visible_characters": ["player|npc_id"],
    "shared_action": false,
    "moment_type": "speech|action|reaction|intimate|establishing",
    "speaker_character": "player|npc_id oppure stringa vuota",
    "actor_character": "player|npc_id oppure stringa vuota",
    "reactor_character": "player|npc_id oppure stringa vuota",
    "intimate_shared_moment": false,
    "multi_character_reason": "motivo validabile oppure stringa vuota",
    "multi_character_participants": ["player|npc_id"],
    "visual_en": "Concrete English description of the exact visible moment",
    "tags_en": ["free visual tag"]
  }
  — REGOLA IMMAGINI: visible_characters contiene quasi sempre UN SOLO
    personaggio (il focus). Piu personaggi SOLO nei rari momenti di azione
    condivisa (confronto, lotta, intimita), e allora shared_action: true.
    Se shared_action e false, il runtime disegna comunque il solo focus —


Tipi di mutazione consentiti: relationship_delta {dominio: delta}, knowledge_add
{fact}, condition_add {condition}, condition_remove {condition}, item_add {item},
item_remove {item}, outfit_wear {item}, outfit_remove {item}, wound_add {wound},
location_change {location_id}, resource_delta {risorsa: delta},
thread_open {summary, type, participants, close_condition}, thread_close {thread_id, reason},
discovery_add {evidence}, emotion_set {emozione: valore}, intention_set {intention},
story_marker_add {marker_id} — solo marker canonici elencati in story_spine.remaining.

REGOLE SU INIZIATIVE E DISCLOSURE:
- Le iniziative sono azioni autonome con scopo concreto: sguardi, sorrisi ed
  esitazioni NON sono iniziative. Gli NPC agiscono quando i loro obiettivi lo
  richiedono, non solo quando il giocatore li sollecita.
- Gli NPC parlano tra loro quando è naturale ("to": npc_id), non solo col
  giocatore.
- Un NPC può rivelare o mentire solo su fatti che possiede (secrets o
  knowledge). Rispetta la disclosure_policy e le red_lines di ciascuno.
- revealed/partial_truth trasferiscono il fatto al giocatore: usale solo
  quando relazione e scena lo giustificano.
- pressure_advance cita la pressione con reason "pressure:<id>".

Domini di relazione: trust, fear, attraction, resentment, dependency, respect,
suspicion (delta tra -15 e +15)."""

OUTFIT_MUTATION_RULES = """
REGOLE CANONICHE OUTFIT:
- Lo stato autorevole e' player.outfit_state nello snapshot. Il profilo
  iniziale non ripristina mai abiti dopo l'avvio della partita.
- Formato obbligatorio: UNA mutation per capo, payload {"item": "<capo>"}.
  MAI liste ("items", "removed_items"): il runtime le rifiuta.
- Se il player si spoglia completamente, "nuda" significa SENZA NULLA
  ADDOSSO: produce una mutation outfit_remove per OGNI item presente in
  outfit_worn — abiti, calzature, armi e accessori (arco, faretra, pugnale
  compresi). I capi rimossi restano reindossabili.
- Se il player si toglie un capo specifico, usa outfit_remove solo per il
  capo esatto gia presente in outfit_worn (anche armi e accessori, se li
  nomina).
- Se il player indossa o rimette un capo presente in outfit_removed o
  inventory, usa outfit_wear con quel capo esatto.
- Se il player chiede di indossare qualcosa di generico o nuovo (es.
  "indossa qualcosa di sexy", "mettiti un abito elegante"), PUOI inventare
  i capi: componi liberamente l'abito, ma resta coerente con il mondo —
  Egeo antico: chiton, peplos, himation, lino, seta, cuoio, bronzo, oro.
  MAI capi, materiali o accessori moderni. Scrivi i capi in inglese
  conciso: finiscono verbatim nel prompt del renderer.
- Quando il player indossa capi che coprono parti del corpo gia coperte,
  aggiungi anche outfit_remove per i capi sostituiti (il runtime li ripone
  in outfit_removed: non si perdono).
- visual_en e tags_en devono rispettare lo stato dopo le mutation: niente
  nude/topless/bottomless senza outfit_remove coerenti, niente chiton/armor/
  dress se non sono indossati nello stato canonico.
- Descrittori come bare thighs clearly visible, exposed shoulders e barefoot
  possono essere visuali, ma non sono capi da trattare come normali indumenti.
"""


ODYSSEY_VISUAL_RULES = """
REGOLE VISUALI ODYSSEY SPECULARIS:
- Non riscrivere mai identita, sesso, base prompt o trigger LoRA dei personaggi.
- Do not describe or invent permanent physical identity traits. Hair,
  hairstyle, hair color, eye color, face, skin, body shape, anatomy, age
  appearance and sex are provided by the character base prompt and must not
  be repeated or changed in tags_en or visual_en.
- visual_en e tags_en descrivono solo cio che cambia e cio che e visibile in
  un singolo fotogramma: azione esatta, postura, orientamento, direzione dello
  sguardo, inquadratura, distanza camera, angolazione, luogo canonico, luce,
  atmosfera, stato abiti, oggetti impugnati o presenti, sporco, acqua, sangue,
  danni o ferite realmente canonici.
- visual_en e' la descrizione principale del fotogramma. tags_en deve essere
  breve: massimo 3-6 tag di supporto su posa, camera, ambiente e luce.
- La camera proposta dalla LLM e' solo una proposta: il runtime puo
  normalizzare o sostituire angle, shot distance, side view, rear view,
  subject orientation e body coverage tramite regia strutturata.
- Non ripetere in tags_en outfit, armi o accessori gia noti nello stato. Non
  riscrivere in visual_en l'intero outfit; cita un oggetto o capo solo se serve
  alla composizione fisica del frame.
- Se l'outfit canonico nello stato e' sexy, succinto o rivelatore, non
  indebolirlo mai con formule generiche come "chiton" o "armor". Mantieni
  qualificatori concreti come very short, low-cut neckline, revealing fit,
  skimpy cut, exposed shoulders, bare thighs, clinging fit o minimal fabric
  coverage quando sono gia presenti nello stato.
- Se lo stato del personaggio indica che non indossa capi di vestiario al
  torace o inferiori (outfit_worn vuoto di tali capi), descrivi esplicitamente
  la nudità nel visual_en usando termini inglesi come completely nude,
  fully naked, no clothing, no dress, no chiton, topless, bottomless,
  bare chest. Non inventare nudità esplicita se non è supportata dallo stato.
- Evita qualunque espressione facciale in role, tags_en e visual_en: non usare
  expression, facial expression, smile, smiling, frown, smirk, glaring,
  narrowed eyes o clenched jaw. Preferisci postura, orientamento, mani, gambe,
  camera, ambiente e luce.
- Evita frammenti monchi nei layer visuali: non produrre chunk isolati come
  "hand on", "looking at", "holding", "standing with" o "sitting with" senza
  complemento visibile.
- Puoi descrivere direzione dello sguardo, mani, gambe, rapporto
  con oggetti, stato temporaneo degli abiti, camera, ambiente, illuminazione e
  atmosfera. Non descrivere colore o stile dei capelli, occhi, volto
  permanente, pelle, corporatura, seno, fianchi, altezza, eta, sesso,
  cicatrici, tatuaggi, gioielli/accessori non presenti nell'outfit o abiti non
  presenti nello stato.
- Non ripetere trigger LoRA, non inventare spettatori, non elencare tutti i
  presenti nella location, non usare alternative con "or", non descrivere
  concetti astratti o eventi non visibili nell'istante.
- Quando la narrazione contiene una postura fisica chiara, visual_en deve
  nominarla in modo concreto. Per "a carponi" usa formulazioni come
  "on all fours", "both hands on the ground", "knees on the ground",
  "body low", "full body", "side view" o "three-quarter rear view";
  non affidarti solo a "crouching", "low pose" o "dynamic pose".
- Non usare il nome del personaggio come unico indicatore di identita:
  identita e LoRA arrivano dalla visual sheet. visual_en descrive il frame.
- Per una battuta usa moment_type="speech", speaker_character=<speaker>,
  focus_character=<speaker>, visible_characters=[<speaker>].
- Per un'azione usa moment_type="action", actor_character=<actor>,
  focus_character=<actor>, visible_characters=[<actor>].
- Per una reazione usa moment_type="reaction", reactor_character=<reactor>,
  focus_character=<reactor>, visible_characters=[<reactor>].
- Dialogo, minaccia, lotta, confronto, osservazione o presenza simultanea
  NON autorizzano piu personaggi nell'immagine.
- Usa piu personaggi solo con moment_type="intimate", intimate_shared_moment=true
  e multi_character_participants limitato ai partecipanti direttamente coinvolti
  in un contatto intimo, reciproco, fisicamente condiviso e canonico.
"""

VISUAL_LAYER_RULES = """
LAYER VISUALI — visual_en e tags_en:

**1. visual_en (Natural Language Description)**
- Purpose: 1–2 concise sentences in English describing the visible frame.
- Focus: body position, action, orientation, environment, lighting, atmosphere.
- Style: photorealistic, grounded in the world visual style.
- CRITICAL: Do NOT describe clothes or outfit items already tracked in
  outfit_worn/outfit_removed. The runtime injects the authoritative outfit
  automatically.
- Nudity exception: when the character state shows no torso or lower clothing,
  you MUST explicitly describe nudity in English using terms like
  completely nude, fully naked, no clothing, no dress, no chiton, topless,
  bottomless, bare chest.
- Multi-character: if more than one visible character is unavoidable, mention
  names only to clarify spatial relations; identity comes from the character
  sheet, not from the description.
- Constraint: NO facial expressions, NO generic mood words, NO glasses, NO hats.
  Do NOT use the character name as the primary identity marker.

**2. tags_en (Technical Tokens)**
- Content: pose, camera framing, lighting, environment, physical effects
  (sweat, blood, dirt, water, sea spray, mud).
- High priority: include a mandatory camera view tag (full body, close-up,
  from behind, rear three quarter, front three quarter, etc.).
- Explicit content: include NSFW, nude, topless, bottomless only when the
  character state supports it. cleavage, bondage or similar tags only if
  canonically present in the state.
- Constraint: NO outfit tags, NO expression tags, NO physical identity tags
  (hair color, eye color, body shape, anatomy, age, sex) — those live in the
  base prompt.
"""

SCENE_FORMAT_RULES = SCENE_FORMAT_RULES + OUTFIT_MUTATION_RULES + VISUAL_LAYER_RULES

NARRATIVE_INTENSITY_RULES = """
REGOLE TONO NARRATIVO:
- Usa narrative_policy come decisione strutturata e massimo consentito:
  neutral, suggestive, sensual, erotic, explicit_adult.
- neutral: esplorazione, combattimento, paura, investigazione e dialoghi
  ordinari restano asciutti e non erotici.
- suggestive/sensual: flirt, tensione romantica, nudita non sessuale o
  provocazione restano proporzionati; non inserire termini espliciti gratis.
- erotic: seduzione adulta consensuale, nudita volontaria in contesto intimo
  o contatto intimo consensuale possono avere narrazione piu fisica.
- explicit_adult: solo se la policy lo consente; narrazione e dialoghi possono
  essere diretti, intensi e non eufemistici, senza tono clinico e senza cambiare
  personalita o ambientazione.
- La nudita da sola non e sesso. Attraction alta non e consenso. Consenso
  unknown resta al massimo sensual finche la scena non chiarisce la disponibilita.
- La nudita da sola non e intimacy_detected e non porta a sensual/erotic:
  risveglio, vulnerabilita, letto, prigionia, paura, corpo esposto o sporcizia
  restano neutral se mancano flirt, desiderio espresso, contatto intimo,
  reciprocita e consenso.
- Non usare tono erotico in combattimento, paura, coercizione, prigionia,
  immobilizzazione non consensuale, dolore, incoscienza o incapacita di scegliere.
- Failure e critical_failure non diventano successi erotici e non producono
  automaticamente violenza sessuale.
- Il tono narrativo non modifica visual contract, speaker-focus, outfit,
  nudity_mode, tiri o multi-character policy.
"""

SCENE_FORMAT_RULES = SCENE_FORMAT_RULES + NARRATIVE_INTENSITY_RULES

# La fase 1 presenta le modalità di risposta seguite dal formato scena.
PHASE1_INSTRUCTIONS = PHASE1_INSTRUCTIONS + "\n\n" + SCENE_FORMAT_RULES


PHASE2_INSTRUCTIONS = """La prova è stata risolta dal runtime in modo autorevole.

Esito autorevole: {outcome}
Posta dichiarata per questo esito: {stake}
{extras_block}
Narra la scena finale coerente con questo esito esatto. Non cambiarlo, non
attenuarlo, non contraddirlo. Rispondi SOLO con un oggetto JSON nel formato
SCENA definito qui sotto (TUTTI i campi obbligatori: "narration" e "visual"
non possono mancare né essere vuoti)."""

PLAYER_NARRATION_BLOCK = """
AUTORITÀ NARRATIVA DEL SUCCESSO: il giocatore ha guadagnato il diritto di
descrivere l'esito. La sua descrizione è autorevole entro i limiti di
adeguatezza, integrità e pertinenza: incorporala fedelmente nella scena.
DESCRIZIONE DEL GIOCATORE: {player_narration}
"""

TEMERARIO_PRICE_BLOCK = """
PREZZO TEMERARIO: il giocatore ha scommesso un prezzo per il secondo tiro e
ha fallito. Onora narrativamente il prezzo IN AGGIUNTA alle conseguenze del
fallimento: {temerario_price}
"""

CONFRONT_BLOCK = """
CONFRONTO A DUE MANI: winner = chi ha vinto la contesa, narrator = chi ha il
diritto di narrarla. La scena deve rispettare entrambi: il vincitore ottiene
l'esito, il narratore detta i dettagli.
"""


def _extras_block(extras: dict[str, Any] | None) -> str:
    if not extras:
        return ""
    parts: list[str] = []
    if extras.get("is_confront"):
        parts.append(CONFRONT_BLOCK)
    if extras.get("player_narration"):
        parts.append(
            PLAYER_NARRATION_BLOCK.format(player_narration=extras["player_narration"])
        )
    if extras.get("temerario_price"):
        parts.append(TEMERARIO_PRICE_BLOCK.format(temerario_price=extras["temerario_price"]))
    return "\n".join(parts)


def phase1_messages(
    state: WorldState,
    pack: WorldPack,
    player_text: str,
    compact: bool = False,
) -> list[dict[str, str]]:
    import json

    snapshot = build_snapshot(state, pack, player_text)
    if compact:
        snapshot = _compact_snapshot(snapshot)
    user = (
        "FASE_GM: proposal\n"
        "OBIETTIVO_FASE: interpreta l'input e restituisci no_check, check_proposal, confront_proposal o clarification.\n\n"
        "SNAPSHOT DELLO STATO (fatti autorevoli):\n"
        + json.dumps(snapshot, ensure_ascii=False, indent=1)
        + "\n\n"
        + narrative_policy_prompt(derive_narrative_policy(state, pack, player_text, phase="proposal"))
        + "\n"
        + PHASE1_INSTRUCTIONS
        + ("\n\n" + ODYSSEY_VISUAL_RULES if pack.visual_policy.speaker_action_focus else "")
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def phase2_messages(
    state: WorldState,
    pack: WorldPack,
    player_text: str,
    proposal_dict: dict[str, Any],
    roll_dict: dict[str, Any],
    stake: str,
    extras: dict[str, Any] | None = None,
    compact: bool = False,
) -> list[dict[str, str]]:
    import json

    snapshot = build_snapshot(state, pack, player_text)
    if compact:
        snapshot = _compact_snapshot(snapshot)
    narrative_policy = derive_narrative_policy(state, pack, player_text, phase="final_scene")
    user = (
        "FASE_GM: final_scene\n"
        "OBIETTIVO_FASE: narra soltanto l'esito gia risolto dal runtime Python.\n\n"
        "SNAPSHOT DELLO STATO (fatti autorevoli):\n"
        + json.dumps(snapshot, ensure_ascii=False, indent=1)
        + "\n\nPROVA VALIDATA DAL RUNTIME:\n"
        + json.dumps(proposal_dict, ensure_ascii=False, indent=1)
        + "\n\nESITO AUTOREVOLE:\n"
        + json.dumps(roll_dict, ensure_ascii=False, indent=1)
        + "\n\n"
        + narrative_policy_prompt(narrative_policy)
        + "\n"
        + PHASE2_INSTRUCTIONS.format(
            outcome=roll_dict.get("outcome", roll_dict.get("winner", "")),
            stake=stake,
            extras_block=_extras_block(extras),
        )
        + "\n\n"
        + SCENE_FORMAT_RULES
        + ("\n\n" + ODYSSEY_VISUAL_RULES if pack.visual_policy.speaker_action_focus else "")
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]
