from decimal import Decimal, ROUND_HALF_UP


def calculate_grn_weights_and_cost(
    gross_weight: Decimal,
    tare_weight: Decimal,
    moisture_percentage: Decimal,
    contamination_kg: Decimal,
    rate_per_kg: Decimal,
) -> dict[str, Decimal]:
    """
    Implements statutory scrap deduction formulas from PRD:
      • Net Weight = Gross Weight - Tare Weight
      • Moisture Deduction (kg) = Net Weight * (Moisture% / 100)
      • Accepted Net Weight = Net Weight - Moisture Deduction - Contamination Deduction
      • Total Payable Amount = Accepted Net Weight * Rate per KG
    """
    two_places = Decimal("0.01")

    # 1. Net Weight Check
    net_weight = gross_weight - tare_weight
    if net_weight < Decimal("0.00"):
        raise ValueError("Tare weight cannot exceed gross weight.")

    # 2. Moisture Deduction Computation
    moisture_pct = max(Decimal("0.00"), min(moisture_percentage, Decimal("100.00")))
    moisture_deduction_kg = (net_weight * (moisture_pct / Decimal("100.00"))).quantize(
        two_places, rounding=ROUND_HALF_UP
    )

    # 3. Accepted Weight Clamping
    contamination = max(Decimal("0.00"), contamination_kg)
    accepted_net_weight = net_weight - moisture_deduction_kg - contamination

    if accepted_net_weight < Decimal("0.00"):
        accepted_net_weight = Decimal("0.00")

    # 4. Total Cost Calculation
    total_cost = (accepted_net_weight * rate_per_kg).quantize(
        two_places, rounding=ROUND_HALF_UP
    )

    return {
        "net_weight": net_weight.quantize(two_places, rounding=ROUND_HALF_UP),
        "moisture_deduction_kg": moisture_deduction_kg,
        "contamination_deduction_kg": contamination.quantize(two_places, rounding=ROUND_HALF_UP),
        "accepted_net_weight": accepted_net_weight.quantize(two_places, rounding=ROUND_HALF_UP),
        "total_payable_amount": total_cost,
    }