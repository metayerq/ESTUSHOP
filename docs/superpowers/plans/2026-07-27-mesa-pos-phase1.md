# Mesa POS Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Mesa Phase 1 sale engine on top of Vendus: typed Vendus client, fiscal go/no-go spike, catalog + checkout API routes, and a tablet sale UI (grid, cart, payment, confirmation) behind a PIN.

**Architecture:** New Next.js 15 (App Router) repo `mesa`. A framework-agnostic `lib/vendus/` module (HTTP client + Zod-validated endpoint functions) is used by both a CLI spike script and thin API routes; the UI is a single client-side state machine over pure cart functions. No database: Vendus is the source of truth, with a 60 s in-memory catalog cache.

**Tech Stack:** Next.js 15, TypeScript, Tailwind (create-next-app defaults), zod@^3, qrcode.react, vitest + @testing-library/react + jsdom, tsx + dotenv (spike script).

**Spec:** `docs/superpowers/specs/2026-07-27-mesa-pos-phase1-design.md` (ESTUSHOP repo).

## Global Constraints

- **Repo:** all tasks run in `/Users/quentinmetayer/github/mesa` (created in Task 1). This directory is outside the current session's working dirs — the executor must be granted access to it.
- **Vendus account:** the **dedicated test account only**. `VENDUS_API_KEY` must never point at the production Estudantina account during Phase 1.
- **`lib/vendus/**` must not import from `next/*` or `react`** — it is used by the CLI spike and must stay framework-agnostic.
- **Never auto-retry a POST to Vendus** — one exception: a single retry on HTTP 429 (a 429 is rejected before processing, so no document was created). A POST that fails at the network level (timeout, connection lost) becomes a `possibly_created` error — never replayed.
- **Env vars** (all read server-side): `VENDUS_API_KEY`, `VENDUS_REGISTER_ID` (optional), `VENDUS_PM_CASH_ID`, `VENDUS_PM_CARD_ID`, `VENDUS_PM_MBWAY_ID`, `MESA_PIN`, `MESA_COOKIE_SECRET`.
- **UI copy in English.** Prices display as `X.XX €` (`toFixed(2)`).
- **Payment codes:** `"NU"` (cash), `"CC"` (card), `"MBWAY"` — these are the wire values between UI and our API.
- **Commits:** conventional style in English (`feat:`, `test:`, `chore:`).
- **Task 5 is a hard gate:** the spike must print GO before Tasks 6-12 are started.
- Zod schemas for Vendus responses are **lenient** (`.passthrough()`, `z.coerce.number()` for numeric strings) but fail loudly (throw `VendusError`) on missing required fields.

## File Structure

| File | Responsibility |
|---|---|
| `lib/vendus/types.ts` | `VendusError` class + error kinds |
| `lib/vendus/client.ts` | `createVendusClient` — HTTP, auth, timeout, retry policy, error normalization |
| `lib/vendus/products.ts` | product/category schemas, pagination helper, `listProducts`, `listCategories`, `createProduct`, `productPrice`, `parseList` |
| `lib/vendus/taxes.ts` | tax schema + `listTaxes` |
| `lib/vendus/documents.ts` | FS/NC payload builders, `createFs`, `createNc`, `getDocument`, `listRecentDocuments`, document schema helpers |
| `scripts/spike.ts` | fiscal go/no-go CLI (`--discover` mode + full run), records fixtures |
| `lib/ttlCache.ts` | generic in-memory TTL cache (`ttlGet`, `ttlClear`) |
| `lib/server/vendus.ts` | `getVendusClient()` singleton from `VENDUS_API_KEY` |
| `lib/server/catalog.ts` | `Catalog` types, `loadCatalog`, cached `getCatalog` |
| `lib/server/checkout.ts` | checkout input schema, `paymentMethodId`, `runCheckout` |
| `lib/server/httpError.ts` | `vendusErrorResponse` — VendusError → HTTP JSON response |
| `app/api/catalog/route.ts` | GET catalog (supports `?fresh=1`) |
| `app/api/checkout/route.ts` | POST checkout |
| `app/api/checkout/recent/route.ts` | GET documents of the last 5 minutes |
| `app/api/login/route.ts` | POST PIN → session cookie |
| `lib/auth.ts` | HMAC session cookie (Web Crypto — edge-compatible) |
| `middleware.ts` | PIN gate on everything except `/login`, `/api/login` |
| `lib/cart.ts` | pure cart functions (`addItem`, `changeQty`, `cartTotal`, `computeChange`, `round2`) |
| `lib/useCatalog.ts` | client hook fetching `/api/catalog` with background refresh |
| `components/ProductGrid.tsx` | category tabs + product tiles |
| `components/CartPanel.tsx` | cart lines, total, Charge button |
| `components/PaymentPanel.tsx` | Cash (with amount received) / Card / MB WAY |
| `components/ConfirmationScreen.tsx` | total, number, ATCUD, QR, New sale |
| `components/CheckRecentScreen.tsx` | possibly_created resolution screen |
| `app/page.tsx` | POS page — state machine wiring everything |
| `app/login/page.tsx` | PIN pad |
| `test/fixtures/*.json` | real Vendus responses recorded by the spike |

---

### Task 1: Scaffold the `mesa` repo and tooling

**Files:**
- Create: repo `/Users/quentinmetayer/github/mesa` (via create-next-app)
- Create: `vitest.config.ts`, `.env.local.example`
- Modify: `package.json` (test script)

**Interfaces:**
- Consumes: nothing.
- Produces: a building Next.js app with `npm test` (vitest, `passWithNoTests`), path alias `@/*` → repo root, deps installed: `zod@^3`, `qrcode.react`; dev deps: `vitest`, `@vitejs/plugin-react`, `@testing-library/react`, `jsdom`, `tsx`, `dotenv`.

- [ ] **Step 1: Check Node version**

Run: `node -v` — expect ≥ v20. Stop and report if older.

- [ ] **Step 2: Scaffold**

```bash
cd /Users/quentinmetayer/github
npx create-next-app@latest mesa --typescript --tailwind --eslint --app --no-src-dir --import-alias "@/*" --use-npm --turbopack
cd mesa
```

create-next-app initializes git with an initial commit.

- [ ] **Step 3: Install dependencies**

```bash
npm install zod@^3 qrcode.react
npm install -D vitest @vitejs/plugin-react @testing-library/react jsdom tsx dotenv
```

- [ ] **Step 4: Create `vitest.config.ts`**

```ts
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  test: { environment: "node", passWithNoTests: true },
  resolve: { alias: { "@": path.resolve(__dirname, ".") } },
});
```

Add to `package.json` scripts: `"test": "vitest run"`.

- [ ] **Step 5: Create `.env.local.example`**

```bash
# Vendus TEST account only — never the Estudantina production key
VENDUS_API_KEY=
# Filled after `npx tsx scripts/spike.ts --discover` (Task 5)
VENDUS_REGISTER_ID=
VENDUS_PM_CASH_ID=
VENDUS_PM_CARD_ID=
VENDUS_PM_MBWAY_ID=
# POS auth
MESA_PIN=
MESA_COOKIE_SECRET=
```

- [ ] **Step 6: Verify**

Run: `npm test` — expect: passes with "no test files found" (passWithNoTests).

- [ ] **Step 7: Commit**

```bash
git add -A && git commit -m "chore: tooling — vitest, zod, qrcode.react, env example"
```

---

### Task 2: Vendus error type + HTTP client

**Files:**
- Create: `lib/vendus/types.ts`, `lib/vendus/client.ts`
- Test: `lib/vendus/client.test.ts`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `class VendusError extends Error { kind: VendusErrorKind; status: number | null; messages: string[] }` with `VendusErrorKind = "auth" | "validation" | "rate_limit" | "network" | "possibly_created" | "unknown"`; constructor `(kind, status, messages)`.
  - `createVendusClient(opts: { apiKey: string; fetchImpl?: typeof fetch; timeoutMs?: number; retryDelayMs?: number }): VendusClient`
  - `interface VendusClient { get(path: string, params?: Record<string, string | number>): Promise<unknown>; post(path: string, body: unknown): Promise<unknown> }`

- [ ] **Step 1: Write the failing tests** — `lib/vendus/client.test.ts`

```ts
import { expect, it, vi } from "vitest";
import { createVendusClient } from "./client";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

const clientWith = (fetchImpl: typeof fetch) =>
  createVendusClient({ apiKey: "k", fetchImpl, retryDelayMs: 0, timeoutMs: 200 });

it("GET returns parsed JSON and sends basic auth + params", async () => {
  const fetchImpl = vi.fn(async (url: unknown, init: RequestInit | undefined) => {
    expect((init!.headers as Record<string, string>).Authorization).toMatch(/^Basic /);
    expect(String(url)).toContain("/products/?page=1");
    return json([{ id: 1 }]);
  });
  const c = clientWith(fetchImpl as unknown as typeof fetch);
  expect(await c.get("/products/", { page: 1 })).toEqual([{ id: 1 }]);
});

it("GET retries on 500 then succeeds", async () => {
  const fetchImpl = vi.fn()
    .mockResolvedValueOnce(json({ oops: 1 }, 500))
    .mockResolvedValueOnce(json({ ok: 1 }));
  const c = clientWith(fetchImpl as unknown as typeof fetch);
  expect(await c.get("/taxes/")).toEqual({ ok: 1 });
  expect(fetchImpl).toHaveBeenCalledTimes(2);
});

it("maps 401 to an auth error", async () => {
  const c = clientWith(vi.fn(async () => json({}, 401)) as unknown as typeof fetch);
  await expect(c.get("/taxes/")).rejects.toMatchObject({ kind: "auth", status: 401 });
});

it("maps 400 with a Vendus error body to validation with messages", async () => {
  const body = { errors: [{ code: "A001", message: "Bad tax" }] };
  const c = clientWith(vi.fn(async () => json(body, 400)) as unknown as typeof fetch);
  await expect(c.post("/documents/", {})).rejects.toMatchObject({
    kind: "validation",
    messages: ["A001: Bad tax"],
  });
});

it("POST network failure becomes possibly_created and is never retried", async () => {
  const fetchImpl = vi.fn().mockRejectedValue(new TypeError("fetch failed"));
  const c = clientWith(fetchImpl as unknown as typeof fetch);
  await expect(c.post("/documents/", {})).rejects.toMatchObject({ kind: "possibly_created" });
  expect(fetchImpl).toHaveBeenCalledTimes(1);
});

it("GET network failure exhausts retries then throws network", async () => {
  const fetchImpl = vi.fn().mockRejectedValue(new TypeError("fetch failed"));
  const c = clientWith(fetchImpl as unknown as typeof fetch);
  await expect(c.get("/taxes/")).rejects.toMatchObject({ kind: "network" });
  expect(fetchImpl).toHaveBeenCalledTimes(3);
});

it("429 is retried once after Retry-After then surfaces rate_limit (even on POST)", async () => {
  const f = vi.fn(async () => new Response("{}", { status: 429, headers: { "Retry-After": "0" } }));
  const c = clientWith(f as unknown as typeof fetch);
  await expect(c.post("/documents/", {})).rejects.toMatchObject({ kind: "rate_limit" });
  expect(f).toHaveBeenCalledTimes(2);
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npx vitest run lib/vendus/client.test.ts` — expect: FAIL (module `./client` not found).

- [ ] **Step 3: Implement `lib/vendus/types.ts`**

```ts
export type VendusErrorKind =
  | "auth"
  | "validation"
  | "rate_limit"
  | "network"
  | "possibly_created"
  | "unknown";

export class VendusError extends Error {
  constructor(
    public kind: VendusErrorKind,
    public status: number | null,
    public messages: string[],
  ) {
    super(`Vendus ${kind}${status ? ` (${status})` : ""}: ${messages.join("; ")}`);
    this.name = "VendusError";
  }
}
```

