# Detour Athletic Engine (`z2tc`) — Complete Mathematical & Physiological Derivations

*Canonical whitepaper and engineering reference for the Detour Run Club marathon engine. Designed both as internal engineering documentation and as the scientific source material for technical blog posts and athlete help guides.*

---

## 1. Oxygen Cost of Running & Continuous Pseudo-$\text{VO}_2\text{max}$ ($VDOT$)

### 1.1 The Daniels & Gilbert (1979) Two-Equation System
Rather than relying on static lookup tables or single-exponent power laws (such as Riegel's $T_2 = T_1 (D_2/D_1)^{1.06}$, which fails to account for the transition from anaerobic capacity to lipid oxidation across wide distance spans), `engine/vdot.py` and `engine/paces.py` implement the continuous **Daniels & Gilbert (1979)** bioenergetic model.

1. **Steady-State Oxygen Cost of Horizontal Running ($\text{mL}\cdot\text{kg}^{-1}\cdot\text{min}^{-1}$):**
   $$\text{VO}_2(v) = -4.60 + 0.182258v + 0.000104v^2$$
   where $v$ is running velocity in meters per minute ($\text{m/min}$). The quadratic term ($0.000104v^2$) captures aerodynamic drag and increasing biomechanical internal work at higher velocities.

2. **Sustainable Fraction of $\text{VO}_2\text{max}$ as a Function of Duration ($t$ in minutes):**
   $$F(t) = \%VO_2\text{max}(t) = 0.8 + 0.1894393e^{-0.012778t} + 0.2989558e^{-0.1932605t}$$
   - Fast-decay exponential ($e^{-0.1932605t}$, $\tau_1 \approx 5.17\text{ min}$): models the rapid depletion of anaerobic work capacity ($W'$) over 800m–5K durations.
   - Slow-decay exponential ($e^{-0.012778t}$, $\tau_2 \approx 78.26\text{ min}$): models glycogen depletion, thermoregulatory drift, and neuromuscular fatigue over 10K–Marathon durations.

3. **Effective Aerobic Capacity ($VDOT$):**
   For a race of distance $d$ (meters) completed in time $t$ (minutes), with mean velocity $v = d/t$:
   $$\text{VDOT}(d, t) = \frac{\text{VO}_2(d/t)}{F(t)}$$

### 1.2 Continuous Inverse Velocity Solver (`engine/paces.py`)
Given any target oxygen uptake $\dot{V} = \%VO_2\text{max}_{\text{zone}} \cdot \text{VDOT}$, we solve the quadratic equation $0.000104v^2 + 0.182258v - (4.60 + \dot{V}) = 0$ analytically for its positive root:
$$v(\dot{V}) = \frac{-0.182258 + \sqrt{0.182258^2 + 4(0.000104)(4.60 + \dot{V})}}{2(0.000104)}$$
and convert directly to pace in seconds per mile ($P_{\text{sec/mi}} = \frac{1609.344}{v(\dot{V})} \times 60$).

### 1.3 Training Zone Fractional Utilization Curves
Each training zone corresponds to a specific physiological stimulus:
- **Easy / Aerobic Base ($E$, $63\%\text{–}74\%\text{ VO}_2\text{max}$):** Maximizes mitochondrial biogenesis, capillary bed proliferation, and left-ventricular stroke volume with minimal sympathetic stress.
- **Marathon Pace ($M$, $78\%\text{–}84\%\text{ VO}_2\text{max}$):** Specific metabolic efficiency at target race velocity; scales upward with $VDOT$ because faster marathoners complete the distance in less time $t$ on the $F(t)$ curve.
- **Lactate Threshold ($T$, $\approx 88\%\text{ VO}_2\text{max}$):** Maximal Lactate Steady State (MLSS), where blood lactate appearance equals oxidative clearance ($\approx 4.0\text{ mmol/L}$).
- **Interval ($I$, $\approx 97.5\%\text{ VO}_2\text{max}$):** Elicits maximal cardiac output and central oxygen delivery ($\text{VO}_2\text{max}$).
- **Repetition ($R$, $105\%\text{–}111\%\text{ VO}_2\text{max}$):** Neuromuscular recruitment, stride mechanics, and running economy ($C_r$) with full recovery between bouts.

---

## 2. Mechanical Running Power, GradeEnergetics & Multi-Modal Isomorphism

### 2.1 Metabolic & Mechanical Cost of Running on Flat and Hilly Terrain
Based on **di Prampero et al. (1986)** and **Minetti et al. (2002)** (*Journal of Applied Physiology*):
- On flat terrain, the net energy cost of running is $C_{r,0} \approx 0.98\text{–}1.04\text{ J}\cdot\text{kg}^{-1}\cdot\text{m}^{-1}$.
- On a slope of fractional gradient $g = \Delta h / \Delta d$, Minetti's 5th-order polynomial gives the metabolic cost of inclined running ($J\cdot\text{kg}^{-1}\cdot\text{m}^{-1}$):
  $$C_r(g) = 155.4g^5 - 30.4g^4 - 43.3g^3 + 46.3g^2 + 19.5g + 3.6$$
- **Instantaneous Mechanical Power ($P$ in Watts):**
  $$P(v, g) = \eta_{\text{mech}} \cdot m \cdot C_r(g) \cdot v + P_{\text{aero}}(v, v_{\text{wind}})$$
  where $m$ is athlete mass in kg and $v$ is speed in $\text{m/s}$.

### 2.2 Why Power Solves the "Unplanned Hill / GPS Lag" Problem Automatically
When an athlete runs an interval or threshold block in NYC (e.g., hitting the Williamsburg Bridge, Manhattan Bridge, or Harlem Hill mid-rep) without a pre-loaded route:
1. **Why Pace Fails on Hills:** Trying to hold flat T-pace ($7:42/\text{mi}$) up a $+4\%$ bridge grade increases metabolic demand by $\approx +22\%$, spiking blood lactate above $8\text{ mmol/L}$ and ruining the workout within 90 seconds. Furthermore, GPS pace lags by 8–15 seconds under bridge cables or tall buildings.
2. **Why Watch Power Works with Zero Route Pre-Planning:** Modern wrist/pod accelerometers + barometric altimeters (Garmin Running Power, Stryd, Coros) compute $P(v, g)$ **instantaneously on the watch at 1 Hz**.
   - If the workout step is exported to the watch with a **Power Target** (or if the athlete knows their Threshold Power ceiling, e.g., $385\text{–}400\text{W}$), the moment the road tilts upward, power spikes *instantly*—the runner naturally shortens their stride to hold $390\text{W}$, let pace drop to $8:30/\text{mi}$ on the climb, and accelerate on the descent while maintaining an exact, flat $88\%\text{ VO}_2\text{max}$ metabolic stimulus!
   - **Dual-Cue Export Rule:** Every structured workout step includes both the **Primary Target** (Pace or Power) and the **Hill/Heat Ceiling Cue** in the step note (e.g., `Target: 7:42/mi | On hills/bridges hold <= 395W (or <= 88% HRmax)`). No route planning required.

---

## 3. Frequency Bounds & The 3-Day vs. 6-Day Periodization Equations

### 3.1 Minimum and Maximum Training Days (`3 <= days_per_week <= 6`)
- **Hard Floor (`3 days/week`):** Below 3 days/week ($1\text{–}2\text{ days/wk}$), musculoskeletal remodeling and mitochondrial half-life ($\approx 5\text{–}7\text{ days}$) cannot sustain marathon preparation safely; forcing an 18–20 mile long run on a 2-day/week runner pushes single-session volume above $65\%$ of weekly load, creating extreme tibial and Achilles injury risk.
- **Default Club Recommendation (`4–5 days/week`):** Optimal balance of polarized stimulus ($2\text{ quality} + 2\text{–}3\text{ easy aerobic}$) and recovery.
- **Hard Ceiling (`6 days/week`):** Even on the cumulative-fatigue track, 1 full day per week (Wednesday) is a mandatory non-running recovery day to prevent overtraining syndrome (OTS).

### 3.2 Deep Dive: How the 3-Day Low-Frequency Architecture Was Derived (Furman FIRST "3plus2" vs. Runna)

When an athlete selects `days_per_week = 3`, standard 5-to-6-day marathon equations fail mathematically: if you enforce Daniels's $30\%$ long-run share cap ($f_{\text{LR}} \le 0.30$) on a 3-day runner peaking at $34\text{ mpw}$, their longest run would be capped at $10.2\text{ miles}$—completely inadequate for a marathon. Conversely, if you give them a $20\text{-mile}$ long run inside a $34\text{ mpw}$ week, their two weekday runs shrink to $7\text{ miles}$ each and the long run consumes $59\%$ of their weekly mileage.

Our 3-day engine (`engine/plan/club.py` + `engine/plan/common.py`) synthesizes two proven low-frequency architectures from exercise physiology and commercial coaching:

#### A. The Furman Institute of Running and Scientific Training (FIRST) "3plus2" Architecture
Developed by **Bill Pierce, Scott Murr, and Ray Moss** at Furman University (*Run Less, Run Faster*, 2007/2021) and validated in Furman lab cohorts:
1. **Zero "Junk" / Recovery Running Days:** Instead of running easy recovery miles on tired legs, all **3 running days are structured quality/purpose workouts** separated by **48 hours** of non-impact recovery (`Tue / Thu / Sat`):
   - **Key Run #1 (Tuesday — Track/Speed, $\text{VO}_2\text{max}$):** Short-to-medium repeats ($400\text{m}$ to $1600\text{m}$) at $I$-pace ($95\text{–}100\%\text{ VO}_2\text{max}$, roughly 5K pace) totaling $3\text{–}5\text{ miles}$ of interval volume ($6\text{–}8\text{ mi}$ total with warmup/cooldown).
   - **Key Run #2 (Thursday — Lactate Threshold / Tempo):** Short, Medium, or Long Tempo runs ($4\text{–}8\text{ miles}$ at $T$-pace / $M$-pace, total session $6\text{–}10\text{ miles}$).
   - **Key Run #3 (Saturday — Long Endurance Run):** Progressive endurance run ($13\text{–}20\text{ miles}$) run significantly faster than traditional conversational jogs ($\text{MP} + 30\text{–}45\text{ sec/mi}$, vs. $\text{MP} + 60\text{–}90\text{ sec/mi}$ in high-mileage plans).
2. **The "+2" Mandatory Non-Impact Cross-Training Days (`3 Runs + 1–2 Cross-Training`):**
   - Because 3 days of running only generates $28\text{–}38\text{ mpw}$ ($4\text{–}5.5\text{ hours}$ of cardiovascular work), FIRST requires **2 days per week (or 1–2 days minimum for recreational marathoners) of 45–60 minutes of non-impact aerobic cross-training** (indoor cycling/Peloton, lap swimming, elliptical, or rowing) at $70\text{–}80\%\text{ HR}_{\text{max}}$.
   - **Physiological mechanism:** Central cardiac adaptations (stroke volume, plasma volume, left-ventricular eccentric hypertrophy) are **modality-independent**—the heart does not know whether oxygen demand comes from cycling or running—while peripheral bone/tendon strain is zero during cycling/swimming.

#### B. How Runna's Commercial 3-Day Algorithm Adapts FIRST for Everyday Runners
Pure Furman FIRST has one famous failure mode for non-elites: making *all three* runs hard (including running the Saturday 20-miler at $\text{MP} + 30\text{s/mi}$) causes high breakdown rates in 4:00–5:00 marathoners. Runna's 3-day marathon engine modifies FIRST in three specific ways:
1. **1 Intervals + 1 Tempo + 1 Polarized/Block Long Run:**
   - **Run 1 (Tue):** Intervals / Hill Repeats ($5\text{–}7\text{ mi}$ total).
   - **Run 2 (Thu):** Tempo / Rolling Threshold ($5\text{–}8\text{ mi}$ total).
   - **Run 3 (Sat/Sun):** Alternates every other week between an **Easy Conversational Long Run** (pure Zone 2 time-on-feet) and a **Block/Progression Long Run** (e.g., $16\text{ mi}$ with the middle or final $6\text{–}8\text{ km}$ at Goal Marathon Pace), rather than running every long run fast.
2. **Volume Share Relaxation ($f_{\text{LR,max}} = 0.50\text{–}0.55$):**
   - Because there are only 2 weekday runs ($5\text{–}8\text{ mi}$ each), the Saturday Long Run is mathematically permitted to represent **$48\%\text{–}55\%$ of total weekly running mileage** (e.g., an $18\text{-mile}$ long run inside a $34\text{-mile}$ week: $7\text{ mi Tue} + 9\text{ mi Thu} + 18\text{ mi Sat} = 34\text{ mi}$).
3. **Deload Cadence Every 3–4 Weeks:** Drops long-run distance by $30\text{–}35\%$ every 4th week so connective tissue catches up.

#### C. How Detour (`z2tc`) Encodes the 3-Day Architecture in Code
In `engine/plan/common.py` (`RUN_DAYS_BY_COUNT[3] = [1, 3, 5]`, i.e., **Tue / Thu / Sat**) and `engine/plan/club.py`:
- **Dynamic Long-Run Share Cap:** When `days_per_week <= 3`, `apply_club_policy()` automatically relaxes `long_run_share_cap` from `0.33` (for 5–6 days) up to **`0.50`** (`effective_share_cap = max(policy.long_run_share_cap, 0.50)`), preventing the weekday runs from artificially starving the Saturday club long run.
- **No Wasted Easy Filler Runs:** The 3 running slots are assigned directly to **Tuesday Quality (Intervals/Hills)**, **Thursday Quality/Steady (Threshold/Tempo)**, and **Saturday Club Long Run**, while **Monday/Wednesday/Friday/Sunday** are designated for **Rest + 1–2 Non-Impact Cross-Training / Strength sessions** (45–60 min Zone 2 bike/swim/elliptical + 20 min heavy slow-resistance calf/soleus/glute work).
- **4–5 Day Default:** For athletes who have the schedule flexibility, we default to **4–5 days/week** (`Tue / Thu / Sat / Sun` or `Tue / Wed / Thu / Sat / Sun`, `long_run_share_cap = 0.35–0.42`) and cap at **6 days/week** (`Mon / Tue / Thu / Fri / Sat / Sun`).

---

## 4. The 3-Hour Long Run Ceiling & The Slower-Runner (10:00–13:00+/mi) Dilemma

### 4.1 The Physiological Physics at $\ge 10:00/\text{mi}$ Easy Pace
Physiological research (Daniels, 2013; Humphrey/Hansons, 2012; Pfitzinger, 2019) demonstrates that beyond **150 to 180 minutes (2.5 to 3.0 hours)** of continuous running:
- Aerobic enzymatic and capillarization signaling plateaus.
- Cortisol, creatine kinase (muscle breakdown), and ground-reaction forces rise exponentially as form degrades.
- Recovery time jumps from 48 hours to 5–7 days, sabotaging the next week's consistency.

**What is the maximum distance a 3-hour (180-min) ceiling allows for slower runners?**

| Goal Marathon | Typical Easy / Long Run Pace | Distance Covered in **2.5 hrs (150 min)** | Distance Covered in **3.0 hrs (180 min)** | Distance if Uncapped (`20 mi`) |
|---|---|---|---|---|
| **3:45:00** ($8:35/\text{mi}$) | $\approx 9:45/\text{mi}$ | $15.4\text{ mi}$ | **$18.5\text{ mi}$** | $20.0\text{ mi}$ ($3\text{h }15\text{m}$) |
| **4:00:00** ($9:09/\text{mi}$) | $\approx 10:15/\text{mi}$ | $14.6\text{ mi}$ | **$17.6\text{ mi}$** | $20.0\text{ mi}$ ($3\text{h }25\text{m}$) |
| **4:30:00** ($10:18/\text{mi}$) | $\approx 11:30/\text{mi}$ | $13.0\text{ mi}$ | **$15.7\text{ mi}$** | $20.0\text{ mi}$ ($3\text{h }50\text{m}$) |
| **5:00:00** ($11:27/\text{mi}$) | $\approx 12:30/\text{mi}$ | $12.0\text{ mi}$ | **$14.4\text{ mi}$** | $20.0\text{ mi}$ ($4\text{h }10\text{m}$) |

### 4.2 How Runna vs. Scientific Coaches Handle Slower Marathoners
- **How Runna Does It:** Runna prioritizes **psychological confidence (distance)** over the 3-hour physiological cap. Even for an $11:30/\text{mi}$ runner on 3 days/week, Runna scales the peak Long Run by distance up to **$30\text{–}32\text{ km}$ ($18.6\text{–}20.0\text{ miles}$)**—which puts that runner on their feet for **$3\text{ hours }45\text{ minutes}$ to $4\text{ hours}$** in training—and compensates by inserting an aggressive **3-to-4-week taper** after the peak 20-miler so they can recover from the orthopedic damage.
- **How Detour (`z2tc`) Solves Both Safely — The 3-Hour Gate + "20-Mile Confidence Override":**
  1. **Default Physiological Mode (3.0-Hour Hard Gate):** By default, our engine caps continuous running at **180 minutes (3.0 hours)** (`LONG_RUN_WINDOW_MIN = (120, 180)`).
  2. **The Informed-Consent "Distance Override" Gate (Engine-Level Setting for the App):** In our plan engine (`AthleteInputs.extended_long_run_risk_ack = True`), if an athlete's easy pace is $\ge 9:30/\text{mi}$ and they explicitly acknowledge the extended time-on-feet risk in the app UI, `apply_club_policy()` unlocks up to a **20-mile peak (`EXTENDED_LONG_RUN_MAX_MIN = 225`, i.e., 3h 45m absolute ceiling)** with a single peak week (`long_run_peak_weeks = 1`) and mandatory run/walk fueling breaks.

### 4.3 Six Evidence-Based Protocols to Build Psychological Confidence *Without* a Single 3.5–4 Hour Continuous Run

For athletes running $10:00\text{–}13:00+/\text{mi}$ who stay inside the safe **3.0-Hour Cap** ($15\text{–}17.5\text{ miles}$ max single run), how do we make them feel **100% bulletproof** about miles $18\text{–}26.2$ on race day?

1. **The "Cumulative Fatigue / Back-to-Back" Weekend Simulation (Simulating Miles 10–26.2):**
   - Instead of one destructive $20\text{-mile}$ ($3\text{h }50\text{m}$) run on Saturday, prescribe a **36-Hour Glycogen-Depletion Double**:
     - **Friday PM (or Saturday AM):** $5\text{–}6\text{ miles}$ at steady Goal Marathon Pace ($M$).
     - **Saturday AM (or Sunday AM, 14–24 hours later):** $15\text{–}16\text{ miles}$ ($2\text{h }45\text{m}\text{–}3\text{h }00\text{m}$).
   - **Why it works psychologically & physiologically:** You start the $16\text{-miler}$ with your legs and glycogen stores already pre-fatigued by $5\text{–}6\text{ miles}$. Miles $1\text{–}16$ of that run physiologically and mentally replicate **Miles $11\text{–}26.2$ of the marathon**—totaling **$21\text{–}22\text{ miles}$ in 24 hours** while keeping overnight sleep and connective-tissue recovery intact between the two bouts!
2. **The "Pre-Fatigued Fast-Finish" (Final 30 Minutes at Goal Marathon Pace):**
   - Running $16\text{ miles}$ where the final $3\text{ miles}$ (minutes $150\text{–}180$) are accelerated down to **Goal Marathon Pace** while holding zero cardiac drift ($Pa:Hr < 5\%$).
   - **Confidence reframing:** Holding race pace at hour $3.0$ of a training week (on top of $15\text{–}20\text{ miles}$ of weekday fatigue with no taper) requires the exact same motor-unit recruitment as holding race pace at hour $3.8$ on race day *after* a 3-week taper and full glycogen supercompensation.
3. **The "4-Hour Hybrid Aerobic Brick" (60-Min Bike/Walk Warmup $\to$ 2.5–3.0 Hour Run):**
   - On Peak Week (Week 14/15), the athlete does **45–60 minutes of Zone 2 indoor cycling or brisk incline walking** *immediately before* heading out the door for their **2.5-to-3.0-hour ($15\text{–}16.5\text{ mi}$) long run**, practicing their full **4-hour race-day gut/fueling schedule** ($60\text{–}90\text{g carbs/hr}$) across the entire 4-hour window.
   - **Why it works:** Their heart, metabolism, and GI tract experience a **continuous 4-hour endurance event** (burning the exact ~2,400 kcal of a marathon and proving their stomach can handle 7–8 gels over 4 hours), while their joints, tibia, and tendons only absorb 2.5–3.0 hours of pavement impact!
4. **Full Race-Day "Dress Rehearsal" Half-Marathon + Plus-Miles (Week 12/13):**
   - Run an official Half-Marathon tune-up race (e.g., Staten Island Half or Bronx 10M) in full race kit, race shoes, bib, and corral start, plus a $2\text{–}3\text{ mile}$ warmup/cooldown ($15\text{–}16\text{ miles}$ total) with negative splits. Nothing calms race-morning anxiety like rehearsing the exact corral, porta-potty, gel belt, and pacing routine in a live bibbed race 4–6 weeks out.
5. **Course-Specific "Mile 16–24" Recon Runs:**
   - Instead of fearing the unknown late-race miles, run the **actual last 10 miles of the marathon course** as one of their $10\text{–}14\text{ mile}$ long runs (e.g., for NYC: starting at the Queensboro Bridge $\to$ 1st Ave $\to$ Willis Ave Bridge $\to$ 5th Ave climb $\to$ Central Park finish). When they hit Mile 16 on race day, their brain switches from *"I've never run past 16 miles"* to *"I know every crack in the pavement from here to the finish line—this is just my 10-mile Saturday loop."*
6. **Transparent "Equivalent Race-Day Readiness" Telemetry in the App:**
   - Most runners only fixate on "20 miles" because static paper plans only have one number on them: *miles*. When our app/sheet shows them:
     - *"Peak Weekend Volume: **21.5 miles in 36 hours**"*
     - *"4-Hour Gut/Fueling Rehearsal: **Completed (280g carbs / 0 GI distress)**"*
     - *"3-Hour Cardiac Drift ($Pa:Hr$): **2.8% (Target < 5.0% — Aerobic Base Verified for 26.2 mi)**"*
     they get objective, data-backed proof that their body is ready for 26.2 miles without needing to injure themselves on a 4-hour training run.

---

## 5. Garmin Training API & Structured Workout Targeting Capabilities

When athletes connect their Garmin account via the official **Garmin Connect Developer Program (Garmin Training API v2)** or import `.FIT` workout files (`engine/workouts`), Garmin natively supports **Pace, Heart Rate, Running Power, and Cadence** targets on every individual workout step:

| Target Mode | Garmin Training API `targetType` | How Ranges Are Defined | Supported Garmin Watches |
|---|---|---|---|
| **1. Pace / Speed** | `SPEED` | Custom min/max in $\text{m/s}$ (converted on-watch to $\text{min/mi}$ or $\text{min/km}$) | All Garmin Forerunner, Fenix, Epix, Venu, Instinct |
| **2. Heart Rate (Zone or BPM)** | `HEART_RATE` | Either `workoutTargetType = HEART_RATE` with **Zone `1–5`** (uses the athlete's on-device HR zones) OR **Custom BPM range** (`targetValueLow` / `targetValueHigh` in bpm) | All Garmin watches (optical wrist HR or HRM-Pro chest strap) |
| **3. Running Power (Zone or Watts)** | `POWER` | Either **Power Zone `1–5`** (relative to the athlete's on-watch rFTP / Threshold Power) OR **Custom Watt range** (`targetValueLow` / `targetValueHigh`, e.g. `375W – 400W`) | Native wrist power (no pod needed) on Forerunner `255 / 265 / 570 / 955 / 965 / 970`, Fenix `7 / 8`, Epix `Gen 2`; or any watch paired with HRM-Pro / Running Dynamics Pod / Stryd |
| **4. Cadence** | `CADENCE` | Custom min/max in steps per minute ($\text{spm}$, e.g. `175–185 spm` for strides/form drills) | All Garmin watches |
| **5. Open / RPE + Step Note** | `OPEN` | Free effort with a 200-char `description` note displayed on the watch screen at step start | All Garmin watches |

### Crucial Garmin API Quirk & How We Handle It
- **One Primary Target Gauge Per Step:** Garmin's `.FIT` and Training API schema allows **exactly one active `targetType` gauge** per step (so the watch's red/green gauge screen will beep for *either* `SPEED`, `POWER`, or `HEART_RATE` on a given step), **plus** an optional `secondaryTargetType` (supported on newer firmware) and a free-text `description` note.
- **Our Multi-Modal Export Strategy:**
  - When an athlete exports or syncs their week to Garmin, they pick their **Primary Watch Gauge Mode**:
    - **`Pace Mode` (Default for Flat/Track):** Primary gauge = `SPEED` (e.g., `7:37–7:47/mi`), Step Note = `"Flat: 7:42/mi | Hills/Heat ceiling: <= 395W or <= 172 bpm (Z4)"`.
    - **`Power Mode` (Recommended for NYC Bridges / Central Park Hills):** Primary gauge = `POWER` (e.g., `380–400W` or `Power Zone 4`), Step Note = `"Target: 390W (~7:42/mi flat) | Auto-adjusts on bridges/hills"`.
    - **`Heart Rate / Zone Mode` (Recommended for Easy/Recovery Runs & Summer Heat):** Primary gauge = `HEART_RATE` (`Zone 2` or `135–152 bpm`), keeping easy days genuinely easy.
