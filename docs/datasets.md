# Datasets

Research inventory. No data is stored in this repository. Numbers from the cited papers/sites;
verify against the current license text before applying.

## Microexpression (spotting / recognition)

| Dataset | Subjects | ME samples | FPS / resolution | Labels | Access |
|---|---|---|---|---|---|
| SMIC (Oulu) | 16 (HS) / 8 (VIS, NIR) | 164 | 100 (HS), 25 | 3 classes | Signed agreement |
| CASME II (CAS) | 26 | 247 | 200, 640x480 | 5 classes + AUs, onset/apex/offset | Signed agreement (casme.psych.ac.cn) |
| SAMM (MMU) | 32 | 159 | 200, 2040x1088 | 8 classes + AUs | Signed agreement |
| CAS(ME)2 | 22 | 57 ME + 300 macro | 30 | spotting, long videos | Signed agreement |
| CAS(ME)3 | 100 | 1,109 ME + 3,490 macro | 30, 1280x720 (+depth) | 7 classes, AUs, physiology | Signed agreement |
| 4DME | 56 | 1,068 | 60 (4D), 30 (RGB/gray/depth) | 22 AUs, 5 emotions | Signed agreement |
| MMEW | 36 | 300 | 90, 1920x1080 | 7 classes | Signed agreement |

Known problems: tiny subject counts; lab elicitation (video clips) rather than interaction;
demographic narrowness; frame rates far above consumer video; label disagreement; class
imbalance (surprise/disgust/other dominate). Spotting results in MEGC 2025 (STRS ~ 0.006-0.009)
show the task is not solved. Evaluation must be LOSO or cross-dataset; random frame-level splits
leak subjects.

## Action Units

| Dataset | Subjects | Frames / labels | Access |
|---|---|---|---|
| BP4D(+) | 41 (BP4D) / 140 (BP4D+) | ~140k frames, 12 AU occurrence (BP4D) | Institutional agreement, non-profit research |
| DISFA | 27 | 130k frames, 12 AU intensities 0-5, 66 landmarks | Agreement |
| RAF-AU, Aff-Wild2, CK+ | - | in-the-wild AU / expression | Agreements; various |

## Deception (research only; never for product claims)

| Dataset | Content | Access |
|---|---|---|
| Real-life Trial (Michigan) | 121 courtroom clips, ~28 s | Agreement |
| Bag-of-Lies | 325 videos, 35 subjects, gaze + EEG | Agreement |
| MU3D | 320 videos, 80 subjects (balanced race/gender), 2 truths + 2 lies each | Free for research |
| Box-of-Lies | 1,049 utterances from a TV game show, 26 guests | Agreement; TV-derived |
| DOLOS | game-show deception, MUMIN annotations | Agreement |

SVC 2025/2026 challenges benchmark cross-domain generalization on these; performance drops
sharply across domains.

## Adapter plan

`datasets/adapters/` will hold one adapter per dataset that reads the licensed local copy and
yields a common record (`subject_id, clip_id, frames or video path, t_onset/apex/offset,
labels, fps`). `datasets/manifests/` holds hashes of the *local* files for reproducibility, not
the data. Nothing under `datasets/data/` is tracked.
