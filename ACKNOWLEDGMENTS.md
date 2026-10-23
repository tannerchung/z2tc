# Scientific Foundations, Acknowledgments & IP Compliance Boundaries

## 1. Scientific Foundations & Bibliography

The deterministic mathematical models, physiological thresholds, and periodization algorithms implemented in the Detour Run Club (`z2tc`) training platform draw upon decades of peer-reviewed exercise physiology and established distance-running literature:

### Peer-Reviewed Physiological Models
- **Oxygen Cost of Running & Pseudo-VO₂max ($VDOT$):**
  - Daniels, J., & Gilbert, J. (1979). *Oxygen Power: Performance Tables for Distance Runners*.
  - $\text{VO}_2 = -4.60 + 0.182258v + 0.000104v^2$
  - $\%VO_2\text{max}(t) = 0.8 + 0.1894393e^{-0.012778t} + 0.2989558e^{-0.1932605t}$
- **Metabolic Power & Energy Cost of Running on Flat and Inclined Terrain:**
  - di Prampero, P. E., Atchou, G., Brückner, J. C., & Moia, C. (1986). *The energetics of endurance running*. European Journal of Applied Physiology, 55(3), 259–266.
  - Minetti, A. E., Moia, C., Roi, G. S., Susta, D., & Ferretti, G. (2002). *Energy cost of walking and running at extreme uphill and downhill slopes*. Journal of Applied Physiology, 93(3), 1039–1046.
