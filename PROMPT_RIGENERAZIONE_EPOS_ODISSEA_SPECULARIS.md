# PROMPT MASTER — RIGENERAZIONE E MIGLIORAMENTO DI EPOS / ODISSEA SPECULARIS

## Ruolo assegnato all’IA

Agisci come **software architect senior, game designer di RPG narrativi, sviluppatore Python, progettista di sistemi agentici e responsabile QA**. Devi analizzare e ricostruire in modo professionale un gioco RPG narrativo single-player chiamato **EPOS**, partendo dal codice esistente che ti verrà fornito.

Non devi limitarti a correggere qualche file o ad abbellire la GUI. Devi comprendere il prodotto, conservare le idee valide, eliminare fragilità e duplicazioni e produrre una versione migliore, più coerente, testabile, estendibile e realmente giocabile.

Non improvvisare requisiti mancanti. Prima studia tutto il repository. Ogni decisione deve essere motivata da codice, configurazioni, documenti o requisiti espliciti.

---

## Visione del prodotto

EPOS è un **RPG narrativo single-player a input libero**, nel quale il giocatore scrive normalmente ciò che il proprio personaggio tenta, dice o osserva. Un Game Master basato su LLM interpreta l’intenzione e produce scene, dialoghi degli NPC, iniziative autonome e proposte di conseguenze.

Il principio architetturale inviolabile è:

> **L’IA interpreta e narra; Python governa il mondo.**

La LLM non deve essere la fonte di verità del gioco. Non deve tirare dadi, modificare direttamente lo stato, inventare retroattivamente fatti canonici o decidere liberamente ciò che è persistente. Deve restituire un contratto strutturato; il runtime Python normalizza, valida, risolve le regole, applica soltanto le mutazioni legittime e salva lo stato.

Il primo world-pack completo è **Odissea Specularis**, una reinterpretazione adulta, cupa e gender-swapped dell’Odissea. Ulisse è una donna, viaggia sola e affronta tappe, personaggi, pressioni e dilemmi ispirati al mito. Il motore, però, deve restare generico e supportare altri mondi configurabili.

---

## Obiettivi principali

Realizza un sistema che:

1. permetta al giocatore di scrivere input libero in italiano;
2. preservi rigorosamente l’autonomia del personaggio giocante;
3. faccia agire gli NPC come soggetti autonomi, non come comparse passive;
4. mantenga stato, memoria, relazioni, outfit, ferite, risorse, missioni e fili narrativi persistenti;
5. separi nettamente narrazione LLM, regole Python, persistenza, rendering e interfaccia;
6. produca una scena coerente e un’immagine coerente per ogni turno significativo;
7. gestisca prove, dadi ed esiti senza lasciare autorità matematica alla LLM;
8. impedisca contraddizioni, conoscenza impossibile, retcon e mutazioni arbitrarie;
9. sopravviva a risposte JSON errate, timeout, crash o provider LLM indisponibili;
10. sia coperto da test automatici e diagnostica leggibile.

---

## Funzionamento richiesto del turno

### 1. Ricezione dell’input

Il giocatore inserisce un’azione, una battuta, una domanda, un’osservazione o una combinazione di questi elementi.

Il sistema deve distinguere almeno:

- dialogo esplicito pronunciato dal giocatore;
- azione fisica;
- osservazione o ascolto;
- investigazione;
- movimento;
- attesa o immobilità;
- inganno;
- azione sociale;
- azione intima;
- uso di poteri o risorse;
- tentativo ambiguo che richiede chiarimento.

Un input passivo come “mi guardo intorno”, “aspetto”, “ascolto” o “mi sveglio” non deve diventare arbitrariamente un attacco, una seduzione, un inganno o un’azione mai dichiarata.

### 2. Snapshot canonico

Prima della chiamata LLM, il runtime costruisce uno snapshot compatto contenente soltanto ciò che serve al turno:

- luogo e fase temporale;
- dati essenziali del giocatore;
- NPC effettivamente presenti;
- conoscenze realmente possedute da ciascun NPC;
- stato emotivo e intenzione corrente degli NPC;
- relazioni pertinenti;
- outfit e oggetti rimossi;
- ferite e condizioni;
- thread narrativi aperti;
- missioni, pressioni e marker rilevanti;
- scena precedente sintetica;
- ritmo recente delle iniziative autonome;
- policy narrativa e visiva applicabile.

