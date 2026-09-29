#!/usr/bin/env python
"""Generate the fictional demo HR knowledge base.

All content in this script is **fictional** and was written for this project. It
does not reproduce, paraphrase or resemble any real company's HR policy.

Outputs (into ``data/documents/``):

* ``fictional_leave_policy.pdf``
* ``fictional_wfh_policy.pdf``
* ``fictional_attendance_policy.pdf``
* ``fictional_employee_benefits.pdf``
* ``fictional_onboarding_policy.pdf``
* ``fictional_code_of_conduct.md``
* ``fictional_resignation_policy.md``

Usage::

    python scripts/generate_sample_documents.py [--force]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "data" / "documents"

DISCLAIMER = (
    "FICTIONAL DEMO DOCUMENT - created for the HR Nexus sample knowledge base. "
    "This is not a real company policy."
)

BODY_STYLE = {"fontname": "helv", "fontsize": 10.5, "leading": 14}


# --------------------------------------------------------------------------- #
# PDF helpers
# --------------------------------------------------------------------------- #
def _page_template(page, title: str, subtitle: str, page_no: int, total: int):
    """Draw the header/footer furniture shared by every page."""
    rect = page.rect
    page.insert_text((54, 58), "HR NEXUS - DEMO KNOWLEDGE BASE", fontsize=7.5, fontname="helv")
    page.insert_text((rect.width - 54 - 190, 58), DISCLAIMER[:62], fontsize=7.5, fontname="helv")
    page.draw_line((54, 64), (rect.width - 54, 64), color=(0.75, 0.78, 0.85), width=0.6)
    page.insert_text(
        (rect.width - 54 - 90, rect.height - 34),
        f"Page {page_no} of {total}",
        fontsize=8,
        fontname="helv",
        color=(0.45, 0.48, 0.55),
    )
    page.insert_text((54, rect.height - 34), f"{title} - {subtitle}", fontsize=8, fontname="helv",
                     color=(0.45, 0.48, 0.55))


def _render(title: str, subtitle: str, pages: list[list[tuple[str, str]]]) -> bytes:
    """Render ``pages`` (a list of blocks) into a paginated PDF and return bytes."""
    import pymupdf

    doc = pymupdf.open()
    total = len(pages)
    for index, blocks in enumerate(pages, start=1):
        page = doc.new_page(width=595, height=842)  # A4
        _page_template(page, title, subtitle, index, total)

        y = 108
        for kind, content in blocks:
            if kind == "h1":
                y += 6
                page.insert_text((54, y), content, fontsize=16, fontname="hebo", color=(0.08, 0.11, 0.2))
                y += 8
                page.draw_line((54, y), (541, y), color=(0.2, 0.35, 0.75), width=1.1)
                y += 22
            elif kind == "h2":
                y += 8
                page.insert_text((54, y), content, fontsize=12, fontname="hebo", color=(0.12, 0.16, 0.28))
                y += 18
            elif kind == "p":
                for line in _wrap(page, content, 487, 10.5):
                    page.insert_text((54, y), line, fontsize=10.5, fontname="helv",
                                     color=(0.13, 0.15, 0.2))
                    y += 14
                y += 6
            elif kind == "li":
                for line in _wrap(page, content, 470, 10.5):
                    page.insert_text((66, y), "- " + line, fontsize=10.5, fontname="helv",
                                     color=(0.13, 0.15, 0.2))
                    y += 14
                y += 3
            elif kind == "note":
                rect = pymupdf.Rect(54, y - 11, 541, y + 13)
                page.draw_rect(rect, color=(0.85, 0.88, 0.96), fill=(0.96, 0.97, 1.0), width=0.5)
                page.insert_text((64, y + 2), content[:110], fontsize=9.5, fontname="heit",
                                 color=(0.2, 0.3, 0.55))
                y += 26
            if y > 770:  # keep content inside the printable area
                break

    return doc.tobytes()


def _text_width(text: str, fontsize: float) -> float:
    """Approximate Helvetica text width (PyMuPDF removed Page.get_text_length)."""
    narrow = set("iljtfIr.,:;'|!()[]{}/\\")
    wide = set("mwMW@%")
    total = 0.0
    for char in text:
        if char in narrow:
            total += 0.30
        elif char in wide:
            total += 0.90
        elif char.isupper() or char.isdigit():
            total += 0.68
        else:
            total += 0.52
    return total * fontsize


def _wrap(page, text: str, width: float, fontsize: float) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if _text_width(candidate, fontsize) > width:
            if current:
                lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


# --------------------------------------------------------------------------- #
# Document content (all fictional)
# --------------------------------------------------------------------------- #
LEAVE_POLICY = [
    [("h1", "Leave Policy"),
     ("p", "Company: Northwind Digital (fictional demo company)"),
     ("p", "Policy owner: People Operations. Applies to all full-time employees "
           "globally. This document describes the fictional leave entitlements used "
           "to demonstrate the HR Nexus knowledge assistant."),
     ("h2", "1. Annual leave entitlement"),
     ("p", "Every full-time employee receives 18 days of paid annual leave per "
           "completed calendar year. The entitlement is granted in full on "
           "1 January and does not pro-rate for employees who joined during the "
           "year, except contractors who are not eligible for paid leave at all."),
     ("h2", "2. Carry forward"),
     ("p", "Up to 5 unused days of annual leave may be carried forward into the "
           "following calendar year. Carried-forward days must be used before "
           "1 March of the following year, after which they expire. A maximum of "
           "5 carried days may be accumulated across years."),
     ("h2", "3. Sick leave"),
     ("p", "Employees receive 10 days of paid sick leave per calendar year. A "
           "medical certificate is required for any absence of 3 consecutive "
           "working days or more. Unused sick leave cannot be carried forward and "
           "is not paid out on termination."),
     ("h2", "4. Parental leave")],
    [("h2", "4.1 Maternity leave"),
     ("p", "Primary caregivers receive 26 weeks of fully paid maternity leave. "
           "Maternity leave may be taken in up to three separate blocks within the "
           "first 18 months after the birth or adoption of a child."),
     ("h2", "4.2 Paternity leave"),
     ("p", "Secondary caregivers receive 6 weeks of fully paid paternity leave, to "
           "be taken within 6 months of the birth or adoption. Two additional "
           "weeks of unpaid paternity leave are available on request."),
     ("h2", "4.3 Parental leave for adoption and surrogacy"),
     ("p", "The same entitlements apply to adoption and surrogacy arrangements. "
           "Employees must notify People Operations at least 30 days before the "
           "expected date where reasonably practicable."),
     ("h2", "5. Unpaid leave"),
     ("p", "Employees may request unpaid leave of any duration. Requests longer "
           "than 4 weeks require approval from the department head and People "
           "Operations. Unpaid leave does not accrue annual leave and may affect "
           "variable pay."),
     ("h2", "6. Public holidays"),
     ("p", "Employees in the country of their employing entity observe the public "
           "holidays of that country. Where a public holiday falls on a weekend, "
           "the following Monday is observed."),
     ("h2", "7. Leave approval"),
     ("p", "All leave must be requested in the HR portal at least 5 working days "
           "before the requested start date. Approval is granted by the direct "
           "manager unless the leave exceeds 10 consecutive working days, in which "
           "case People Operations must also approve."),
     ("h2", "8. Leave during notice period"),
     ("p", "Unused annual leave may be taken during a notice period with manager "
           "approval. Leave already booked cannot be cancelled by the employee less "
           "than 2 weeks before it starts."),
     ("note", "Questions about leave are answered by People Operations: people@northwind.example")],
]

WFH_POLICY = [
    [("h1", "Work From Home Policy"),
     ("p", "Company: Northwind Digital (fictional demo company)"),
     ("h2", "1. Principles"),
     ("p", "Northwind Digital is a hybrid company. Work from home is a permanent "
           "entitlement for roles that are classified as remote-eligible, and a "
           "team-level arrangement for other roles."),
     ("h2", "2. Eligibility"),
     ("li", "Remote-eligible roles: all Product, Engineering, Design and Research "
            "positions, plus any role explicitly listed in the HR system."),
     ("li", "Hybrid roles: Customer Success, Sales and Finance default to 2 office "
            "days per week."),
     ("li", "On-site roles: Facilities, Security and certain Operations roles "
            "require on-site presence on all working days."),
     ("h2", "3. Core collaboration hours"),
     ("p", "Employees must be reachable between 10:00 and 16:00 in their team's "
           "primary time zone. Outside these hours employees may work at times "
           "that suit them. Teams spanning 4 or more time zones nominate a 2-hour "
           "overlap window for synchronous collaboration."),
     ("h2", "4. Equipment and expenses"),
     ("p", "Each remote-eligible employee receives a one-time home office budget of "
           "600 USD for a monitor, keyboard, chair or lighting. Employees may claim "
           "up to 45 USD per month towards home internet. A company laptop and "
           "security key are issued on the first day of remote work.")],
    [("h2", "5. Security and data protection"),
     ("p", "All work must be performed on the company-issued device. The device "
           "must be locked whenever it is unattended and screen locking must not be "
           "disabled. Confidential HR and customer data must not be discussed in "
           "public places where it can be overheard."),
     ("h2", "6. Working from another country"),
     ("p", "Employees may work remotely from outside their country of employment for "
           "a maximum of 20 working days per calendar year, subject to People "
           "Operations approval and to tax and immigration review. Requests must be "
           "made at least 4 weeks in advance."),
     ("h2", "7. Measuring outcomes"),
     ("p", "Performance is measured on outcomes rather than presence. Employees are "
           "not expected to work fixed hours from home, but they must attend team "
           "rituals, one-to-ones and customer meetings in the agreed time zone."),
     ("h2", "8. Review"),
     ("p", "The policy is reviewed every 12 months by People Operations. Feedback "
           "can be submitted through the engagement survey or directly to the "
           "People Operations team."),
     ("note", "Equipment requests are handled through the IT service desk.")],
]

ATTENDANCE_POLICY = [
    [("h1", "Attendance, Hours and Time Off Policy"),
     ("p", "Company: Northwind Digital (fictional demo company)"),
     ("h2", "1. Standard working hours"),
     ("p", "The standard working week is 40 hours, Monday to Friday. Core working "
           "hours are 10:00 to 16:00 local time. Flexible start and end times are "
           "permitted provided the employee is available during core hours."),
     ("h2", "2. Working days and weekends"),
     ("p", "Saturday and Sunday are non-working days. Some customer-facing teams "
           "operate a rotating weekend roster; team members on the roster receive "
           "time off in lieu for each weekend shift worked."),
     ("h2", "3. Recording time"),
     ("p", "Employees do not clock in or out. Time worked is recorded through the "
           "timesheet in the HR portal, which must be submitted every two weeks. "
           "Submitting a timesheet late more than three times in a quarter is "
           "treated as a policy violation."),
     ("h2", "4. Late arrival"),
     ("p", "Arriving after 10:00 is recorded as a late arrival. More than 3 late "
           "arrivals in a calendar month triggers a conversation with the manager. "
           "Frequent lateness may result in formal disciplinary action."),
     ("h2", "5. Absence without notice"),
     ("p", "An employee who does not attend work and does not notify their manager "
           "before the scheduled start time is recorded as an unauthorised absence. "
           "Three unauthorised absences in a rolling 12-month period are treated as "
           "gross misconduct and may result in dismissal."),
     ("h2", "6. Working during sickness"),
     ("p", "Employees who are unwell should not work, even remotely. If an employee "
           "reports working while on sick leave, People Operations may request a "
           "medical certificate to confirm fitness to work.")],
    [("h2", "7. Overtime"),
     ("p", "Overtime is not paid. Time worked beyond 40 hours in a week is taken "
           "back as time off in lieu, which must be taken within the following "
           "calendar month. Approval for overtime is required in advance from the "
           "direct manager."),
     ("h2", "8. Part-time and flexible schedules"),
     ("p", "Part-time schedules are agreed per employee and normally run at 80% or "
           "50% of full time. Flexible schedules covering an early shift (07:00 "
           "start) are available to designated teams."),
     ("h2", "9. Travel and commuting"),
     ("p", "Employees who travel for work record travel time as working time where "
           "reasonably possible. Commuting time is not recorded as working time."),
     ("h2", "10. Breaches of this policy"),
     ("p", "Breaches are handled through the disciplinary process described in the "
           "Code of Conduct. Where an absence is caused by an emergency, the "
           "employee is expected to notify their manager as soon as reasonably "
           "practicable."),
     ("note", "Attendance records are reviewed by People Operations every month.")],
]

BENEFITS = [
    [("h1", "Employee Benefits Guide"),
     ("p", "Company: Northwind Digital (fictional demo company)"),
     ("h2", "1. Health insurance"),
     ("p", "Employees are enrolled in the company medical plan from their first day "
           "of employment, with no waiting period. Dependents may be added at any "
           "time during the year. The employee contributes 20% of the monthly "
           "premium and the company contributes 80%."),
     ("h2", "2. Dental and vision"),
     ("p", "A supplementary dental plan and a vision plan are provided free of "
           "charge. The vision plan covers an annual eye examination and a frame "
           "allowance of 200 USD per calendar year."),
     ("h2", "3. Retirement savings"),
     ("p", "Employees can join the 401(k) retirement savings plan from day one. The "
           "company matches 4% of salary, vesting over 3 years. The contribution "
           "limit is set by the plan administrator each year."),
     ("h2", "4. Life insurance"),
     ("p", "The company provides life insurance equal to 2 times base salary, plus "
           "voluntary supplemental life insurance at the employee's own cost."),
     ("h2", "5. Paid parental leave supplements"),
     ("p", "All fully paid parental leave described in the Leave Policy is topped up "
           "to 100% of base salary for the first 3 months, so that parents receive "
           "full pay rather than only the statutory amount.")],
    [("h2", "6. Learning and development"),
     ("p", "Each employee receives an annual learning budget of 1,200 USD and 5 "
           "dedicated learning days. Conference attendance requires manager approval "
           "and is covered by the learning budget."),
     ("h2", "7. Wellness"),
     ("p", "Employees receive a quarterly wellbeing stipend of 100 USD for fitness, "
           "mental health or ergonomic products. A confidential employee assistance "
           "programme provides 8 free counselling sessions per year."),
     ("h2", "8. Equipment and home office"),
     ("p", "Remote-eligible employees receive a 600 USD one-time home office budget "
           "and a monthly home internet allowance of 45 USD, as described in the "
           "Work From Home Policy."),
     ("h2", "9. Relocation support"),
     ("p", "Employees relocating for a new role inside the company receive up to "
           "8,000 USD towards relocation costs, available after 12 months in the new "
           "role."),
     ("h2", "10. Time off in lieu"),
     ("p", "Employees may convert up to 5 unused wellness days each year into "
           "time off in lieu, subject to manager approval."),
     ("note", "Benefits questions: benefits@northwind.example")],
]

ONBOARDING = [
    [("h1", "Onboarding and Joining Process"),
     ("p", "Company: Northwind Digital (fictional demo company)"),
     ("h2", "1. Before your first day"),
     ("li", "You receive an offer letter and a welcome pack at least 10 working "
            "days before your start date."),
     ("li", "People Operations sends your equipment shipment tracking number."),
     ("li", "You complete the secure identity verification form in the HR portal."),
     ("h2", "2. Documents required on the first day"),
     ("li", "Signed employment contract and confidentiality agreement."),
     ("li", "Proof of identity: passport or national identity card."),
     ("li", "Proof of address dated within the last 3 months."),
     ("li", "Bank account details for salary payment."),
     ("li", "Signed tax declaration and social security details where applicable."),
     ("li", "Signed employee handbook acknowledgement."),
     ("li", "Emergency contact details."),
     ("h2", "3. First week"),
     ("p", "Day one includes IT setup, payroll registration and a welcome session "
           "with People Operations. Your manager runs a team introduction session "
           "and assigns a buddy for your first month."),
     ("h2", "4. Probation period"),
     ("p", "New employees have a probation period of 3 months for professional "
           "roles and 6 months for graduate roles. A probation review meeting takes "
           "place at the midpoint and at the end of the period."),
     ("h2", "5. 30-60-90 day plan"),
     ("p", "Every new employee agrees a written 30-60-90 day plan with their "
           "manager during the first week. The plan is reviewed at the 90 day "
           "probation checkpoint.")],
    [("h2", "6. Security training"),
     ("p", "All new employees must complete security awareness training within the "
           "first 5 working days. Compliance with the acceptable use policy is a "
           "condition of employment."),
     ("h2", "7. Relocation and remote onboarding"),
     ("p", "Employees who join remotely receive a equipment shipment to their home "
           "address. Remote onboarding includes a mandatory 1:1 video call with "
           "People Operations in the employee's first week."),
     ("h2", "8. Who to contact"),
     ("li", "Payroll and benefits: benefits@northwind.example"),
     ("li", "Equipment and access: it-helpdesk@northwind.example"),
     ("li", "Contracts and policies: people@northwind.example"),
     ("note", "Complete onboarding tasks in the HR portal within the first 10 days.")],
]

CODE_OF_CONDUCT = """---
title: "Code of Conduct (Fictional Demo Document)"
owner: "People Operations"
version: "3.2"
---

