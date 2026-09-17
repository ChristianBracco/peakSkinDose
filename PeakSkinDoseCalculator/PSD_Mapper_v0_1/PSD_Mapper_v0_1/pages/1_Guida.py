"""Guida spaziale interattiva: come il PSD Mapper ricostruisce la dose cutanea.

Pagina Streamlit con figure generate dal codice reale (guide_figures) e
spiegazioni dettagliate di algoritmo e formule, basate sugli articoli:
  - Johnson & Bolch, Med. Phys. 38(10), 2011.
  - Krajinović et al., J. Appl. Clin. Med. Phys. 22(11), 2021 (SkinCare).
"""
from __future__ import annotations
import streamlit as st
import guide_figures as gf

st.set_page_config(page_title="HELP PSD Mapper", layout="wide")

st.title("Guida al PSD Mapper")
st.caption(
    "Come si passa dagli eventi di irraggiamento del report Excel alla mappa di dose "
    "cutanea e alla Peak Skin Dose (PSD). Modello dosimetrico e geometrico basato su "
    "Johnson & Bolch (2011) e Krajinović et al. (2021, SkinCare)."
)

with st.expander("Indice", expanded=True):
    st.markdown(
        "1. Cos'è la PSD e da dove partiamo\n"
        "2. La formula della dose cutanea\n"
        "3. Il sistema di riferimento e il paziente\n"
        "4. Dagli angoli del tubo alla direzione del fascio\n"
        "5. Il movimento del lettino\n"
        "6. La piramide del fascio e la dimensione del campo\n"
        "7. Il test 'il punto è nel fascio?' (coordinate del fascio, normale N, test completo)\n"
        "8. La correzione inverse-square\n"
        "9. I fattori di correzione (CF, TAF, Fθ, BSF, MEAC)\n"
        "10. Dalla mappa planare all'ellissoide\n"
        "11. Individuazione della PSD\n"
        "12. Cosa fa il codice, funzione per funzione\n"
        "13. Limiti e commissioning"
    )

# ---------------------------------------------------------------------------
st.header("1. Cos'è la PSD e da dove partiamo")
st.markdown(
    """
La **Peak Skin Dose (PSD)** è la dose massima ricevuta da un singolo punto della
pelle del paziente durante l'intera procedura interventistica. È il parametro
clinicamente rilevante per il rischio di reazioni cutanee deterministiche
(eritema, epilazione, necrosi), perché ciò che conta non è la dose *totale*
distribuita sul corpo, ma quanto si accumula nel **punto più esposto**.

Il nostro punto di partenza è il **report strutturato dettagliato** in Excel: ogni
riga è un *evento di irraggiamento*, cioè una singola pressione del pedale di
fluoroscopia o una singola acquisizione. Per ogni evento conosciamo:

- il **kerma in aria al punto di riferimento** `Ka,r` (colonna *Kerma in Aria* o
  *KAP*, in Gy) — quanta radiazione è stata erogata;
- gli **angoli del tubo**: primario α (LAO/RAO) e secondario β (CRA/CAU);
- la **posizione del lettino**: laterale, altezza, longitudinale;
- le **distanze**: sorgente-isocentro (SOD) e sorgente-detettore (SID);
- il **DAP** (prodotto dose-area), da cui ricaviamo la dimensione del campo.

Come scrivono Johnson & Bolch, il sistema funziona *"traducendo il reference point
air kerma alla posizione della pelle del paziente"*, rappresentata da un modello
computazionale (Johnson & Bolch, 2011).

L'idea, in una frase: **per ogni evento proiettiamo geometricamente il fascio sul
modello del paziente, calcoliamo quanta dose arriva a ciascun punto di pelle
colpito, e sommiamo su tutti gli eventi. Il massimo della somma è la PSD.**
"""
)

