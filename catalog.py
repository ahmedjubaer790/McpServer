"""Semantic notes for the AI Reporting Layer (3 Views Setup)."""

from __future__ import annotations

CURRENCY = "BDT (Bangladeshi taka)"
FISCAL_NOTE = (
    "SmartStore operates retail outlets. Weekly sales peak on Friday and Saturday. "
    "Daily trading patterns shift during campaign and holiday periods."
)

VIEWS: dict[str, dict[str, str]] = {
    "V_SMART_DAILY_SALES": {
        "grain": "One outlet, one business date.",
        "use": "Daily revenue analysis. Use SUM(total_gross_sales) for gross sales, "
               "SUM(total_tax) for VAT, and SUM(total_transactions) for transaction count.",
        "trap": "total_gross_sales is VAT-inclusive. For average basket size, calculate "
                "total_gross_sales / total_transactions.",
    },
    "V_SMART_CASH_VARIANCE": {
        "grain": "One outlet, one register business day.",
        "use": "Daily cash integrity. drawer_balance is physical cash; system_balance is POS balance; "
               "cash_variance is the gap. Identifies store cash shortages and excess.",
        "trap": "A negative cash_variance indicates a cash SHORTAGE (drawer < system); a positive "
                "value indicates an EXCESS. status_flag = 'SHORT_HIGH' or 'EXCESS_HIGH' flags variances > 2,000 BDT.",
    },
    "V_SMART_CUSTOMER_RETENTION": {
        "grain": "One anonymized customer, one outlet.",
        "use": "Customer visit frequency, repeat retention, and outlet loyalty analysis.",
        "trap": "customer_hash is a cryptographically salted SHA-256 hash. Personal phone numbers "
                "and NIDs are strictly masked and cannot be reverse-engineered.",
    },
}

CROSS_CHECKS = [
    "Cash Integrity: Any outlet showing 'SHORT_HIGH' or 'EXCESS_HIGH' in V_SMART_CASH_VARIANCE "
    "for multiple dates requires an audit.",
    "Sales vs Frequency: Compare total_gross_sales in V_SMART_DAILY_SALES against visit frequency "
    "in V_SMART_CUSTOMER_RETENTION to gauge customer spend per visit.",
]

OPEN_ASSUMPTIONS = [
    "A1: Outlets in all three views map seamlessly via OUTLET_NAME / OUTLET_ID.",
    "A2: total_gross_sales in V_SMART_DAILY_SALES includes VAT.",
    "A3: All transactions represented are verified and active (STATUS = 'A').",
    "A4: Customer mobile numbers are normalized before SHA-256 hashing.",
]


def overview() -> str:
    """Returns structured markdown briefing for the get_schema_notes tool."""
    parts = [
        "# SmartStore AI Reporting Semantic Layer",
        f"Currency: {CURRENCY}",
        f"Note: {FISCAL_NOTE}",
        "",
        "## Available Views",
    ]
    for name, meta in VIEWS.items():
        parts.append(f"\n### {name}")
        parts.append(f"- Grain: {meta['grain']}")
        parts.append(f"- Use: {meta['use']}")
        parts.append(f"- Trap: {meta['trap']}")

    parts.append("\n## Cross Checks")
    parts += [f"- {c}" for c in CROSS_CHECKS]

    parts.append("\n## Open Assumptions")
    parts += [f"- {a}" for a in OPEN_ASSUMPTIONS]

    return "\n".join(parts)



# """Semantic notes for the AI Reporting Layer.

# This is the difference between an AI that merely queries the database and one
# that truly understands the business logic. Each entry states the grain (what one 
# row represents), what the view is for, and the operational traps to avoid. 
# Claude reads this before generating SQL, which is why it produces accurate joins 
# and aggregations on the first attempt.

# Edit freely as the business model evolves - it is semantic documentation, not runtime code.
# """

# from __future__ import annotations #type hints/annotations handling

