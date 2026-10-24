# GemmaCacao 🍫

**Il maître chocolatier che ti guida, a voce, nella degustazione della tua scatola di cioccolatini.**

## Cos'è

Una cioccolateria spedisce a casa una scatola di cioccolatini. Dentro c'è un QR code: inquadrandolo con il telefono si apre GemmaCacao, una piccola app web che trasforma l'apertura della scatola in un'esperienza guidata.

1. **Fai una foto** alla scatola aperta, dall'alto.
2. GemmaCacao **conta i dolcetti** e **riconosce** quali sono, confrontandoli con il catalogo del negozio.
3. Indichi **quanti siete** con un contatore.
4. Inizia la **degustazione a voce**: il maître conosce una persona alla volta (nome e gusti preferiti) e consiglia a ciascuno il dolcetto più adatto, spiegando perché. La foto della scatola resta in alto e mostra chi sta assaggiando cosa.
5. Dopo l'assaggio chiede a ognuno, chiamandolo per nome, com'era. Impara dai commenti, aggiorna il profilo di gusto di ogni persona (lo vedi salvare sullo schermo) e propone il dolcetto successivo.
6. Si continua così finché la scatola è vuota. Alla fine compare un **riepilogo a schede**: per ogni persona i dolcetti assaggiati, i voti, il preferito e i gusti che il maître ha capito.

Si parla come con una persona: niente moduli da compilare. Se c'è rumore si può tenere premuto il pulsante per parlare, oppure scrivere la risposta.

Per il negozio è anche un modo per sapere cosa piace davvero ai clienti: ogni commento viene registrato.

**Non solo cioccolato.** Dalla home, il pulsante **Area negozio** (in alto a destra) apre un login simulato con le credenziali già compilate. Da lì il proprietario trova la **Configurazione** (tipo di attività: cioccolateria, enoteca, caseificio, torrefazione, birrificio…; identità del negozio, guida vocale, catalogo, QR code) e le **Analytics** (andamento delle degustazioni, classifica delle praline più apprezzate, gusti più richiesti, feedback dei clienti). Sono pagine dimostrative: campi e dati non sono collegati.

---

## Architettura

Stack tecnologico, librerie, schemi del sistema e del flusso conversazionale sono in **[ARCHITECTURE.md](ARCHITECTURE.md)**.

In breve: frontend React (PWA), backend FastAPI in Python con LangGraph, Gemma 4 per il linguaggio, ElevenLabs per la voce, YOLOE + CLIP su ONNX Runtime per riconoscere i dolcetti, SQLite + `sqlite-vec` come database.

---

## Come usarlo

**Prerequisiti:** [uv](https://docs.astral.sh/uv/), Node 20 o superiore, una key ElevenLabs e una key di Google AI Studio.

```bash
# 1. Chiavi (file esclusi da git)
npx -y @elevenlabs/cli@latest onboard init   # salva ELEVENLABS_API_KEY in .env.local
cp backend/.env.example backend/.env         # GOOGLE_API_KEY (+ opzionale GOOGLE_API_KEY_FALLBACK)

# 2. Installazione e catalogo demo
make setup

# 3. Avvio (backend su :8000, frontend su :5173)
make dev
```

Poi:

1. Apri <http://localhost:5173/s/demo>: è la pagina che aprirebbe il QR code.
2. Premi **Scatta una foto** e scegli `img/scatola_aperta.jpg`.
3. Premi **Avanti**, scegli quanti siete, poi **Inizia la degustazione** e rispondi a voce.
4. Per chiudere prima della fine, premi **Concludi degustazione**: il maître ringrazia e compare il riepilogo di quanto raccolto fino a lì.

Altri comandi: `make test` (test), `make lint` (controlli), `make seed` (ricarica il catalogo).

> Nomi, note di degustazione e allergeni del catalogo demo sono dati di esempio ricavati da `img/descrizioni_dolci.txt`: vanno verificati con la cioccolateria.

---

## Presentazione

In `presentation/index.html` ci sono le 5 slide che introducono la demo: copertina, problema, soluzione, architettura e passaggio alla demo live. È un unico file HTML, senza build né dipendenze.

```bash
open presentation/index.html        # macOS (su Linux: xdg-open)
```

| Tasto | Azione |
|---|---|
| `→` `↓` `Spazio` / clic a destra | slide successiva |
| `←` `↑` / clic a sinistra | slide precedente |
| `F` | schermo intero |
| `N` | mostra/nasconde le note per lo speaker |

L'indirizzo ricorda la slide aperta (`index.html#4` apre l'architettura). I font arrivano da Google Fonts: senza connessione le slide funzionano comunque, con Georgia e Arial al loro posto.
