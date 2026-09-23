from decimal import Decimal


def calculate_grn_weights_and_cost(
    gross_weight: Decimal,
    tare_weight: Decimal,
    moisture_percentage: Decimal,
    contamination_kg: Decimal,
    rate_per_kg: Decimal,
) -> dict[str, Decimal]:
    """
    Implements deduction formulas from the PRD[cite: 1]:
    Net Weight = Gross - Tare
    Moisture Deduction = Net Weight * (Moisture% / 100)
    Accepted Net Weight = Net Weight - Moisture Deduction - Contamination Deduction
    """
    net_weight = gross_weight - tare_weight
    if net_weight < Decimal("0.00"):
        raise ValueError("Tare weight cannot exceed gross weight.")

    moisture_deduction_kg = net_weight * (moisture_percentage / Decimal("100.00"))
    accepted_net_weight = net_weight - moisture_deduction_kg - contamination_kg

    if accepted_net_weight < Decimal("0.00"):
        accepted_net_weight = Decimal("0.00")

    total_cost = (accepted_net_weight * rate_per_kg).quantize(Decimal("0.01"))

    return {
        "net_weight": net_weight.quantize(Decimal("0.01")),
        "accepted_net_weight": accepted_net_weight.quantize(Decimal("0.01")),
        "total_payable_amount": total_cost,
    }