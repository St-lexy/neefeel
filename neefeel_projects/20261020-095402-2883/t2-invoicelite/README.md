# InvoiceLite

A client-side invoice builder for Nigerian freelancers. Three static files, no build
step, no backend, no database, no third-party JavaScript.

**Data handling:** every field you type is stored in this browser's `localStorage`
under the key `invoicelite.state.v1` (plus `invoicelite.seq.v1` for invoice
numbering). Nothing is ever transmitted to a server, so no personal data is
processed server-side and NDPA 2023 server-side obligations are not triggered.

---

## Files

| File          | Purpose                                                  |
| ------------- | -------------------------------------------------------- |
| `index.html`  | Input form + live invoice preview + print markup          |
| `styles.css`  | Mobile-first layout, print stylesheet (`@media print`)    |
| `app.js`      | State, subtotal/tax math, `localStorage` persistence      |

---

## Run it locally

1. Save all three files in one folder.
2. Double-click `index.html` (works over `file://`), or serve it:

```bash
python3 -m http.server 8080
# open http://localhost:8080
```

No install, no npm, no build.

---

## Features

- Add and remove line items (always keeps at least one row).
- Live running subtotal in NGN with thousands separators (`₦1,250,000.00`).
- Optional VAT/tax rate and "amount paid" → balance due.
- Invoice number auto-increments and persists (`INV-001`, `INV-002`, …);
  falls back to `INV-001` when no sequence exists.
- Full state (business, client, items, dates, notes) survives a refresh.
- Print / Save-as-PDF via the browser's own print dialog.
- "Reset" wipes all local data and restarts numbering at `INV-001`.

---

## Deployment (free static host, TLS included)

Documentation only — nothing here has been deployed and no domain has been bought.

### Netlify (drag-and-drop, no account needed to preview)

1. Go to <https://app.netlify.com/drop>.
2. Drag the folder containing `index.html`, `styles.css`, `app.js`.
3. Netlify returns a URL like `https://your-name-123.netlify.app` with TLS already on.
4. Optional: claim the site to a free account, then *Site settings → Change site name*.

### Netlify (git-connected)

1. Push the three files to a GitHub/GitLab repo.
2. <https://app.netlify.com> → *Add new site → Import an existing project*.
3. Build command: **leave empty**. Publish directory: **`.`** (repo root).
4. Deploy. TLS is provisioned automatically.

### Vercel

1. Push the three files to a GitHub/GitLab/Bitbucket repo.
2. <https://vercel.com/new> → import the repo.
3. Framework preset: **Other**. Build command: **empty**. Output directory: **`.`**.
4. Deploy. TLS is included on `*.vercel.app`.

### Vercel CLI alternative

```bash
npm i -g vercel
vercel --prod     # from the folder containing index.html
```

Both hosts serve over HTTPS by default, so the invoice data stays in the visitor's
browser and is never sent to the host as request data.

---

## Explicit non-goals for this batch

- **PDF export** as a server-side/generated file — use the browser's
  "Print → Save as PDF" instead.
- **Authentication / accounts** — there are no users to authenticate.
- **Multi-user collaboration or sharing** — no server, so no shared records.
- **Any server-side storage, backup or sync of personal data.**

---

## Clearing your data

The **Reset** button removes both `localStorage` keys. You can also clear site
data from your browser's settings; there is no other copy anywhere.