- [ ] **Step 4: Implement `lib/vendus/client.ts`**

```ts
import { VendusError } from "./types";

const BASE_URL = "https://www.vendus.pt/ws/v1.1";

export interface VendusClientOptions {
  apiKey: string;
  fetchImpl?: typeof fetch;
  timeoutMs?: number;
  retryDelayMs?: number;
}

export interface VendusClient {
  get(path: string, params?: Record<string, string | number>): Promise<unknown>;
  post(path: string, body: unknown): Promise<unknown>;
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

async function readErrorMessages(res: Response): Promise<string[]> {
  const fallback = [`HTTP ${res.status}`];
  try {
    const body = await res.json();
    if (Array.isArray(body?.errors) && body.errors.length)
      return body.errors.map((e: { code?: string; message?: string }) =>
        e.code ? `${e.code}: ${e.message ?? ""}`.trim() : String(e.message ?? e),
      );
    if (typeof body?.message === "string") return [body.message];
    return fallback;
  } catch {
    return fallback;
  }
}

export function createVendusClient(opts: VendusClientOptions): VendusClient {
  const fetchImpl = opts.fetchImpl ?? fetch;
  const timeoutMs = opts.timeoutMs ?? 10_000;
  const retryDelayMs = opts.retryDelayMs ?? 300;
  const authHeader = "Basic " + Buffer.from(`${opts.apiKey}:`).toString("base64");

  async function request(
    method: "GET" | "POST",
    path: string,
    params?: Record<string, string | number>,
    body?: unknown,
  ): Promise<unknown> {
    const url = new URL(BASE_URL + path);
    for (const [k, v] of Object.entries(params ?? {})) url.searchParams.set(k, String(v));

    const attempt = async (): Promise<Response> => {
      const ctrl = new AbortController();
      const timer = setTimeout(() => ctrl.abort(), timeoutMs);
      try {
        return await fetchImpl(url.toString(), {
          method,
          headers: { Authorization: authHeader, "Content-Type": "application/json" },
          body: body === undefined ? undefined : JSON.stringify(body),
          signal: ctrl.signal,
        });
      } finally {
        clearTimeout(timer);
      }
    };

    const maxAttempts = method === "GET" ? 3 : 1;
    let retried429 = false;
    let lastNetworkError: unknown;

    for (let i = 0; i < maxAttempts; i++) {
      let res: Response;
      try {
        res = await attempt();
      } catch (e) {
        if (method === "POST") {
          // The request may have reached Vendus: NEVER replay a POST.
          throw new VendusError("possibly_created", null, [
            "Request may have reached Vendus",
            String(e),
          ]);
        }
        lastNetworkError = e;
        if (i < maxAttempts - 1) await sleep(retryDelayMs);
        continue;
      }

      if (res.ok) return res.json();
      const messages = await readErrorMessages(res);

      if (res.status === 401 || res.status === 403)
        throw new VendusError("auth", res.status, messages);
      if (res.status === 429) {
        if (!retried429) {
          // 429 = rejected before processing: one retry is safe, even for POST.
          retried429 = true;
          const raHeader = res.headers.get("Retry-After");
          const ra = raHeader === null ? NaN : Number(raHeader);
          await sleep(Number.isFinite(ra) ? Math.min(ra * 1000, 5000) : 1000);
          i--;
          continue;
        }
        throw new VendusError("rate_limit", 429, messages);
      }
      if (res.status >= 500) {
        if (method === "GET" && i < maxAttempts - 1) {
          await sleep(retryDelayMs);
          continue;
        }
        throw new VendusError("network", res.status, messages);
      }
      throw new VendusError("validation", res.status, messages);
    }
    throw new VendusError("network", null, [String(lastNetworkError)]);
  }

  return {
    get: (path, params) => request("GET", path, params),
    post: (path, body) => request("POST", path, undefined, body),
  };
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `npx vitest run lib/vendus/client.test.ts` — expect: 7 PASS.

- [ ] **Step 6: Commit**

```bash
git add lib/vendus && git commit -m "feat: vendus http client with normalized errors and safe retry policy"
```

---

### Task 3: Read modules — products, categories, taxes (with pagination)

**Files:**
- Create: `lib/vendus/products.ts`, `lib/vendus/taxes.ts`
- Test: `lib/vendus/products.test.ts`

**Interfaces:**
- Consumes: `VendusClient` (Task 2), `VendusError` (Task 2).
- Produces:
  - `productSchema` / `VendusProduct` (fields: `id: number`, `title: string`, `gross_price?`, `price?`, `category_id?`, `status?` — passthrough), `categorySchema` / `VendusCategory` (`id: number`, `title: string`).
  - `listProducts(client): Promise<VendusProduct[]>`, `listCategories(client): Promise<VendusCategory[]>`, `createProduct(client, input): Promise<VendusProduct>`, `productPrice(p): number`.
  - `parseList<T>(schema, data, what): T[]` and `listAllPages<T>(client, path, schema, what): Promise<T[]>` (used by Task 4).
  - `taxSchema` / `VendusTax`, `listTaxes(client): Promise<VendusTax[]>`.

- [ ] **Step 1: Write the failing tests** — `lib/vendus/products.test.ts`

```ts
import { expect, it, vi } from "vitest";
import { listCategories, listProducts, productPrice, productSchema } from "./products";
import { listTaxes } from "./taxes";
import type { VendusClient } from "./client";

const fakeClient = (get: ReturnType<typeof vi.fn>): VendusClient =>
  ({ get, post: vi.fn() }) as unknown as VendusClient;

const page = (n: number, count: number) =>
  Array.from({ length: count }, (_, i) => ({
    id: n * 1000 + i,
    title: `P${n}-${i}`,
    gross_price: "1.50",
    extra_field: "ok",
  }));

it("paginates until a short page", async () => {
  const get = vi.fn().mockResolvedValueOnce(page(1, 100)).mockResolvedValueOnce(page(2, 3));
  const products = await listProducts(fakeClient(get));
  expect(products).toHaveLength(103);
  expect(get).toHaveBeenNthCalledWith(1, "/products/", { page: 1, per_page: 100 });
  expect(get).toHaveBeenNthCalledWith(2, "/products/", { page: 2, per_page: 100 });
});

it("coerces string ids/prices and tolerates unknown fields", () => {
  const p = productSchema.parse({ id: "7", title: "Coffee", gross_price: "1.20", whatever: true });
  expect(p.id).toBe(7);
  expect(productPrice(p)).toBe(1.2);
});

it("falls back from gross_price to price to 0", () => {
  expect(productPrice(productSchema.parse({ id: 1, title: "A", price: "2.00" }))).toBe(2);
  expect(productPrice(productSchema.parse({ id: 1, title: "A" }))).toBe(0);
});

it("throws a loud VendusError on unexpected shapes", async () => {
  const get = vi.fn().mockResolvedValue({ not: "a list" });
  await expect(listProducts(fakeClient(get))).rejects.toMatchObject({ kind: "unknown" });
});