# Code of Conduct

> **FICTIONAL DEMO DOCUMENT.** Northwind Digital is an invented company created
> for the HR Nexus sample knowledge base. Nothing in this document describes a
> real organisation.

## 1. Purpose

This Code of Conduct sets the standard of behaviour expected from everyone at
Northwind Digital. It applies to employees, contractors, managers and anyone
acting on behalf of the company.

## 2. Respect in the workplace

We treat colleagues, candidates and customers with respect. Harassment,
bullying, discrimination and violence are not tolerated in any form, including
verbal abuse, written messages and social media posts made in a work context.

## 3. Discrimination

We make employment decisions on the basis of skill and business requirements.
Discrimination on the grounds of race, colour, religion, gender, gender
identity, sexual orientation, age, disability, or any other protected
characteristic is prohibited.

## 4. Reporting concerns

Employees who experience or witness misconduct should report it to their
manager, to People Operations at people@northwind.example, or through the
anonymous ethics line. Reports are investigated confidentially within 10 working
days.

Retaliation against anyone who reports a concern in good faith is a serious
disciplinary matter.

## 5. Conflicts of interest

Employees must disclose any personal, financial or family relationship with a
supplier, customer or competitor to People Operations. Employees may not accept
gifts or hospitality worth more than 100 USD from any supplier or customer.

