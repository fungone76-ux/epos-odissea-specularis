# RESORT WORLD DESIGN V1

## Stato

Documento canonico di progettazione del nuovo world adulto ambientato in un resort di lusso.

Questo world deve essere aggiunto senza eliminare o modificare il world `odyssey_specularis`.

Il contenuto è ancora in progettazione. Le decisioni confermate vengono consolidate qui progressivamente prima dell'implementazione.

---

## 1. Premessa generale

Il giocatore interpreta un miliardario in vacanza in un resort mediterraneo di lusso.

Il protagonista guida un gruppo internazionale diversificato con interessi in tecnologia, finanza, immobiliare e lusso. Arriva principalmente per una vacanza esclusiva, ma sa che il resort è in difficoltà economica e potrebbe valutarne l'acquisto.

Luna, Stella e Maria sono tutte adulte e lavorano nel servizio VIP del resort come cameriere, accompagnatrici o intrattenitrici professionali. Cercano di guadagnarsi la preferenza del cliente per motivazioni personali differenti.

Le dinamiche adulte possono emergere come conseguenza di relazioni, fiducia, attrazione, scelte e consenso. La ricchezza o il ruolo del protagonista non producono disponibilità automatica.

---

## 2. Protagonista

### Struttura scelta

Via intermedia:

- ruolo e passato economico sono fissi;
- nome, aspetto e abilità vengono personalizzati dal giocatore;
- la personalità non è predefinita;
- il giocatore decide liberamente che impronta dare al miliardario durante la partita.

### Identità economica

Il protagonista controlla un gruppo internazionale diversificato.

### Motivazione iniziale

La vacanza è autentica, ma esiste anche una possibile opportunità di investimento nel resort.

### Conseguenze registrate dal sistema

Il sistema non assegna una personalità al protagonista, ma registra le conseguenze delle sue azioni attraverso:

- fiducia;
- attrazione;
- rispetto;
- sospetto;
- risentimento;
- paura;
- reputazione presso il personale;
- giudizio della direttrice;
- valutazione finale sull'acquisto del resort.

---

## 3. Struttura temporale

### Durata

- sette giorni iniziali;
- possibile estensione segreta del soggiorno;
- ogni giorno è suddiviso in:
  - mattina;
  - pomeriggio;
  - sera;
  - notte.

### Avanzamento del tempo

Sistema misto:

- i dialoghi brevi non consumano automaticamente una fascia;
- attività importanti, appuntamenti, escursioni, missioni e riposo possono far avanzare il tempo;
- dopo troppi turni nella stessa fascia, il mondo procede comunque;
- gli NPC seguono programmi e presenze coerenti con giorno e fascia.

### Nota tecnica

Il motore base possiede turni e `time_phase`, ma non un calendario completo numerato.

L'implementazione dovrà introdurre un runtime specifico del world, senza riscrivere EPOS e senza alterare Odissea, per gestire:

- giorno corrente;
- fascia corrente;
- giorni rimanenti;
- soglie di avanzamento;
- schedule NPC;
- eventi temporali;
- scadenze;
- estensione segreta.

Nome provvisorio del modulo:

```text
src/epos/resort_runtime.py
```

---

## 4. Tono e struttura narrativa

Il tono principale è una miscela equilibrata di:

- vacanza adulta e seduttiva;
- competizione relazionale;
- dramma leggero;
- possibile acquisizione economica del resort.

La parte economica deve avere un peso equilibrato:

- non deve trasformare il gioco in un gestionale;
- deve dare una direzione alla settimana;
- deve influenzare missioni, giudizi e finale;
- la vacanza e le relazioni restano centrali.

Il resort è in difficoltà economica e nasconde alcuni problemi interni, ma non deve esserci un complotto eccessivamente complesso.

Il mistero personale di Luna è il principale elemento più profondo.

---

## 5. Informazioni iniziali degli NPC

- Luna, Stella e Maria sanno che il protagonista è un cliente VIP eccezionalmente importante.
- Non sanno inizialmente che potrebbe acquistare il resort.
- Solo Victoria Hale conosce il possibile interesse economico del protagonista.

