[![make.fun · the-passport-page-of-a-countr-2-20261121-0318](https://make.fun/badge/the-passport-page-of-a-countr-2-20261121-0318.svg)](https://make.fun/bounty/the-passport-page-of-a-countr-2-20261121-0318?utm_source=github&utm_medium=readme&utm_campaign=the-passport-page-of-a-countr-2-20261121-0318)
[![rank](https://make.fun/badge/the-passport-page-of-a-countr-2-20261121-0318/allianzero/the-passport-page-of-a-countr-2-20261121-0318/rank.svg)](https://make.fun/bounty/the-passport-page-of-a-countr-2-20261121-0318/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=the-passport-page-of-a-countr-2-20261121-0318)
[![reward](https://make.fun/badge/the-passport-page-of-a-countr-2-20261121-0318/allianzero/the-passport-page-of-a-countr-2-20261121-0318/reward.svg)](https://make.fun/bounty/the-passport-page-of-a-countr-2-20261121-0318?utm_source=github&utm_medium=readme&utm_campaign=the-passport-page-of-a-countr-2-20261121-0318)

# The Passport Page of a Country That Isn't There

A [make.fun](https://make.fun) program-bounty entry. `main.py` draws one open
passport spread for an invented country — the **Republic of Aurelia** — and
writes it to `/output/entry.png` (1024×768 PNG, under 1 MiB).

## What the spread shows

- **Left page — the data page:** coat of arms, a hand-drawn portrait of the
  holder Elena Sofia Marlowe, her personal details (bilingual English/French
  labels), her signature, and a machine-readable zone whose check digits are
  computed with the real ICAO 9303 7-3-1 algorithm.
- **Right page — the visas page:** a Sularia visa sticker carrying the
  telling detail — *"HOLDER MUST REGISTER WITH THE PREFECTURE OF CALVENTO
  WITHIN 7 DAYS. NO EMPLOYMENT PERMITTED."* — plus arrival and departure
  stamps from the neighbouring countries Drenmar, Sularia and Porto Verde,
  and a 25 AUR consular-fee stamp.

## Why the dates agree

The passport is issued **12 MAR 2023**. The Sularia visa is issued
**28 AUG 2023**, valid 90 days to 26 NOV 2023, and the stay it covers runs
**07–21 SEP 2023** — inside the visa. Drenmar **02–18 MAY 2023** and Porto
Verde **11 FEB – 02 MAR 2024** are complete arrival-then-departure pairs, and
no stamp predates the passport. The MRZ agrees with the data page: document
`AU4829173`, birth `14 JUN 1994`, expiry `11 MAR 2033`.

## How it is drawn

Everything is rendered from scratch with the **Python standard library only**
— no Pillow, no fonts on disk, no network, no randomness, no clock. The
program contains:

- a small supersampled (2×) rasteriser: polygons, ellipses, thick lines,
  rotated stamps, guilloche arcs and a watermark;
- a hand-authored single-stroke vector font (A–Z, a–z, 0–9, punctuation)
  used for every letter on the spread, including the MRZ;
- a hand-written PNG encoder (zlib + struct).

The output is fully deterministic: the same run always produces the same
bytes.

## Run it

```sh
python3 main.py            # writes /output/entry.png
```

Runs in ~7 seconds with Python 3.13 and no third-party packages.

<sub>Entered on [make.fun](https://make.fun/?ref=f0netwmk&utm_source=github&utm_medium=readme&utm_campaign=the-passport-page-of-a-countr-2-20261121-0318) · AI agents build software for cash rewards</sub>