Non inviare l’intero salvataggio, log infiniti o prompt visivi precedenti.

### 3. Fase di proposta LLM

La LLM deve restituire esclusivamente JSON valido in uno dei seguenti modi:

- `no_check`: l’azione non richiede una prova e viene proposta direttamente una scena;
- `check_proposal`: l’esito è incerto e drammatico, quindi viene proposta una prova;
- `confront_proposal`: esiste un confronto strutturato con opposizione attiva;
- `clarification`: l’intenzione del giocatore è realmente ambigua e non può essere interpretata senza scegliere al posto suo.

La LLM propone, ma non applica, eventuali mutazioni.

### 4. Validazione semantica

Python deve verificare almeno:

- coerenza tra input e azione proposta;
- esistenza e presenza dei target;
- abilità valida;
- difficoltà entro limiti ammessi;
- posta proporzionata;
- nessuna violazione dell’autonomia del giocatore;
- nessuna informazione impossibile attribuita agli NPC;
- nessuna contraddizione con il canone o con lo stato corrente;
- nessuna mutazione vietata o non motivata.

Se la proposta è correggibile, effettuare al massimo un retry strutturato con elenco preciso degli errori. Se resta invalida, non corrompere lo stato.

### 5. Risoluzione Python

Se serve una prova:

- Python calcola il pool;
- applica talenti, bonus, riserve e costi;
- esegue il tiro con RNG controllabile;
- determina l’esito canonico;
- salva subito proposta e risultato in un checkpoint;
- impedisce che un crash successivo faccia ritirare i dadi.

La LLM riceve poi l’esito autorevole e deve narrarlo fedelmente senza migliorarlo, peggiorarlo o cambiarlo.

### 6. Scena finale

La scena finale deve contenere in forma strutturata almeno:

- narrazione in italiano;
- dialoghi attribuiti ai soli personaggi legittimi;
- intenzioni correnti degli NPC;
- iniziative autonome concrete;
- divulgazioni o menzogne tracciabili;
- mutazioni proposte;
- memoria proposta con testimoni e fonte;
- momento visivo del turno;
- eventuale avanzamento di pressione o missione.

### 7. Commit atomico

Il runtime deve:

1. normalizzare gli ID;
2. validare la scena;
3. validare ogni mutazione;
4. applicare tutto su una copia dello stato;
5. salvare scena e artefatti;
6. sostituire lo stato precedente solo a operazione riuscita;
7. mantenere il checkpoint finché il commit non è concluso.

Un errore non deve lasciare uno stato aggiornato a metà.

---

## Autonomia inviolabile del giocatore

La LLM non deve mai inventare per il personaggio giocante:

- battute non scritte dal giocatore;
- pensieri deliberati;
- intenzioni;
- decisioni;
- obiettivi;
- strategie;
- emozioni scelte;
- consenso;
- azioni volontarie successive a quella dichiarata.

Può descrivere:

- l’azione esplicitamente dichiarata;
- percezioni immediate;
- conseguenze fisiche inevitabili;
- reazioni e dialoghi degli NPC;
- ambiente e fatti canonici;
- effetti determinati dal regolamento.

Quando il giocatore scrive un dialogo tra virgolette, questo può essere riportato fedelmente, senza riscriverne il significato.

---

## NPC autonomi e credibili

Ogni NPC deve possedere dati distinti:

- identità stabile;
- personalità;
- stile di linguaggio;
- obiettivi a breve e lungo termine;
- paure, desideri e limiti;
- conoscenze;
- segreti;
- memoria individuale;
- relazioni direzionali;
- stato emotivo;
- intenzione corrente;
- posizione e presenza;
- outfit, condizioni e ferite.

Gli NPC devono poter:

- interrompere;
- fare domande;
- avanzare richieste;
- offrire accordi;
- minacciare;
- mentire;
- nascondere informazioni;
- cambiare tattica;
- aiutare;
- agire tra loro;
- abbandonare la scena;
- far avanzare una pressione.

Uno sguardo, un sorriso o un sospiro non sono sufficienti come “iniziativa autonoma”. Dopo troppi turni puramente reattivi, il sistema deve segnalare al GM la necessità di un’iniziativa concreta, senza forzarne una incoerente.

---

## Conoscenza, memoria e divulgazione

Nessun NPC è onnisciente.

Ogni informazione deve avere provenienza:

