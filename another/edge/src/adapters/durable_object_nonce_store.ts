import type { NonceStorePort } from "../ports/nonce_store_port.js";

const NONCE_TTL_MS = 60_000; // 60с, как в §4 спецификации

interface NonceEntry {
  expiresAt: number;
  consumed: boolean;
}

/**
 * NonceLedgerObject — сам Durable Object (см. wrangler.toml:
 * `[[durable_objects.bindings]]`). Экспортируется из index.ts, чтобы
 * рантайм Workers мог найти класс по имени.
 *
 * Строгая консистентность Durable Objects (единственный "владелец" объекта,
 * все операции сериализуются) — то, чего не давал Cache API из исходного
 * черновика (см. docs/adr в архитектурной спецификации, правка #2).
 * Состояние хранится в `this.state.storage` (переживает рестарт/эвикцию
 * самого объекта рантаймом Cloudflare), но т.к. TTL nonce — всего 60с, это
 * скорее подстраховка, чем критичное требование.
 */
export class NonceLedgerObject implements DurableObject {
  constructor(
    private readonly state: DurableObjectState,
    private readonly env: unknown,
  ) {}

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === "/issue" && request.method === "GET") {
      return this.handleIssue();
    }
    if (url.pathname === "/consume" && request.method === "POST") {
      const body = (await request.json()) as { nonce?: string };
      if (!body.nonce) {
        return new Response("missing nonce", { status: 400 });
      }
      return this.handleConsume(body.nonce);
    }
    return new Response("not found", { status: 404 });
  }

  private async handleIssue(): Promise<Response> {
    await this.purgeExpired();

    const nonce = bytesToHex(crypto.getRandomValues(new Uint8Array(16)));
    const entry: NonceEntry = { expiresAt: Date.now() + NONCE_TTL_MS, consumed: false };
    await this.state.storage.put(nonceKey(nonce), entry);

    return Response.json({ nonce });
  }

  private async handleConsume(nonce: string): Promise<Response> {
    const key = nonceKey(nonce);
    const entry = await this.state.storage.get<NonceEntry>(key);

    if (!entry || entry.expiresAt < Date.now() || entry.consumed) {
      return Response.json({ ok: false });
    }

    entry.consumed = true;
    await this.state.storage.put(key, entry);
    return Response.json({ ok: true });
  }

  /**
   * purgeExpired — простая уборка устаревших записей при каждой выдаче
   * nonce, чтобы storage не рос неограниченно. Для масштаба "закрытая
   * группа пользователей" (§1, §17 спецификации) частоты issue вполне
   * достаточно для поддержания объёма хранилища в разумных пределах;
   * при большем масштабе стоит вынести это в alarm() (Durable Objects
   * Alarms API), а не делать на каждый issue.
   */
  private async purgeExpired(): Promise<void> {
    const now = Date.now();
    const all = await this.state.storage.list<NonceEntry>({ prefix: "nonce:" });
    const expiredKeys: string[] = [];
    for (const [key, entry] of all) {
      if (entry.expiresAt < now) {
        expiredKeys.push(key);
      }
    }
    if (expiredKeys.length > 0) {
      await this.state.storage.delete(expiredKeys);
    }
  }
}

function nonceKey(nonce: string): string {
  return `nonce:${nonce}`;
}

function bytesToHex(bytes: Uint8Array): string {
  return Array.from(bytes)
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

/**
 * DurableObjectNonceStore — адаптер NonceStorePort со стороны основного
 * fetch-обработчика Worker'а. Всегда обращается к ОДНОМУ глобальному
 * экземпляру Durable Object (`idFromName("global")`) — это осознанное
 * упрощение для масштаба "закрытая группа" (см. ADR-2 в архитектурной
 * спецификации): один объект сериализует все операции, что и даёт строгую
 * консистентность. При росте масштаба до сотен/тысяч устройств стоит
 * шардировать по client_id (`idFromName(clientId)`), жертвуя глобальной
 * атомарностью ради параллелизма — но для целевого масштаба системы это
 * не требуется.
 */
export class DurableObjectNonceStore implements NonceStorePort {
  constructor(private readonly namespace: DurableObjectNamespace) {}

  private stub(): DurableObjectStub {
    const id = this.namespace.idFromName("global");
    return this.namespace.get(id);
  }

  async issueNonce(): Promise<string> {
    const res = await this.stub().fetch("https://nonce-ledger.internal/issue");
    if (!res.ok) {
      throw new Error(`nonce ledger issue failed: ${res.status}`);
    }
    const body = (await res.json()) as { nonce: string };
    return body.nonce;
  }

  async consumeNonce(nonce: string): Promise<boolean> {
    const res = await this.stub().fetch("https://nonce-ledger.internal/consume", {
      method: "POST",
      body: JSON.stringify({ nonce }),
      headers: { "Content-Type": "application/json" },
    });
    if (!res.ok) {
      return false;
    }
    const body = (await res.json()) as { ok: boolean };
    return body.ok;
  }
}