# ---------------------------------------------------------------------------
st.header("2. La formula della dose cutanea")
st.markdown(
    "Per ogni evento, la dose depositata in un punto di pelle segue l'equazione "
    "fondamentale dello skin dose mapping (Krajinović 2021, Eq. 1):"
)
st.latex(
    r"D \;=\; K_{a,r}\,\cdot\, CF \,\cdot\, TAF \,\cdot\, F_{\theta}\,\cdot\,"
    r"\left(\dfrac{d_{IRP}}{d_{patient}}\right)^{2}\,\cdot\, BSF \,\cdot\, MEAC"
)
st.markdown(
    r"""
dove:

| Simbolo | Significato | Ruolo |
|---|---|---|
| $K_{a,r}$ | kerma in aria al punto di riferimento interventistico (IRP) | dato di input dell'evento |
| $CF$ | fattore di calibrazione del $K_{a,r}$ | corregge la lettura strumentale |
| $TAF$ | *table attenuation factor* (trasmissione tavolo+materassino a 0°) | attenuazione del supporto |
| $F_{\theta}$ | fattore obliquo | attenuazione extra del supporto ad angolo |
| $\left(d_{IRP}/d_{patient}\right)^2$ | correzione inverse-square | riporta il kerma dal punto di rif. alla pelle |
| $BSF$ | *backscatter factor* | aggiunge la retrodiffusione dal paziente |
| $MEAC$ | rapporto coeff. assorbimento massico aria→tessuto | converte kerma in aria in dose al tessuto |

La **PSD** è quindi il massimo, su tutta la superficie campionata, della somma dei
contributi di tutti gli eventi:
"""
)
st.latex(
    r"\mathrm{PSD} \;=\; \max_{(\theta,\,z)}\ \sum_{e\,\in\,\text{eventi}} D_{e}(\theta, z)"
)
st.info(
    "Nel codice i fattori costanti sono raggruppati in `Corrections.product` "
    "(= BSF · MEAC · TAF · CF), mentre l'inverse-square e Fθ, che dipendono dal "
    "singolo punto/evento, sono applicati separatamente nel ciclo di calcolo."
)

# ---------------------------------------------------------------------------
st.header("3. Il sistema di riferimento e il paziente")
c1, c2 = st.columns([1.05, 1])
with c1:
    st.pyplot(gf.fig_reference_frame(), clear_figure=True)
with c2:
    st.markdown(
        """
Usiamo una terna cartesiana centrata sull'**isocentro** dell'arco a C:

- **x** — asse *laterale* (larghezza del paziente);
- **y** — asse *antero-posteriore* (spessore); alla proiezione neutra 0°/0° la
  sorgente è **sotto** il paziente supino e il fascio punta da posteriore verso
  anteriore, cioè verso $+y$;
- **z** — asse *longitudinale* (cranio-caudale).

Il paziente supino è modellato come un **cilindro a sezione ellittica**: un'ellisse
di semiassi $a = \\text{larghezza}/2$ (laterale) e $b = \\text{spessore}/2$ (AP),
estrusa lungo $z$. È l'approccio dei "modelli semplificati" citato negli articoli
come base geometrica prima dei modelli antropomorfi più realistici.

L'ellisse cattura il fatto che il tronco è più largo che profondo: la distanza
fuoco-pelle cambia molto tra proiezioni AP e laterali, e questo pesa sulla dose
tramite l'inverse-square.
"""
    )

# ---------------------------------------------------------------------------
st.header("4. Dagli angoli del tubo alla direzione del fascio")
st.markdown(
    "Dai due angoli del tubo costruiamo il **versore di propagazione** del fascio "
    "(dal fuoco verso il detettore):"
)
st.latex(
    r"\mathbf{d} = \big(\sin\alpha\,\cos\beta,\;\; \cos\alpha\,\cos\beta,\;\; \sin\beta\big)"
)
st.markdown(
    """
Verifica dei casi limite (utile per capire le convenzioni):

- $\\alpha=0,\\ \\beta=0 \\Rightarrow \\mathbf{d}=(0,1,0)$: fascio dritto verso l'alto,
  proiezione postero-anteriore. ✔
- $\\alpha \\ne 0$: rotazione nel **piano assiale** $x$–$y$ (obliquità LAO/RAO). ✔
- $\\beta \\ne 0$: inclinazione fuori dal piano assiale, cranio-caudale (CRA/CAU). ✔

Insieme a $\\mathbf{d}$ definiamo due assi ortonormali del **piano del campo**,
$\\mathbf{e}_1$ ed $\\mathbf{e}_2$, che serviranno a misurare quanto un punto è
dentro o fuori dal rettangolo del fascio:
"""
)
st.latex(r"\mathbf{e}_1 = (\cos\alpha,\; -\sin\alpha,\; 0), \qquad \mathbf{e}_2 = \mathbf{e}_1 \times \mathbf{d}")
st.markdown(
    "La terna $\\{\\mathbf{e}_1, \\mathbf{e}_2, \\mathbf{d}\\}$ è destrorsa: "
    "$\\mathbf{d}$ è la profondità, $\\mathbf{e}_1$ ed $\\mathbf{e}_2$ il piano trasversale. "
    "Questa è esattamente la funzione `_beam_axes` del motore."
)
_gc = st.columns([1, 6, 1])[1]
_gc.pyplot(gf.fig_beam_direction(), clear_figure=True, use_container_width=True)

