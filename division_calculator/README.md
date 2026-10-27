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

When prompted, enter the number of infantry battalions, choose `support` or
`line` artillery, then enter the number of artillery battalions. For example,
enter `9`, `support`, and `1` for nine infantry battalions and one support-
artillery company. Choose `line` to calculate line artillery battalions
instead.

## What it calculates

- **Manpower and combat width:** infantry and the selected artillery type's
  values added together.
- **Equipment:** infantry equipment and artillery equipment, shown separately
  and as a combined total.
- **Soft attack:** infantry soft attack is always shown. For line artillery,
  artillery soft attack is also calculated and added to show a combined
  estimate. For support artillery, its modifier and base equipment stats are
  shown separately.
- **Average organisation:** the weighted average of infantry organisation
  (60) and the selected artillery organisation (0), using the entered counts.

## Assumptions and limitations

The calculator uses the values recorded in `division_calculator.py`: 1,000
manpower, 2 width, 100 infantry equipment, and 25.5 soft attack per infantry
battalion; 300 manpower, 0 width, and 12 artillery equipment per support-
artillery company; and 500 manpower, 3 width, and 24 artillery equipment per
line-artillery battalion. Both use 0 organisation. Artillery equipment soft
attack (26) and defense (11) are the base 1934 equipment values. Later
equipment tiers have different stats.

The `-0.5` artillery support soft-attack value is a modifier from the game
files, not a standalone amount of attack, so it is shown rather than added to
infantry soft attack. The printed artillery equipment defense is a base
equipment stat, not a complete division defense total. This program does not
calculate the full in-game combat stats.

The line-artillery soft-attack estimate uses the base equipment soft-attack
value (26) for each entered line battalion; it is not a full in-game division
stat calculation.

The organisation calculation treats each entered artillery battalion/company
as one value in the average, just like each infantry battalion. Enter `0` for
both counts to see a zeroed report.
