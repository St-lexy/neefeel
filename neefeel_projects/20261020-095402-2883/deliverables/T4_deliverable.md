# Deliverable: Model the Year-1 domain and hosting cash floor (no spend authorized)

**Department:** finance

## InvoiceLite — Year-1 Fixed Infrastructure Cash Floor

**No spend authorized. No domain purchase initiated. No registrar, Paystack, or hosting account action taken in this deliverable.** This is a model, not a commitment.

### Line-item model

| # | Line item | Year-1 amount | Cost type | Status | Basis / assumption |
|---|---|---|---|---|---|
| 1 | Domain registration — `.com.ng` or standard `.com`, non-premium | **₦15,000** | Fixed, one-time | **PENDING APPROVAL — blocked, no purchase initiated** | ≈1 year at a NiRA-accredited registrar (`.com.ng` realistically ₦12,000–₦18,000 depending on registrar) or a standard `.com` at ~$10–11. Assumes naira-quoted, VAT-inclusive. **Renewal not covered.** |
| 2 | Static hosting — Netlify/Vercel free tier | **₦0** | Fixed | Authorized-inert — zero cost, no commitment | 100GB bandwidth/month. A client-side invoice generator serving HTML/CSS/JS will not approach this in Year 1. |
| 3 | TLS certificate | **₦0** | Fixed | Included with host | Auto-provisioned by the platform. No action. |
| 4 | Business email | **₦0** | Fixed | **DEFERRED — not covered by this floor** | PoC runs on a personal address or the registrar's free forwarding. Zoho free tier is the v2 path. |
| 5 | Paystack processing | **1.5% + ₦100, capped ₦2,000** | **Variable, transaction-time** | Not a fixed cost. No merchant onboarding authorized. | Charged only when money actually moves. At ₦2,500 that is ₦137.50 per transaction (94.5% take-home). Cap binds at ₦126,667 — irrelevant at this price point. |
| 6 | Contingency buffer | **₦5,000** | Held, unspent | **HELD — UNAPPROVED** | Covers FX movement on a USD `.com`, VAT if registrar prices are exclusive (+7.5% = ₦1,125), or a renewal surprise. Released only on your explicit approval. |

### Gross Year-1 cash floor

> **₦15,000 committed + ₦5,000 held = ₦20,000 gross fixed cash floor.**

Only **₦15,000** of that is a spend request. The ₦5,000 is a reserve, not an outlay.

**This floor does not cover email or payment-processing fees.** Email is deferred at ₦0. Paystack is variable and only exists once there is revenue to process — it is a margin tax, not overhead.

### Sensitivity: is ₦15,000 a hard ceiling or a first tranche?

**One-line answer: it is a first tranche, not a ceiling — it buys exactly one year of one domain and nothing else.**

- **Year-2 exposure:** most registrars discount year 1 and renew higher. Budget ₦18,000–₦25,000 for a `.com` renewal, ₦12,000–₦18,000 for `.com.ng`. Three-year price certainty (multi-year registration) would require ~₦45,000 — that exceeds your approval envelope and is a separate decision, not a line in this one.
- **Currency:** a `.com` is USD-denominated. At ~₦1,500/$, $10–11 consumes the entire ₦15,000 with **zero FX buffer** — a 15% naira slide turns this line into a shortfall. `.com.ng` is naira-quoted and removes that risk. If the `.com` brand matters more than currency certainty, the ₦5,000 contingency stops being optional.
- **The real ceiling is the commercial one.** The moment you add auth and server-side persistence to enforce a paid tier, hosting leaves ₦0 and NDPA 2023 obligations attach (Legal already flagged this). Estimated commercial floor: **₦35,000–₦50,000 Year-1** (₦20,000 PoC floor + ₦0–₦30,000 paid-tier infra + compliance scoping from Legal, currently unquantified). ₦15,000 is nowhere near that.

### Unit-economics check on the unapproved ₦2,500/month hypothesis

Labeled a hypothesis, not a decision — but it must survive the fee table before it becomes one.