# ---------------------------------------------------------------------------
st.header("5. Il movimento del lettino")
c1, c2 = st.columns([1, 1.05])
with c1:
    st.pyplot(gf.fig_table_motion(), clear_figure=True)
with c2:
    st.markdown(
        """
Il tubo è fisso sull'arco a C; è il **paziente sul lettino** che si muove. Nel
modello convertiamo le posizioni del tavolo in uno spostamento $\\mathbf{q}$ della
geometria del fascio rispetto al paziente:
"""
    )
    st.latex(
        r"""\mathbf{q} = \begin{pmatrix}
        s_{lat}\,(lat - lat_{rif}) + o_x \\
        s_{h}\,(h - h_{rif}) + o_y \\
        s_{lon}\,(lon - lon_{rif}) + o_z
        \end{pmatrix}"""
    )
    st.markdown(
        """
- $lat_{rif}, h_{rif}, lon_{rif}$ sono le **mediane non nulle** delle posizioni del
  tavolo in quella procedura (il tavolo "a riposo" del caso);
- $s_{lat}, s_h, s_{lon} \\in \\{-1, +1\\}$ sono i **segni** delle convenzioni di
  movimento (da fissare in commissioning);
- $o_x, o_y, o_z$ sono offset opzionali del paziente rispetto all'isocentro.

La **sorgente** (fuoco) è poi a distanza SOD dall'isocentro, nella direzione
opposta a $\\mathbf{d}$:
"""
    )
    st.latex(r"\text{sorgente} = \mathbf{q} - SOD\,\cdot\,\mathbf{d}")

st.warning(
    "I segni delle assi e gli offset sono i parametri più delicati: vanno "
    "calibrati con esposizioni note (AP e oblique) prima di fidarsi della posizione "
    "della mappa. Krajinović nota che l'orientamento del modello è assunto supino e "
    "centrato sul tavolo."
)

# ---------------------------------------------------------------------------
st.header("6. La piramide del fascio e la dimensione del campo")
c1, c2 = st.columns([1, 1])
with c1:
    st.pyplot(gf.fig_pyramid(), clear_figure=True)
with c2:
    st.markdown(
        """
Ogni evento è rappresentato come una **piramide a quattro lati** (four-sided
projection pyramid, Johnson & Bolch): apice nel fuoco, base rettangolare al
**piano di riferimento** (IRP), posto a distanza
"""
    )
    st.latex(r"d_{IRP} = SOD - \text{offset}_{rif} \quad (\text{default } 150\ \text{mm})")
    st.markdown(
        """
Le dimensioni della base $w_{rif} \\times h_{rif}$ vengono ricavate, in ordine di
priorità:

1. **Da DAP / Ka,r** (metodo preferito). Poiché per definizione
   $DAP = K_{a,r}\\times \\text{Area}$:
"""
    )
    st.latex(r"\text{Area}_{rif}\,[\text{mm}^2] = \dfrac{DAP}{K_{a,r}}\times 100, \qquad w_{rif}=h_{rif}=\sqrt{\text{Area}_{rif}}")
    st.markdown(
        """
   (con DAP in Gy·cm² e Ka,r in Gy, il rapporto è in cm² → ×100 per mm²;
   il rapporto d'aspetto è preso dalla collimazione se presente, altrimenti quadrato).
2. **Da colonne di collimazione** proiettate al piano di riferimento:
   $w_{rif} = w_{det}\\cdot d_{IRP}/SID$.
3. **Collimazione fissa** configurabile (fallback finale).
"""
    )