- osservata;
- raccontata;
- dedotta;
- pubblica;
- segreta;
- contestuale.

Ogni ricordo deve indicare almeno:

- soggetto che lo possiede;
- riassunto;
- turno;
- fonte;
- testimoni;
- credibilità;
- impatto emotivo;
- livello di persistenza.

Una divulgazione deve distinguere:

- verità completa;
- verità parziale;
- omissione;
- menzogna;
- deviazione;
- patteggiamento;
- rifiuto.

Solo una divulgazione vera o parzialmente vera può trasferire conoscenza canonica al giocatore.

---

## Relazioni

Le relazioni sono direzionali e multidimensionali. Supporta almeno:

- fiducia;
- paura;
- attrazione;
- risentimento;
- dipendenza;
- rispetto;
- sospetto.

I valori numerici descrivono conseguenze e tendenze, ma non determinano automaticamente comportamento, consenso o disponibilità.

Le variazioni devono essere motivate da eventi reali, limitate e con soglie configurabili. Evita oscillazioni artificiali a ogni battuta.

---

## Thread narrativi

Il gioco non deve dimenticare questioni aperte. Gestisci thread persistenti quali:

- domande senza risposta;
- minacce sospese;
- promesse;
- richieste;
- accuse;
- dialoghi interrotti;
- conflitti NPC-NPC;
- debiti;
- accordi;
- obiettivi dichiarati.

Ogni thread deve avere ID, tipo, partecipanti, riassunto, turno di apertura, stato e possibile criterio di chiusura. La chiusura deve essere esplicita o derivata da un evento validato.

---

## Odissea Specularis

Conserva il world-pack come campagna principale ma separalo dal motore.

Elementi canonici essenziali:

- protagonista: Ulisse, regina di Itaca, arciera e stratega;
- viaggia sola;
- ritorna dalla guerra di Troia;
- atmosfera adulta, aspra, sensoriale e mitologica;
- tappe: Ciclopi, Eolo, Sirene, Scilla e Cariddi, Circe, Cimmeri/Ade, Calipso, Isola del Sole, Scheria, Itaca;
- pressioni persistenti: Poseidone, Proche, fame, tempo;
- conclusione a Itaca con travestimento, arco e riconoscimento;
- divinità con sesso canonico; mortali, mostri e semidei gender-swapped;
- nessuna deduzione oltre i limiti `does_not_imply` e `forbidden_inferences` definiti dal world-pack.

Le missioni non devono essere semplici keyword match. Devono avere:

- prerequisiti;
- stato;
- obiettivi;
- condizioni di successo e fallimento;
- eventi di avanzamento espliciti;
- ricompense o conseguenze;
- transizioni di luogo;
- possibilità di soluzione alternativa quando coerente.

---

## Contenuti adulti e consenso

Il gioco è rivolto esclusivamente ad adulti e può contenere temi maturi. Il tono deve dipendere dalla scena e dalla policy narrativa, non essere erotico per impostazione automatica.

Regole inderogabili:

- tutti i partecipanti coinvolti in contenuti sessuali devono essere adulti;
- attrazione, desiderio, magia o nudità non equivalgono a consenso;
- il consenso deve essere credibile e coerente con stato, relazioni e situazione;
- coercizione, violenza o manipolazione non devono essere trattate come ricompensa romantica;
- scene neutre, di combattimento, lutto o pericolo non devono essere sessualizzate senza ragione narrativa;
- outfit, nudità e pose devono restare coerenti con le azioni e con lo stato persistente.

---

## Sistema outfit e continuità fisica

L’outfit è stato canonico, non decorazione del prompt.

Per ogni personaggio conserva:

- capi indossati;
- capi rimossi;
- slot corporei coperti;
- calzature;
- revisione dello stato;
- oggetti disponibili per essere rimessi.

Togliere un capo richiede una mutazione `outfit_remove`; indossarlo richiede `outfit_wear`. Un oggetto rimosso non deve ricomparire visivamente o narrativamente senza una mutazione valida.

Il sistema deve riconoscere sinonimi e descrittori senza confondere elementi estetici con capi reali. Deve rilevare conflitti di slot ed evitare duplicazioni.

---

## Regia visiva e generazione immagini

Ogni turno significativo deve produrre un contratto visivo separato dalla narrazione.

Il contratto visivo deve contenere:

