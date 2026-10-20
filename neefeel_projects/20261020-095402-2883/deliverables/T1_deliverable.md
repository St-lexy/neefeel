# Deliverable: Define the two-field invoice data model, calculation rule, and core user story

**Department:** product

# Product Definition — InvoiceLite Batch One (PoC v0.1)

**Status:** ready for build. No founder gate on this artifact.
**Owner:** Product. **Consumed by:** Engineering (batch one), Finance/GTM (context only).
**Scope:** one screen, one calculation, one stored counter. Anything not written below is out.

---

## 1. Scope Statement

InvoiceLite v0.1 is a client-side invoice calculator for Nigerian freelancers. It collects a client label and a set of line items, computes a subtotal, and renders a copy-pasteable invoice in NGN. It stores nothing on a server, authenticates no one, and produces no file artifact.

**Success criterion for this batch:** a user can go from empty screen to a WhatsApp-pasteable, correctly totaled invoice in under 60 seconds, on a phone browser, with no signup.

---

## 2. Data Model — Exactly Two Essential Fields

These two fields carry the product's only logic. Everything else on the screen is a label.

### Field 1 — `invoiceNumber`
| Attribute | Value |
|---|---|
| Type | `string` |
| Format | `INV-` + zero-padded 3-digit integer (`INV-001`, `INV-002`, …) |
| Source of truth | `localStorage` key `invoicelite.lastInvoiceNumber` |
| Fallback | `"INV-001"` when the key is absent, empty, or unparseable |
| Overflow | Past `INV-999`, widen to 4 digits (`INV-1000`) — do not truncate |
| Editable | Yes. User may overwrite the displayed value; the overwritten value becomes that invoice's number and does **not** affect the counter |

**Commit rule (decision):** the counter is *read* on page load to display the next number, but *persisted* only when the user takes a finalizing action on that invoice (Copy / Print). A page refresh without a finalizing action reuses the same number. This prevents burning numbers on reloads and prevents duplicate numbers on re-renders of the same draft.

### Field 2 — `lineItems`
| Attribute | Value |
|---|---|
| Type | `Array<{ description: string, quantity: number, unitPrice: number }>` |
| `description` | Free text, required, trimmed, max 120 chars |
| `quantity` | Integer ≥ 1. No decimals in v1 |
| `unitPrice` | Integer ≥ 0, **whole naira only**. No decimals, no kobo in v1 |
| Cardinality | Minimum 1 line item to produce a valid invoice; soft cap 50 (no enforced limit, just no pagination) |

### Non-essential label field (not counted toward the two)
`clientName` — single free-text string, optional, rendered on the invoice. It is a **label, not a record**: there is no client object, no contact fields, no client list, no lookup. The core user story requires it; structure around it does not exist.

### Persisted state shape
```
invoicelite.lastInvoiceNumber : string   // "INV-007"
invoicelite.draft             : JSON     // { invoiceNumber, clientName, lineItems[] }
```
Draft persists on input so a refresh doesn't destroy work. Two keys, no schema versioning in v1 (v2 will need it — see Risks).

---

## 3. Calculation Rule — Singular

```
subtotal = Σ ( quantity_i × unitPrice_i )   for all lineItems i
```

- Exactly one computed value is displayed: **Subtotal**. There is no tax line, no discount line, no grand total distinct from subtotal, no per-line total requirement (per-line totals are optional display; they must not introduce a second formula).
- Rendering: NGN with thousands separators and the `₦` prefix — `₦1,250,000`. Grouping is comma, 3-digit. No decimal places rendered in v1.
- Recomputation is synchronous on every input change. No debounce needed, no async, no rounding step (inputs are integers, so the result is an integer).
- Empty or invalid line items contribute `0` and never throw. An invoice with zero valid line items renders `₦0` **and** disables the Copy action.

---

## 4. Core User Story (verbatim)

> As a Nigerian freelancer, I can enter a client name and a few line items and see my total owed, so I can send a WhatsApp-ready invoice in under 60 seconds.