it("lists categories and taxes", async () => {
  const get = vi.fn().mockResolvedValue([{ id: 1, title: "Drinks" }]);
  expect(await listCategories(fakeClient(get))).toEqual([{ id: 1, title: "Drinks" }]);
  const get2 = vi.fn().mockResolvedValue([{ id: 3, type: "NOR", rate: "23" }]);
  expect((await listTaxes(fakeClient(get2)))[0]).toMatchObject({ type: "NOR", rate: 23 });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npx vitest run lib/vendus/products.test.ts` — expect: FAIL (modules not found).

- [ ] **Step 3: Implement `lib/vendus/products.ts`**

```ts
import { z } from "zod";
import type { VendusClient } from "./client";
import { VendusError } from "./types";

export const productSchema = z
  .object({
    id: z.coerce.number(),
    title: z.string(),
    gross_price: z.coerce.number().optional(),
    price: z.coerce.number().optional(),
    category_id: z.coerce.number().nullish(),
    status: z.string().optional(),
  })
  .passthrough();
export type VendusProduct = z.infer<typeof productSchema>;

export const categorySchema = z
  .object({ id: z.coerce.number(), title: z.string() })
  .passthrough();
export type VendusCategory = z.infer<typeof categorySchema>;

export function parseList<T>(schema: z.ZodType<T>, data: unknown, what: string): T[] {
  const r = z.array(schema).safeParse(data);
  if (!r.success)
    throw new VendusError("unknown", null, [
      `Unexpected Vendus ${what} response: ${r.error.message}`,
    ]);
  return r.data;
}

const PER_PAGE = 100;
const MAX_PAGES = 50;

export async function listAllPages<T>(
  client: VendusClient,
  path: string,
  schema: z.ZodType<T>,
  what: string,
): Promise<T[]> {
  const out: T[] = [];
  for (let page = 1; page <= MAX_PAGES; page++) {
    const data = await client.get(path, { page, per_page: PER_PAGE });
    const items = parseList(schema, data, what);
    out.push(...items);
    if (items.length < PER_PAGE) break;
  }
  return out;
}

export const listProducts = (client: VendusClient) =>
  listAllPages(client, "/products/", productSchema, "products");

export const listCategories = (client: VendusClient) =>
  listAllPages(client, "/products/categories/", categorySchema, "categories");

export const productPrice = (p: VendusProduct): number => p.gross_price ?? p.price ?? 0;

export interface CreateProductInput {
  title: string;
  gross_price: number;
  tax_id?: string;
  category_id?: number;
  reference?: string;
}

export async function createProduct(
  client: VendusClient,
  input: CreateProductInput,
): Promise<VendusProduct> {
  const data = await client.post("/products/", input);
  const r = productSchema.safeParse(data);
  if (!r.success)
    throw new VendusError("unknown", null, [
      `Unexpected create-product response: ${r.error.message}`,
    ]);
  return r.data;
}
```

- [ ] **Step 4: Implement `lib/vendus/taxes.ts`**

```ts
import { z } from "zod";
import type { VendusClient } from "./client";
import { listAllPages } from "./products";

export const taxSchema = z
  .object({
    id: z.union([z.coerce.number(), z.string()]),
    title: z.string().optional(),
    rate: z.coerce.number().optional(),
    type: z.string().optional(), // NOR / INT / RED / ISE
  })
  .passthrough();
export type VendusTax = z.infer<typeof taxSchema>;

export const listTaxes = (client: VendusClient) =>
  listAllPages(client, "/taxes/", taxSchema, "taxes");
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `npx vitest run lib/vendus/products.test.ts` — expect: 5 PASS.

- [ ] **Step 6: Commit**

```bash
git add lib/vendus && git commit -m "feat: vendus read modules — products, categories, taxes with pagination"
```

---

### Task 4: Write modules — documents (FS/NC) and recent documents

**Files:**
- Create: `lib/vendus/documents.ts`
- Test: `lib/vendus/documents.test.ts`

**Interfaces:**
- Consumes: `VendusClient`, `VendusError`, `parseList` (Task 3).
- Produces:
  - `documentSchema` / `VendusDocument` (fields: `id: number`, `number?`, `atcud?`, `qrcode?`, `qr_code?`, `amount_gross?`, `amount_net?`, `date?`, `system_time?` — passthrough).
  - `documentQrData(d): string | null`, `documentTotal(d): number | null`.
  - `interface DocumentItem { id: number; qty: number }`.
  - `buildFsPayload({ items, paymentMethodId, registerId? })`, `buildNcPayload({ relatedDocumentId, items })`.
  - `createFs(client, input): Promise<VendusDocument>`, `createNc(client, input): Promise<VendusDocument>`, `getDocument(client, id): Promise<VendusDocument>`.
  - `listRecentDocuments(client, { sinceMinutes?, now? }?): Promise<VendusDocument[]>`.

**Note:** the exact NC linkage field (`related_document_id`) is a best guess from the Vendus docs — the spike (Task 5) confirms it against the live API; if rejected, adjust `buildNcPayload` and its test there.

- [ ] **Step 1: Write the failing tests** — `lib/vendus/documents.test.ts`

```ts
import { expect, it, vi } from "vitest";
import {
  buildFsPayload,
  buildNcPayload,
  createFs,
  documentQrData,
  documentSchema,
  listRecentDocuments,
} from "./documents";
import type { VendusClient } from "./client";

const fakeClient = (fns: Partial<Record<"get" | "post", ReturnType<typeof vi.fn>>>): VendusClient =>
  ({ get: fns.get ?? vi.fn(), post: fns.post ?? vi.fn() }) as unknown as VendusClient;

it("builds an FS payload with items and one payment", () => {
  expect(buildFsPayload({ items: [{ id: 5, qty: 2 }], paymentMethodId: 9, registerId: 3 })).toEqual({
    type: "FS",
    register_id: 3,
    items: [{ id: 5, qty: 2 }],
    payments: [{ id: 9 }],
  });
});

it("omits register_id when not provided", () => {
  expect(buildFsPayload({ items: [{ id: 5, qty: 1 }], paymentMethodId: 9 })).not.toHaveProperty(
    "register_id",
  );
});

it("builds an NC payload linked to the original document", () => {
  expect(buildNcPayload({ relatedDocumentId: 77, items: [{ id: 5, qty: 1 }] })).toEqual({
    type: "NC",
    related_document_id: 77,
    items: [{ id: 5, qty: 1 }],
  });
});

it("parses a created document and finds QR data under either field name", () => {
  const a = documentSchema.parse({ id: 1, number: "FS T1/1", atcud: "ABC-1", qrcode: "QRDATA" });
  expect(documentQrData(a)).toBe("QRDATA");
  const b = documentSchema.parse({ id: 2, qr_code: "QR2" });
  expect(documentQrData(b)).toBe("QR2");
  expect(documentQrData(documentSchema.parse({ id: 3 }))).toBeNull();
});

it("createFs posts to /documents/ and parses the response", async () => {
  const post = vi.fn().mockResolvedValue({ id: 10, number: "FS T1/10", amount_gross: "3.00" });
  const doc = await createFs(fakeClient({ post }), { items: [{ id: 1, qty: 1 }], paymentMethodId: 2 });
  expect(post).toHaveBeenCalledWith("/documents/", expect.objectContaining({ type: "FS" }));
  expect(doc.amount_gross).toBe(3);
});

it("filters recent documents by time window, keeping date-only docs from today", async () => {
  const now = new Date("2026-07-27T20:00:00"); // local time on purpose (no Z)
  const get = vi.fn().mockResolvedValue([
    { id: 1, system_time: "2026-07-27 19:58:00" },
    { id: 2, system_time: "2026-07-27 18:00:00" },
    { id: 3, date: "2026-07-27" },
    { id: 4, date: "2026-07-26" },
  ]);
  const docs = await listRecentDocuments(fakeClient({ get }), { sinceMinutes: 5, now });
  expect(docs.map((d) => d.id)).toEqual([1, 3]);
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npx vitest run lib/vendus/documents.test.ts` — expect: FAIL (module not found).

- [ ] **Step 3: Implement `lib/vendus/documents.ts`**

```ts
import { z } from "zod";
import type { VendusClient } from "./client";
import { VendusError } from "./types";
import { parseList } from "./products";

export const documentSchema = z
  .object({
    id: z.coerce.number(),
    number: z.string().optional(),
    atcud: z.string().nullish(),
    // The QR field name varies across the docs — capture both.
    qrcode: z.string().nullish(),
    qr_code: z.string().nullish(),
    amount_gross: z.coerce.number().optional(),
    amount_net: z.coerce.number().optional(),
    date: z.string().optional(),
    system_time: z.string().optional(),
  })
  .passthrough();
export type VendusDocument = z.infer<typeof documentSchema>;

export const documentQrData = (d: VendusDocument): string | null => d.qrcode ?? d.qr_code ?? null;
export const documentTotal = (d: VendusDocument): number | null => d.amount_gross ?? null;

export interface DocumentItem {
  id: number;
  qty: number;
}

export function buildFsPayload(input: {
  items: DocumentItem[];
  paymentMethodId: number;
  registerId?: number;
}) {
  return {
    type: "FS",
    ...(input.registerId !== undefined ? { register_id: input.registerId } : {}),
    items: input.items.map((i) => ({ id: i.id, qty: i.qty })),
    payments: [{ id: input.paymentMethodId }],
  };
}

export function buildNcPayload(input: { relatedDocumentId: number; items: DocumentItem[] }) {
  // Linkage field confirmed by the spike (Task 5); adjust here + test if the API rejects it.
  return {
    type: "NC",
    related_document_id: input.relatedDocumentId,
    items: input.items.map((i) => ({ id: i.id, qty: i.qty })),
  };
}

async function postDocument(client: VendusClient, payload: unknown): Promise<VendusDocument> {
  const data = await client.post("/documents/", payload);
  const r = documentSchema.safeParse(data);
  if (!r.success)
    throw new VendusError("unknown", null, [
      `Unexpected create-document response: ${r.error.message}`,
    ]);
  return r.data;
}

export const createFs = (
  client: VendusClient,
  input: { items: DocumentItem[]; paymentMethodId: number; registerId?: number },
) => postDocument(client, buildFsPayload(input));

export const createNc = (
  client: VendusClient,
  input: { relatedDocumentId: number; items: DocumentItem[] },
) => postDocument(client, buildNcPayload(input));

export async function getDocument(client: VendusClient, id: number): Promise<VendusDocument> {
  const data = await client.get(`/documents/${id}/`);
  const r = documentSchema.safeParse(data);
  if (!r.success)
    throw new VendusError("unknown", null, [`Unexpected document response: ${r.error.message}`]);
  return r.data;
}

export async function listRecentDocuments(
  client: VendusClient,
  { sinceMinutes = 5, now = new Date() }: { sinceMinutes?: number; now?: Date } = {},
): Promise<VendusDocument[]> {
  const data = await client.get("/documents/", { per_page: 20 });
  const docs = parseList(documentSchema, data, "documents");
  const pad = (n: number) => String(n).padStart(2, "0");
  const todayIso = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
  return docs.filter((d) => {
    const t = d.system_time ?? d.date;
    if (!t) return false;
    if (!t.includes(":")) return t.startsWith(todayIso); // date-only: keep today's docs
    const ms = new Date(t.replace(" ", "T")).getTime();
    return !Number.isNaN(ms) && ms >= now.getTime() - sinceMinutes * 60_000;
  });
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `npx vitest run lib/vendus/documents.test.ts` — expect: 6 PASS.

- [ ] **Step 5: Commit**

```bash
git add lib/vendus && git commit -m "feat: vendus documents module — FS/NC creation, recent documents"
```

---

### Task 5: Fiscal spike go/no-go 🚦 HARD GATE

**Files:**
- Create: `scripts/spike.ts`, `docs/spike-findings.md`, `lib/vendus/fixtures.test.ts`
- Create (at runtime): `test/fixtures/*.json`

**Interfaces:**
- Consumes: everything from Tasks 2-4.
- Produces: GO/NO-GO verdict; real response fixtures in `test/fixtures/`; confirmed values for `VENDUS_REGISTER_ID` / `VENDUS_PM_*` env vars; confirmed (or corrected) `documentSchema` field names and `buildNcPayload` linkage field.

**This task requires the human: create the test-account API key, fill `.env.local`, and review the verdict. Do not proceed to Task 6 without an explicit GO.**

- [ ] **Step 1: Write `scripts/spike.ts`**

```ts
/* Fiscal go/no-go spike — run against the Vendus TEST account only.
   Usage:
     npx tsx scripts/spike.ts --discover   # list registers & payment methods
     npx tsx scripts/spike.ts              # full spike run
*/
import dotenv from "dotenv";
import { mkdirSync, writeFileSync } from "node:fs";
import { createVendusClient } from "../lib/vendus/client";
import { listTaxes } from "../lib/vendus/taxes";
import { createProduct, listProducts } from "../lib/vendus/products";
import { createNc, documentQrData, documentSchema } from "../lib/vendus/documents";
import { VendusError } from "../lib/vendus/types";

dotenv.config({ path: ".env.local" });
dotenv.config();

const apiKey = process.env.VENDUS_API_KEY;
if (!apiKey) {
  console.error("VENDUS_API_KEY missing (.env.local)");
  process.exit(1);
}
const client = createVendusClient({ apiKey });

const FIXTURES = "test/fixtures";
const save = (name: string, data: unknown) => {
  mkdirSync(FIXTURES, { recursive: true });
  writeFileSync(`${FIXTURES}/${name}.json`, JSON.stringify(data, null, 2));
};

type Check = { name: string; ok: boolean; note: string };
const checks: Check[] = [];
const record = (name: string, ok: boolean, note = "") => {
  checks.push({ name, ok, note });
  console.log(`${ok ? "✅" : "❌"} ${name}${note ? ` — ${note}` : ""}`);
};

async function discover() {
  console.log("— Registers —");
  console.log(JSON.stringify(await client.get("/registers/"), null, 2));
  for (const path of ["/documents/paymentmethods/", "/paymentmethods/"]) {
    try {
      console.log(`— Payment methods (${path}) —`);
      console.log(JSON.stringify(await client.get(path), null, 2));
      return;
    } catch {
      /* endpoint absent: try the next one */
    }
  }
  console.log("No payment-methods endpoint found — read the ids in the Vendus backoffice.");
}

async function spike() {
  const pmCash = Number(process.env.VENDUS_PM_CASH_ID);
  if (!Number.isFinite(pmCash)) {
    console.error("Set VENDUS_PM_CASH_ID first (run with --discover).");
    process.exit(1);
  }
  const registerId = process.env.VENDUS_REGISTER_ID
    ? Number(process.env.VENDUS_REGISTER_ID)
    : undefined;

  // 1. Read access
  const taxes = await listTaxes(client);
  save("taxes", taxes);
  record("read taxes", taxes.length > 0, `${taxes.length} taxes`);
  const products = await listProducts(client);
  record("read products", true, `${products.length} products`);

  // 2. Product creation (validates the write CRUD used in Phase 2)
  let productId: number;
  try {
    const p = await createProduct(client, {
      title: "SPIKE TEST ITEM",
      gross_price: 0.1,
      tax_id: "NOR",
      reference: "SPIKE-1",
    });
    save("product-created", p);
    productId = p.id;
    record("create product", true, `id ${p.id}`);
  } catch (e) {
    record("create product", false, String(e));
    return verdict();
  }

  // 3. Test FS — raw post so the untouched response gets printed and saved
  let fsId: number;
  try {
    const raw = await client.post("/documents/", {
      type: "FS",
      ...(registerId !== undefined ? { register_id: registerId } : {}),
      items: [{ id: productId, qty: 1 }],
      payments: [{ id: pmCash }],
    });
    save("document-fs", raw);
    console.log("FS raw response:\n" + JSON.stringify(raw, null, 2));
    const doc = documentSchema.parse(raw);
    fsId = doc.id;
    record("FS has a series number", !!doc.number, doc.number ?? "MISSING");
    record("FS has an ATCUD", !!doc.atcud, doc.atcud ?? "MISSING — check the real field name in the raw response");
    record("FS has QR data", !!documentQrData(doc), documentQrData(doc) ? "present" : "MISSING — check the real field name");
  } catch (e) {
    record("create FS", false, String(e));
    return verdict();
  }

  // 4. Cross-check: document is listed; note which register/series it landed in
  const recent = await client.get("/documents/", { per_page: 10 });
  save("documents-list", recent);
  record(
    "FS visible in /documents/",
    JSON.stringify(recent).includes(String(fsId)),
    "inspect documents-list.json: which register/series did it land in?",
  );

  // 5. Cancel via NC
  try {
    const nc = await createNc(client, { relatedDocumentId: fsId, items: [{ id: productId, qty: 1 }] });
    save("document-nc", nc);
    record("NC created with ATCUD", !!nc.atcud, nc.number ?? "");
  } catch (e) {
    const msg = e instanceof VendusError ? e.messages.join("; ") : String(e);
    record("NC created with ATCUD", false, `ADJUST buildNcPayload if the linkage field is wrong — API said: ${msg}`);
  }

  return verdict();
}

function verdict() {
  console.log("\n══ VERDICT ══");
  console.table(checks);
  const go = checks.every((c) => c.ok);
  console.log(go ? "\nGO ✅ — fiscal chain validated end-to-end" : "\nNO-GO ❌ — fix the failing checks before building any UI");
  process.exit(go ? 0 : 1);
}

(process.argv.includes("--discover") ? discover() : spike()).catch((e) => {
  console.error(e);
  process.exit(1);
});
```

- [ ] **Step 2: Human setup**

Copy `.env.local.example` to `.env.local`; paste the **test account** API key (Vendus backoffice → Settings → API).

- [ ] **Step 3: Run discovery**

Run: `npx tsx scripts/spike.ts --discover`
Expected: registers list (and payment methods if the endpoint exists). Fill `VENDUS_REGISTER_ID` and `VENDUS_PM_CASH_ID` / `VENDUS_PM_CARD_ID` / `VENDUS_PM_MBWAY_ID` in `.env.local` (from the output or the backoffice).

- [ ] **Step 4: Run the full spike**

Run: `npx tsx scripts/spike.ts`
Expected: GO with all checks ✅. If a check fails on a **field name** (ATCUD/QR under a different key, or the `payments`/NC payload rejected): inspect the raw JSON printed and the API error messages, update `documentSchema` / `buildFsPayload` / `buildNcPayload` **and their tests** in `lib/vendus/documents.ts`, run `npm test`, and re-run the spike until GO.

- [ ] **Step 5: Write `docs/spike-findings.md`**

Record what the spike revealed (from the real output — not invented): which register/series API documents land in, whether it interferes with a POS register's numbering, exact ATCUD/QR field names, the working NC payload shape, and the payment-method ids used. One short section per point.

- [ ] **Step 6: Add the fixtures regression test** — `lib/vendus/fixtures.test.ts`

```ts
import { existsSync, readFileSync } from "node:fs";
import { expect, it } from "vitest";
import { z } from "zod";
import { documentSchema } from "./documents";
import { productSchema } from "./products";
import { taxSchema } from "./taxes";

const load = (name: string) => JSON.parse(readFileSync(`test/fixtures/${name}.json`, "utf8"));

it("parses the real fixtures recorded by the spike", () => {
  if (!existsSync("test/fixtures/document-fs.json")) return; // spike not run yet
  expect(() => documentSchema.parse(load("document-fs"))).not.toThrow();
  expect(() => documentSchema.parse(load("document-nc"))).not.toThrow();
  expect(() => z.array(taxSchema).parse(load("taxes"))).not.toThrow();
  expect(() => productSchema.parse(load("product-created"))).not.toThrow();
});
```

Run: `npm test` — expect: all PASS.

- [ ] **Step 7: Sanitize and commit**

Check `test/fixtures/*.json` for account identifiers (company name, NIF, tokens) and redact if present (keep structure intact).

```bash
git add scripts docs test lib/vendus && git commit -m "feat: fiscal go/no-go spike with recorded fixtures and findings"
```

- [ ] **Step 8: 🚦 STOP — report the verdict to the user and wait for explicit GO before Task 6.**

---

### Task 6: TTL cache + catalog service + `/api/catalog`

**Files:**
- Create: `lib/ttlCache.ts`, `lib/server/vendus.ts`, `lib/server/catalog.ts`, `lib/server/httpError.ts`, `app/api/catalog/route.ts`
- Test: `lib/ttlCache.test.ts`, `lib/server/catalog.test.ts`

**Interfaces:**
- Consumes: `createVendusClient`, `listProducts`, `listCategories`, `listTaxes`, `productPrice`, `VendusError`.
- Produces:
  - `ttlGet<T>(key: string, ttlMs: number, loader: () => Promise<T>, cacheable?: (v: T) => boolean): Promise<T>` and `ttlClear(): void`.
  - `getVendusClient(): VendusClient` (throws `VendusError("auth", ...)` if `VENDUS_API_KEY` unset).
  - `interface CatalogProduct { id: number; name: string; price: number; categoryId: number | null }`, `interface CatalogCategory { id: number; name: string }`, `interface CatalogTax { id: number | string; type: string | null; rate: number | null }`, `interface Catalog { products: CatalogProduct[]; categories: CatalogCategory[]; taxes: CatalogTax[] }`.
  - `loadCatalog(client): Promise<Catalog>`, `getCatalog(opts?: { fresh?: boolean }): Promise<Catalog>` (60 s cache).
  - `vendusErrorResponse(e: unknown): NextResponse` — status map: auth→500, validation→422, rate_limit→429, network→502, possibly_created→504, unknown→502; body `{ error: { kind, messages } }`.
  - Route: `GET /api/catalog[?fresh=1]` → `Catalog` JSON.

- [ ] **Step 1: Write the failing tests** — `lib/ttlCache.test.ts`

```ts
import { afterEach, expect, it, vi } from "vitest";
import { ttlClear, ttlGet } from "./ttlCache";

afterEach(() => {
  ttlClear();
  vi.useRealTimers();
});

it("caches within the TTL and reloads after", async () => {
  vi.useFakeTimers();
  const loader = vi.fn().mockResolvedValue("v1");
  expect(await ttlGet("k", 1000, loader)).toBe("v1");
  expect(await ttlGet("k", 1000, loader)).toBe("v1");
  expect(loader).toHaveBeenCalledTimes(1);
  vi.advanceTimersByTime(1500);
  await ttlGet("k", 1000, loader);
  expect(loader).toHaveBeenCalledTimes(2);
});

it("never caches values deemed not cacheable", async () => {
  const loader = vi.fn().mockResolvedValue([]);
  const cacheable = (v: unknown[]) => v.length > 0;
  await ttlGet("k", 1000, loader, cacheable);
  await ttlGet("k", 1000, loader, cacheable);
  expect(loader).toHaveBeenCalledTimes(2);
});
```

And `lib/server/catalog.test.ts`:

```ts
import { expect, it, vi } from "vitest";
import { loadCatalog } from "./catalog";
import type { VendusClient } from "@/lib/vendus/client";

it("shapes products, categories and taxes and drops status=off products", async () => {
  const get = vi.fn(async (path: string) => {
    if (path === "/products/")
      return [
        { id: 1, title: "Coffee", gross_price: "1.20", category_id: 10 },
        { id: 2, title: "Old", gross_price: "9.99", status: "off" },
      ];
    if (path === "/products/categories/") return [{ id: 10, title: "Drinks" }];
    if (path === "/taxes/") return [{ id: 3, type: "NOR", rate: 23 }];
    throw new Error("unexpected " + path);
  });
  const catalog = await loadCatalog({ get, post: vi.fn() } as unknown as VendusClient);
  expect(catalog.products).toEqual([{ id: 1, name: "Coffee", price: 1.2, categoryId: 10 }]);
  expect(catalog.categories).toEqual([{ id: 10, name: "Drinks" }]);
  expect(catalog.taxes).toEqual([{ id: 3, type: "NOR", rate: 23 }]);
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npx vitest run lib/ttlCache.test.ts lib/server/catalog.test.ts` — expect: FAIL (modules not found).

- [ ] **Step 3: Implement `lib/ttlCache.ts`**

```ts
type Entry = { at: number; value: unknown };
const store = new Map<string, Entry>();

export async function ttlGet<T>(
  key: string,
  ttlMs: number,
  loader: () => Promise<T>,
  cacheable: (v: T) => boolean = (v) => !!v,
): Promise<T> {
  const hit = store.get(key);
  if (hit && Date.now() - hit.at < ttlMs) return hit.value as T;
  const value = await loader();
  if (cacheable(value)) store.set(key, { at: Date.now(), value });
  return value;
}

// Clears the whole store (only the catalog uses it in Phase 1).
export function ttlClear(): void {
  store.clear();
}
```

- [ ] **Step 4: Implement `lib/server/vendus.ts`**

```ts
import { createVendusClient, type VendusClient } from "@/lib/vendus/client";
import { VendusError } from "@/lib/vendus/types";

let client: VendusClient | null = null;

export function getVendusClient(): VendusClient {
  const apiKey = process.env.VENDUS_API_KEY;
  if (!apiKey) throw new VendusError("auth", null, ["VENDUS_API_KEY is not set"]);
  if (!client) client = createVendusClient({ apiKey });
  return client;
}
```

- [ ] **Step 5: Implement `lib/server/catalog.ts`**

```ts
import type { VendusClient } from "@/lib/vendus/client";
import { listCategories, listProducts, productPrice } from "@/lib/vendus/products";
import { listTaxes } from "@/lib/vendus/taxes";
import { ttlClear, ttlGet } from "@/lib/ttlCache";
import { getVendusClient } from "./vendus";

export interface CatalogProduct {
  id: number;
  name: string;
  price: number;
  categoryId: number | null;
}
export interface CatalogCategory {
  id: number;
  name: string;
}
export interface CatalogTax {
  id: number | string;
  type: string | null;
  rate: number | null;
}
export interface Catalog {
  products: CatalogProduct[];
  categories: CatalogCategory[];
  taxes: CatalogTax[];
}

export async function loadCatalog(client: VendusClient): Promise<Catalog> {
  const [products, categories, taxes] = await Promise.all([
    listProducts(client),
    listCategories(client),
    listTaxes(client),
  ]);
  return {
    products: products
      .filter((p) => p.status !== "off")
      .map((p) => ({ id: p.id, name: p.title, price: productPrice(p), categoryId: p.category_id ?? null })),
    categories: categories.map((c) => ({ id: c.id, name: c.title })),
    taxes: taxes.map((t) => ({ id: t.id, type: t.type ?? null, rate: t.rate ?? null })),
  };
}

export function getCatalog(opts: { fresh?: boolean } = {}): Promise<Catalog> {
  if (opts.fresh) ttlClear();
  return ttlGet("catalog", 60_000, () => loadCatalog(getVendusClient()), (c) => c.products.length > 0);
}
```

- [ ] **Step 6: Implement `lib/server/httpError.ts` and the route**

```ts
import { NextResponse } from "next/server";
import { VendusError, type VendusErrorKind } from "@/lib/vendus/types";

const STATUS: Record<VendusErrorKind, number> = {
  auth: 500,
  validation: 422,
  rate_limit: 429,
  network: 502,
  possibly_created: 504,
  unknown: 502,
};

export function vendusErrorResponse(e: unknown) {
  const err = e instanceof VendusError ? e : new VendusError("unknown", null, [String(e)]);
  return NextResponse.json(
    { error: { kind: err.kind, messages: err.messages } },
    { status: STATUS[err.kind] },
  );
}
```

`app/api/catalog/route.ts`:

```ts
import { NextRequest, NextResponse } from "next/server";
import { getCatalog } from "@/lib/server/catalog";
import { vendusErrorResponse } from "@/lib/server/httpError";

export const dynamic = "force-dynamic";

export async function GET(req: NextRequest) {
  try {
    const fresh = req.nextUrl.searchParams.get("fresh") === "1";
    return NextResponse.json(await getCatalog({ fresh }));
  } catch (e) {
    return vendusErrorResponse(e);
  }
}
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `npx vitest run lib/ttlCache.test.ts lib/server/catalog.test.ts` — expect: 3 PASS.

- [ ] **Step 8: Manual smoke**

Run: `npm run dev`, then `curl -s localhost:3000/api/catalog` — expect: catalog JSON from the test account (auth middleware doesn't exist yet). Stop the dev server.

- [ ] **Step 9: Commit**

```bash
git add lib app && git commit -m "feat: catalog service with 60s cache and /api/catalog route"
```

---

### Task 7: Checkout service + `/api/checkout` + `/api/checkout/recent`

**Files:**
- Create: `lib/server/checkout.ts`, `app/api/checkout/route.ts`, `app/api/checkout/recent/route.ts`
- Test: `lib/server/checkout.test.ts`

**Interfaces:**
- Consumes: `Catalog` (Task 6), `createFs`, `documentTotal`, `documentQrData`, `listRecentDocuments` (Task 4), `getVendusClient`, `getCatalog`, `vendusErrorResponse` (Task 6).
- Produces:
  - `checkoutInputSchema` — `{ items: [{ productId: int>0, qty: int 1..99 }]+, payment: "NU"|"CC"|"MBWAY", amountReceived?: number>=0 }`.
  - `paymentMethodId(payment): number` (reads `VENDUS_PM_CASH_ID` / `VENDUS_PM_CARD_ID` / `VENDUS_PM_MBWAY_ID`; throws `VendusError("auth", ...)` if missing).
  - `interface CheckoutResult { number: string; atcud: string | null; qrData: string | null; total: number; change?: number }` — consumed by the UI (Task 11).
  - `runCheckout(client, catalog, input): Promise<CheckoutResult>`.
  - Routes: `POST /api/checkout` → `CheckoutResult` | error body; `GET /api/checkout/recent` → `{ id, number, total, time }[]`.

- [ ] **Step 1: Write the failing tests** — `lib/server/checkout.test.ts`

```ts
import { beforeEach, expect, it, vi } from "vitest";
import { paymentMethodId, runCheckout } from "./checkout";
import type { Catalog } from "./catalog";
import type { VendusClient } from "@/lib/vendus/client";

const catalog: Catalog = {
  products: [{ id: 1, name: "Coffee", price: 1.2, categoryId: null }],
  categories: [],
  taxes: [],
};

beforeEach(() => {
  process.env.VENDUS_PM_CASH_ID = "41";
  process.env.VENDUS_PM_CARD_ID = "42";
  process.env.VENDUS_PM_MBWAY_ID = "43";
  delete process.env.VENDUS_REGISTER_ID;
});

it("charges a cash sale and computes change from the Vendus total", async () => {
  const post = vi.fn().mockResolvedValue({
    id: 9, number: "FS T1/9", atcud: "AB-9", qrcode: "QR", amount_gross: "2.40",
  });
  const result = await runCheckout({ get: vi.fn(), post } as unknown as VendusClient, catalog, {
    items: [{ productId: 1, qty: 2 }],
    payment: "NU",
    amountReceived: 5,
  });
  expect(post).toHaveBeenCalledWith("/documents/", {
    type: "FS",
    items: [{ id: 1, qty: 2 }],
    payments: [{ id: 41 }],
  });
  expect(result).toEqual({ number: "FS T1/9", atcud: "AB-9", qrData: "QR", total: 2.4, change: 2.6 });
});

it("rejects unknown product ids before calling Vendus", async () => {
  const post = vi.fn();
  await expect(
    runCheckout({ get: vi.fn(), post } as unknown as VendusClient, catalog, {
      items: [{ productId: 999, qty: 1 }],
      payment: "CC",
    }),
  ).rejects.toMatchObject({ kind: "validation" });
  expect(post).not.toHaveBeenCalled();
});

it("falls back to the catalog price when Vendus omits the total", async () => {
  const post = vi.fn().mockResolvedValue({ id: 9, number: "FS T1/9" });
  const result = await runCheckout({ get: vi.fn(), post } as unknown as VendusClient, catalog, {
    items: [{ productId: 1, qty: 2 }],
    payment: "CC",
  });
  expect(result.total).toBe(2.4);
  expect(result.change).toBeUndefined();
});

it("fails loudly when a payment method id env is missing", () => {
  delete process.env.VENDUS_PM_MBWAY_ID;
  expect(() => paymentMethodId("MBWAY")).toThrowError(/VENDUS_PM_MBWAY_ID/);
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npx vitest run lib/server/checkout.test.ts` — expect: FAIL (module not found).

- [ ] **Step 3: Implement `lib/server/checkout.ts`**

```ts
import { z } from "zod";
import type { VendusClient } from "@/lib/vendus/client";
import { createFs, documentQrData, documentTotal } from "@/lib/vendus/documents";
import { VendusError } from "@/lib/vendus/types";
import type { Catalog } from "./catalog";

export const checkoutInputSchema = z.object({
  items: z
    .array(z.object({ productId: z.number().int().positive(), qty: z.number().int().min(1).max(99) }))
    .min(1),
  payment: z.enum(["NU", "CC", "MBWAY"]),
  amountReceived: z.number().nonnegative().optional(),
});
export type CheckoutInput = z.infer<typeof checkoutInputSchema>;

export interface CheckoutResult {
  number: string;
  atcud: string | null;
  qrData: string | null;
  total: number;
  change?: number;
}

const round2 = (n: number) => Math.round(n * 100) / 100;

const PM_ENV: Record<CheckoutInput["payment"], string> = {
  NU: "VENDUS_PM_CASH_ID",
  CC: "VENDUS_PM_CARD_ID",
  MBWAY: "VENDUS_PM_MBWAY_ID",
};

export function paymentMethodId(payment: CheckoutInput["payment"]): number {
  const envName = PM_ENV[payment];
  const raw = process.env[envName];
  const id = Number(raw);
  if (!raw || !Number.isFinite(id))
    throw new VendusError("auth", null, [`Missing env ${envName} (payment method id — see spike output)`]);
  return id;
}

export async function runCheckout(
  client: VendusClient,
  catalog: Catalog,
  input: CheckoutInput,
): Promise<CheckoutResult> {
  const known = new Map(catalog.products.map((p) => [p.id, p]));
  const missing = input.items.filter((i) => !known.has(i.productId));
  if (missing.length)
    throw new VendusError("validation", null, [
      `Unknown product id(s): ${missing.map((m) => m.productId).join(", ")}`,
    ]);

  const registerId = process.env.VENDUS_REGISTER_ID
    ? Number(process.env.VENDUS_REGISTER_ID)
    : undefined;

  const doc = await createFs(client, {
    items: input.items.map((i) => ({ id: i.productId, qty: i.qty })),
    paymentMethodId: paymentMethodId(input.payment),
    registerId,
  });

  const total =
    documentTotal(doc) ??
    round2(input.items.reduce((s, i) => s + known.get(i.productId)!.price * i.qty, 0));
  const change =
    input.payment === "NU" && input.amountReceived !== undefined
      ? round2(input.amountReceived - total)
      : undefined;

  return {
    number: doc.number ?? String(doc.id),
    atcud: doc.atcud ?? null,
    qrData: documentQrData(doc),
    total,
    ...(change !== undefined && change >= 0 ? { change } : {}),
  };
}
```

- [ ] **Step 4: Implement the routes**

`app/api/checkout/route.ts`:

```ts
import { NextRequest, NextResponse } from "next/server";
import { getCatalog } from "@/lib/server/catalog";
import { checkoutInputSchema, runCheckout, type CheckoutInput } from "@/lib/server/checkout";
import { vendusErrorResponse } from "@/lib/server/httpError";
import { getVendusClient } from "@/lib/server/vendus";

export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  let input: CheckoutInput;
  try {
    input = checkoutInputSchema.parse(await req.json());
  } catch {
    return NextResponse.json(
      { error: { kind: "validation", messages: ["Invalid checkout payload"] } },
      { status: 400 },
    );
  }
  try {
    const catalog = await getCatalog();
    return NextResponse.json(await runCheckout(getVendusClient(), catalog, input));
  } catch (e) {
    return vendusErrorResponse(e);
  }
}
```

`app/api/checkout/recent/route.ts`:

```ts
import { NextResponse } from "next/server";
import { listRecentDocuments } from "@/lib/vendus/documents";
import { vendusErrorResponse } from "@/lib/server/httpError";
import { getVendusClient } from "@/lib/server/vendus";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const docs = await listRecentDocuments(getVendusClient(), { sinceMinutes: 5 });
    return NextResponse.json(
      docs.map((d) => ({
        id: d.id,
        number: d.number ?? String(d.id),
        total: d.amount_gross ?? null,
        time: d.system_time ?? d.date ?? "",
      })),
    );
  } catch (e) {
    return vendusErrorResponse(e);
  }
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `npx vitest run lib/server/checkout.test.ts` — expect: 4 PASS. Then `npm test` — all suites PASS.

- [ ] **Step 6: Manual smoke against the test account**

Run: `npm run dev`, then (using a real product id from `/api/catalog`):

```bash
curl -s localhost:3000/api/catalog | head -c 400
curl -s -X POST localhost:3000/api/checkout -H "Content-Type: application/json" \
  -d '{"items":[{"productId":REPLACE_WITH_REAL_ID,"qty":1}],"payment":"NU","amountReceived":1}'
```

Expected: a JSON `CheckoutResult` with a document number. This creates a real FS on the **test account** — that is fine.

- [ ] **Step 7: Commit**

```bash
git add lib app && git commit -m "feat: checkout service and routes — FS creation, change, recent documents"
```

---

### Task 8: PIN auth — cookie lib, middleware, login API + page

**Files:**
- Create: `lib/auth.ts`, `middleware.ts`, `app/api/login/route.ts`, `app/login/page.tsx`
- Test: `lib/auth.test.ts`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `makeSessionCookie(secret: string): Promise<string>`, `verifySessionCookie(secret: string, cookie: string | undefined): Promise<boolean>`; cookie name `mesa_session`; `POST /api/login` body `{ pin: string }` → 200 + cookie | 401.

**Note:** `lib/auth.ts` must use only Web Crypto (`crypto.subtle`) — no `node:crypto` import — because the middleware runs on the edge runtime.

- [ ] **Step 1: Write the failing tests** — `lib/auth.test.ts`

```ts
import { expect, it } from "vitest";
import { makeSessionCookie, verifySessionCookie } from "./auth";

it("verifies a cookie it signed", async () => {
  const c = await makeSessionCookie("secret-1");
  expect(await verifySessionCookie("secret-1", c)).toBe(true);
});

it("rejects missing, tampered or wrong-secret cookies", async () => {
  const c = await makeSessionCookie("secret-1");
  expect(await verifySessionCookie("secret-1", undefined)).toBe(false);
  expect(await verifySessionCookie("secret-1", c + "x")).toBe(false);
  expect(await verifySessionCookie("secret-2", c)).toBe(false);
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npx vitest run lib/auth.test.ts` — expect: FAIL (module not found).

- [ ] **Step 3: Implement `lib/auth.ts`**

```ts
const SESSION_VALUE = "mesa-session-v1";
const enc = new TextEncoder();

async function hmacHex(secret: string, value: string): Promise<string> {
  const key = await crypto.subtle.importKey(
    "raw",
    enc.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const sig = await crypto.subtle.sign("HMAC", key, enc.encode(value));
  return Array.from(new Uint8Array(sig))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

export async function makeSessionCookie(secret: string): Promise<string> {
  return `v1.${await hmacHex(secret, SESSION_VALUE)}`;
}

export async function verifySessionCookie(
  secret: string,
  cookie: string | undefined,
): Promise<boolean> {
  if (!cookie) return false;
  return cookie === (await makeSessionCookie(secret));
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `npx vitest run lib/auth.test.ts` — expect: 2 PASS.

- [ ] **Step 5: Implement `middleware.ts`**

```ts
import { NextRequest, NextResponse } from "next/server";
import { verifySessionCookie } from "@/lib/auth";

const PUBLIC = ["/login", "/api/login"];

export async function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;
  if (PUBLIC.some((p) => pathname.startsWith(p))) return NextResponse.next();
  const ok = await verifySessionCookie(
    process.env.MESA_COOKIE_SECRET ?? "",
    req.cookies.get("mesa_session")?.value,
  );
  if (ok) return NextResponse.next();
  if (pathname.startsWith("/api/"))
    return NextResponse.json(
      { error: { kind: "auth", messages: ["Not authenticated"] } },
      { status: 401 },
    );
  return NextResponse.redirect(new URL("/login", req.url));
}

export const config = { matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"] };
```

- [ ] **Step 6: Implement `app/api/login/route.ts`**

```ts
import { NextRequest, NextResponse } from "next/server";
import { makeSessionCookie } from "@/lib/auth";

export async function POST(req: NextRequest) {
  const { pin } = await req.json().catch(() => ({}));
  if (!process.env.MESA_PIN || pin !== process.env.MESA_PIN)
    return NextResponse.json({ ok: false }, { status: 401 });
  const cookie = await makeSessionCookie(process.env.MESA_COOKIE_SECRET ?? "");
  const res = NextResponse.json({ ok: true });
  res.cookies.set("mesa_session", cookie, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    maxAge: 60 * 60 * 24 * 30,
    path: "/",
  });
  return res;
}
```

- [ ] **Step 7: Implement `app/login/page.tsx`**

```tsx
"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";

const KEYS = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "", "0", "⌫"];

export default function LoginPage() {
  const [pin, setPin] = useState("");
  const [wrong, setWrong] = useState(false);
  const router = useRouter();

  async function submit() {
    const res = await fetch("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pin }),
    });
    if (res.ok) {
      router.push("/");
      router.refresh();
    } else {
      setWrong(true);
      setPin("");
    }
  }

  function tap(k: string) {
    setWrong(false);
    if (k === "⌫") setPin((p) => p.slice(0, -1));
    else if (k) setPin((p) => (p.length < 8 ? p + k : p));
  }

  return (
    <main className="flex h-dvh flex-col items-center justify-center gap-6">
      <h1 className="text-3xl font-bold">Mesa</h1>
      <div className="h-10 text-3xl tracking-widest">{pin.replace(/./g, "•")}</div>
      {wrong && <p className="text-rose-600">Wrong PIN</p>}
      <div className="grid grid-cols-3 gap-3">
        {KEYS.map((k, i) => (
          <button
            key={i}
            onClick={() => tap(k)}
            disabled={!k}
            className="h-16 w-20 rounded-xl bg-gray-200 text-2xl font-semibold disabled:opacity-0"
          >
            {k}
          </button>
        ))}
      </div>
      <button
        onClick={submit}
        disabled={!pin}
        className="h-14 w-64 rounded-xl bg-gray-900 text-xl font-semibold text-white disabled:opacity-40"
      >
        Enter
      </button>
    </main>
  );
}
```

- [ ] **Step 8: Manual verification**

Set `MESA_PIN` and `MESA_COOKIE_SECRET` in `.env.local`. Run `npm run dev`:
- `curl -i localhost:3000/api/catalog` → 401 JSON.
- Browser `localhost:3000/` → redirected to `/login`; wrong PIN → "Wrong PIN"; correct PIN → back on `/` and `/api/catalog` loads.

- [ ] **Step 9: Commit**

```bash
git add lib middleware.ts app && git commit -m "feat: shared-PIN auth with signed session cookie"
```

---

### Task 9: Cart logic (pure functions)

**Files:**
- Create: `lib/cart.ts`
- Test: `lib/cart.test.ts`

**Interfaces:**
- Consumes: nothing.
- Produces: `interface CartLine { productId: number; name: string; unitPrice: number; qty: number }`; `addItem(lines: CartLine[], p: { id: number; name: string; price: number }): CartLine[]` (a `CatalogProduct` is structurally accepted); `changeQty(lines, productId, delta): CartLine[]` (removes at qty ≤ 0); `cartTotal(lines): number`; `computeChange(total, received): number`; `round2(n): number`.

- [ ] **Step 1: Write the failing tests** — `lib/cart.test.ts`

```ts
import { expect, it } from "vitest";
import { addItem, cartTotal, changeQty, computeChange } from "./cart";

const coffee = { id: 1, name: "Coffee", price: 1.2 };
const cake = { id: 2, name: "Cake", price: 3.5 };

it("adds a new line, then increments the same product", () => {
  let lines = addItem([], coffee);
  lines = addItem(lines, coffee);
  lines = addItem(lines, cake);
  expect(lines).toEqual([
    { productId: 1, name: "Coffee", unitPrice: 1.2, qty: 2 },
    { productId: 2, name: "Cake", unitPrice: 3.5, qty: 1 },
  ]);
});

it("changeQty adjusts and removes lines at zero", () => {
  let lines = addItem([], coffee);
  lines = changeQty(lines, 1, +1);
  expect(lines[0].qty).toBe(2);
  lines = changeQty(lines, 1, -1);
  lines = changeQty(lines, 1, -1);
  expect(lines).toEqual([]);
});

it("totals avoid floating point dust", () => {
  const lines = [
    { productId: 1, name: "A", unitPrice: 0.1, qty: 1 },
    { productId: 2, name: "B", unitPrice: 0.2, qty: 1 },
  ];
  expect(cartTotal(lines)).toBe(0.3);
});

it("computes change", () => {
  expect(computeChange(2.4, 5)).toBe(2.6);
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npx vitest run lib/cart.test.ts` — expect: FAIL (module not found).

- [ ] **Step 3: Implement `lib/cart.ts`**

```ts
export interface CartLine {
  productId: number;
  name: string;
  unitPrice: number;
  qty: number;
}

export const round2 = (n: number) => Math.round(n * 100) / 100;

export function addItem(
  lines: CartLine[],
  p: { id: number; name: string; price: number },
): CartLine[] {
  const existing = lines.find((l) => l.productId === p.id);
  if (!existing) return [...lines, { productId: p.id, name: p.name, unitPrice: p.price, qty: 1 }];
  return lines.map((l) => (l.productId === p.id ? { ...l, qty: l.qty + 1 } : l));
}

export function changeQty(lines: CartLine[], productId: number, delta: number): CartLine[] {
  return lines
    .map((l) => (l.productId === productId ? { ...l, qty: l.qty + delta } : l))
    .filter((l) => l.qty > 0);
}

export const cartTotal = (lines: CartLine[]) =>
  round2(lines.reduce((s, l) => s + l.unitPrice * l.qty, 0));

export const computeChange = (total: number, received: number) => round2(received - total);
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `npx vitest run lib/cart.test.ts` — expect: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add lib && git commit -m "feat: pure cart functions"
```

---

### Task 10: Catalog hook + ProductGrid + CartPanel components

**Files:**
- Create: `lib/useCatalog.ts`, `components/ProductGrid.tsx`, `components/CartPanel.tsx`
- Test: `components/ProductGrid.test.tsx`, `components/CartPanel.test.tsx`

**Interfaces:**
- Consumes: `Catalog`, `CatalogProduct` (type-only imports from `@/lib/server/catalog` — safe in client components), `CartLine`, `cartTotal` (Task 9).
- Produces:
  - `useCatalog(): { catalog: Catalog | null; error: boolean; loading: boolean; reload: (fresh?: boolean) => void }` — initial fetch of `/api/catalog`, silent background refresh every 5 min, `reload(true)` hits `?fresh=1`.
  - `<ProductGrid catalog activeCategoryId onSelectCategory onTapProduct />` with `activeCategoryId: number | "all"`.
  - `<CartPanel lines onInc onDec onCharge />` — Charge disabled when empty; `onInc`/`onDec` receive a `productId`.

- [ ] **Step 1: Write the failing tests** — `components/ProductGrid.test.tsx`

```tsx
// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ProductGrid } from "./ProductGrid";
import type { Catalog } from "@/lib/server/catalog";

afterEach(cleanup);

const catalog: Catalog = {
  categories: [
    { id: 10, name: "Drinks" },
    { id: 20, name: "Food" },
  ],
  products: [
    { id: 1, name: "Coffee", price: 1.2, categoryId: 10 },
    { id: 2, name: "Cake", price: 3.5, categoryId: 20 },
  ],
  taxes: [],
};

it("shows all products and fires onTapProduct", () => {
  const onTap = vi.fn();
  render(
    <ProductGrid catalog={catalog} activeCategoryId="all" onSelectCategory={vi.fn()} onTapProduct={onTap} />,
  );
  fireEvent.click(screen.getByText("Coffee"));
  expect(onTap).toHaveBeenCalledWith(catalog.products[0]);
});

it("filters by active category and fires onSelectCategory", () => {
  const onSelect = vi.fn();
  render(
    <ProductGrid catalog={catalog} activeCategoryId={20} onSelectCategory={onSelect} onTapProduct={vi.fn()} />,
  );
  expect(screen.queryByText("Coffee")).toBeNull();
  screen.getByText("Cake");
  fireEvent.click(screen.getByText("Drinks"));
  expect(onSelect).toHaveBeenCalledWith(10);
});
```

And `components/CartPanel.test.tsx`:

```tsx
// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { CartPanel } from "./CartPanel";

afterEach(cleanup);

it("disables Charge when empty and fires callbacks", () => {
  const onCharge = vi.fn();
  const { rerender } = render(<CartPanel lines={[]} onInc={vi.fn()} onDec={vi.fn()} onCharge={onCharge} />);
  const btn = screen.getByText("Charge") as HTMLButtonElement;
  expect(btn.disabled).toBe(true);

  const onInc = vi.fn();
  rerender(
    <CartPanel
      lines={[{ productId: 1, name: "Coffee", unitPrice: 1.2, qty: 2 }]}
      onInc={onInc}
      onDec={vi.fn()}
      onCharge={onCharge}
    />,
  );
  expect(screen.getAllByText("2.40 €").length).toBeGreaterThan(0);
  fireEvent.click(screen.getByLabelText("increase Coffee"));
  expect(onInc).toHaveBeenCalledWith(1);
  fireEvent.click(btn);
  expect(onCharge).toHaveBeenCalled();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npx vitest run components` — expect: FAIL (modules not found).

- [ ] **Step 3: Implement `lib/useCatalog.ts`**

```ts
"use client";
import { useCallback, useEffect, useState } from "react";
import type { Catalog } from "@/lib/server/catalog";

async function fetchCatalog(fresh: boolean): Promise<Catalog> {
  const res = await fetch("/api/catalog" + (fresh ? "?fresh=1" : ""));
  if (!res.ok) throw new Error("catalog fetch failed");
  return res.json();
}

export function useCatalog() {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(true);

  const reload = useCallback((fresh = false) => {
    setError(false);
    setLoading(true);
    fetchCatalog(fresh)
      .then(setCatalog)
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    reload();
    const t = setInterval(() => fetchCatalog(false).then(setCatalog).catch(() => {}), 5 * 60_000);
    return () => clearInterval(t);
  }, [reload]);

  return { catalog, error, loading, reload };
}
```

- [ ] **Step 4: Implement `components/ProductGrid.tsx`**

```tsx
"use client";
import type { Catalog, CatalogProduct } from "@/lib/server/catalog";

const CATEGORY_COLORS = [
  "bg-amber-200", "bg-sky-200", "bg-emerald-200", "bg-rose-200",
  "bg-violet-200", "bg-lime-200", "bg-orange-200", "bg-cyan-200",
];

interface Props {
  catalog: Catalog;
  activeCategoryId: number | "all";
  onSelectCategory: (id: number | "all") => void;
  onTapProduct: (p: CatalogProduct) => void;
}

export function ProductGrid({ catalog, activeCategoryId, onSelectCategory, onTapProduct }: Props) {
  const colorOf = (categoryId: number | null) => {
    const idx = catalog.categories.findIndex((c) => c.id === categoryId);
    return idx === -1 ? "bg-gray-200" : CATEGORY_COLORS[idx % CATEGORY_COLORS.length];
  };
  const visible =
    activeCategoryId === "all"
      ? catalog.products
      : catalog.products.filter((p) => p.categoryId === activeCategoryId);

  return (
    <div className="flex h-full flex-col">
      <div className="flex gap-2 overflow-x-auto p-2">
        {[{ id: "all" as const, name: "All" }, ...catalog.categories].map((c) => (
          <button
            key={c.id}
            onClick={() => onSelectCategory(c.id)}
            className={`min-h-12 shrink-0 rounded-lg px-5 text-lg font-semibold ${
              activeCategoryId === c.id ? "bg-gray-900 text-white" : "bg-gray-200"
            }`}
          >
            {c.name}
          </button>
        ))}
      </div>
      <div className="grid flex-1 auto-rows-min grid-cols-4 gap-2 overflow-y-auto p-2">
        {visible.map((p) => (
          <button
            key={p.id}
            onClick={() => onTapProduct(p)}
            className={`min-h-28 rounded-xl p-2 text-left shadow ${colorOf(p.categoryId)}`}
          >
            <div className="text-lg font-semibold leading-tight">{p.name}</div>
            <div className="mt-1 text-base">{p.price.toFixed(2)} €</div>
          </button>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Implement `components/CartPanel.tsx`**

```tsx
"use client";
import type { CartLine } from "@/lib/cart";
import { cartTotal } from "@/lib/cart";

interface Props {
  lines: CartLine[];
  onInc: (productId: number) => void;
  onDec: (productId: number) => void;
  onCharge: () => void;
}

export function CartPanel({ lines, onInc, onDec, onCharge }: Props) {
  const total = cartTotal(lines);
  return (
    <div className="flex h-full flex-col border-l bg-white">
      <div className="flex-1 overflow-y-auto">
        {lines.length === 0 && <p className="p-4 text-gray-500">Cart is empty</p>}
        {lines.map((l) => (
          <div key={l.productId} className="flex items-center gap-2 border-b p-3">
            <div className="flex-1">
              <div className="font-medium">{l.name}</div>
              <div className="text-sm text-gray-600">{(l.unitPrice * l.qty).toFixed(2)} €</div>
            </div>
            <button
              aria-label={`decrease ${l.name}`}
              onClick={() => onDec(l.productId)}
              className="h-12 w-12 rounded-lg bg-gray-200 text-xl"
            >
              −
            </button>
            <span className="w-8 text-center text-lg">{l.qty}</span>
            <button
              aria-label={`increase ${l.name}`}
              onClick={() => onInc(l.productId)}
              className="h-12 w-12 rounded-lg bg-gray-200 text-xl"
            >
              +
            </button>
          </div>
        ))}
      </div>
      <div className="border-t p-4">
        <div className="mb-3 flex justify-between text-2xl font-bold">
          <span>Total</span>
          <span>{total.toFixed(2)} €</span>
        </div>
        <button
          onClick={onCharge}
          disabled={lines.length === 0}
          className="h-16 w-full rounded-xl bg-gray-900 text-2xl font-semibold text-white disabled:opacity-40"
        >
          Charge
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `npx vitest run components` — expect: 3 PASS.

- [ ] **Step 7: Commit**

```bash
git add lib components && git commit -m "feat: catalog hook, product grid and cart panel components"
```

---

### Task 11: POS page state machine + payment, confirmation and check screens

**Files:**
- Create: `components/PaymentPanel.tsx`, `components/ConfirmationScreen.tsx`, `components/CheckRecentScreen.tsx`
- Modify: `app/page.tsx` (replace boilerplate), `app/layout.tsx` (title "Mesa"), `app/globals.css` (keep only the Tailwind import — drop the dark-mode body styling)
- Test: `app/pos-page.test.tsx`

**Interfaces:**
- Consumes: everything from Tasks 7, 9, 10 — `CheckoutResult` (type-only), `addItem`, `changeQty`, `cartTotal`, `computeChange`, `useCatalog`, `ProductGrid`, `CartPanel`.
- Produces:
  - `<PaymentPanel total onPay onCancel />` with `onPay(payment: "NU" | "CC" | "MBWAY", amountReceived?: number)`.
  - `<ConfirmationScreen result onDone />`, `<CheckRecentScreen onResolved onBack />`.
  - `app/page.tsx` — view states `sale | payment | submitting | confirm | check | configError`; single-flight guard via a ref.
- Error mapping in the page (from the spec's error matrix):
  - HTTP ok → confirm screen, cart cleared.
  - body kind `possibly_created` **or the fetch itself throws** (our server may have called Vendus) → check screen.
  - kind `auth` → blocking configError screen.
  - kind `validation` → back to sale, cart intact, banner "Rejected by Vendus — nothing was charged. <messages>".
  - anything else → back to sale, banner "Nothing was charged — check connection and retry."

- [ ] **Step 1: Write the failing tests** — `app/pos-page.test.tsx`

```tsx
// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import PosPage from "./page";

const catalogBody = {
  categories: [{ id: 10, name: "Drinks" }],
  products: [{ id: 1, name: "Coffee", price: 1.2, categoryId: 10 }],
  taxes: [],
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function stubFetch(onCheckout: () => Promise<Response>) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: unknown) => {
      const u = String(url);
      if (u.startsWith("/api/catalog"))
        return new Response(JSON.stringify(catalogBody), { status: 200 });
      if (u === "/api/checkout") return onCheckout();
      throw new Error("unexpected fetch " + u);
    }),
  );
}

it("charges once even on a double tap", async () => {
  let checkoutCalls = 0;
  stubFetch(() => {
    checkoutCalls++;
    return new Promise<Response>(() => {}); // stays in flight
  });
  render(<PosPage />);
  fireEvent.click(await screen.findByText("Coffee"));
  fireEvent.click(screen.getByText("Charge"));
  const card = screen.getByText("Card");
  fireEvent.click(card);
  fireEvent.click(card);
  await waitFor(() => expect(checkoutCalls).toBe(1));
});

it("shows the confirmation screen after a successful charge", async () => {
  stubFetch(async () =>
    new Response(
      JSON.stringify({ number: "FS T1/9", atcud: "AB-9", qrData: null, total: 1.2 }),
      { status: 200 },
    ),
  );
  render(<PosPage />);
  fireEvent.click(await screen.findByText("Coffee"));
  fireEvent.click(screen.getByText("Charge"));
  fireEvent.click(screen.getByText("Card"));
  await screen.findByText("New sale");
  screen.getByText("FS T1/9");
});

it("returns to the sale with a banner when Vendus rejects the sale", async () => {
  stubFetch(async () =>
    new Response(
      JSON.stringify({ error: { kind: "validation", messages: ["A001: Bad tax"] } }),
      { status: 422 },
    ),
  );
  render(<PosPage />);
  fireEvent.click(await screen.findByText("Coffee"));
  fireEvent.click(screen.getByText("Charge"));
  fireEvent.click(screen.getByText("Card"));
  await screen.findByText(/nothing was charged/i);
  screen.getByText("Charge"); // cart intact
  screen.getByText("Coffee");
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npx vitest run app/pos-page.test.tsx` — expect: FAIL (components not found / boilerplate page).

- [ ] **Step 3: Implement `components/PaymentPanel.tsx`**

```tsx
"use client";
import { useState } from "react";
import { computeChange } from "@/lib/cart";

interface Props {
  total: number;
  onPay: (payment: "NU" | "CC" | "MBWAY", amountReceived?: number) => void;
  onCancel: () => void;
}

export function PaymentPanel({ total, onPay, onCancel }: Props) {
  const [cashMode, setCashMode] = useState(false);
  const [received, setReceived] = useState("");
  const receivedNum = Number(received.replace(",", "."));
  const change = received && Number.isFinite(receivedNum) ? computeChange(total, receivedNum) : null;

  return (
    <div className="flex h-full w-full flex-col items-center justify-center gap-4 p-6">
      <div className="text-4xl font-bold">{total.toFixed(2)} €</div>
      {!cashMode ? (
        <>
          <button onClick={() => setCashMode(true)} className="h-20 w-72 rounded-xl bg-emerald-600 text-2xl font-semibold text-white">
            Cash
          </button>
          <button onClick={() => onPay("CC")} className="h-20 w-72 rounded-xl bg-sky-600 text-2xl font-semibold text-white">
            Card
          </button>
          <button onClick={() => onPay("MBWAY")} className="h-20 w-72 rounded-xl bg-rose-600 text-2xl font-semibold text-white">
            MB WAY
          </button>
        </>
      ) : (
        <>
          <input
            inputMode="decimal"
            placeholder="Amount received (optional)"
            value={received}
            onChange={(e) => setReceived(e.target.value)}
            className="h-14 w-72 rounded-lg border px-4 text-center text-xl"
          />
          {change !== null && change >= 0 && <div className="text-xl">Change: {change.toFixed(2)} €</div>}
          {change !== null && change < 0 && <div className="text-xl text-rose-600">Amount is below total</div>}
          <button
            onClick={() => onPay("NU", received && change !== null && change >= 0 ? receivedNum : undefined)}
            disabled={change !== null && change < 0}
            className="h-20 w-72 rounded-xl bg-emerald-600 text-2xl font-semibold text-white disabled:opacity-40"
          >
            Charge cash
          </button>
        </>
      )}
      <button onClick={onCancel} className="mt-4 h-12 w-72 rounded-lg bg-gray-200 text-lg">
        Back
      </button>
    </div>
  );
}
```

- [ ] **Step 4: Implement `components/ConfirmationScreen.tsx`**

```tsx
"use client";
import { QRCodeSVG } from "qrcode.react";
import type { CheckoutResult } from "@/lib/server/checkout";

export function ConfirmationScreen({ result, onDone }: { result: CheckoutResult; onDone: () => void }) {
  return (
    <div className="flex h-full w-full flex-col items-center justify-center gap-4 p-6 text-center">
      <div className="text-5xl font-bold text-emerald-600">{result.total.toFixed(2)} €</div>
      {result.change !== undefined && <div className="text-2xl">Change: {result.change.toFixed(2)} €</div>}
      <div className="text-lg text-gray-700">{result.number}</div>
      {result.atcud && <div className="text-sm text-gray-500">ATCUD: {result.atcud}</div>}
      {result.qrData && <QRCodeSVG value={result.qrData} size={180} />}
      <button onClick={onDone} className="mt-6 h-16 w-72 rounded-xl bg-gray-900 text-2xl font-semibold text-white">
        New sale
      </button>
    </div>
  );
}
```

- [ ] **Step 5: Implement `components/CheckRecentScreen.tsx`**

```tsx
"use client";
import { useEffect, useState } from "react";

interface RecentDoc {
  id: number;
  number: string;
  total: number | null;
  time: string;
}

export function CheckRecentScreen({ onResolved, onBack }: { onResolved: () => void; onBack: () => void }) {
  const [docs, setDocs] = useState<RecentDoc[] | null>(null);
  const [error, setError] = useState(false);

  const load = () => {
    setError(false);
    setDocs(null);
    fetch("/api/checkout/recent")
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then(setDocs)
      .catch(() => setError(true));
  };
  useEffect(load, []);

  return (
    <div className="flex h-full w-full flex-col items-center justify-center gap-4 p-6">
      <h2 className="text-2xl font-bold">The sale may have been recorded</h2>
      <p className="text-gray-600">Documents from the last 5 minutes:</p>
      {error && (
        <button onClick={load} className="h-12 rounded-lg bg-gray-200 px-6">
          Retry
        </button>
      )}
      {docs === null && !error && <p>Loading…</p>}
      {docs && docs.length === 0 && <p className="text-gray-500">No recent documents found.</p>}
      {docs &&
        docs.map((d) => (
          <div key={d.id} className="flex w-96 justify-between rounded-lg border p-3 text-lg">
            <span>{d.number}</span>
            <span>{d.total !== null ? `${d.total.toFixed(2)} €` : "—"}</span>
          </div>
        ))}
      <div className="mt-4 flex gap-4">
        <button onClick={onResolved} className="h-16 rounded-xl bg-emerald-600 px-8 text-xl font-semibold text-white">
          It&apos;s there — done
        </button>
        <button onClick={onBack} className="h-16 rounded-xl bg-rose-600 px-8 text-xl font-semibold text-white">
          It&apos;s not — back to cart
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 6: Implement `app/page.tsx`**

```tsx
"use client";
import { useRef, useState } from "react";
import { useCatalog } from "@/lib/useCatalog";
import { addItem, cartTotal, changeQty, type CartLine } from "@/lib/cart";
import { ProductGrid } from "@/components/ProductGrid";
import { CartPanel } from "@/components/CartPanel";
import { PaymentPanel } from "@/components/PaymentPanel";
import { ConfirmationScreen } from "@/components/ConfirmationScreen";
import { CheckRecentScreen } from "@/components/CheckRecentScreen";
import type { CheckoutResult } from "@/lib/server/checkout";

type View =
  | { kind: "sale" }
  | { kind: "payment" }
  | { kind: "submitting" }
  | { kind: "confirm"; result: CheckoutResult }
  | { kind: "check" }
  | { kind: "configError"; messages: string[] };

export default function PosPage() {
  const { catalog, error, loading, reload } = useCatalog();
  const [lines, setLines] = useState<CartLine[]>([]);
  const [activeCategoryId, setActiveCategoryId] = useState<number | "all">("all");
  const [view, setView] = useState<View>({ kind: "sale" });
  const [banner, setBanner] = useState<string | null>(null);
  const inFlight = useRef(false);

  async function pay(payment: "NU" | "CC" | "MBWAY", amountReceived?: number) {
    if (inFlight.current) return;
    inFlight.current = true;
    setBanner(null);
    setView({ kind: "submitting" });
    let res: Response;
    try {
      res = await fetch("/api/checkout", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          items: lines.map((l) => ({ productId: l.productId, qty: l.qty })),
          payment,
          ...(amountReceived !== undefined ? { amountReceived } : {}),
        }),
      });
    } catch {
      // The request to our server was lost: Vendus may still have been called.
      inFlight.current = false;
      setView({ kind: "check" });
      return;
    }
    inFlight.current = false;
    if (res.ok) {
      const result: CheckoutResult = await res.json();
      setLines([]);
      setView({ kind: "confirm", result });
      return;
    }
    const body = await res.json().catch(() => null);
    const kind = body?.error?.kind as string | undefined;
    const messages: string[] = body?.error?.messages ?? [];
    if (kind === "possibly_created") {
      setView({ kind: "check" });
      return;
    }
    if (kind === "auth") {
      setView({ kind: "configError", messages });
      return;
    }
    setView({ kind: "sale" });
    setBanner(
      kind === "validation"
        ? `Rejected by Vendus — nothing was charged. ${messages.join(" ")}`
        : "Nothing was charged — check connection and retry.",
    );
  }

  if (loading)
    return <main className="flex h-dvh items-center justify-center text-xl">Loading catalog…</main>;
  if (error || !catalog)
    return (
      <main className="flex h-dvh flex-col items-center justify-center gap-4">
        <p className="text-xl">Could not load the catalog.</p>
        <button onClick={() => reload()} className="h-14 rounded-xl bg-gray-900 px-8 text-xl text-white">
          Retry
        </button>
      </main>
    );

  return (
    <main className="relative flex h-dvh">
      {view.kind === "confirm" ? (
        <ConfirmationScreen result={view.result} onDone={() => setView({ kind: "sale" })} />
      ) : view.kind === "check" ? (
        <CheckRecentScreen
          onResolved={() => {
            setLines([]);
            setView({ kind: "sale" });
          }}
          onBack={() => setView({ kind: "sale" })}
        />
      ) : view.kind === "configError" ? (
        <div className="flex h-full w-full flex-col items-center justify-center gap-3 p-6 text-center">
          <h2 className="text-2xl font-bold text-rose-600">Configuration error</h2>
          <p className="text-gray-600">{view.messages.join(" ") || "Check the server environment variables."}</p>
        </div>
      ) : view.kind === "payment" || view.kind === "submitting" ? (
        <div className="relative h-full w-full">
          <PaymentPanel total={cartTotal(lines)} onPay={pay} onCancel={() => setView({ kind: "sale" })} />
          {view.kind === "submitting" && (
            <div className="absolute inset-0 flex items-center justify-center bg-white/70 text-2xl font-semibold">
              Charging…
            </div>
          )}
        </div>
      ) : (
        <>
          <div className="h-full flex-[2]">
            <ProductGrid
              catalog={catalog}
              activeCategoryId={activeCategoryId}
              onSelectCategory={setActiveCategoryId}
              onTapProduct={(p) => setLines((ls) => addItem(ls, p))}
            />
          </div>
          <div className="h-full flex-1">
            <CartPanel
              lines={lines}
              onInc={(id) => setLines((ls) => changeQty(ls, id, +1))}
              onDec={(id) => setLines((ls) => changeQty(ls, id, -1))}
              onCharge={() => setView({ kind: "payment" })}
            />
          </div>
          <button
            onClick={() => reload(true)}
            aria-label="Refresh catalog"
            className="absolute bottom-2 left-2 rounded-full bg-gray-200 px-3 py-2 text-sm"
          >
            ⟳
          </button>
        </>
      )}
      {banner && (
        <div className="absolute inset-x-0 top-0 bg-rose-600 p-3 text-center text-white" role="alert">
          {banner}
          <button onClick={() => setBanner(null)} className="ml-4 underline">
            Dismiss
          </button>
        </div>
      )}
    </main>
  );
}
```

- [ ] **Step 7: Clean the shell**

- `app/globals.css`: replace the whole content with `@import "tailwindcss";`
- `app/layout.tsx`: set `metadata` to `{ title: "Mesa", description: "Point of sale" }`; leave the rest of the boilerplate layout as-is.

- [ ] **Step 8: Run tests to verify they pass**

Run: `npx vitest run app/pos-page.test.tsx` — expect: 3 PASS. Then `npm test` — all suites PASS.

- [ ] **Step 9: Build + manual smoke**

Run: `npm run build` — expect: success, no type errors. Then `npm run dev`: log in, tap products, charge with Card → confirmation with number/ATCUD/QR (real FS on the test account).

- [ ] **Step 10: Commit**

```bash
git add app components lib && git commit -m "feat: POS page — payment, confirmation and possibly-created check flows"
```

---

### Task 12: README, manual tablet checklist, Vercel deploy

**Files:**
- Create: `README.md`
- Modify: nothing else

**Interfaces:**
- Consumes: everything; `docs/spike-findings.md` (Task 5).
- Produces: documented repo + deployed prototype.

- [ ] **Step 1: Write `README.md`**

```markdown
# Mesa — POS layer on Vendus (Phase 1)

Tablet point-of-sale UI on top of the Vendus API (fiscal engine: certified
documents, ATCUD, QR, series). Phase 1 = sale engine prototype, validated
against a dedicated Vendus TEST account. Spec and plan live in the ESTUSHOP
repo under `docs/superpowers/`.

## Setup

1. `npm install`
2. `cp .env.local.example .env.local` and fill:
   - `VENDUS_API_KEY` — TEST account only, never Estudantina production
   - `VENDUS_REGISTER_ID`, `VENDUS_PM_CASH_ID`, `VENDUS_PM_CARD_ID`,
     `VENDUS_PM_MBWAY_ID` — from `npx tsx scripts/spike.ts --discover`
   - `MESA_PIN`, `MESA_COOKIE_SECRET` — POS access
3. `npm run dev`

## Fiscal spike (go/no-go, also a permanent smoke test)

- `npx tsx scripts/spike.ts --discover` — list registers & payment methods
- `npx tsx scripts/spike.ts` — full run: creates a test product, a 0.10 € FS,
  checks series/ATCUD/QR, cancels it with an NC, prints a GO/NO-GO table.
  Creates real documents on the TEST account.
- Findings (series behaviour, field names): see `docs/spike-findings.md`.

## Tests

`npm test` — vitest. Zod schemas are also validated against real responses
recorded by the spike in `test/fixtures/`.

## Manual tablet checklist (end of Phase 1)

- [ ] Login: wrong PIN rejected, correct PIN opens the grid; PIN not asked again after reload
- [ ] Cash sale with change: amount received larger than total shows correct change; confirmation shows number + ATCUD + QR
- [ ] Card sale: 2 taps from cart; confirmation OK
- [ ] Double-tap on a payment button: only one document created (check Vendus backoffice)
- [ ] Airplane mode just before charging: "The sale may have been recorded" screen appears; both outcomes work
- [ ] Airplane mode while browsing: catalog error screen + Retry works
- [ ] Price changed in Vendus backoffice: sale total follows Vendus, not the stale tile (within 60 s or after ⟳)
- [ ] Empty cart: Charge disabled
- [ ] Landscape tablet: no horizontal scroll, touch targets comfortable
```

- [ ] **Step 2: Full check**

Run: `npm test` then `npm run build` — expect: all PASS, build clean.

- [ ] **Step 3: Commit**

```bash
git add README.md && git commit -m "docs: readme with setup, spike usage and tablet checklist"
```

- [ ] **Step 4: Deploy to Vercel**

Create a GitHub repo and push, then either import it in the Vercel dashboard or:

```bash
npx vercel link
# add each env var (values from .env.local):
npx vercel env add VENDUS_API_KEY production
npx vercel env add VENDUS_REGISTER_ID production
npx vercel env add VENDUS_PM_CASH_ID production
npx vercel env add VENDUS_PM_CARD_ID production
npx vercel env add VENDUS_PM_MBWAY_ID production
npx vercel env add MESA_PIN production
npx vercel env add MESA_COOKIE_SECRET production
npx vercel --prod
```

- [ ] **Step 5: Verify deployed**

Open the production URL on the tablet: login → grid → one Card sale → confirmation. Then run the manual tablet checklist from the README and report results to the user.

---

## Plan Self-Review Notes

- **Spec coverage:** typed client + asymmetric retry (T2), pagination/Zod-lenient reads (T3), FS/NC builders + recent docs (T4), spike gate with fixtures + findings doc (T5), 60 s cache + `fresh=1` (T6), server-side prices/change + error matrix statuses (T7), PIN + 30-day signed cookie + edge-safe crypto (T8), pure cart functions (T9), tablet grid/cart (T10), 2-tap checkout + submit lock + confirmation QR + possibly-created check screen + banners + config-error screen + refresh button (T11), manual checklist + deploy (T12). No Playwright (per spec).
- **Known best-guesses validated by the spike (T5):** `payments: [{ id }]` shape, NC `related_document_id` linkage, ATCUD/QR response field names. Each has a concrete adjustment path (schema + payload builders + their tests).
- **Client-side fetch failure during checkout maps to the check screen** (not "nothing was charged") — deliberate deviation refining the spec's error matrix: the tablet→server leg is as ambiguous as the server→Vendus leg.