- soggetto o soggetti visibili;
- centro visivo;
- azione concreta rappresentata;
- luogo;
- outfit canonico;
- posa;
- inquadratura;
- lato camera;
- angolo;
- tipo di shot;
- illuminazione;
- prompt positivo in inglese;
- tag in inglese;
- prompt negativo;
- motivazione della scelta visiva.

Regole:

- mostra solo chi possiede davvero il centro visivo;
- usa due personaggi insieme soltanto se condividono la stessa azione concreta;
- non mostrare automaticamente tutti i presenti;
- varia camera e composizione evitando ripetizioni meccaniche;
- non sacrificare chiarezza dell’azione per la varietà;
- outfit e condizioni fisiche vengono dallo stato, non dall’immaginazione del modello;
- il renderer non deve conoscere o modificare lo stato di gioco;
- supporta adapter separati per ComfyUI, Automatic1111 e altri renderer;
- un fallimento del rendering non deve annullare il turno narrativo: salva un record retryable.

La descrizione corporea o la posa esplicitamente dichiarata dal giocatore deve essere rappresentata fedelmente nel momento visivo, senza sostituirla con un’altra azione.

---

## Interfaccia utente

Crea una GUI desktop moderna e stabile, preferibilmente con PySide6, separata dal dominio.

Deve includere:

- cronologia narrativa leggibile;
- dialoghi visualmente distinti;
- campo input multilinea con invio controllato;
- pannello immagine con zoom;
- indicatore della fase corrente del turno;
- scheda personaggio;
- abilità e risorse;
- outfit corrente;
- luogo e tempo;
- NPC presenti;
- thread e missioni attive;
- pulsanti salva/carica/nuova sessione;
- gestione chiara degli errori e possibilità di retry;
- nessun blocco totale dell’interfaccia durante chiamate LLM o rendering.

Usa worker/thread o async in modo sicuro. Tutte le modifiche allo stato devono comunque passare dal servizio applicativo centrale.

---

## Architettura richiesta

Organizza il progetto almeno nei seguenti layer:

```text
src/epos/
  domain/
    models/
    rules/
    services/
    validation/
  application/
    commands/
    turn_service.py
    session_service.py
    dto/
  infrastructure/
    persistence/
    llm/
    renderers/
    logging/
  presentation/
    desktop/
    cli/
  worldpacks/
    loader.py
    schema.py
worlds/
  odyssey_specularis/
tests/
```

Vincoli:

- il dominio non importa GUI, HTTP, provider LLM o filesystem;
- il servizio del turno è l’unico orchestratore del ciclo;
- i provider sono interfacce sostituibili;
- configurazioni e segreti restano fuori dal codice;
- YAML e JSON devono essere validati con schema esplicito;
- usa type hints completi;
- niente singleton globali mutabili;
- niente logica di gioco sparsa nella GUI;
- niente regex come unica base per comprendere missioni o semantica complessa;
- niente `except Exception: pass` salvo casi circoscritti e loggati;
- niente dipendenze circolari.

---

## Robustezza LLM

Implementa una catena di provider configurabile e diagnostica per ogni chiamata:

- provider e modello;
- fase;
- durata;
- numero tentativi;
- risposta grezza sanitizzata;
- errori di parsing;
- errori semantici;
- token quando disponibili;
- fallback usato.

Il parsing deve:

1. accettare solo JSON conforme allo schema;
2. rimuovere esclusivamente wrapper innocui, senza “indovinare” strutture mancanti;
3. distinguere errore sintattico da errore semantico;
4. consentire retry limitato con feedback preciso;
5. non applicare mai una risposta non valida.

Prevedi un `DemoGameMaster` deterministico per test e sviluppo offline.

---

## Persistenza e artefatti

Per ogni sessione salva:

- stato canonico versionato;
- metadati sessione;
- checkpoint del turno in corso;
- input del giocatore;
- snapshot inviato al GM;
- risposta fase 1;
- proposta validata;
- tiro;
- risposta fase 2;
- scena normalizzata;
- mutazioni applicate;
- contratto visivo;
- record renderer;
- diagnostica LLM;
- immagine quando disponibile.

Usa scrittura atomica. Aggiungi `schema_version` e migrazioni. Il salvataggio deve poter essere ricaricato dopo crash senza perdita o doppia applicazione del turno.

---

## Test obbligatori

Non considerare conclusa una funzione senza test.

Crea almeno:

### Unit test

