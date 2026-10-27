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
support_manpower = 300
support_width = 0
support_equipment = 12
support_soft_attack_modifier = -0.5
support_equipment_soft_attack = 26  # base artillery equipment (1934 tier)
support_equipment_defense = 11      # base artillery equipment (1934 tier)
support_org = 0

# --- Line artillery (common/units/artillery_brigade.txt + equipment/artillery.txt) ---
line_manpower = 500
line_width = 3
line_equipment = 24
line_soft_attack = 26  # base artillery equipment soft attack (1934 tier)
line_equipment_defense = 11
line_org = 0

while True:
    infantry_input = input(
        "Infantry battalions (or 'exit' to quit): "
    ).strip()
    if infantry_input.lower() == "exit":
        raise SystemExit

    inf_battalions = int(infantry_input)
    artillery_type = input("Artillery type (support or line): ").lower()

    if artillery_type == "support":
        art_manpower = support_manpower
        art_width = support_width
        art_equipment = support_equipment
        art_org = support_org
    elif artillery_type == "line":
        art_manpower = line_manpower
        art_width = line_width
        art_equipment = line_equipment
        art_org = line_org
    else:
        print("Please enter 'support' or 'line'.")
        raise SystemExit(1)

    art_battalions = int(input(f"{artillery_type.title()} artillery battalions: "))

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
    artillery_soft_attack = 0
    if artillery_type == "line":
        artillery_soft_attack = art_battalions * line_soft_attack
    total_soft_attack = infantry_soft_attack + artillery_soft_attack
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
    if artillery_type == "support":
        print(f"Support soft-attack modifier: {support_soft_attack_modifier}")
        print(f"Base artillery equipment soft attack: {support_equipment_soft_attack}")
        print(f"Base artillery equipment defense: {support_equipment_defense}")
    else:
        print(f"Line artillery soft attack: {artillery_soft_attack}")
        print(f"Base artillery equipment defense: {line_equipment_defense}")
        print(f"Calculated soft attack: {total_soft_attack}")
    print(f"Average organisation: {average_org}")
