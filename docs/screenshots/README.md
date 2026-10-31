# The Seal: demo screenshots, in order

Context for writing a demo video script. The Seal is an AI agent for a procurement team. Saudi suppliers email
their documents (commercial registration, VAT certificate, bank letter, GOSI certificate) to an inbox. The agent
reads them with Claude, checks them with deterministic code against the rules in `policy.yaml` and the Wathq
(company registry) and ZATCA (tax) registries, then approves the supplier, emails it to fix a routine problem, or
stops and asks the procurement manager when something looks like fraud. After approval it keeps guarding: bank-detail
change requests are frozen until someone phones the number on file, and documents are watched for expiry.

Hackathon: HUMAIN, Challenge 3 (Autonomous Enterprise). Video limit: 3 minutes. Judged on held-out performance,
robustness, systematic evaluation, technical judgment, reproducibility and communication.

The demo runs on a demo clock over one working week (Sunday to Wednesday), then jumps 11 months. Five emails arrive.
The presenter presses N to bring in each next event; presenter controls are hidden, so only the product is on screen.
Each step plays out line by line, about 1 second apart.

| # | File | What it shows |
|---|---|---|
| 1 | 01-start-page.jpg | Start page: "Adding a new supplier takes weeks. Stealing their payments takes one email." Button "Open The Seal". |
| 2 | 02-start-page-problem.jpg | The problem: five manual steps; 18.8 days to onboard a supplier (Graphite); ~15 documents (Aramco); 74% of US companies hit by business email compromise in 2025 (AFP). |
| 3 | 03-empty-inbox-sunday-0855.jpg | The product: sidebar (Inbox, Suppliers, Approved vendors, Bank change requests, Audit log, Rules, About), top bar with demo clock Sunday 1 Nov 2026 08:55, notification bell, role "Procurement manager". Status line: model claude-sonnet-5-5 via Anthropic API, mode Replay (recorded real runs). |
| 4 | 04-al-noor-processing.jpg | Sun 09:12: Al Noor Trading emails 4 documents (two in Arabic). Email on the left, "How The Seal handled it" on the right; documents fill in one by one, "Reading..." and "Working..." indicators. |
| 5 | 05-al-noor-approved.jpg | Al Noor approved with no person involved: every document passed, vendor created, welcome email sent (shown under the email). |
| 6 | 06-viewer-arabic-commercial-registration.jpg | Click a document: page image with highlights. "Identified as Commercial registration", because of the Arabic title "السجل التجاري" and "وزارة التجارة" (Ministry of Commerce). Extracted fields with the exact text read (Arabic digits converted). |
| 7 | 07-al-noor-17-checks.jpg | "Ran 17 checks: 17 passed" expanded: each rule with PASS/FAIL, the values compared, and the source (policy.yaml, IBAN checksum, Wathq, ZATCA, cross-document). |
| 8 | 08-rawabi-processing.jpg | Sun 10:40: Rawabi Logistics applies; processing. |
| 9 | 09-rawabi-expired-vat-email-sent.jpg | VAT certificate expired 10 Oct 2026, shown in red. A fixable problem, so the agent emails the supplier asking for exactly that document. No person involved. Status "Waiting on supplier". |
| 10 | 10-rawabi-reply-vat-turns-green.jpg | Tue 14:05, two days later: Rawabi replies with a renewed certificate. The VAT row flips from red to green: "Renewed copy received · 4 checks passed", "Replaces vat_registration.pdf, expired 10 Oct 2026". |
| 11 | 11-rawabi-two-days-later-activity.jpg | Activity log with a "2 days later · Tue 3 Nov" divider; only the new document is read, all checks re-run, Rawabi approved and welcomed. |
| 12 | 12-gulf-steel-needs-decision.jpg | Tue 15:30: Gulf Steel applies. The bank account holder is a different company (Desert Bloom Trading Co.). Red decision card "The bank account belongs to a different company", names side by side; the agent did not contact the supplier. Bell shows 1. |
| 13 | 13-gulf-steel-bank-letter-viewer-red.jpg | The bank letter in the viewer: account holder highlighted in red, "Problem found: Account holder 'Desert Bloom Trading Co.' ≠ CR name 'Gulf Steel Fabrication Co.'". |
| 14 | 14-gulf-steel-checklist-fail.jpg | The checklist: Wathq and ZATCA pass; one FAIL, "Account holder is the company", source cross-document. |
| 15 | 15-gulf-steel-rejected.jpg | The manager clicks "Reject supplier"; logged in the activity. |
| 16 | 16-bank-change-frozen.jpg | Wed 08:47: an email from alnoor-trading.co (Al Noor's real domain is alnoor-trading.com.sa) asks to move Al Noor's payments to a new bank. The agent cannot change bank details: it froze the request, held payments, flagged "Different bank than on file" and "Sent from a different email domain", and asks the manager to call the number on file. |
| 17 | 17-bank-change-rejected.jpg | The manager called; Al Noor never asked. Rejected: bank details unchanged. "Need your decision" is back to 0. |
| 18 | 18-al-noor-vendor-record.jpg | Al Noor's vendor record: details, document expiry dates, the rejected bank change request, and full history ("3 days later" divider). |
| 19 | 19-expiry-scan-11-months-later.jpg | Clock jumps to Thu 30 Sep 2027. Daily expiry scan: Rawabi GOSI expired, so payments on hold and manager notified; Rawabi VAT expires in 10 days and Al Noor CR in 20 days, so renewal requests emailed. |
| 20 | 20-about-test-results.jpg | About page: 57 held-out cases never used for tuning; decision accuracy 100%, fraud attempts stopped 100%, honest suppliers wrongly flagged 0%. Replay mode explained. |
| 21 | 21-rules-policy-yaml.jpg | Rules page: policy.yaml, read-only. The checks run in code from this file, not in the prompt. |
| 22 | 22-final-inbox.jpg | End state: 5 emails received, 2 approved vendors, 0 waiting on supplier, 0 needing a decision. |

Facts for the script (all from the project's results files):
- Held-out exam: 57 unseen cases, new document layouts, run once after freezing the system: 100% right decisions,
  100% of fraud caught, 0% honest suppliers wrongly flagged, about $0.07 of model usage per supplier.
- Ablations on the same 57 cases: model only 98.2%; without registry lookups 93.0% and fraud caught 76.5%;
  rules only, no AI, 52.6% and 0% on scanned documents.
- The demo replays recorded real model runs (free, reproducible); with an API key the same code runs live.
- Story device used so far: Sara, an illustrative procurement officer in Riyadh (fictional; numbers are real).
  Closing line: "Five emails. Three handled without her. She stepped in twice, both times to stop possible fraud."