- **Critical Power ($CP$) & Anaerobic Work Capacity ($W'$):**
  - Monod, H., & Scherrer, J. (1965). *The work capacity of a synergic muscular group*. Ergonomics, 8(3), 329–338.
  - Vanhatalo, A., Doust, J. H., & Burnley, M. (2007). *Determination of critical power using a 3-min all-out test*. Medicine & Science in Sports & Exercise, 39(3), 548–555.
- **Autonomic Nervous System (HRV rMSSD) Guided Training:**
  - Kiviniemi, A. M., Hautala, A. J., Kinnunen, H., & Tulppo, M. P. (2007). *Endurance training guided individually by daily heart rate variability measurements*. European Journal of Applied Physiology, 101(6), 743–751.
  - Plews, D. J., Laursen, P. B., Stanley, J., Kilding, A. E., & Buchheit, M. (2013). *Training adaptation and heart rate variability in elite endurance athletes: opening the door to effective monitoring*. Sports Medicine, 43(9), 773–781.
- **Acute:Chronic Workload Ratio (ACWR) & Impulse-Response Modeling:**
  - Banister, E. W., Calvert, T. W., Savage, M. V., & Bach, T. (1975). *A systems model of training for athletic performance*. Australian Journal of Sports Medicine, 7(3), 57–61.
  - Gabbett, T. J. (2016). *The training—injury prevention paradox: should athletes be training smarter and harder?* British Journal of Sports Medicine, 50(5), 273–280.
- **3-Day / Low-Frequency High-Intensity Marathon Preparation (FIRST Method):**
  - Pierce, B., Murr, S., & Moss, R. (2007). *Run Less, Run Faster: Become a Faster, Stronger Runner with the Revolutionary 3-Day-a-Week Training Program*. Rodale Books (Furman Institute of Running and Scientific Training).

### Foundational Coaching Texts
We strongly encourage every athlete in the Detour community to purchase and study the original coaching texts whose physiological principles inform distance-running periodization:
- **Daniels, J.** (2013). *Daniels' Running Formula* (3rd ed.). Human Kinetics.
- **Pfitzinger, P., & Douglas, S.** (2009) / **Pfitzinger, P., & Latter, P.** (2019). *Advanced Marathoning* (2nd / 3rd ed.). Human Kinetics.
- **Humphrey, L., Hanson, K., & Hanson, K.** (2012). *Hansons Marathon Method*. VeloPress.
- **Higdon, H.** (2011). *Marathon: The Ultimate Training Guide* (4th ed.). Rodale Books.

---

## 2. Hard Legal & IP Compliance Guardrails (Commercial & Public Deployment)

Under U.S. Copyright Law (**17 U.S.C. § 102(b)**), mathematical equations, physiological principles, training concepts, and algorithmic procedures are not copyrightable. However, an author's **verbatim expression** (prose, chapter text, static schedule tables, and brand trademarks) is strictly protected.

When exposing `z2tc` or the Detour 3-Layer Athletic Engine via any public web application, club portal, or paid membership tier, all contributors and automated agents MUST enforce these five compliance rules:

### Rule 1: Zero Copyrighted Book Files in Repository or Public Bundles
- Raw book PDFs and page-scan caches (`*.pdf`, `*.jsonl`) must reside **exclusively** in local personal storage (`~/Documents/Running/Reference/`) and remain permanently listed in `.gitignore`.
- Never bundle, serve, or quote verbatim book paragraphs in user-facing UIs.

### Rule 2: Algorithmic Computation Over Verbatim Lookup Tables (Enforced in Code)
- **Continuous Equation Paces (`engine/paces.py`):** Evaluates the inverse of the **Daniels-Gilbert (1979) quadratic VO₂ equation** continuously across the full VDOT range (`30..85`) with zero dependency on static JSON lookup tables (`daniels_table_5_2.json` has been removed from the repository).
- **Parametric Periodization Generators (`engine/plan/`):** All schedule modules (`engine/plan/daniels.py`, `engine/plan/pfitzinger.py`, `engine/plan/pfitz_grids.py`, `engine/plan/hanson_grids.py`, `engine/plan/higdon_grids.py`) generate mesocycle progressions procedurally from mathematical volume/intensity rules rather than static verbatim text tables.
- **External Reference Tooling:** All book search and table-extraction utilities (`book_search.py`, `extract_daniels_tables.py`) and reference PDFs live exclusively in `~/Documents/Running/Reference/` outside the repository.

### Rule 3: Trademark & Naming Hygiene in User-Facing UI
- **Never** use author names or book titles as product tier names, buttons, or marketing labels (e.g., do NOT label options *"Jack Daniels Plan"*, *"Pfitzinger 18/55"*, *"Hansons Method"*, or *"Hal Higdon Novice"*).
- **Use Functional Physiology Labels Instead:**
  - *Detour 2Q Polarized Engine* (or *Threshold & Blended Long-Run Track*)
  - *Detour High-Volume Endurance Engine* (or *Midweek Medium-Long Track*)
  - *Detour Cumulative Fatigue Engine* (or *6-Day Distributed Volume Track*)
  - *Detour 3-Day Time-Crunched Engine* (or *3-Run Quality + Cross-Training Track*)
- Credit the authors properly in the `Acknowledgments & Scientific Foundations` footer page, alongside an explicit disclaimer: *"Detour Run Club is an independent athletic organization and is not affiliated with, endorsed by, or sponsored by Dr. Jack Daniels, Pete Pfitzinger, Hansons-Brooks Distance Project, Hal Higdon, or their respective publishers."*

### Rule 4: Multi-Modal Prescription Switching (Power ↔ Pace ↔ Heart Rate / RPE)
- Every workout step generated by the engine (`ExportStep`) must support dynamic target rendering based on the athlete's connected hardware and preference:
  - **Mode A — Mechanical Power (`Watts` / `%CP`):** Primary target for athletes with Garmin Running Power, Stryd, or Coros (e.g., `Zone 2: 285–335W` / `80–85% CP`).
  - **Mode B — Physiological Pace (`min/mi` or `min/km`):** Primary target for GPS-only road/track sessions, automatically grade-adjusted where applicable.
  - **Mode C — Heart Rate / Autonomic Effort (`%LTHR`, `%HRmax`, or `RPE 1–10`):** Automatic fallback during Yellow Gate recovery days, high heat/humidity (`>65°F` dew point), or for beginners without power sensors.

### Rule 5: Liability Shield, Entity Structure & Medical Disclaimers
- **Corporate Entity Separation:** Operate paid memberships, coaching tools, and club events through a dedicated Limited Liability Company (LLC) with **RRCA (Road Runners Club of America) / USATF Commercial General Liability Insurance**.
- **Mandatory Clickwrap Waiver & Assumption of Risk:** Require explicit checkbox acceptance prior to account creation, Strava/Garmin OAuth connection, or workout export:
  1. **Non-Medical Disclaimer:** The software is an automated mathematical scheduling utility, not a physician, physical therapist, or medical device.
  2. **Express Assumption of Risk:** Endurance training and marathon racing carry inherent risks of musculoskeletal injury, rhabdomyolysis, cardiac events, and death.
  3. **Athlete Override Authority:** All automated power/pace/HR targets and readiness gates are informational suggestions; the athlete retains 100% sole responsibility to slow down, stop, or modify any session based on physical symptoms.