## 6. Social media

Employees must not post confidential information, customer data or internal
policies on social media. They may share their own views provided they do not
imply that they are speaking on behalf of the company.

## 7. Intellectual property

All work created during employment, including code, designs, documents and
inventions, belongs to the company. Employees must assign all relevant rights to
Northwind Digital in their employment contract.

## 8. Discipline

Breaches of this Code of Conduct are handled through the disciplinary process.
Depending on severity, consequences range from a written warning to summary
dismissal.
"""

RESIGNATION_POLICY = """---
title: "Resignation and Notice Policy (Fictional Demo Document)"
owner: "People Operations"
version: "2.1"
---

# Resignation and Notice

> **FICTIONAL DEMO DOCUMENT.** Invented for the HR Nexus sample knowledge base.

## 1. Notice period

Employees must give **60 days (8 weeks)** of written notice. The notice period
applies to all permanent employees regardless of grade.

| Employment type | Notice period |
| --- | --- |
| Permanent employee | 60 days |
| Graduate employee | 30 days during the first 6 months, then 60 days |
| Fixed-term employee | The remainder of the contract or 30 days, whichever is shorter |

## 2. How to resign

1. Tell your manager verbally as early as possible.
2. Submit written notice through the HR portal, addressed to People Operations.
3. People Operations confirms the last working day in writing within 5 working days.
4. Complete the exit checklist and hand over your work before your last day.