st.success(
    "Nei report allegati non ci sono colonne di collimazione, quindi il metodo 1 "
    "(DAP/Ka,r) è quello effettivamente usato — coerente con la letteratura, che "
    "ricava la geometria del campo dai dati dosimetrici quando la collimazione non è nota."
)

# ---------------------------------------------------------------------------
st.header("7. Il test: 'il punto è nel fascio?'")
st.markdown(
    r"""
Fin qui abbiamo costruito, per ogni evento, la geometria del fascio: la posizione
della **sorgente**, la direzione $\mathbf{d}$ e i due assi trasversali
$\mathbf{e}_1, \mathbf{e}_2$ (§4), più le dimensioni della base della piramide
$w_{rif}, h_{rif}$ (§6). Ora dobbiamo rispondere, per **ogni singolo punto della
pelle**, a una domanda binaria: *quel punto viene colpito da questo fascio, sì o no?*

Se la risposta è sì, quel punto riceverà una dose (che calcoleremo con
l'inverse-square, §9). Se è no, questo evento non contribuisce a quel punto.

### 7.1 Portare il punto nel riferimento del fascio

Il modo più pulito per fare il test è smettere di ragionare nelle coordinate del
mondo $(x, y, z)$ e passare alle coordinate **del fascio**. Preso un punto di pelle
$\mathbf{P}$, calcoliamo il vettore che va dalla sorgente al punto:
"""
)
st.latex(r"\mathbf{V} = \mathbf{P} - \text{sorgente}")
st.markdown(
    r"""
Poi proiettiamo $\mathbf{V}$ sui tre assi del fascio. Ognuna delle tre proiezioni
ha un significato geometrico preciso:
"""
)
st.latex(
    r"""\underbrace{t = \mathbf{V}\cdot\mathbf{d}}_{\text{profondità lungo il fascio}}
    \qquad
    \underbrace{u = \mathbf{V}\cdot\mathbf{e}_1}_{\text{scarto in larghezza}}
    \qquad
    \underbrace{v = \mathbf{V}\cdot\mathbf{e}_2}_{\text{scarto in altezza}}"""
)
st.markdown(
    r"""
- $t$ dice **quanto è lontano il punto dal fuoco**, misurato lungo l'asse del fascio;
- $u$ e $v$ dicono **quanto il punto è spostato lateralmente** rispetto all'asse
  centrale, nelle due direzioni trasversali.

La figura mostra questa scomposizione nel piano $\mathbf{d}$–$\mathbf{e}_1$ (per
l'altra direzione, $v$, vale lo stesso ragionamento):
"""
)
_gc = st.columns([1, 5, 1])[1]
_gc.pyplot(gf.fig_beam_coordinates(), clear_figure=True, use_container_width=True)

st.markdown(
    r"""
### 7.2 Il cono si allarga con la profondità

La piramide ha apice nel fuoco e base $w_{rif}\times h_{rif}$ al piano di
riferimento, che si trova a profondità $t = d_{IRP}$. Per triangoli simili, a una
profondità generica $t$ la sezione del fascio è scalata dal fattore $t/d_{IRP}$.
Quindi la **semi-apertura** del campo a profondità $t$ vale:
"""
)
st.latex(
    r"\text{semi-larghezza}(t) = 0.5\,w_{rif}\,\dfrac{t}{d_{IRP}}, \qquad "
    r"\text{semi-altezza}(t) = 0.5\,h_{rif}\,\dfrac{t}{d_{IRP}}"
)
st.markdown(
    r"""
Vicino al fuoco (t piccolo) il campo è stretto; più ci si allontana, più si allarga.
La sezione trasversale a una data profondità è un **rettangolo**: il punto è dentro
il fascio se le sue coordinate trasversali $(u, v)$ cadono dentro quel rettangolo.
"""
)
_gc = st.columns([2, 3, 2])[1]
_gc.pyplot(gf.fig_inside_test(), clear_figure=True, use_container_width=True)

