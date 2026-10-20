# Deliverable: Draft the freemium revenue hypothesis, clearly labeled unapproved

**Department:** finance

# InvoiceLite — Freemium Revenue Hypothesis

## DRAFT — UNAPPROVED HYPOTHESIS, NOT A DECISION

**No pricing is to be published, charged, advertised, or represented to any user without explicit founder approval. No Paystack merchant account is authorized, no subscription product is configured, and no charge of any amount has been initiated or scheduled. This document is a model.**

| Field | Value |
|---|---|
| Status | DRAFT — unapproved hypothesis |
| Supersedes | Nothing |
| Consistent with | T4 Year-1 fixed infrastructure cash floor (₦15,000 committed + ₦5,000 held = ₦20,000) |
| Authorized spend implied | **₦0** |
| Product PRD conflict | **None recorded** — Product's PRD specifies no tiers and no price points |

---

## 1. The hypothesis

| Tier | Price | Included |
|---|---|---|
| Free | ₦0 | 5 invoices per calendar month |
| Unlimited | **₦2,500 / month** | Unlimited invoices |

- Billing cadence: monthly, naira-denominated, card or transfer via Paystack. Annual prepay is *not* part of this hypothesis (see §8).
- Payment-gateway fees are **absorbed by InvoiceLite**, not surcharged to the customer. Paystack's **1.5% + ₦100, capped at ₦2,000** is therefore a **variable cost that sits on top of the subscription price in the cost stack** — it reduces take-home on every charge and scales with subscriber count, unlike the fixed cost floor in T4.
- The ₦2,500 figure is inherited from T4's fee-table check and is presented here unchanged. It is not validated by market testing — see §9.

---

## 2. Target segment, and why the gate is calibrated to it

**Nigerian solo freelancers and 1–5 person micro-businesses issuing 5–20 invoices monthly.**

The free cap of 5/month is well-matched to that band. The band spans 16 discrete monthly volumes (5 through 20); only a user issuing *exactly* 5 invoices can live permanently inside the free tier.

- **≤6% of the target band is fully served by the free tier.** The other ~94% must either pay or manually re-issue the same invoice number.
- The gate is not too loose. It is arguably too *tight at the low end*: a freelancer issuing 6 invoices/month pays ₦2,500 for one extra invoice — an effective **₦417 per marginal invoice**. At 20 invoices/month the same ₦2,500 is **₦125 per invoice**. The single flat tier prices light users harshly and heavy users generously.
- **But the gate's calibration is irrelevant if it cannot be enforced.** On the architecture Engineering shipped (client-side, localStorage, no auth, no server persistence), a user clears storage — or simply never clears it — and stays free forever. Until metering exists server-side, the real funnel is not "5 free then pay," it is **"unlimited free, pay if you feel like it."** This is the single biggest number in this document and it is discussed in §5.

---

## 3. Unit economics at ₦2,500/month

Paystack fee at ₦2,500: 1.5% = ₦37.50, plus ₦100 flat = **₦137.50** (the ₦2,000 cap binds only at ₦126,667 gross — irrelevant here).

| Item | Amount |
|---|---|
| Gross subscription | ₦2,500.00 |
| Paystack fee (variable) | (₦137.50) |
| **Net take-home per paid user-month** | **₦2,362.50** |
| Take-home rate | **94.5%** |
| Other COGS | ₦0.00 (static hosting on free tier; marginal cost to serve one paying user ≈ ₦0) |
| **Contribution margin per paid user-month** | **₦2,362.50** |

**The ₦100 flat fee — not the 1.5% — is the binding constraint.** It is 4.0% of gross at ₦2,500, 6.7% at ₦1,500, and 10.0% at ₦1,000.

### Why ₦2,500 and not a cheaper visible tier

Holding blended CAC at T4's **₦2,500** and retention at 6 months:

| Tier price | Paystack fee | Net take-home | Take-home % | CAC payback | LTV (6 mo) | LTV:CAC |
|---|---|---|---|---|---|---|
| ₦500 | ₦107.50 | ₦392.50 | 78.5% | 6.4 mo | ₦2,355 | **0.9:1** |
| ₦1,000 | ₦115.00 | ₦885.00 | 88.5% | 2.8 mo | ₦5,310 | **2.1:1** |
| ₦1,500 | ₦122.50 | ₦1,377.50 | 91.8% | 1.8 mo | ₦8,265 | **3.3:1** |
| **₦2,500** | **₦137.50** | **₦2,362.50** | **94.5%** | **1.06 mo** | **₦14,175** | **5.7:1** |
| ₦5,000 | ₦175.00 | ₦4,825.00 | 96.5% | 0.52 mo | ₦28,950 | 11.6:1 |

A ₦1,000 tier does not fail on fees — it fails on **acquisition economics**: at a 6-month average life it returns 2.1:1, and if retention slips to 3 months it returns 1.05:1, i.e. it does not pay for its own acquisition. **Any future tier below ₦1,500 must be justified against this table, not against competitor pricing.**

---

## 4. Reconciliation with the T4 fixed-cost floor

| Metric | Value | Derivation |
|---|---|---|
| Year-1 fixed cash floor (gross) | ₦20,000 | ₦15,000 committed domain + ₦5,000 held contingency |
| Committed portion only | ₦15,000 | Unapproved; pending founder sign-off |
| Paid user-months to recover gross floor | **8.5** | ₦20,000 ÷ ₦2,362.50 |
| Paid user-months to recover committed portion | **6.4** | ₦15,000 ÷ ₦2,362.50 |
| Monthly amortized infra (Yr-1 domain only) | ₦1,250 | ₦15,000 ÷ 12 |
| Monthly amortized infra (Yr-2 renewal, ₦18k–₦25k) | ₦1,500–₦2,083 | T4 renewal estimate |
| **Paying subscribers to cover monthly infra** | **1** | ₦2,362.50 > ₦2,083 |

**Operating break-even is one subscriber.** That is not a validation of the model — it means the business has no cost problem at all, and therefore no cost lever. Every constraint is on the revenue side: distribution, conversion, and retention. Scenarios that "break even" here should not be read as traction.

---

## 5. Free-to-paid conversion — two scenarios, and a model-integrity flag

Conversion assumptions for self-serve SMB tools typically run 2–5%. **That benchmark assumes an enforced gate.** With no enforcement, voluntary-payment conversion realistically sits at **0.3–1.0%**. I am modeling both.

| Scenario | Gate | Assumed conversion | Paying subs per 1,000 free MAU | Net MRR per 1,000 MAU |
|---|---|---|---|---|
| A — gate enforced (needs auth + server metering) | Enforced | 3.0% | 30 | ₦70,875 |
| B — gate unenforced (shipped architecture) | Not enforceable | 0.5% | 5 | ₦11,812.50 |

**The same product, at the same price, produces a 6x swing in revenue purely from whether metering exists.** Scenario B is what the current build supports.

### Model-integrity flag: ₦2,500 CAC is undefined and the definition decides whether this business works

T4 states a blended CAC of ₦2,500 and a payback of 1.06 months, which only holds if ₦2,500 is **per paying customer**. If ₦2,500 is per *free signup* — which is how self-serve acquisition costs are normally quoted — the numbers