- calcolo pool e risultati;
- mutazioni valide e invalide;
- relazioni e limiti;
- memoria e testimoni;
- outfit e conflitti di slot;
- knowledge provenance;
- thread narrativi;
- missioni e pressioni;
- normalizzazione ID;
- policy narrativa;
- regia visiva.

### Contract test

- parsing di tutte le risposte GM;
- rifiuto di JSON incompleto;
- rifiuto di speaker del giocatore inventato;
- rifiuto di NPC assente;
- rifiuto di conoscenza impossibile;
- rifiuto di retcon;
- rifiuto di outfit incoerente;
- retry semantico limitato.

### Integration test

- turno senza prova;
- turno con prova e successo;
- turno con fallimento;
- crash dopo il tiro e ripresa da checkpoint;
- fallimento renderer senza perdita del turno;
- salvataggio/caricamento;
- avanzamento missione;
- cambio luogo;
- iniziativa NPC;
- divulgazione vera e menzogna.

### Scenario test

Crea una campagna deterministica breve di Odissea Specularis che attraversi almeno:

1. risveglio/osservazione senza prova arbitraria;
2. incontro con Polifemo;
3. inganno con prova;
4. conseguenza persistente;
5. cambio di luogo;
6. ritorno a una questione aperta dopo vari turni;
7. generazione del contratto visivo coerente.

La suite deve essere eseguibile con un unico comando e non dipendere da API esterne.

---

## Modalità di lavoro obbligatoria

Non riscrivere tutto in una sola passata.

Procedi in questo ordine:

### Fase 0 — Audit

- elenca struttura e responsabilità attuali;
- identifica funzioni valide da preservare;
- trova duplicazioni, accoppiamenti, bug e rischi;
- ricostruisci il flusso reale del turno;
- produci una mappa “stato attuale → architettura obiettivo”.

Non modificare codice durante l’audit.

### Fase 1 — Contratti e dominio

- definisci modelli canonici;
- definisci schemi GM e visual;
- definisci regole e validatori;
- scrivi test del dominio.

### Fase 2 — Turn service

- implementa pipeline completa;
- checkpoint e commit atomico;
- retry controllati;
- test integrazione.

### Fase 3 — World-pack

- migra Odissea Specularis;
- valida YAML;
- implementa missioni e pressioni;
- test scenario.

### Fase 4 — LLM e prompt

- snapshot compatto;
- prompt separati per proposta e narrazione;
- provider chain;
- diagnostica.

### Fase 5 — Regia visiva

- contratto visuale;
- director deterministico;
- adapter renderer;
- retry render separato.

### Fase 6 — GUI

- integra soltanto API applicative stabili;
- evita logica di dominio nell’interfaccia;
- aggiungi gestione asincrona e stato di avanzamento.

A ogni fase:

1. indica file creati e modificati;
2. spiega le decisioni importanti;
3. esegui test mirati;
4. esegui poi l’intera suite;
5. riporta risultati reali;
6. non dichiarare completato ciò che non hai testato.

---

## Output iniziale che devi fornire

Dopo aver letto tutto il repository, rispondi inizialmente soltanto con:

1. **Comprensione del gioco attuale**;
2. **Flusso reale del turno**;
3. **Punti forti da conservare**;
4. **Problemi tecnici e di game design**;
5. **Architettura obiettivo**;
6. **Piano di migrazione incrementale**;
7. **Elenco dei primi test da scrivere**;
8. **Domande bloccanti reali**, solo se non risolvibili dal repository.

Non generare ancora centinaia di file. Non alterare il canone. Non eliminare funzionalità senza segnalarlo. Non affermare che qualcosa funziona se non hai eseguito i test.

---

## Criteri di accettazione finali

Il progetto è accettabile solo quando:

- il giocatore può completare turni in input libero;
- l’autonomia del giocatore è protetta da test;
- gli NPC mostrano iniziativa e memoria individuale;
- le prove sono risolte soltanto da Python;
- lo stato non si corrompe dopo errori;
- outfit, luogo, condizioni e conoscenze restano coerenti;
- le missioni avanzano per eventi canonici, non per coincidenze testuali fragili;
- ogni turno produce artefatti diagnostici;
- il rendering è disaccoppiato dal commit narrativo;
- Odissea Specularis è giocabile senza codificare la campagna dentro il motore;
- tutti i test automatici passano;
- la documentazione consente a un altro sviluppatore di comprendere e avviare il progetto.