st.markdown(
    r"""
### 7.3 La normale alla superficie $\mathbf{N}$

Manca un ultimo ingrediente. Un fascio che attraversa il paziente incontra la
superficie **due volte**: una all'ingresso (lato rivolto alla sorgente) e una
all'uscita (lato opposto). Per la dose cutanea ci interessa solo l'**entrata**.

Per distinguerle usiamo la **normale esterna** $\mathbf{N}$: il vettore unitario
perpendicolare alla superficie del paziente in quel punto, che punta **verso
l'esterno** del corpo. Per il cilindro ellittico ha una forma analitica semplice
(gradiente dell'ellisse, normalizzato):
"""
)
st.latex(
    r"\mathbf{N} = \text{normalizza}\!\left(\dfrac{\cos\theta}{a},\; "
    r"\dfrac{\sin\theta}{b},\; 0\right)"
)
st.markdown(
    r"""
Il **segno del prodotto scalare** $\mathbf{N}\cdot\mathbf{d}$ ci dice da che parte
siamo:

- $\mathbf{N}\cdot\mathbf{d} < 0$ → la normale è **opposta** al fascio: la superficie
  guarda verso la sorgente. È la faccia di **entrata**. ✔
- $\mathbf{N}\cdot\mathbf{d} > 0$ → la normale è **concorde** col fascio: superficie
  di **uscita**. ✘ (scartata)
"""
)
_gc = st.columns([2, 3, 2])[1]
_gc.pyplot(gf.fig_surface_normal(), clear_figure=True, use_container_width=True)

st.markdown(
    r"""
### 7.4 Il test completo

Mettendo insieme i tre ingredienti — profondità, scarto trasversale, e lato di
entrata — un punto è **irraggiato** da un evento se e solo se soddisfa
simultaneamente tutte queste condizioni:
"""
)
st.latex(
    r"""\begin{cases}
    t > 0 & \text{il punto è davanti alla sorgente (non dietro)} \\[4pt]
    \mathbf{N}\cdot\mathbf{d} < 0 & \text{è sulla superficie di entrata} \\[4pt]
    |u| \le 0.5\,w_{rif}\,\dfrac{t}{d_{IRP}} & \text{sta dentro la larghezza del cono} \\[6pt]
    |v| \le 0.5\,h_{rif}\,\dfrac{t}{d_{IRP}} & \text{sta dentro l'altezza del cono}
    \end{cases}"""
)
st.markdown(
    r"""
Le ultime due disuguaglianze sono, in pratica, l'intersezione del punto con le
**quattro facce** della piramide (Johnson & Bolch): il punto è nel campo se, alla
sua profondità $t$, le coordinate trasversali stanno dentro il rettangolo che il
cono ritaglia. Nel codice queste quattro condizioni sono valutate in blocco,
vettorialmente, su tutti i punti della griglia in una volta sola (variabile
`inside` in `calculate_map`).
"""
)
st.info(
    "Riassunto: **t** filtra in profondità, **N·d** sceglie la faccia di entrata, "
    "**u** e **v** verificano che il punto sia dentro il rettangolo del campo a "
    "quella profondità. Solo i punti che passano tutti e quattro i controlli "
    "ricevono dose da quell'evento."
)

# ---------------------------------------------------------------------------
st.header("8. La correzione inverse-square")
st.markdown(
    """
Il $K_{a,r}$ è misurato al **punto di riferimento**, a distanza $d_{IRP}$ dal
fuoco. Per un punto di pelle a distanza $t$ dal fuoco (la profondità calcolata
sopra), la legge dell'inverso del quadrato riporta il kerma alla posizione reale:
"""
)
st.latex(r"D \;\propto\; K_{a,r}\,\left(\dfrac{d_{IRP}}{t}\right)^{2}")
c1, c2 = st.columns([1.2, 1])
with c1:
    st.pyplot(gf.fig_inverse_square(), clear_figure=True)
with c2:
    st.markdown(
        """
- Se la pelle è **più vicina** al fuoco del punto di riferimento ($t < d_{IRP}$), il
  fattore è $>1$: la dose cutanea **supera** il $K_{a,r}$.
- Se è **più lontana** ($t > d_{IRP}$), il fattore è $<1$.

È il motivo per cui la geometria conta tanto: due eventi con lo stesso $K_{a,r}$
ma proiezioni diverse depositano dosi cutanee molto diverse, perché cambia la
distanza fuoco-pelle.
"""
    )

