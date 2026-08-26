import type { ClientRecord, EnrollmentRecord, UserRepositoryPort } from "../ports/user_repository_port.js";

export interface RestProxyConfig {
  baseUrl: string;
  secret: string;
}

/**
 * RestProxyUserRepository — HTTPS-клиент к нашему origin API
 * (`/internal/v1/...` на HF/Render). Замена мёртвого Atlas Data API.
 * См. docs/adr/0005-mongo-rest-proxy.md.
 */
export class RestProxyUserRepository implements UserRepositoryPort {
  constructor(private readonly cfg: RestProxyConfig) {}

  private endpoint(path: string): string {
    return `${this.cfg.baseUrl.replace(/\/$/, "")}${path}`;
  }

  private async post<T>(path: string, body: Record<string, unknown>): Promise<{ status: number; json: T | null; text: string }> {
    const res = await fetch(this.endpoint(path), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Another-Proxy-Secret": this.cfg.secret,
      },
      body: JSON.stringify(body),
    });
    const text = await res.text();
    let json: T | null = null;
    if (text) {
      try {
        json = JSON.parse(text) as T;
      } catch {
        json = null;
      }
    }
    return { status: res.status, json, text };
  }

  async findClient(clientId: string): Promise<ClientRecord | null> {
    const { status, json } = await this.post<{
      client_id: string;
      public_key_hex: string | null;
      vless_user_id_hex: string | null;
      is_banned: boolean;
      quota_limit_bytes: number;
      bytes_used: number;
    }>("/internal/v1/clients/find", { client_id: clientId });
    if (status === 404) return null;
    if (status !== 200 || !json) {
      throw new Error(`mongo rest proxy findClient failed: ${status}`);
    }
    return {
      clientId: json.client_id,
      publicKeyHex: json.public_key_hex ?? "",
      vlessUserIdHex: json.vless_user_id_hex ?? "",
      isBanned: json.is_banned,
      quotaLimitBytes: json.quota_limit_bytes,
      bytesUsed: json.bytes_used,
    };
  }

  async findEnrollmentByTokenHash(tokenHash: string): Promise<EnrollmentRecord | null> {
    const { status, json } = await this.post<{
      client_id: string;
      expires_at_unix_seconds: number;
    }>("/internal/v1/enrollments/find", { token_hash: tokenHash });
    if (status === 404) return null;
    if (status !== 200 || !json) {
      throw new Error(`mongo rest proxy findEnrollment failed: ${status}`);
    }
    return {
      clientId: json.client_id,
      expiresAtUnixSeconds: json.expires_at_unix_seconds,
    };
  }

  async bindDeviceIdentity(
    clientId: string,
    publicKeyHex: string,
    vlessUserIdHex: string,
    publicKeyMldsaHex?: string,
  ): Promise<void> {
    const { status } = await this.post("/internal/v1/clients/bind", {
      client_id: clientId,
      public_key_hex: publicKeyHex,
      vless_user_id_hex: vlessUserIdHex,
      public_key_mldsa65_hex: publicKeyMldsaHex ?? null,
    });
    if (status !== 200) {
      throw new Error(`mongo rest proxy bindDeviceIdentity failed: ${status}`);
    }
  }

  async consumeEnrollmentToken(tokenHash: string): Promise<void> {
    const { status } = await this.post("/internal/v1/enrollments/consume", { token_hash: tokenHash });
    if (status !== 200) {
      throw new Error(`mongo rest proxy consumeEnrollmentToken failed: ${status}`);
    }
  }

  async incrementUsage(clientId: string, bytesDelta: number): Promise<void> {
    const { status } = await this.post("/internal/v1/clients/usage", {
      client_id: clientId,
      bytes_delta: bytesDelta,
    });
    if (status !== 200) {
      throw new Error(`mongo rest proxy incrementUsage failed: ${status}`);
    }
  }
}
