import { connect } from "cloudflare:sockets";
import { parseRequestHeader, encodeResponseHeader, VlessProtocolError } from "../domain/vless_protocol.js";
import type { SessionInfo, SessionStorePort } from "../ports/session_store_port.js";
import type { UserRepositoryPort } from "../ports/user_repository_port.js";

export interface ProxyDeps {
  sessionStore: SessionStorePort;
  userRepo: UserRepositoryPort;
  ctx: ExecutionContext;
  onFinished?: (clientId: string, bytes: number) => void;
}

/**
 * handleProxy — data-plane шлюз Tier1 (§8.1 спецификации): Worker termину
 * ет WebSocket от Go-ядра, разбирает VLESS-заголовок, открывает исходящий
 * TCP через Cloudflare TCP Sockets API (`connect()` из `cloudflare:sockets`)
 * и перекачивает байты в обе стороны. Cloudflare выступает точкой выхода
 * (не просто транспортом до отдельного бэкенда) — см. §8.1 архитектурной
 * спецификации про это архитектурное решение и его ограничения (лимит
 * одновременных сокетов на Worker, запрет исходящих TCP к IP-диапазонам
 * самого Cloudflare).
 */
export async function handleProxy(request: Request, deps: ProxyDeps): Promise<Response> {
  if (request.headers.get("Upgrade") !== "websocket") {
    return new Response("expected websocket upgrade", { status: 426 });
  }

  const authHeader = request.headers.get("Authorization") ?? "";
  const bearerMatch = /^Bearer\s+(.+)$/i.exec(authHeader);
  if (!bearerMatch) {
    return new Response("missing bearer token", { status: 401 });
  }
  const session = await deps.sessionStore.validate(bearerMatch[1]!);
  if (!session) {
    return new Response("invalid or expired session token", { status: 401 });
  }

  const pair = new WebSocketPair();
  const client = pair[0];
  const server = pair[1];
  server.accept();

  pumpConnection(server, session, deps).catch((err) => {
    console.error("proxy pump failed", err);
    try {
      server.close(1011, "internal error");
    } catch {
      /* соединение уже могло быть закрыто */
    }
  });

  return new Response(null, { status: 101, webSocket: client });
}

/**
 * pumpConnection — основной цикл после апгрейда. Реализован через очередь
 * входящих WS-сообщений (а не прямой pipeTo), т.к. нужно сначала накопить
 * и разобрать VLESS-заголовок (который может прийти не одним WS-фреймом),
 * и только после этого открывать исходящий TCP-сокет — адрес назначения
 * известен только из содержимого заголовка, а не заранее.
 */