| Price point | Paystack fee | Net take-home | Take-home % |
|---|---|---|---|
| ₦500/mo | ₦107.50 | ₦392.50 | 78.5% |
| ₦1,500/mo | ₦122.50 | ₦1,377.50 | 91.8% |
| **₦2,500/mo** | **₦137.50** | **₦2,362.50** | **94.5%** |
| ₦5,000/mo | ₦175.00 | ₦4,825.00 | 96.5% |

**The ₦100 flat fee is the constraint, not the 1.5%.** Any tier below ₦1,500/month is structurally weak; sub-₦1,000 tiers are not viable. ₦2,500 clears the bar cleanly. Do not promote a ₦999 tier later without re-running this.

- **Blended CAC estimate: ₦2,500.** Assumes 60% organic/referral (~₦500 effective cost per user in content and community time) and 40% paid social targeting Nigerian freelancers (~₦5,000 CAC) → 0.6(500) + 0.4(5,000) = ₦2,300, rounded up for conservatism.
- **Contribution margin per paid user-month: ₦2,362.50** — no COGS beyond the gateway. Gross margin 94.5%.
- **CAC payback: 1.06 months (~32 days).** Healthy.
- **LTV:** 6-month median retention → ₦14,175. **LTV:CAC = 5.7:1.** At 3-month retention → ₦7,087.50, **2.8:1**. Break-even retention is ~1.1 months; anything under 2 months average life fails a 2:1 threshold. **Retention is the whole model.**
- **Floor coverage:** ₦20,000 gross floor ÷ ₦2,362.50 = **8.5 paid user-months**. Three paying subscribers retained three months, or two retained ~4.25 months, recovers the entire Year-1 fixed floor. Against the ₦15,000 committed only, it is 6.4 user-months.

### Enforcement gap — flagging before it becomes a spec

The freemium gate (5 invoices/month free, unlimited paid) **cannot be enforced on the architecture Product and Engineering specified.** That build is client-side with localStorage, no auth, no server persistence — a user clears storage, or simply never clears it, and stays free forever. Conversion rests entirely on goodwill.

Product's PRD is silent on pricing, so I am not recording a pricing contradiction today. But this hypothesis cannot be promoted to spec without auth and server-side metering, which is exactly the scope Engineering deliberately excluded — and which moves the floor to the ₦35,000–₦50,000 envelope above.

### What I need from you

1. Approve or cut the ₦15,000 domain spend — and say whether `.com.ng` (naira-certain) or `.com` (FX-exposed) is the call, because it changes whether the ₦5,000 contingency is released.
2. Approve or redline the ₦5,000 contingency as held reserve.
3. Confirm the ₦2,500/month hypothesis stays a hypothesis until auth and metering are scoped.

Risks:
- ₦15,000 domain registration remains unpurchased and unapproved; executing it requires your explicit sign-off and a registrar transaction, neither of which this model authorizes.
- A `.com` is USD-denominated at ~$10–11; at ₦1,500/$ that consumes the full ₦15,000 with zero FX buffer, and a 15% naira slide creates a shortfall that only the ₦5,000 contingency absorbs.
- Year-1 pricing is not renewal pricing — expect ₦18,000–₦25,000 on `.com` renewal, so the Year-1 floor understates steady-state cost by ₦3,000–₦10,000 annually.
- If registrar quotes are VAT-exclusive, add 7.5% (₦1,125) and the floor becomes ₦21,125; the ₦5,000 contingency covers this but then covers nothing else.
- Paystack's ₦100 flat fee makes every sub-₦1,500/month tier structurally weak (₦500 nets 78.5%); the ₦2,500 hypothesis is sound at 94.5%, but a cheaper tier later breaks the model.
- The freemium tier gate is unenforceable on the shipped client-side architecture — a paywall cannot exist without auth and server metering, both explicitly out of scope, so every conversion assumption here is unvalidated.
- Retention, not CAC, is the single point of failure: at 3-month average life LTV:CAC falls to 2.8:1, and below ~2 months the business does not cover acquisition.
- The ₦20,000 floor is a proof-of-concept floor, not a commercial one; monetization adds an estimated ₦15,000–₦30,000 of infra plus unquantified NDPA 2023 compliance cost, and Legal should scope that before any launch decision.