# ---------------------------------------------------------------------------
st.header("9. I fattori di correzione")
st.markdown(
    """
Oltre all'inverse-square, la dose viene moltiplicata per una serie di fattori,
tutti configurabili nella pagina principale:

- **$CF$ — calibrazione del $K_{a,r}$.** L'RDSR fornisce un unico $CF$ che corregge
  il kerma dichiarato contro le misure di controllo qualità. La tolleranza normativa
  sul $K_{a,r}$ visualizzato può arrivare al ±35% sopra 100 mGy, quindi il $CF$ è
  tutt'altro che trascurabile (Krajinović 2021, riformulato).
- **$TAF$ — table attenuation factor.** Trasmissione di tavolo + materassino a
  incidenza normale. In letteratura valori a 0° per tavolo+materassino spaziano
  circa 0.59–0.89 tra sistemi diversi: un fattore molto influente e non definito
  nell'RDSR (Krajinović 2021, riformulato).
- **$F_\\theta$ — fattore obliquo.** Quando il fascio attraversa il supporto ad
  angolo, il cammino nel materiale cresce con $1/\\cos\\theta$. Modelliamo la
  trasmissione obliqua come $TAF^{1/\\cos\\theta}$, quindi il fattore relativo
  rispetto a 0° è:
"""
)
st.latex(r"F_{\theta} = TAF^{\left(\frac{1}{\cos\theta_{inc}} - 1\right)}")
st.markdown(
    """
  Solo i fasci che entrano da sotto (che attraversano il tavolo) hanno
  $F_\\theta \\ne 1$; per gli altri $F_\\theta = 1$.
- **$BSF$ — backscatter factor.** Aggiunge la radiazione retrodiffusa dai tessuti
  sottostanti, che incrementa la dose in superficie.
- **$MEAC$ — rapporto dei coefficienti di assorbimento massico** (tessuto/aria):
  converte il kerma in aria in dose assorbita al tessuto molle.

Negli articoli $BSF$ e $MEAC$ sono interpolati dai coefficienti di
**Benmakhlouf et al. (2011)** in funzione della qualità del fascio e della
dimensione del campo. In questo prototipo sono **valori fissi** configurabili: è
la semplificazione principale da superare per l'uso clinico.
"""
)

# ---------------------------------------------------------------------------
st.header("10. Dalla mappa planare all'ellissoide")
st.markdown(
    """
La superficie del cilindro ellittico è campionata da due parametri: l'angolo
circonferenziale $\\theta$ e la posizione longitudinale $z$. Questi sono anche gli
**assi della mappa planare** (il cilindro "srotolato"). Ogni nodo $(\\theta, z)$
corrisponde a un punto 3D e alla sua normale esterna:
"""
)
st.latex(
    r"X = a\cos\theta, \quad Y = b\sin\theta, \quad Z = z; \qquad "
    r"\mathbf{N} = \text{normalizza}\!\left(\tfrac{\cos\theta}{a},\ \tfrac{\sin\theta}{b},\ 0\right)"
)
st.markdown(
    """
La proiezione 3D **non è un secondo calcolo**: è la stessa griglia, con gli stessi
valori di dose, vista in due modi. Srotolando lungo $\\theta$ si ottiene la heatmap
2D; riavvolgendola sull'ellisse si ottiene la superficie 3D. La corrispondenza è
biunivoca:
"""
)
_gc = st.columns([1, 6, 1])[1]
_gc.pyplot(gf.fig_unwrap(), clear_figure=True, use_container_width=True)

# ---------------------------------------------------------------------------
st.header("11. Individuazione della PSD")
st.markdown(
    """
Accumulati i contributi di tutti gli eventi sulla griglia, la dose vive in una
matrice `dose[z, θ]`. Il sistema:

1. trova il **massimo** della matrice → sono le coordinate $(\\theta_{peak}, z_{peak})$;
2. le converte nel punto 3D $(x, y, z)$ e le marca su heatmap e superficie;
3. **rifà il test di appartenenza al fascio solo per quel punto**, evento per
   evento, per elencare quali esposizioni hanno contribuito alla PSD e con quanta
   dose ciascuna (funzione `event_contributions_at_peak`).

Questa tabella dei contributi dice se la PSD è dominata da poche acquisizioni
pesanti o da molte fluoroscopie sullo stesso angolo — informazione preziosa per
ottimizzare il protocollo.
"""
)