# CURRENCY = "BDT (Bangladeshi taka)"
# FISCAL_NOTE = (
#     "SmartStore operates retail outlets across multiple zones in Bangladesh. "
#     "Weekly sales peak on Friday and Saturday evenings. Seasonal campaigns "
#     "(Eid-ul-Fitr, Eid-ul-Adha, Puja, and Year-End Clearance) drastically shift "
#     "trading volume - never compare campaign months with regular trading periods "
#     "without explicitly stating the context."
# )

# VIEWS: dict[str, dict[str, str]] = {
#     "V_AI_OUTLET": {
#         "grain": "One physical retail outlet / store.",
#         "use": "The core dimension table. Join all transaction and reconciliation views "
#                "to this for outlet_name, region_name, and outlet_type.",
#         "trap": "is_franchise flags franchised outlets. Confirm with management whether "
#                 "franchise sales should be included in consolidated company revenue.",
#     },
#     "V_AI_DAILY_SALES": {
#         "grain": "One outlet, one business date, one POS counter, one item line.",
#         "use": "Revenue analysis by category, brand, and outlet. Use SUM(line_total) for "
#                "gross revenue and SUM(tax_amount) for total VAT/Tax.",
#         "trap": "Never use COUNT(*) to count total customer transactions because a single "
#                 "order contains multiple item lines. Use COUNT(DISTINCT order_id) instead. "
#                 "unit_price is VAT-exclusive; line_total includes applicable tax.",
#     },
#     "V_AI_HOURLY_TRAFFIC": {
#         "grain": "One outlet, one date, one hour window (0-23), one payment method.",
#         "use": "Hourly sales heatmaps, peak footfall tracking, shift scheduling, and "
#                "digital payment (MFS/Card) adoption rates.",
#         "trap": "Hours with zero transactions are completely absent from rows (not 0). "
#                 "Always use a calendar/time-dimension spine if you need a continuous 24-hour graph.",
#     },
#     "V_AI_CASH_VARIANCE": {
#         "grain": "One outlet, one business day.",
#         "use": "Daily register and cash drawer integrity. physical_cash is the actual cash "
#                "counted by the cashier; system_cash is POS registered cash; cash_variance is the gap. "
#                "Critical view for detecting store-level cash leakages.",
#         "trap": "A negative cash_variance indicates a cash SHORTAGE (drawer < system); a positive "
#                 "value indicates an EXCESS. Both are anomalies. signoff_status = 'PENDING' means "
#                 "the day has not been audited by Accounts.",
#     },
#     "V_AI_TARGET_DAILY": {
#         "grain": "One outlet, one business date.",
#         "use": "Daily revenue budgets and sales targets assigned by Central Operations.",
#         "trap": "ASSUMPTION A1: If an outlet shows a target but zero sales, verify if the "
#                 "outlet was temporarily closed for renovation before reporting zero achievement.",
#     },
#     "V_AI_SCORECARD": {
#         "grain": "One outlet, one calendar month.",
#         "use": "Target vs actual revenue with achievement_pct. Primary metric feeding "
#                "outlet manager incentive calculations.",
#         "trap": "A NULL achievement_pct indicates the sales target was zero or not configured, "
#                 "not that the outlet had zero performance. Always clarify the distinction.",
#     },
#     "V_AI_EXPENSE": {
#         "grain": "One outlet, one business day, one expense head, one voucher line.",
#         "use": "Store-level operating expenses (OPEX) such as petty cash, utilities, and logistics. "
#                "Aggregate with V_AI_DAILY_SALES for store-level EBITDA calculations.",
#         "trap": "voucher_total repeats across multiple expense lines of the same voucher. "
#                 "Never SUM(voucher_total) — always SUM(expense_amount).",
#     },
#     "V_AI_CUSTOMER_METRICS": {
#         "grain": "One customer, one outlet, one business day.",
#         "use": "Customer retention, repeat basket size, and average order value (AOV).",
#         "trap": "customer_hash is a cryptographically salted SHA-256 hash. It is mathematically "
#                 "impossible to reverse it back to a phone number or NID. Raw customer lists "
#                 "must go through formal DBA data-protection clearance.",
#     },
#     "V_AI_CUSTOMER_RFM": {
#         "grain": "One customer entity.",
#         "use": "Recency, Frequency, and Monetary scores on a 1 to 4 scale (4 is the highest). "
#                "Segments: R=4, F=4, M=4 are Champions; R=1, F=4 are At-Risk Loyalists.",
#         "trap": "RFM scores are relative percentiles of the total customer base. A drop in score "
#                 "might indicate overall base growth rather than individual inactivity.",
#     },
#     "V_AI_DISCOUNT_EXPOSURE": {
#         "grain": "One outlet, one day, one promo campaign.",
#         "use": "Discount vouchers issued, promotional markdowns, and campaign ROI. "
#                "Pair with footfall to detect promo abuse or margin erosion.",
#         "trap": "This view counts promotional allowances granted at POS. A surge in discount "
#                 "value alongside flat sales volume indicates severe margin leakage.",
#     },
#     "V_AI_INVENTORY_STOCK": {
#         "grain": "One outlet, one SKU/Product item.",
#         "use": "Current on-hand stock levels, safety stock thresholds, and stockout alerts.",
#         "trap": "available_qty reflects real-time unreserved stock. Negative quantities indicate "
#                 "POS unbilled handovers or delayed GRN entries.",
#     },
# }

