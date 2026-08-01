# RESORT WORLD DESIGN V1 — MISSIONI

## Stato

Addendum canonico al design di **Seven Nights at Azure Crown**. Questo file consolida le decisioni approvate sulle missioni e corregge ogni scelta precedente incompatibile.

## Struttura generale

Il world usa un sistema misto composto da:

- una missione principale;
- quattro missioni personali, una per Stella, Maria, Luna e Victoria;
- piccoli eventi giornalieri opzionali.

Le missioni devono essere chiare, specifiche, misurabili e governate dal runtime Python. La LLM interpreta i personaggi, ma non decide autonomamente avanzamenti, successi, fallimenti o rivelazioni.

## Missione principale

Il protagonista arriva inizialmente per valutare il resort. Durante i sette giorni incontra piccoli problemi di servizio, tensioni interne e una difficoltà economica concreta.

Questi elementi devono restare secondari rispetto a vacanza, relazioni e competizione. Non deve esistere un complotto complesso.

La difficoltà economica concreta è un debito bancario in scadenza. La scadenza cade durante il settimo giorno, così la decisione economica conclusiva coincide con la fine del soggiorno.

Alla fine il protagonista può:

- acquistare il resort;
- rifiutare;
- imporre condizioni;
- proporre una gestione diversa;
- subordinare l'accordo a cambiamenti riguardanti personale e organizzazione.

## Rivelazione delle missioni personali

Sistema misto:

- all'inizio il giocatore percepisce che ciascun NPC desidera qualcosa;
- la missione personale completa si rivela gradualmente;
- fiducia, confidenze, eventi e scelte sbloccano nuovi passaggi;
- gli errori normali complicano o deviano la missione;
- solo decisioni gravi e consapevoli possono chiuderla definitivamente.

## Stella — La promozione internazionale

Obiettivo: ottenere la promozione nel servizio VIP internazionale entro la fine del soggiorno.

Passaggi principali:

- organizzare con successo un'attività importante;
- ricevere almeno una valutazione positiva esplicita dal protagonista;
- dimostrare iniziativa senza compromettere il servizio;
- superare una prova professionale stabilita da Victoria;
- evitare un richiamo grave.

Successo: Victoria approva la candidatura e il protagonista può sostenerla formalmente.

Esito alternativo: Stella riceve una seconda opportunità o una raccomandazione diversa.

Fallimento definitivo: sabotaggio consapevole, grave scorrettezza o perdita totale della fiducia di Victoria.

## Maria — Un futuro stabile

Obiettivo: ottenere entro la fine del soggiorno un contratto stabile e meglio retribuito nel servizio VIP dell'Azure Crown Resort.

Passaggi principali:

- gestire con successo la suite presidenziale;
- risolvere almeno un problema di servizio senza creare tensioni;
- ottenere una valutazione positiva dal protagonista;
- dimostrare affidabilità durante un momento difficile;
- convincere Victoria che merita maggiore responsabilità.

Successo: Maria riceve un contratto stabile con condizioni migliori.

Esito alternativo: ottiene una raccomandazione per un altro incarico nel gruppo del protagonista.

Fallimento definitivo: grave negligenza volontaria o perdita completa della fiducia professionale.

## Luna — Il legame nascosto

Obiettivo: scoprire la verità sul legame tra la propria famiglia e il protagonista.

Oggetto canonico: una vecchia lettera conservata da Luna.

Autore canonico della lettera: il padre del protagonista.

Contenuto canonico:

- la lettera chiede che Luna venga protetta;
- la richiesta riguarda Luna quando era ancora bambina;
- il padre del protagonista aveva un debito morale verso la madre di Luna;
- la madre di Luna lo aveva aiutato durante una grave crisi personale o professionale;
- in cambio egli aveva promesso di proteggere Luna;
- la promessa non fu mantenuta perché il padre del protagonista morì prima di completarla;
- non esistono complotti, sabotaggi o ulteriori livelli nascosti dietro il fallimento della promessa.

La lettera contiene un riferimento, una firma o un dettaglio aziendale riconoscibile ma ambiguo. Non deve rivelare immediatamente tutta la verità.

Principi runtime:

- Luna conosce l'esistenza della lettera;
- non conosce necessariamente il significato completo;
- la LLM non deve rivelarla prima dello sblocco previsto;
- il runtime decide quando può mostrarla, quali passaggi vengono completati e quali informazioni diventano canoniche;
- il prompt della LLM riceve solo lo stato attuale della missione, le conoscenze possedute, i thread rilevanti e i limiti di rivelazione.

Regola architetturale: **Python governa la missione; la LLM interpreta Luna.**

## Victoria — Salvare l'Azure Crown

Obiettivo: convincere il protagonista ad acquistare il resort entro la fine del soggiorno.

Passaggi principali:

- mostrargli i punti di forza reali della struttura;
- gestire senza scandali i problemi di servizio;
- presentargli con trasparenza il debito bancario;
- dimostrare che il personale e l'organizzazione possono funzionare bene;
- ottenere una decisione finale favorevole entro il settimo giorno.

Successo: il protagonista acquista il resort.

Esito alternativo: non acquista immediatamente, ma apre una trattativa concreta o propone condizioni precise.

Fallimento definitivo: il protagonista rifiuta ogni trattativa per gravi inganni, errori o perdita totale di fiducia.