# ---------------------------------------------------------------------------
st.header("12. Cosa fa il codice, funzione per funzione")
st.markdown(
    """
| Funzione (`psd_engine.py`) | Cosa fa |
|---|---|
| `load_excel` | Sceglie il foglio giusto, riconosce le colonne (con alias), scarta righe di riepilogo, distingue report dettagliati e cumulativi. |
| `_resolve_columns` | Mappa i nomi logici (`kar`, `alpha`, …) alle colonne reali, gestendo alias come `Kerma in Aria` vs `KAP`. |
| `detect_report_kind` | Decide se il file è *detailed* (mappabile) o *cumulative* (solo totali). |
| `prepare_events` | Trasforma le righe in eventi geometrici: calcola $d_{IRP}$, ricostruisce $w_{rif}, h_{rif}$ (DAP/Ka,r → collimazione → fisso). |
| `_beam_axes` | Costruisce $\\mathbf{d}, \\mathbf{e}_1, \\mathbf{e}_2$ dagli angoli. |
| `make_skin_grid` | Genera la griglia $(\\theta, z)$, i punti 3D e le normali dell'ellisse. |
| `calculate_map` | Cuore del calcolo: per ogni evento applica il test di appartenenza e accumula la dose con inverse-square e fattori. |
| `_oblique_factor` | Calcola $F_\\theta$ per i fasci che attraversano il tavolo. |
| `event_contributions_at_peak` | Ricostruisce l'elenco degli eventi che contribuiscono alla PSD. |
| `field_consistency` | Controllo di qualità: confronta l'area di campo osservata (DAP/Ka,r) con quella proiettata dalla collimazione. |
"""
)
st.code(
    "# nucleo dell'accumulo dose (calculate_map)\n"
    "inside = (t > 0) & (N·d < 0) & (|u| <= 0.5*wref*t/dref) & (|v| <= 0.5*href*t/dref)\n"
    "dose[inside] += kar * (dref / t[inside])**2 * corr.product * f_theta",
    language="python",
)

# ---------------------------------------------------------------------------
st.header("13. Limiti e commissioning")
st.markdown(
    """
Questo è un **prototipo di commissioning/ricerca**, non un sistema dosimetrico
clinicamente validato. Limiti principali, coerenti con quanto discusso negli articoli:

- **Contorno semplificato**: ellisse invece di modello antropomorfo (gli articoli
  mostrano errori più bassi con modelli patient-sculpted).
- **Fattori fissi**: $BSF$ e $MEAC$ dovrebbero dipendere da qualità del fascio e
  dimensione del campo (coefficienti di Benmakhlouf 2011).
- **Posizione relativa**: la posizione anatomica assoluta non è ricavabile in modo
  affidabile dal solo Excel.
- **Convenzioni da fissare**: segni delle assi tavolo e offset del punto di
  riferimento vanno calibrati con esposizioni note.

**Passi di validazione consigliati**: esporre un fantoccio con una proiezione AP e
alcune oblique note, registrare l'export Excel e misurare posizione/dose con film
(XR-RV3 Gafchromic) o dosimetri (OSLD/TLD), quindi bloccare segni, origine del
riferimento e modello di correzione confrontando calcolo e misura.
"""
)

st.divider()
st.caption(
    "Fonti: Johnson PB, Borrego D, Balter S, et al. *Skin dose mapping for "
    "fluoroscopically guided interventions.* Med Phys. 2011;38(10):5490–5499. — "
    "Krajinović M, Kržanović N, Ciraj-Bjelac O. *Vendor-independent skin dose "
    "mapping application for interventional radiology and cardiology.* J Appl Clin "
    "Med Phys. 2021;22(11):144–156. Contenuti degli articoli riformulati per "
    "aderenza alle licenze."
)