Questa asimmetria informativa deve essere rispettata dalla conoscenza canonica degli NPC.

---

## 6. Luna, Stella e Maria

### Rapporto iniziale

Le tre collaborano professionalmente, ma le alleanze sono variabili.

Le scelte del giocatore possono produrre:

- collaborazione;
- amicizia;
- gelosia;
- rivalità;
- alleanze temporanee;
- confidenze;
- favoritismi percepiti;
- thread relazionali aperti.

### Motivazioni differenti

#### Stella

Vuole ottenere una promozione nel servizio VIP internazionale. È la più apertamente ambiziosa e competitiva.

#### Maria

Cerca stabilità economica e professionale. Può avere una responsabilità privata non ancora definita.

#### Luna

Possiede un collegamento personale misterioso con il passato del protagonista.

La natura concreta del collegamento — lettera, fotografia, documento o altra prova — sarà definita in seguito.

### Nota tecnica

Le relazioni numeriche del motore base devono essere usate come conseguenze, non come ordini automatici di comportamento.

Servirà una logica di campagna specifica per:

- gelosia;
- rivalità;
- collaborazione;
- alleanze;
- favoritismi;
- soglie evento;
- reazioni NPC-NPC.

Nome provvisorio del modulo:

```text
src/epos/resort_relationships.py
```

---

## 7. Victoria Hale

### Identità

Nome canonico: **Victoria Hale**.

Ruolo: direttrice del servizio VIP e responsabile operativa del resort.

È adulta, elegante, autoritaria, manipolatrice e pienamente coinvolta nella storia.

### Funzioni narrative

Victoria:

- assegna incarichi e turni;
- coordina il soggiorno del protagonista;
- controlla la qualità del servizio;
- organizza attività ed eventi;
- premia o richiama il personale;
- modifica incarichi, privilegi e bonus;
- alimenta deliberatamente la competizione;
- cerca di impressionare il protagonista;
- vuole favorire l'acquisizione del resort;
- può sviluppare un proprio rapporto con il protagonista;
- può avere missioni e interessi personali.

Le conseguenze disciplinari devono restare coerenti con il contesto lavorativo e narrativo. Eventuali dinamiche adulte richiedono scelta e consenso.

### Rapporto iniziale con le tre donne

- premia Stella per l'iniziativa;
- usa Maria come riferimento professionale;
- considera Luna la più difficile da controllare;
- sfrutta queste differenze per aumentare la competizione.

### Base prompt canonico

Il seguente prompt deve essere conservato come base visiva del personaggio, senza sostituirne arbitrariamente identità o LoRA:

```text
score_9,score_8_up,score_7_up,masterpiece , realistic, zatanna, mature woman, , black hair, long hair,  , cute, huge ass, bottom heavy, wide hips, huge breast,  grey eyes,  pink lips,  ,  <lora:Zatanna_-_DC_Animated_Universe:0.6> <lora:Expressive_H:0.4> <lora:FantasyWorldPonyV2:0.3>
```

Il termine `zatanna` è parte del prompt visivo fornito, ma il personaggio narrativo è Victoria Hale e non il personaggio DC.

---

## 8. Resort

### Stile generale

Resort mediterraneo moderno di lusso.

Principi visivi:

- ambienti esclusivi;
- materiali pregiati;
- vista mare quando appropriata;
- atmosfera moderna, luminosa e raffinata;
- ogni location deve apparire lussuosa;
- evitare ridondanza e sovraccarico dei prompt.

### Ampiezza

Resort compatto con 8–10 location ben utilizzate.

Le location previste sono:

1. suite presidenziale;
2. lobby;
3. ristorante;
4. piscina;
5. spa;
6. spiaggia privata;
7. lounge bar;
8. ufficio di Victoria.

Eventuali nona e decima location saranno valutate solo se realmente utili.

---

## 9. Regola canonica per i prompt ambientali

Ogni location deve avere **soltanto 2 o 3 tag ambientali distintivi**.

Motivazione:

