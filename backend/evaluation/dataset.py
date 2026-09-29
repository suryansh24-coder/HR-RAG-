"""Retrieval evaluation dataset.

Each case states a question, the documents that *should* be retrieved
(``expected_documents``) and, optionally, a phrase that must appear in the
retrieved text. ``in_domain: false`` marks questions the knowledge base cannot
answer — the assistant must refuse instead of inventing a policy.

``expected_documents`` values are matched against the ``filename`` stored in the
Qdrant payload using a case-insensitive substring comparison, so
``"leave policy"`` matches ``fictional_leave_policy.pdf``.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class EvalCase:
    id: str
    question: str
    expected_documents: list[str] = field(default_factory=list)
    must_contain: list[str] = field(default_factory=list)
    must_not_contain: list[str] = field(default_factory=list)
    in_domain: bool = True
    category: str = "general"
    notes: str = ""


EVAL_CASES: list[EvalCase] = [
    # --- Leave policy ---------------------------------------------------
    EvalCase(
        id="leave_annual_days",
        question="How many paid leave days do I get per year?",
        expected_documents=["leave_policy"],
        must_contain=["18"],
        category="leave",
    ),
    EvalCase(
        id="leave_carry_forward",
        question="Can I carry forward unused annual leave to next year?",
        expected_documents=["leave_policy"],
        must_contain=["5"],
        category="leave",
    ),
    EvalCase(
        id="leave_sick_days",
        question="How many sick leave days do I have?",
        expected_documents=["leave_policy"],
        category="leave",
    ),
    EvalCase(
        id="leave_maternity",
        question="What is the maternity leave entitlement?",
        expected_documents=["leave_policy"],
        must_contain=["26"],
        category="leave",
    ),
    EvalCase(
        id="leave_paternity",
        question="How much paternity leave do I get?",
        expected_documents=["leave_policy"],
        must_contain=["6 weeks"],
        category="leave",
    ),
    EvalCase(
        id="leave_carry_forward_expiry",
        question="When do carried forward leave days expire?",
        expected_documents=["leave_policy"],
        must_contain=["1 March"],
        category="leave",
    ),
    # --- Work from home -------------------------------------------------
    EvalCase(
        id="wfh_core_hours",
        question="What is the work from home policy?",
        expected_documents=["wfh_policy"],
        category="wfh",
    ),
    EvalCase(
        id="wfh_office_days",
        question="How many office days per week do hybrid employees need to attend?",
        expected_documents=["wfh_policy"],
        category="wfh",
    ),
    EvalCase(
        id="wfh_equipment_budget",
        question="What is the home office equipment budget?",
        expected_documents=["wfh_policy"],
        must_contain=["600"],
        category="wfh",
    ),
    EvalCase(
        id="wfh_other_country",
        question="Can I work remotely from a different country?",
        expected_documents=["wfh_policy"],
        category="wfh",
    ),
    # --- Attendance -----------------------------------------------------
    EvalCase(
        id="attendance_working_hours",
        question="What are the standard working hours?",
        expected_documents=["attendance_policy"],
        must_contain=["40"],
        category="attendance",
    ),
    EvalCase(
        id="attendance_core_hours",
        question="What are the core working hours I need to be available?",
        expected_documents=["attendance_policy"],
        category="attendance",
    ),
    EvalCase(
        id="attendance_unauthorised_absence",
        question="What happens if I do not show up to work without telling my manager?",
        expected_documents=["attendance_policy"],
        category="attendance",
    ),
    EvalCase(
        id="attendance_overtime",
        question="How is overtime compensated?",
        expected_documents=["attendance_policy"],
        must_contain=["time off in lieu"],
        category="attendance",
    ),
    # --- Benefits -------------------------------------------------------
    EvalCase(
        id="benefits_health_insurance",
        question="What health insurance do I get and how much do I pay?",
        expected_documents=["employee_benefits"],
        category="benefits",
    ),
    EvalCase(
        id="benefits_retirement",
        question="How much does the company match for retirement savings?",
        expected_documents=["employee_benefits"],
        must_contain=["4%"],
        category="benefits",
    ),
    EvalCase(
        id="benefits_learning_budget",
        question="What is the annual learning and development budget?",
        expected_documents=["employee_benefits"],
        must_contain=["1,200"],
        category="benefits",
    ),
    EvalCase(
        id="benefits_wellness",
        question="What wellness benefits are available?",
        expected_documents=["employee_benefits"],
        category="benefits",
    ),
    # --- Onboarding -----------------------------------------------------
    EvalCase(
        id="onboarding_documents",
        question="What documents do I need to bring on my first day?",
        expected_documents=["onboarding_policy"],
        category="onboarding",
    ),
    EvalCase(
        id="onboarding_probation",
        question="How long is the probation period?",
        expected_documents=["onboarding_policy"],
        must_contain=["3 months"],
        category="onboarding",
    ),
    EvalCase(
        id="onboarding_security_training",
        question="When must new employees complete security training?",
        expected_documents=["onboarding_policy"],
        category="onboarding",
    ),
    # --- Resignation ----------------------------------------------------
    EvalCase(
        id="resignation_notice",
        question="What is the notice period for resigning?",
        expected_documents=["resignation_policy"],
        must_contain=["60 days"],
        category="resignation",
    ),
    EvalCase(
        id="resignation_process",
        question="What is the process to resign from the company?",
        expected_documents=["resignation_policy"],
        category="resignation",
    ),
    EvalCase(
        id="resignation_garden_leave",
        question="What is garden leave?",
        expected_documents=["resignation_policy"],
        category="resignation",
    ),
    # --- Code of conduct ------------------------------------------------
    EvalCase(
        id="conduct_reporting",
        question="How do I report misconduct or harassment?",
        expected_documents=["code_of_conduct"],
        category="conduct",
    ),
    EvalCase(
        id="conduct_gifts",
        question="Can I accept gifts from suppliers?",
        expected_documents=["code_of_conduct"],
        must_contain=["100 USD"],
        category="conduct",
    ),
    # --- Out of scope: must NOT be answered -----------------------------
    EvalCase(
        id="oos_stock_trading",
        question="What is the company's stock trading policy?",
        in_domain=False,
        category="out_of_scope",
        notes="Not covered by any document. The assistant must refuse.",
    ),
    EvalCase(
        id="oos_ceo_address",
        question="What is the CEO's home address?",
        in_domain=False,
        category="out_of_scope",
    ),
    EvalCase(
        id="oos_competitor_salary",
        question="What does a competitor pay their software engineers?",
        in_domain=False,
        category="out_of_scope",
    ),
    EvalCase(
        id="oos_office_recipe",
        question="What is the recipe for sourdough bread?",
        in_domain=False,
        category="out_of_scope",
    ),
    EvalCase(
        id="oos_server_cost",
        question="How much does the company spend on cloud servers each month?",
        in_domain=False,
        category="out_of_scope",
    ),
    EvalCase(
        id="oos_headcount",
        question="How many employees work in the San Francisco office?",
        in_domain=False,
        category="out_of_scope",
    ),
]


def by_category() -> dict[str, list[EvalCase]]:
    grouped: dict[str, list[EvalCase]] = {}
    for case in EVAL_CASES:
        grouped.setdefault(case.category, []).append(case)
    return grouped