async function pumpConnection(server: WebSocket, session: SessionInfo, deps: ProxyDeps): Promise<void> {
  const inbound = createMessageQueue(server);

  // --- Шаг 1: накапливаем байты, пока не получится разобрать заголовок ---
  let buffered: Bytes = new Uint8Array(0);
  let parsed: ReturnType<typeof parseRequestHeader> | null = null;

  while (parsed === null) {
    const chunk = await inbound.next();
    if (chunk === null) {
      server.close(1000, "closed before vless header received");
      return;
    }
    buffered = concat(buffered, chunk);
    try {
      parsed = parseRequestHeader(buffered);
    } catch (err) {
      if (err instanceof VlessProtocolError && err.message.startsWith("incomplete header")) {
        continue; // ждём ещё данных
      }
      server.close(1002, "invalid vless header");
      return;
    }
  }

  if (parsed.userIdHex !== session.vlessUserIdHex) {
    // Bearer-токен валиден, но VLESS UUID в заголовке не совпадает с тем,
    // что был выдан этой сессии — доп. проверка на случай кражи/подмены
    // UUID отдельно от токена (см. §7.2 про SessionCredentials как пару
    // значений, а не одно).
    server.close(1008, "vless user id mismatch");
    return;
  }

  // --- Шаг 2: открываем исходящий TCP к реальному адресу назначения ---
  let socket: ReturnType<typeof connect>;
  try {
    socket = connect({ hostname: parsed.destHost, port: parsed.destPort });
  } catch (err) {
    server.close(1011, "upstream connect failed");
    return;
  }

  server.send(encodeResponseHeader());

  const leftoverPayload = buffered.subarray(parsed.headerLength);
  const writer = socket.writable.getWriter();
  let bytesSent = 0;
  let bytesRecv = 0;

  if (leftoverPayload.length > 0) {
    await writer.write(leftoverPayload);
    bytesSent += leftoverPayload.length;
  }

  // --- Шаг 3a: WS → TCP ---
  const wsToTcp = (async () => {
    for (;;) {
      const chunk = await inbound.next();
      if (chunk === null) break;
      await writer.write(chunk);
      bytesSent += chunk.length;
    }
    await writer.close().catch(() => {});
  })();

  // --- Шаг 3b: TCP → WS ---
  const tcpToWs = (async () => {
    const reader = socket.readable.getReader();
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      server.send(value);
      bytesRecv += value.length;
    }
  })();

  await Promise.allSettled([wsToTcp, tcpToWs]);

  try {
    server.close(1000, "upstream closed");
  } catch {
    /* уже закрыт */
  }

  // --- Шаг 4: батчевый учёт квоты (§8.4) — здесь упрощённо, раз в конце
  // соединения, а не через промежуточный Durable Object-счётчик, как
  // описано в спецификации для длинных сессий. Для типичных VPN-сессий
  // (минуты-часы) это приемлемо; для очень долгих соединений имеет смысл
  // периодический flush — TODO v2.
  const totalBytes = bytesSent + bytesRecv;
  if (totalBytes > 0) {
    deps.ctx.waitUntil(
      deps.userRepo.incrementUsage(session.clientId, totalBytes).catch((err) => {
        console.error("incrementUsage failed", err);
      }),
    );
  }
  deps.onFinished?.(session.clientId, totalBytes);
}

/** Bytes — единый алиас поверх Uint8Array<ArrayBufferLike>, чтобы обойти
 * строгую параметризацию Uint8Array по типу буфера (ArrayBuffer vs
 * ArrayBufferLike), появившуюся в TS 5.5+/lib.dom — без него разные
 * источники байт (WS-фреймы, TCP readable stream, ручная конкатенация)
 * выводятся с несовместимыми типами буфера, хотя рантайм-поведение
 * идентично. */
type Bytes = Uint8Array<ArrayBufferLike>;

/**
 * createMessageQueue — превращает событийную модель WebSocket ('message',
 * 'close') в async-итератор, чтобы можно было писать pumpConnection как
 * последовательный код (await inbound.next()), а не разваливать логику по
 * колбэкам.
 */
function createMessageQueue(ws: WebSocket): { next: () => Promise<Bytes | null> } {
  const queue: Bytes[] = [];
  const waiters: Array<(v: Bytes | null) => void> = [];
  let closed = false;

  ws.addEventListener("message", (event: MessageEvent) => {
    const data = event.data;
    const bytes: Bytes =
      typeof data === "string" ? new TextEncoder().encode(data) : new Uint8Array(data as ArrayBuffer);
    if (waiters.length > 0) {
      waiters.shift()!(bytes);
    } else {
      queue.push(bytes);
    }
  });

  const onClose = () => {
    closed = true;
    while (waiters.length > 0) {
      waiters.shift()!(null);
    }
  };
  ws.addEventListener("close", onClose);
  ws.addEventListener("error", onClose);

  return {
    next(): Promise<Bytes | null> {
      if (queue.length > 0) {
        return Promise.resolve(queue.shift()!);
      }
      if (closed) {
        return Promise.resolve(null);
      }
      return new Promise((resolve) => waiters.push(resolve));
    },
  };
}

function concat(a: Bytes, b: Bytes): Bytes {
  const out = new Uint8Array(a.length + b.length);
  out.set(a, 0);
  out.set(b, a.length);
  return out;
}
