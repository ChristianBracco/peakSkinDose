# Guida spaziale al PSD Mapper

Guida al funzionamento geometrico e dosimetrico del sistema: come si passa dagli
eventi di irraggiamento del report Excel alla **Peak Skin Dose (PSD)** e alla mappa
di dose sulla superficie del paziente.

Riferimenti di letteratura:
- Johnson PB, Borrego D, Balter S, Johnson K, Siragusa D, Bolch WE. *Skin dose mapping for fluoroscopically guided interventions.* Med Phys. 2011;38(10):5490–5499. doi:10.1118/1.3633935.
- Krajinović M, Kržanović N, Ciraj-Bjelac O. *Vendor-independent skin dose mapping application for interventional radiology and cardiology.* J Appl Clin Med Phys. 2021;22(2):145–157. doi:10.1002/acm2.13167.

---

## 1. Idea generale del sistema

Ogni riga del report dettagliato è un **evento di irraggiamento** (una pressione del
pedale). Per ogni evento il sistema conosce:

- il kerma in aria al punto di riferimento (`Ka,r`, colonna *Kerma in Aria*, in Gy);
- gli angoli del tubo (primario LL = α, secondario AP = β);
- la posizione del tavolo (laterale, altezza, longitudinale);
- le distanze sorgente-isocentro (SOD) e sorgente-detettore (SID);
- il DAP (per ricostruire la dimensione del campo).

Il flusso è:

```
Evento Excel
   │  (1) ricostruzione geometria fascio: sorgente, direzione, dimensioni campo
   ▼
Piramide a 4 lati (apice = fuoco, base = piano di riferimento)
   │  (2) intersezione con il modello del paziente (cilindro ellittico)
   ▼
Punti di pelle "colpiti" dal fascio
   │  (3) dose = Ka,r · correzioni · inverse-square
   ▼
Accumulo su tutti gli eventi  →  mappa 2D (θ, z) e superficie 3D
   │  (4) massimo della mappa
   ▼
PSD (Peak Skin Dose)
```

---

## 2. La formula della PSD

La dose depositata da un evento su un punto di pelle segue il modello della
letteratura (SkinCare, Eq. 1):

```
Dose = Ka,r · CF · TAF · Fθ · (d_IRP / d_paziente)² · BSF · MEAC
```

| Simbolo | Significato | Dove nel codice |
|---|---|---|
| `Ka,r` | Kerma in aria al punto di riferimento (IRP) | `e["kar"]` |
| `CF` | Fattore di calibrazione del Ka,r | `Corrections.kar_calibration` |
| `TAF` | Trasmissione di tavolo + materassino a 0° | `Corrections.support_transmission` |
| `Fθ` | Fattore obliquo (attenuazione extra ad angolo) | `_oblique_factor(...)` |
| `(d_IRP/d_paz)²` | Correzione inverse-square dal punto di rif. alla pelle | `(e["dref"] / t)**2` |
| `BSF` | Fattore di backscatter | `Corrections.bsf` |
| `MEAC` | Rapporto coeff. assorbimento aria→tessuto | `Corrections.tissue_f` |

Nel codice i fattori costanti sono raggruppati in `Corrections.product` (= BSF · MEAC ·
TAF · CF), mentre inverse-square e Fθ dipendono dal singolo punto/evento e sono
applicati separatamente:

```python
dose[inside] += e["kar"] * (e["dref"] / t[inside])**2 * corr.product * f_theta
```

La **PSD** è il valore massimo della dose accumulata su tutta la griglia di pelle,
sommando i contributi di *tutti* gli eventi:

```
PSD = max over (θ, z) di  Σ_eventi Dose_evento(θ, z)
```

### 2.1 Il termine inverse-square in dettaglio

`Ka,r` è misurato al **punto di riferimento interventistico (IRP)**, che si trova a
distanza fissa `d_IRP` dal fuoco lungo l'asse del fascio:

```
d_IRP = SOD − offset_riferimento         (nel codice: e["dref"])
```

dove `offset_riferimento` (default 150 mm) porta il punto dall'isocentro verso la
sorgente, come da convenzione IEC per l'IRP.

