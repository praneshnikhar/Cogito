"""Seed the knowledge base with realistic sample documents so the demo works
immediately after `docker compose up`."""

import asyncio
import logging
import os

from app import db
from app.core.ingestion import create_document

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("cogito.seed")

SAMPLE_DOCS = [
    ("contract_penalties.md", "contract",
     """# Vendor Contract 2026 — Penalty Clauses

4.1 Late Delivery
The vendor agrees that any delay in delivering the contracted goods beyond the agreed
date accrues a penalty of 0.5% of the order value per full day of delay, capped at 15%.

4.2 Force Majeure
Neither party is liable for failure to perform if the failure is caused by events beyond
reasonable control, including natural disasters, war, or pandemics.

4.3 Dispute Resolution
Any dispute arising from this agreement shall first be submitted to mediation in
Singapore, then to binding arbitration under the Singapore International Arbitration
Centre rules.

4.4 Confidentiality
The receiving party shall protect confidential information with at least the same care
it uses for its own confidential information.

Vendor obligations include delivery milestones, quarterly reporting, and a data-break
notification SLA of 4 hours.
"""),
    ("onboarding_holiday.md", "text",
     """# Company Holiday Policy 2026

Annual leave accrues at 4 weeks per year for full-time employees, prorated for
part-time staff. Public holidays observed: New Year's Day, Lunar New Year (2 days),
Good Friday, Labour Day, National Day, Deepavali, and Christmas Day.

Employees may carry forward up to 5 days of unused leave into the following year.
Approval is required two weeks in advance for peak seasons (June and December).
Sick leave of up to 14 days is covered by medical certificate.

Remote work is allowed up to 3 days per week. New hires receive prorated leave in
their first year.
"""),
    ("climate_policy.md", "text",
     """# Corporate Climate Policy

Our net-zero commitment targets a 50% reduction in scope 1 and scope 2 emissions by
2030 relative to 2020 levels, and net zero across all scopes by 2050.

Energy: 100% renewable electricity across office and data-center footprint by 2027.
Travel: a 30% reduction in business air travel by 2026 via virtual-first meetings.
Supply chain: top 100 vendors must disclose emissions and set science-based targets.

Offsetting is used only for residual emissions and must be high-integrity, removal
based, and third-party verified.
"""),
    ("privacy_notice.md", "text",
     """# Data Privacy Notice

We collect only the personal data needed to provide our services: name, contact
details, and usage activity. We process personal data for legitimate business
purposes and never sell user data to third parties.

Data retention: account data is retained for the duration of the account plus 30 days.
You may request access, correction, or deletion of your personal data at any time by
contacting privacy@example.com. Complaints may be raised with the local data
protection authority.
"""),
]


async def seed() -> None:
    await db.ensure_indexes()
    count = await db.col(db.DOCUMENTS).count_documents({})
    if count > 0:
        print(f"knowledge base already has {count} documents; skipping seed.")
        return
    ids = []
    for filename, doc_type, text in SAMPLE_DOCS:
        doc_id = await create_document(
            filename, text.encode("utf-8"), doc_type, "seed"
        )
        ids.append(doc_id)
    print(f"queued {len(ids)} sample documents. The ingest-worker will index them.",
          os.getenv("COGITO_SEED_WAIT", "worker-required"))
    # give the change-stream worker a beat to index before returning
    for _ in range(20):
        pending = await db.col(db.DOCUMENTS).count_documents({"status": "pending"})
        if pending == 0:
            break
        await asyncio.sleep(0.5)
    print("indexed document count:", await db.col(db.DOCUMENTS).count_documents({"status": "indexed"}))


if __name__ == "__main__":
    asyncio.run(seed())