## 3. Garden leave

Northwind Digital may place an employee on garden leave (paid, but not working)
for all or part of the notice period. Garden leave is used where there is a risk
to the business, its clients or its data.

## 4. Working during notice

You are expected to work normally and to support a good handover during your
notice period. Your manager will agree a handover plan in the first week of
notice.

## 5. Leaving allowances

| Length of service | Payment in lieu of notice |
| --- | --- |
| Less than 12 months | No payment |
| 12 months to 2 years | 15 days |
| 2 to 5 years | 30 days |
| More than 5 years | 45 days |

Payments in lieu of notice are not payable if the company terminates the
employment for misconduct or if the company exercises garden leave.

## 6. Final pay

Final pay is issued on the last working day of the month in which employment
ends. It includes salary for days worked, unused annual leave up to 5 days, and
any expenses not yet claimed.

## 7. Benefits after leaving

Health insurance cover continues until the end of the month in which employment
ends. Employees may continue cover under the private continuation scheme for up
to 9 months.

## 8. Exit interview

All leavers are invited to an exit interview within 10 working days of their last
day. Exit interviews are confidential and are reported to the People team in
aggregate.

## 9. Offboarding

Access to internal systems is revoked at 18:00 on the last working day unless the
employee is on garden leave, in which case access is revoked immediately.
"""


def _write_pdf(name: str, title: str, subtitle: str, pages: list) -> Path:
    path = OUTPUT_DIR / name
    path.write_bytes(_render(title, subtitle, pages))
    return path


def _write_text(name: str, content: str) -> Path:
    path = OUTPUT_DIR / name
    path.write_text(content, encoding="utf-8")
    return path


def generate(force: bool = False) -> list[Path]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []

    targets: list[tuple[Path, str]] = [
        (OUTPUT_DIR / "fictional_leave_policy.pdf", "pdf"),
        (OUTPUT_DIR / "fictional_wfh_policy.pdf", "pdf"),
        (OUTPUT_DIR / "fictional_attendance_policy.pdf", "pdf"),
        (OUTPUT_DIR / "fictional_employee_benefits.pdf", "pdf"),
        (OUTPUT_DIR / "fictional_onboarding_policy.pdf", "pdf"),
        (OUTPUT_DIR / "fictional_code_of_conduct.md", "md"),
        (OUTPUT_DIR / "fictional_resignation_policy.md", "md"),
    ]

    for path, kind in targets:
        if path.exists() and not force:
            print(f"  skip (exists) {path.relative_to(PROJECT_ROOT)}")
            continue
        if kind == "pdf":
            mapping = {
                "fictional_leave_policy.pdf": ("Leave Policy", "Leave and absence"),
                "fictional_wfh_policy.pdf": ("Work From Home Policy", "Remote work"),
                "fictional_attendance_policy.pdf": (
                    "Attendance Policy",
                    "Hours and attendance",
                ),
                "fictional_employee_benefits.pdf": (
                    "Employee Benefits Guide",
                    "Benefits and wellbeing",
                ),
                "fictional_onboarding_policy.pdf": (
                    "Onboarding and Joining Process",
                    "Onboarding",
                ),
            }
            title, subtitle = mapping[path.name]
            pages = {
                "fictional_leave_policy.pdf": LEAVE_POLICY,
                "fictional_wfh_policy.pdf": WFH_POLICY,
                "fictional_attendance_policy.pdf": ATTENDANCE_POLICY,
                "fictional_employee_benefits.pdf": BENEFITS,
                "fictional_onboarding_policy.pdf": ONBOARDING,
            }[path.name]
            created.append(_write_pdf(path.name, title, subtitle, pages))
        else:
            content = CODE_OF_CONDUCT if "conduct" in path.name else RESIGNATION_POLICY
            created.append(_write_text(path.name, content))
        print(f"  created {path.relative_to(PROJECT_ROOT)}")

    return created


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force", action="store_true", help="overwrite existing demo documents"
    )
    args = parser.parse_args()

    print(f"Generating fictional HR demo documents into {OUTPUT_DIR}")
    created = generate(force=args.force)
    print(f"\nDone: {len(created)} document(s) written.")
    print("Reminder: all content is fictional demo material for HR Nexus.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