Per un punto di pelle a distanza `t` dal fuoco (misurata lungo l'asse del fascio),
la legge dell'inverso del quadrato dà:

```
Dose(t) ∝ Ka,r · (d_IRP / t)²
```

Se la pelle è più vicina al fuoco del punto di riferimento (`t < d_IRP`), il fattore
è > 1 e la dose cutanea supera il Ka,r; se è più lontana, è < 1.

### 2.2 Il fattore obliquo Fθ

Solo i fasci che entrano **da sotto** il paziente (proiezioni postero-anteriori)
attraversano tavolo e materassino. Per questi, il cammino nel supporto cresce con
`1/cos(θ_inc)`, dove `θ_inc` è l'angolo rispetto alla normale del tavolo. La
trasmissione a angolo obliquo diventa `TAF^(1/cosθ)`, quindi il fattore relativo
rispetto all'incidenza normale è:

```
Fθ = TAF^(1/cos(θ_inc) − 1)
```

Nel modello, `cos(θ_inc)` è la componente della direzione del fascio lungo l'asse
verticale (+y). Fasci laterali o dall'alto non attraversano il supporto → `Fθ = 1`.

---

## 3. Sistema di riferimento e geometria del fascio

### 3.1 Assi del mondo

Il sistema usa una terna cartesiana centrata sull'isocentro:

```
        +y (AP, anteriore)
         │
         │
         └───── +x (laterale)
        /
      +z (longitudinale, testa-piedi)
```

- **x**: laterale (larghezza del paziente)
- **y**: antero-posteriore (spessore); a 0°/0° la sorgente è **sotto** il paziente
  supino e il fascio punta posteriore→anteriore, cioè verso +y
- **z**: longitudinale (asse cranio-caudale)

### 3.2 Direzione del fascio dagli angoli del tubo

Dagli angoli primario α (LL) e secondario β (AP) si costruisce il **versore di
propagazione** del fascio `d` (dal fuoco verso il detettore):

```
d = ( sin α · cos β ,  cos α · cos β ,  sin β )
```

(vedi `_beam_axes`). Verifica dei casi limite:
- α=0, β=0 → `d = (0, 1, 0)`: fascio dritto verso l'alto (postero-anteriore). ✔
- α≠0 → rotazione nel piano assiale x–y (obliquità LAO/RAO). ✔
- β≠0 → inclinazione cranio-caudale (CRA/CAU) fuori dal piano assiale. ✔

Insieme a `d` si definiscono due assi ortonormali del piano del campo, `e1` ed `e2`,
che servono a misurare quanto un punto è dentro o fuori dal rettangolo del fascio:

```
e1 = ( cos α , −sin α , 0 )          # asse "larghezza" del campo
e2 = e1 × d                          # asse "altezza" del campo
```

`{e1, e2, d}` formano una terna destrorsa: `d` è la profondità, `e1` ed `e2` il piano
trasversale del fascio.

### 3.3 Posizione della sorgente

Il movimento del tavolo sposta il paziente rispetto all'isocentro. Il vettore di
spostamento `q` (posizione dell'isocentro-fascio nel riferimento del paziente) è:

```
q_x = segno_lat  · (lat − lat_rif)  + offset_x
q_y = segno_alt  · (alt − alt_rif)  + offset_y
q_z = segno_lon  · (lon − lon_rif)  + offset_z
```

I valori `_rif` sono le **mediane non-nulle** delle posizioni tavolo di quella
procedura (il tavolo "a riposo" del caso). I segni e gli offset sono i parametri di
commissioning che si regolano confrontando con esposizioni note.

La **sorgente** (fuoco) è a distanza SOD dall'isocentro, nella direzione opposta a
`d`:

```
sorgente = q − SOD · d
```

---

## 4. Dimensione del campo: dal DAP alla base della piramide

Nei report allegati **non ci sono colonne di collimazione**, quindi la dimensione
del campo si ricava con questa priorità:

1. **Da DAP / Ka,r** (metodo preferito). Poiché `DAP = Ka,r · Area`, l'area del campo
   al piano di riferimento è:
   ```
   Area_rif [mm²] = (DAP / Ka,r) · 100        # da cm² a mm²
   ```
   Assunto rapporto d'aspetto quadrato (in mancanza di collimazione):
   ```
   w_rif = h_rif = √(Area_rif)
   ```

2. **Da colonne di collimazione** (se presenti), proiettando la dimensione dal
   detettore al piano di riferimento con il rapporto delle distanze:
   ```
   w_rif = w_detettore · d_IRP / SID
   ```

3. **Collimazione fissa** configurabile (fallback finale) proiettata allo stesso modo.

`w_rif` e `h_rif` sono le dimensioni della **base della piramide** di irraggiamento,
posta al piano di riferimento (a distanza `d_IRP` dal fuoco).

---

## 5. Proiezione del campo sulla mappa planare (griglia θ–z)

Il modello di paziente è un **cilindro ellittico**: sezione ellittica (semiassi
`a = larghezza/2`, `b = spessore_AP/2`) estruso lungo z.

### 5.1 Costruzione della griglia di pelle

La superficie viene campionata con due parametri — l'angolo circonferenziale θ e la
posizione longitudinale z — che sono **le due coordinate della mappa planare** (il
cilindro "srotolato"):

```
θ ∈ [−π, π)      (n_theta punti)
z ∈ [−L/2, L/2]  (n_z punti)
```

Ogni nodo `(θ, z)` corrisponde a un punto 3D sulla superficie ellittica:

```
X = a · cos θ
Y = b · sin θ
Z = z
```

e alla **normale esterna** in quel punto (gradiente dell'ellisse, normalizzato):

```
N = normalizza( ( cos θ / a ,  sin θ / b ,  0 ) )
```

Questa corrispondenza `(θ, z) ↔ (X, Y, Z)` è ciò che lega la mappa planare alla
superficie 3D: la heatmap 2D e la superficie 3D mostrano gli **stessi valori**, solo
con parametrizzazioni diverse.

### 5.2 Test "il punto è dentro il fascio?"

Per ogni evento e ogni punto di pelle `P`, si porta `P` nel riferimento del fascio.
Sia `V = P − sorgente`. Le tre coordinate nel sistema del fascio sono:

```
t = V · d       # profondità lungo l'asse del fascio (distanza dal fuoco)
u = V · e1      # posizione trasversale (larghezza)
v = V · e2      # posizione trasversale (altezza)
```

La piramide ha apice nel fuoco e base `w_rif × h_rif` a profondità `d_IRP`. A una
profondità generica `t` la sezione del fascio si allarga linearmente:

```
scala = t / d_IRP
semi-larghezza(t) = 0.5 · w_rif · scala
semi-altezza(t)   = 0.5 · h_rif · scala
```

Il punto è **irraggiato** se soddisfa contemporaneamente:

```
(1)  t > 0                              # davanti alla sorgente, non dietro
(2)  N · d < 0                          # superficie di ENTRATA (vedi 5.3)
(3)  |u| ≤ 0.5 · w_rif · (t/d_IRP)      # dentro la larghezza del cono
(4)  |v| ≤ 0.5 · h_rif · (t/d_IRP)      # dentro l'altezza del cono
```

Le condizioni (3) e (4) sono l'intersezione geometrica del punto con le **quattro
facce della piramide** (Johnson & Bolch): un punto è nel campo se le sue coordinate
trasversali stanno dentro il rettangolo che il cono ritaglia a quella profondità.

### 5.3 Solo superficie di entrata

La condizione `N · d < 0` tiene solo i punti la cui normale esterna è **opposta**
alla direzione del fascio, cioè la faccia del paziente rivolta verso la sorgente. I
punti sul lato di uscita (dove il fascio esce dal paziente) hanno `N · d > 0` e
vengono scartati: la dose cutanea di interesse è quella d'ingresso.

### 5.4 Deposizione della dose

Per tutti i punti che superano il test, si somma il contributo dell'evento:

```
Dose(punto) += Ka,r · (d_IRP / t)² · (BSF·MEAC·TAF·CF) · Fθ
```

Ripetendo su tutti gli eventi si ottiene il campo di dose sull'intera griglia. Il
risultato è rimodellato in una matrice 2D `dose[z, θ]` — la **mappa planare** —
visualizzata come heatmap.

---

## 6. Dalla mappa planare all'ellissoide (superficie 3D)

La proiezione sull'ellissoide non richiede un secondo calcolo: è la **stessa griglia**
vista in 3D. Per ogni nodo `(θ, z)`:

- il **valore di dose** è quello già calcolato nella mappa planare;
- la **posizione 3D** è `(X, Y, Z) = (a·cos θ, b·sin θ, z)`.

Quindi:

```
Mappa planare (heatmap)          Superficie 3D
   asse x  = θ (angolo)     →     X = a·cos θ,  Y = b·sin θ
   asse y  = z              →     Z = z
   colore  = dose           →     colore superficie = stessa dose
```

Srotolando il cilindro lungo θ si ottiene la vista 2D; riavvolgendolo sull'ellisse si
ottiene la vista 3D. Il **punto di PSD** (massimo della dose) è marcato in entrambe:
sulla mappa alle coordinate `(θ_peak, z_peak)`, sulla superficie al corrispondente
`(X, Y, Z)`.

### 6.1 Perché un'ellisse e non un cerchio

La sezione del tronco umano è più larga (laterale) che profonda (AP), per cui
un'ellisse con `a > b` approssima il contorno meglio di un cerchio. La distanza
fuoco-pelle — e quindi l'inverse-square — cambia molto tra proiezioni AP e laterali;
la forma ellittica cattura questa differenza. È comunque un'approssimazione: la
letteratura usa modelli antropomorfi più realistici per ridurre l'errore
(§ limitazioni nel README).

---

## 7. Individuazione del punto di PSD e contributi

Trovato il massimo della matrice `dose[z, θ]`, il sistema:

1. legge le coordinate `(θ_peak, z_peak)` e le converte in 3D `(x, y, z)`;
2. rifà il test di appartenenza al fascio **solo per quel punto**, evento per evento,
   per elencare quali esposizioni hanno contribuito alla PSD e con quanta dose
   (`event_contributions_at_peak`).

Questo produce la tabella "Events contributing to the PSD point": utile per capire se
la PSD è dovuta a poche acquisizioni pesanti o a molte fluoroscopie sullo stesso
angolo.

---

## 8. Riepilogo dei parametri di commissioning

| Parametro | Effetto geometrico/dosimetrico |
|---|---|
| Larghezza / spessore AP fantoccio | Semiassi `a`, `b` dell'ellisse → distanze fuoco-pelle |
| Lunghezza mappata | Estensione lungo z della griglia |
| Offset punto di riferimento | Posizione dell'IRP → `d_IRP`, base della piramide |
| Segni tavolo (lat/alt/lon) | Direzione dello spostamento paziente ↔ fascio |
| Offset paziente x/y/z | Posizionamento del paziente rispetto all'isocentro |
| BSF, MEAC, TAF, CF, Fθ | Fattori moltiplicativi della dose |
| Collimazione fissa / distanze default | Fallback quando mancano colonne |

Regolare **prima** segni e offset (con esposizioni AP e oblique note), **poi** i
fattori di dose, confrontando con film/OSLD/TLD o un sistema commissionato.


## Riferimenti aggiuntivi per correzioni e incertezza

- Benmakhlouf H, Bouchard H, Fransson A, Andreo P. *Backscatter factors and mass energy-absorption coefficient ratios for diagnostic radiology dosimetry.* Phys Med Biol. 2011;56(22):7179–7204. doi:10.1088/0031-9155/56/22/012.
- Jones AK, Pasciak AS. *Calculating the peak skin dose resulting from fluoroscopically guided interventions. Part I: Methods.* J Appl Clin Med Phys. 2011;12(4):231–244. doi:10.1120/jacmp.v12i4.3670. Part II: *Case studies.* 2012;13(1):174–186. doi:10.1120/jacmp.v13i1.3693.
- Dabin J, Blidéanu V, Ciraj-Bjelac O, et al. *Accuracy of skin dose mapping in interventional cardiology: Comparison of 10 software products following a common protocol.* Phys Med. 2021;82:279–294. doi:10.1016/j.ejmp.2021.02.016.
- Krajinović M, Vujisić M, Ciraj-Bjelac O. *Uncertainty associated with the use of software solutions utilizing DICOM RDSR for skin dose assessment in interventional radiology and cardiology.* Radiat Prot Dosimetry. 2021;196(3–4):129–135. doi:10.1093/rpd/ncab146.
