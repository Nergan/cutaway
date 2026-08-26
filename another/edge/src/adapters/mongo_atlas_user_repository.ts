import type { ClientRecord, EnrollmentRecord, UserRepositoryPort } from "../ports/user_repository_port.js";

export interface MongoDataApiConfig {
  baseUrl: string; // MONGO_DATA_API_URL, см. .env.example
  apiKey: string; // MONGO_DATA_API_KEY
  dataSource: string; // имя кластера в Atlas (обычно совпадает с именем проекта)
  database: string; // MONGO_DB_NAME
}

/**
 * MongoAtlasUserRepository — v1 ходила в Atlas Data API.
 *
 * Data API / App Services достигли EOL 30 сентября 2025. Этот адаптер в
 * реальном деплое больше не к чему подключиться. Замена — HTTPS-клиент к
 * нашему REST-прокси на HF/Render (нативный драйвер по MONGO_URI), см.
 * docs/adr/0005-mongo-rest-proxy.md. Пока прокси нет, /enroll и /auth в
 * проде не читают базу. Код оставлен как контракт порта, не как рабочий прод.
 */
export class MongoAtlasUserRepository implements UserRepositoryPort {
  constructor(private readonly cfg: MongoDataApiConfig) {}

  private async callAction<T>(action: string, body: Record<string, unknown>): Promise<T> {
    const res = await fetch(`${this.cfg.baseUrl}/action/${action}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "api-key": this.cfg.apiKey,
      },
      body: JSON.stringify({
        dataSource: this.cfg.dataSource,
        database: this.cfg.database,
        ...body,
      }),
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(`mongo data api ${action} failed: ${res.status} ${text}`);
    }
    return (await res.json()) as T;
  }

  async findClient(clientId: string): Promise<ClientRecord | null> {
    const result = await this.callAction<{ document: MongoUserDoc | null }>("findOne", {
      collection: "users",
      filter: { "clients.client_id": clientId },
      projection: { "clients.$": 1 },
    });

    const doc = result.document;
    const client = doc?.clients?.[0];
    if (!client) {
      return null;
    }

    return {
      clientId: client.client_id,
      publicKeyHex: client.public_key,
      vlessUserIdHex: client.vless_user_id,
      isBanned: client.is_banned,
      quotaLimitBytes: client.quota_limit_bytes,
      bytesUsed: client.bytes_used,
    };
  }

  async findEnrollmentByTokenHash(tokenHash: string): Promise<EnrollmentRecord | null> {
    const result = await this.callAction<{ document: MongoUserDoc | null }>("findOne", {
      collection: "users",
      filter: { "clients.enrollment_token_hash": tokenHash },
      projection: { "clients.$": 1 },
    });

    const client = result.document?.clients?.[0];
    if (!client || !client.enrollment_expires_at) {
      return null;
    }

    return {
      clientId: client.client_id,
      expiresAtUnixSeconds: Math.floor(new Date(client.enrollment_expires_at).getTime() / 1000),
    };
  }

  async bindDeviceIdentity(clientId: string, publicKeyHex: string, vlessUserIdHex: string): Promise<void> {
    await this.callAction("updateOne", {
      collection: "users",
      filter: { "clients.client_id": clientId },
      update: {
        $set: {
          "clients.$.public_key": publicKeyHex,
          "clients.$.vless_user_id": vlessUserIdHex,
          "clients.$.key_created_at": new Date().toISOString(),
        },
      },
    });
  }

  async consumeEnrollmentToken(tokenHash: string): Promise<void> {
    await this.callAction("updateOne", {
      collection: "users",
      filter: { "clients.enrollment_token_hash": tokenHash },
      update: {
        $set: { "clients.$.enrollment_token_hash": null, "clients.$.enrollment_expires_at": null },
      },
    });
  }

  async incrementUsage(clientId: string, bytesDelta: number): Promise<void> {
    await this.callAction("updateOne", {
      collection: "users",
      filter: { "clients.client_id": clientId },
      update: {
        $inc: { "clients.$.bytes_used": bytesDelta },
        $set: { "clients.$.last_activity": new Date().toISOString() },
      },
    });
  }
}

/** Форма документа так, как его возвращает Atlas Data API (snake_case поля схемы §10). */
interface MongoUserDoc {
  user_id: string;
  clients: Array<{
    client_id: string;
    public_key: string;
    vless_user_id: string;
    is_banned: boolean;
    quota_limit_bytes: number;
    bytes_used: number;
    enrollment_token_hash?: string | null;
    enrollment_expires_at?: string | null;
  }>;
}
