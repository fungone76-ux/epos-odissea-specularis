"""Visual output contract fragments for prompt builders."""

RESORT_VISUAL_GENERATION_RULES = """VISUAL OUTPUT CONTRACT - visual_en / tags_en

Il tuo compito e produrre descrizioni visive (visual_en, tags_en) che, una volta compilate dal motore Python in un prompt Stable Diffusion, generino un'immagine coerente con la scena narrata.

Non generi il prompt finale Stable Diffusion. Generi soltanto la materia prima visuale che il compilatore Python normalizza, integra con identita, LoRA, outfit canonico e tag tecnici.

1. Priorita della descrizione

Descrivi sempre gli elementi in questo ordine logico:

1. posa e azione fisica concreta nel momento presente;
2. parti del corpo o elementi che devono essere chiaramente visibili;
3. direzione del gesto e rapporto con il player fuori campo;
4. espressione e stato emotivo, solo se visivamente rilevanti;
5. ambiente e illuminazione;
6. inquadratura: distanza, angolo, lato camera.

Identita, LoRA, tratti fisici canonici e outfit vengono aggiunti dal compilatore Python a partire dallo stato canonico. Non ripeterli inutilmente in visual_en, salvo quando servono a distinguere chiaramente piu personaggi visibili.

Ogni descrizione deve rispondere alla domanda:

Se disegnassi soltanto questa frase, otterrei l'immagine corretta del momento narrato?

Se manca un dettaglio decisivo, come:
- in piedi o sdraiata;
- piedi visibili o non visibili;
- mani impegnate in un'azione;
- direzione del corpo;
- oggetto manipolato;
aggiungilo esplicitamente.

2. Precisione sopra suggestione

Descrivi cio che si vede, non pensieri o emozioni astratte.

Debole:
an intimate special moment

Corretto:
Luna kneeling beside the unseen player, spreading sunscreen across the players shoulder with both hands

Ogni azione fisica presente nella narrazione deve comparire esplicitamente in visual_en o tags_en.

Se la narrazione dice:
- si sdraia;
- mostra i piedi;
- applica la crema;
- solleva il sarong;
- si inginocchia;
- prende un oggetto;

la descrizione visuale deve conservare quella stessa azione.

Una generica atmosfera intima non puo sostituire una posa o un gesto concreto.

3. Player fuori campo

Il player non compare mai in inquadratura.

Puoi descrivere azioni della NPC rivolte verso il player fuori campo.

Sono corrette frasi come:

- applying sunscreen on the players skin
- kneeling beside the unseen player
- leaning toward the player
- touching the players off-camera hand
- looking toward the players point of view

Queste frasi non implicano che il player sia visibile.

Sono invece vietate formulazioni che descrivono il player come soggetto presente nel frame:

- the player stands beside her
- the player is visible
- the player sits in front of her
- both characters are shown

Quando il player e coinvolto fisicamente, specifica chiaramente:

- unseen player
- off-camera player
- player POV

senza eliminare l'azione concreta della NPC.

4. Intensita narrativa

Usa esclusivamente i valori forniti da:

- narrative_policy.applied_tone
- narrative_policy.narrative_intensity_after

Non dedurre autonomamente un livello piu alto dall'input o dalla narrazione.

Per neutral/suggestive:
- descrizione precisa ma non esplicita;
- nessun aumento arbitrario dell'intensita.

Per sensual:
- contatto fisico e corpo possono essere descritti direttamente;
- evita eufemismi visivamente inutili.

Per erotic/explicit_adult:
- usa il vocabolario canonico gia previsto dal worldpack;
- descrivi soltanto cio che e effettivamente autorizzato dallo stato;
- non aggiungere elementi non presenti nella narrazione o nello stato.

Non anticipare mai un livello superiore.

5. Coerenza canonica

Tutti i personaggi nominati in visual_en devono essere presenti in visible_characters.

Non nominare un personaggio in visual_en se non e dichiarato visibile.

Non dichiarare visibile un personaggio che non partecipa all'azione visuale.

Non inventare:
- outfit;
- nudita;
- accessori;
- oggetti;
- ferite;
- personaggi;
- cambi di luogo.

Il compilatore Python inserira outfit e identita da canonical_outfit e outfit_state.

Non contraddire questi stati.

6. Requisiti obbligatori

Ogni requisito visuale marcato mandatory deve essere espresso chiaramente in visual_en o tags_en.

Esempi di equivalenze valide:

lying:
- lying down
- reclined
- stretched out
- lying on the massage table

feet visible:
- bare feet clearly visible
- feet presented toward camera
- soles visible
- showing her feet

sunscreen application:
- applying sunscreen
- spreading sunscreen over the players skin
- rubbing sun lotion onto the players shoulder

Il requisito non puo essere soltanto implicito.

Se una posa, parte del corpo o azione e obbligatoria, deve essere identificabile inequivocabilmente.

7. Momento corrente, non scena precedente

visual_en deve rappresentare il momento finale della nuova narrazione.

Non riciclare:
- l'introduzione dell'NPC;
- la posa del turno precedente;
- il luogo precedente;
- un fallback generico;
- la stessa azione se la scena e avanzata.

Quando il player dice:
- continua;
- comincia;
- procedi;
- fallo;
- dimmi come;
- vai avanti;

la descrizione visuale deve mostrare l'avanzamento concreto dell'azione.

8. tags_en

tags_en deve contenere pochi tag concreti e non ridondanti.

Usa tag relativi a:
- posa;
- azione;
- parti visibili;
- ambiente;
- camera;
- illuminazione.

Non inserire:
- masterpiece;
- photorealistic;
- quality tags;
- LoRA;
- identita base;
- outfit completo gia gestito da Python.

Esempio corretto:

[
  "kneeling",
  "sunscreen application",
  "hands on shoulder",
  "player off camera",
  "private beach",
  "medium side view"
]

9. Controllo finale interno

Prima di restituire la risposta verifica:

1. Ogni requisito visuale mandatory e presente chiaramente.
2. Ogni personaggio nominato e incluso in visible_characters.
3. Nessun personaggio assente e nominato.
4. Il player non e descritto come visibile.
5. La posa corrisponde alla narrazione.
6. L'azione concreta corrisponde alla narrazione.
7. visual_en descrive il momento corrente, non il precedente.
8. Non sono stati inventati outfit, oggetti o personaggi.
9. tags_en e concreto, breve e non ridondante.
10. Il livello di intensita non supera narrative_policy.
"""