**Supporting acceptance criteria (build-and-verify, this batch):**
1. Given a fresh browser with empty `localStorage`, the invoice number field displays `INV-001`.
2. Given a prior committed number of `INV-004`, a new session displays `INV-005`.
3. Given line items `[Design, qty 2, ₦75,000]` and `[Revisions, qty 1, ₦25,000]`, the screen displays `₦175,000`.
4. Given `qty = 3, unitPrice = ₦0`, the line renders and contributes `₦0`; the invoice is still copyable if another line item is non-zero.
5. Given a completed invoice, tapping Copy yields plain text containing client name, invoice number, each line item, and the formatted subtotal — pasteable into WhatsApp with no broken characters (`₦` must survive clipboard).
6. Given a page refresh mid-entry, the form repopulates from `localStorage`.
7. Given a cleared `localStorage`, the app renders without error and resets to `INV-001`.
8. First meaningful paint to copyable invoice: **under 60 seconds for a first-time user on a mid-range Android phone**.

---

## 5. Deferred to v2 — Explicit, Not Forgotten

Each of these is a deliberate cut, not an oversight:

- Client contact details beyond a name (email, phone, address, TIN)
- Due date / payment terms
- Tax / VAT (and therefore any tax-inclusive calculation)
- Discounts (percentage or flat)
- Multi-currency (NGN only in v1)
- Templates / saved invoice layouts
- Logo and branding (colours, fonts, watermark)
- PDF export
- Auth, accounts, multi-user, server-side persistence
- Payment links / Paystack integration

**Additional v1 constraints (not features, but boundaries):** whole-naira amounts only (no kobo, no fractional quantities); single-device numbering; no invoice history or list view — v1 holds exactly one invoice draft at a time.

---

## 6. Open Assumption — Awaiting Founder Confirmation

**Auto-increment numbering is an assumption, not a decision.** It is implemented as specified above because it is the cheapest thing that satisfies the user story today. What is *not* confirmed:

- Whether invoice numbers should be globally unique, or are acceptable as device-local.
- Whether the `INV-###` prefix and format match how the founder (or target users) actually number invoices.
- Whether numbering should be user-configurable (prefix, starting number, reset).
- Whether the counter should be committed at finalize (as specified) or at invoice creation.

A change to any of these is confined to one function in `app.js` plus one key in `localStorage`. Say so now if the answer differs; after Engineering ships, it becomes a migration.

---

## 7. Definition of Done — Batch One

- Two files of logic behave as specified above, deployed to a free-tier host over TLS.
- All eight acceptance criteria manually verified, including a cleared-storage run and a clipboard round-trip on a real phone.
- Calculation verified against three hand-computed totals.
- Deferred list confirmed absent from the build (no half-built VAT field, no disabled "PDF" button).

Risks:
- Device-local auto-increment means two devices, a cleared browser, or a private window can both produce `INV-001` and send duplicate-numbered invoices to the same client — a credibility problem for the user and a support problem for us. Founder confirmation needed; unresolved by design.
- Commit-on-finalize adds genuine state logic (a "committed" flag, a finalize handler, a reload path) to `app.js`. It is not hard, but it is more than a naive static form and it is where the duplicate/burn-number bugs will live. Engineering should price it before accepting.
- Whole-naira-only with integer quantities cannot represent hourly billing (e.g. ₦12,500 × 1.5 hrs) or kobo-precise pricing — a real freelancer pattern, not an edge case. This will surface as a v2 schema change, not a config toggle.
- `localStorage` draft shape is unversioned in v1. The first v2 field addition silently breaks resuming drafts saved under v1. Cheap to fix now, annoying later.
- Client name is in the user story but intentionally not modeled. If the founder wants structured client data, that is a data-model change, not a field addition.
- Commodity risk stands unresolved: a client-side invoice calculator has a hundred free competitors. This artifact proves capability, not defensibility. It does not block batch one; it blocks any go-to-market motion.