- evitare prompt troppo lunghi;
- non diluire il peso del personaggio;
- facilitare la lettura da parte del modello Stable Diffusion;
- dare priorità a identità, outfit, posa, azione ed espressione.

Composizione prevista del prompt:

```text
qualità generale
+ base prompt canonico del personaggio
+ outfit persistente
+ posa, azione ed espressione
+ 2 o 3 tag ambientali
+ eventuale illuminazione o fascia oraria
+ inquadratura
```

Le zone interne di una stessa location non diventano necessariamente location separate. Possono usare un singolo tag sostitutivo o aggiuntivo, senza accumulare tutti i tag generali.

---

## 10. Location definite

### 10.1 Suite presidenziale

È la base del protagonista nel corpo centrale del resort.

Resta una sola location di mappa, ma comprende diverse zone narrative:

- ingresso privato;
- salotto;
- camera;
- bagno di lusso;
- cabina armadio;
- terrazza vista mare.

Tag ambientali canonici:

```text
modern mediterranean luxury suite, warm elegant interior, sea-view windows
```

Esempi di tag zona, da usare in sostituzione o come unico dettaglio aggiuntivo:

```text
elegant lounge area
luxury hotel bedroom
marble spa bathroom
private sea-view terrace
```

### 10.2 Lobby

Grande, luminosa e lussuosa, con reception moderna e vista sul mare.

Tag ambientali canonici:

```text
luxury resort lobby, marble reception, sea-view glass hall
```

### 10.3 Ristorante

Ristorante elegante vista mare, con servizio raffinato e atmosfera premium.

Tag ambientali canonici:

```text
luxury seaside restaurant, elegant dining room, ocean-view terrace
```

---

## 11. Missioni, dadi e sistemi da utilizzare

Il nuovo world deve sfruttare i sistemi generali disponibili nel programma, inclusi:

- tiri di dado;
- confronti sociali;
- missioni;
- passaggi e progressione di missione;
- relazioni;
- pressioni;
- thread narrativi;
- memoria e conoscenza con provenienza;
- outfit persistenti;
- presenza degli NPC;
- eventi programmati;
- scene e immagini coerenti;
- salvataggio e caricamento.

I dadi possono essere richiesti per:

- comprendere menzogne o esitazioni;
- persuadere o negoziare;
- ottenere fiducia;
- risolvere problemi del resort;
- superare confronti professionali o sociali;
- completare missioni personali;
- scoprire informazioni;
- affrontare imprevisti durante le attività.

Il denaro non deve sostituire automaticamente prove, consenso o conseguenze.

---

## 12. Vincoli di implementazione

1. Non eliminare o alterare `odyssey_specularis`.
2. Creare un world-pack separato.
3. Evitare ID, regole e tracker specifici di Odissea.
4. Aggiungere un launcher separato.
5. Implementare runtime e logiche specifiche solo dove il motore generale non copre il requisito.
6. Conservare compatibilità con salvataggi e test esistenti.
7. Aggiungere test dedicati per calendario, schedule, relazioni, missioni e prompt ambientali.
8. Non implementare prima di aver completato e approvato il design essenziale.

Struttura prevista:

```text
worlds/
├── odyssey_specularis/
└── resort_world/
    ├── world.yaml
    ├── npcs.yaml
    └── visual.yaml
```

Il nome definitivo della cartella e il titolo del world sono ancora da scegliere.

---

## 13. Decisioni ancora da prendere

- titolo definitivo del world;
- nome del resort;
- localizzazione geografica;
- descrizione e tag delle location rimanenti;
- schedule giornaliero degli NPC;
- base prompt canonici di Luna, Stella e Maria da recuperare dalle fonti corrette;
- outfit iniziali e varianti;
- abilità del protagonista;
- missioni principali e personali;
- natura concreta del mistero di Luna;
- responsabilità privata di Maria;
- eventi dei sette giorni;
- condizioni dell'estensione segreta;
- condizioni e finali dell'acquisizione;
- regole esatte di avanzamento temporale;
- titolo e launcher del nuovo world.
