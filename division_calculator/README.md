# HOI4 Division Calculator

A small Python program for calculating selected Hearts of Iron IV division
statistics from the number of infantry battalions and support-artillery
companies you enter. It is also a learning project: the values and calculations
are written out directly so they are easy to follow.

## Run the calculator

Open a terminal in this folder and run:

```text
python division_calculator.py
```

When prompted, enter the number of infantry battalions and support-artillery
companies. For example, enter `9` and then `1` for a division with nine
infantry battalions and one support-artillery company.

## What it calculates

- **Manpower:** infantry and support-artillery manpower added together.
- **Combat width:** infantry width and support-artillery width added together.
- **Equipment:** infantry equipment and artillery equipment, shown separately
  and as a combined total.
- **Infantry soft attack:** infantry battalion soft attack multiplied by the
  infantry count.
- **Average organisation:** the weighted average of infantry organisation
  (60) and artillery organisation (0), using the entered counts.
- **Artillery values:** the support-battalion soft-attack modifier and the
  base artillery equipment soft attack and defense are printed separately.

## Assumptions and limitations

The calculator uses the values recorded in `division_calculator.py`: 1,000
manpower, 2 width, 100 infantry equipment, and 25.5 soft attack per infantry
battalion; 300 manpower, 0 width, and 12 artillery equipment per support-
artillery company. Artillery equipment soft attack (26) and defense (11) are
the base 1934 equipment values. Later equipment tiers have different stats.

The `-0.5` artillery support soft-attack value is a modifier from the game
files, not a standalone amount of attack, so it is shown rather than added to
infantry soft attack. Likewise, the printed artillery equipment defense is a
base equipment stat, not a complete division defense total. This program does
not calculate the full in-game combat stats.

The organisation calculation treats each entered support-artillery company
as one value in the average, just like each infantry battalion. Enter `0` for
both counts to see a zeroed report.