# CROSS_CHECKS = [
#     "Cash Integrity Check: V_AI_CASH_VARIANCE.physical_cash vs system_cash. "
#     "Any |cash_variance| > 2,000 BDT for two consecutive days is an internal control failure.",

#     "Footfall vs Revenue Check: Rising customer counts in V_AI_CUSTOMER_METRICS with flat "
#     "or declining revenue in V_AI_DAILY_SALES and high discount volume in V_AI_DISCOUNT_EXPOSURE "
#     "is the classic signal of discount leakage.",

#     "Three-Way Reconciliation: Compare daily POS digital receipts in V_AI_HOURLY_TRAFFIC against "
#     "bank statement deposit settlements with a 1-to-2 business day settlement lag.",

#     "Scorecard vs Incentive Integrity: Outlets showing high achievement_pct in V_AI_SCORECARD "
#     "with recurring negative cash variances in V_AI_CASH_VARIANCE must be audited prior to incentive release.",
# ]

# OPEN_ASSUMPTIONS = [
#     "A1: Outlets in TARGET_DAILY map 1:1 with OUTLET_ID in sales transactions.",
#     "A2: line_total in V_AI_DAILY_SALES is net of line discounts and includes statutory VAT.",
#     "A3: STATUS = 'A' represents active and valid transactions across all tables.",
#     "A4: Customer mobile numbers are normalized to standard E.164 format before SHA-256 hashing.",
#     "A5: Franchised outlet sales are segregated from company-owned store revenue.",
#     "A6: Returns/Refunds are stored as negative line_total values in V_AI_DAILY_SALES.",
# ]


# def overview() -> str:
#     """A compact, structured briefing string returned by the get_schema_notes tool."""
#     parts = [
#         "# SmartStore AI Reporting Semantic Layer Guide",
#         f"Base Currency: {CURRENCY}",
#         f"Operational Note: {FISCAL_NOTE}",
#         "",
#         "## Available Semantic Views",
#     ]
#     for name, meta in VIEWS.items():
#         parts.append(f"\n### {name}")
#         parts.append(f"- Grain: {meta['grain']}")
#         parts.append(f"- Intended Use: {meta['use']}")
#         parts.append(f"- Guardrail / Trap: {meta['trap']}")

#     parts.append("\n## Multi-View Cross Checks")
#     parts += [f"- {c}" for c in CROSS_CHECKS]

#     parts.append("\n## Open Business Assumptions")
#     parts += [f"- {a}" for a in OPEN_ASSUMPTIONS]

#     return "\n".join(parts)