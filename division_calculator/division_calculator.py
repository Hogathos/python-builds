# division_calculator.py
# HOI4 division stats calculator — started 2026-10-15
# Stats below were read from the game files by hand (vanilla, all DLC, no mods).
# Add new battalion types by copying the infantry block and filling in
# values from that unit's files under common/units/ and common/units/equipment/.

# --- Infantry (common/units/infantry.txt + equipment/infantry.txt) ---
inf_manpower = 1000      # men per battalion
inf_width = 2            # combat width per battalion
inf_equipment = 100      # infantry equipment needed per battalion
inf_soft_attack = 25.5   # per battalion (equipment 3 x 8.5, verified in designer)
inf_org = 60             # organisation — averaged across battalions, not summed

# --- Support artillery (common/units/artillery.txt + equipment/artillery.txt) ---
art_manpower = 300          # men per battalion
art_width = 0               # combat width per battalion
art_equipment = 12          # artillery equipment needed per battalion
art_soft_attack_modifier = -0.5  # support-battalion modifier in artillery.txt
art_equipment_soft_attack = 26   # base artillery equipment (1934 tier)
art_equipment_defense = 11       # base artillery equipment (1934 tier)
art_org = 0                      # max organisation

inf_battalions = int(input("Infantry battalions: "))
art_battalions = int(input("Support artillery battalions: "))

total_manpower = (
    inf_battalions * inf_manpower
    + art_battalions * art_manpower
)
total_width = (
    inf_battalions * inf_width
    + art_battalions * art_width
)
total_equipment = (
    inf_battalions * inf_equipment
    + art_battalions * art_equipment
)
infantry_soft_attack = inf_battalions * inf_soft_attack
total_battalions = inf_battalions + art_battalions

if total_battalions > 0:
    average_org = (
        inf_battalions * inf_org
        + art_battalions * art_org
    ) / total_battalions
else:
    average_org = 0

print("\nDivision report")
print(f"Manpower: {total_manpower}")
print(f"Combat width: {total_width}")
print(f"Infantry equipment: {inf_battalions * inf_equipment}")
print(f"Artillery equipment: {art_battalions * art_equipment}")
print(f"Total equipment: {total_equipment}")
print(f"Infantry soft attack: {infantry_soft_attack}")
print(f"Artillery support soft-attack modifier: {art_soft_attack_modifier}")
print(f"Base artillery equipment soft attack: {art_equipment_soft_attack}")
print(f"Base artillery equipment defense: {art_equipment_defense}")
print(f"Average organisation: {average_org}")
