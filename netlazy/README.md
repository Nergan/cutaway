# netlazy

[Читать на русском (README.ru.md)](./README.ru.md)

`netlazy` is an independent dating and networking application designed to operate without reliance on external identity providers, SMS gateways, or email verification services. Authentication is managed entirely through client-side generated key pairs and cryptographic signatures, ensuring a self-contained system.

---

## Key Features

*   **Independent Authentication**: Each account is a locally generated Ed25519 key together with an ML-DSA-65 key. Requests are authenticated with those signatures instead of passwords or third-party logins, and the server keeps no session.
*   **On-the-Fly Media Obfuscation**: Uploaded media (images, video, and audio) is stored as a low-resolution public cover appended with an encrypted payload. The original file is decrypted on-the-fly by the viewing client, preventing direct scraping of raw files from the storage CDN.
*   **Proof of Work Rate-Limiting**: To prevent registration floods and spam without relying on third-party CAPTCHA services, the platform requires clients to solve a cryptographic challenge (Proof of Work) before performing sensitive state changes.
*   **Handshake Matching System**: Mutual consent is established using progressive "handshakes" (Share, Exchange, Demand, and Mutual) to negotiate how and when private contact details are revealed.

---

## Directory Overview

*   `domain/` — Core business models and repository abstractions.
*   `application/` — Use case services handling authentication, profile updates, and handshakes.
*   `infrastructure/` — MongoDB repositories, CDN storage integration, and media processing.
*   `presentation/` — FastAPI routers and cryptographic request signature validation.
*   `frontend/` — Client-side SPA built with Vue 3 and Vite, configured for optional Capacitor native app builds.

## API

The hub serves the app at `/netlazy`. JSON lives under `/netlazy/api`. `GET /netlazy/api` lists the group prefixes. Pages `/netlazy/profile`, `/feed`, `/inbox`, `/privacy`, and `/welcome` return the web client. A third-party client only needs the JSON routes below.

There is no session and no cookie. Every account request carries its own signature. JSON bodies use `Content-Type: application/json`. Media upload sends the raw file bytes. Errors are `{"detail": "..."}`.

### Signing

An account has two public keys, sent once at registration:

* Ed25519 public key, PEM (`SubjectPublicKeyInfo`).
* ML-DSA-65 public key, hex of the raw 1952 bytes.

`user_id` is the hex SHA-256 of the Ed25519 key in DER `SubjectPublicKeyInfo` form, followed by the raw ML-DSA-65 bytes. Keep `user_id` on the client. It identifies the signer. It is not an address for someone else's profile.

Every signed request sends:

| Header | Value |
| --- | --- |
| `X-User-Id` | `user_id` |
| `X-Timestamp` | Unix seconds. The server accepts it within 120 seconds of its own clock. |
| `X-Nonce` | A fresh string. Reuse within about five minutes returns 401. |
| `X-Body-Hash` | Hex SHA-256 of the raw body. An empty body hashes as the SHA-256 of zero bytes. |
| `X-Signed-Path` | Request path, including `/netlazy`, without the query. |
| `X-Signature-Ed25519` | Standard base64 of the Ed25519 signature. |
| `X-Signature-MLDSA` | Standard base64 of the ML-DSA-65 signature. |
| `X-Fingerprint` | Optional client marker. Registration and chain requests remember it. |

Both signatures cover the same UTF-8 canonical text. The three kinds of text are not interchangeable.

**Read** (`PQDA-READ-v1`). Used by `GET /profile/me`, `GET /inbox`, `GET /push/preferences`, `POST /feed/search`, and `GET /feed/form/{slug}` when `X-User-Id` is present. The chain does not move, and the response has no `X-Next-Anchor`.

```text
PQDA-READ-v1
METHOD
/netlazy/api/inbox

1710000000
nonce
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
```

The blank line is the raw query string. `POST /feed/search` has an empty query, so that line stays empty. A real query is included without the leading `?`, exactly as it appears on the request.

**Chain** (`PQDA-v1`). Used by every account change: profile edits, media, form links, handshakes, key rotation, and account deletion. Add `X-Chain-Anchor` with an anchor the server still remembers (the latest five). The canonical text ends with that anchor:

```text
PQDA-v1
METHOD
/netlazy/api/profile/me

1710000000
nonce
body-hash
previous-anchor
```

A successful chain response sets `X-Next-Anchor`. Store it and send it as the next anchor. The server value is SHA-256 hex of `PQDA-CHAIN-v1|` plus `previous-anchor|user_id|METHOD|signed-path|body-hash|nonce|timestamp`. Send chain requests one at a time for the same account. A parallel chain request signed with the same anchor can fall outside the window of five and return `409` with detail `Execution trace broken or outdated`.

**Anchor recovery** (`PQDA-ANCHOR-v1`). `GET /auth/anchor` only. This text has no query line and no anchor:

```text
PQDA-ANCHOR-v1
GET
/netlazy/api/auth/anchor
1710000000
nonce
body-hash
```

The response is `{"current_anchor": "..."}`. Use it after a `409`, then repeat the chain request with a new nonce and timestamp. This call does not move the chain.

`401` with detail `Unknown user` means the keys are not registered. Other signature failures are `401` with detail `Invalid authentication credentials`. `403` with detail `banned` means the account, address, or fingerprint is blocked.

### Proof of work

`POST /auth/register` and `POST /inbox/handshakes` also require a proof of work.

1. `GET /security/challenge` returns `{"challenge_id", "difficulty"}`. This route is unsigned. The default difficulty is 4.
2. Find a decimal nonce such that hex SHA-256 of `challenge_id + nonce` (the two strings joined) starts with `difficulty` zeros.
3. Send `X-Challenge-Id` and `X-Pow-Nonce` with the protected request.

A challenge is single-use and expires after about five minutes. A missing or wrong solution is `400` with detail `Invalid or missing Proof of Work`.

### What another person can see

Feed search, a profile opened by its link, and the profile embedded in an inbox item return only a public profile:

```json
{
  "id": "public id",
  "bio": "",
  "tags": [],
  "media": [{ "url": "", "media_type": "image", "blur": false }],
  "audio": null,
  "contacts": [{ "type": "email", "value": "open@example.com" }],
  "form": "my-link",
  "media_key": "base64"
}
```

`id` is a random public identifier, stored on the profile. Use it in `seen_ids` and as `receiver_id`. It is not `user_id`. Private contacts, the account id, the profile creation time, the match score, and the full list of links are absent. `form` is the primary public link, or `null`.

`media_key` is standard base64 of a 32-byte AES-GCM key. Import those bytes as a raw AES-GCM key. A stored file is a low-resolution cover, then the bytes `||NLZ_PAYLOAD||`, then a 12-byte nonce, then the ciphertext. `media_type` is `image`, `video`, or `audio`.

`GET` and `PUT /profile/me` return the owner's own record in addition to those public fields: `user_id`, `media_id`, `created_at`, `score`, `contacts` with `is_private`, `forms`, and `primary_form`. Only a signature from that account can read or change it.

### Routes

Unsigned indexes (`GET /auth`, `/profile`, `/feed`, `/inbox` is signed, `/tags`, `/security`) point at the routes in their group. `GET /inbox` is the inbox itself, not an index.

**Account**

| Method and path | Auth | Body and result |
| --- | --- | --- |
| `GET /auth/footprint-check` | none | `{"has_accounts": true\|false}` when this address or `X-Fingerprint` already belongs to an account. |
| `POST /auth/register` | proof of work | `{"ed25519_public_pem", "mldsa_public_hex"}`. `201` returns `user_id`, `genesis_anchor`, and a message. `400` if the keys are invalid or already registered. The genesis anchor is SHA-256 hex of `PQDA-CHAIN-v1\|genesis\|` plus `user_id`. |
| `GET /auth/anchor` | anchor recovery | `{"current_anchor"}`. |
| `POST /auth/rotate` | chain | `{"new_ed25519_public_pem", "new_mldsa_public_hex"}`. Returns `new_user_id` and `new_anchor`. The profile keeps its public id and media key material. Existing handshakes are removed. `X-Next-Anchor` is the new genesis anchor. |
| `DELETE /auth/account` | chain | `204`. Deletes the account, profile, and handshakes. |

**Profile.** Owner routes return the owner record. `GET /profile/me` is a read. The other profile routes are chain requests.

| Method and path | Body and result |
| --- | --- |
| `PUT /profile/me` | `{"bio", "tags", "contacts": [{"type", "value", "is_private"}]}`. Bio is at most 500 characters. At most 50 tags, and each tag must exist in the catalog. At most 20 contacts. `type` is `email`, `link`, `phone`, or `unknown`. A contact value is at most 500 characters. Unknown tags are `400`. |
| `POST /profile/me/media?blur=false` | Raw file bytes, up to 25 MB. At most 10 images and videos; one audio item replaces the previous audio. `415` for an unsupported type, `422` if processing fails, `400` when the limit is reached. |
| `PUT /profile/me/media/order` | `{"urls": ["..."]}` in the new order. |
| `DELETE /profile/me/media?url=&index=` | Removes one image or video. `index` is optional. `404` when it is missing. |
| `DELETE /profile/me/audio` | Clears the audio item. |
| `PATCH /profile/me/media/blur?url=&blur=true&index=` | Sets the blur flag. |
| `POST /profile/me/forms` | `{"value": "my-link"}` or `{"value": null}` to generate a link. A custom link is 2–48 characters, lowercase letters and single hyphens, with no digits. A generated link is a UUID. An account can hold 8 links. |
| `POST /profile/me/forms/{slug}/regenerate` | Replaces a generated link. |
| `PUT /profile/me/forms/{slug}/primary` | Makes that link the one returned as `form`. |
| `DELETE /profile/me/forms/{slug}` | Removes one link. |

Form errors use details `form_invalid` (`400`), `form_taken` (`409`), `form_limit` (`400`), and `form_not_found` (`404`).

**Feed**

`POST /feed/search` accepts an anonymous caller or a read signature. The body is:

```json
{
  "seen_ids": ["public id"],
  "requires": ["tag"],
  "excludes": ["tag"],
  "bonus": ["tag"],
  "abonus": ["tag"]
}
```

The response is up to 20 public profiles, newest first. `seen_ids` are public ids already shown; unknown ids are ignored. The caller's own profile and anyone already in a handshake with the caller are left out. A profile appears when it has a bio, a tag, media, audio, or a public contact.

`GET /feed/form/{slug}` returns one public profile. `404` detail `form_not_found` when the link is missing, invalid, or belongs to a banned account. The same anonymous-or-read rule applies.

A public link opens the web client at `/netlazy/feed?form={slug}`.

**Inbox.** `GET /inbox` is a read. Handshake changes are chain requests. Creating one also needs proof of work.

| Method and path | Body and result |
| --- | --- |
| `GET /inbox` | A list of inbox items. |
| `POST /inbox/handshakes` | `{"receiver_id", "type", "offered_contact", "message"}`. `receiver_id` is the public profile id. `type` is `share`, `exchange`, `demand`, or `mutual`. `share`, `exchange`, and `mutual` require `offered_contact`. `demand` must omit it. `message` is at most 100 characters. |
| `POST /inbox/handshakes/{id}/resolve` | `{"status": "accepted"\|"declined", "returned_contact"}`. Only the receiver of a pending item can resolve it. Accepting `demand`, `exchange`, or `mutual` requires `returned_contact`. Accepting `share` must omit it. Declining hides the item from the receiver. |
| `POST /inbox/handshakes/{id}/read` | Marks the item read for the person who still needs to see it: the receiver while it is pending, the sender after it is accepted or declined. |
| `DELETE /inbox/handshakes/{id}` | `204`. Hides the item for the caller. The record is removed when both people have hidden it. The sender cannot withdraw a pending `exchange`, `demand`, or `mutual`. |

`404` detail `profile_not_found` means the public id is unknown. Sending to yourself is `400` with detail `Cannot send handshake to self`. A repeated pair updates the existing pending or declined item, except a decline that the same receiver already made.

An inbox item looks like this. `created_at` and `updated_at` are the handshake times. `offered_contact` and `returned_contact` are the values the two people chose to reveal, which is separate from the public contact list.

```json
{
  "id": "handshake id",
  "type": "exchange",
  "status": "pending",
  "is_sender": true,
  "is_read": false,
  "offered_contact": "me@example.com",
  "returned_contact": null,
  "message": null,
  "created_at": "2026-10-15T00:00:00+00:00",
  "updated_at": "2026-10-15T00:00:00+00:00",
  "profile": { }
}
```

`profile` is a public profile.

**Push.** Notifications go out when a `share`, `exchange`, or `demand` request is created or updated for the account. `mutual` follows the exchange switch. The text is the request type in the device language. Contacts and the optional message are not included. A closed site tab still receives the notification.

Windows and other browsers use Web Push. The Android app uses Android push. An Android browser still uses Web Push, and the system shows it as an Android notification. Each device is stored on its own.

`GET /push/preferences` is a read. Changing preferences or a device subscription is a chain request. `GET /push/key` is unsigned. Missing preferences mean every switch is on.

| Method and path | Body and result |
| --- | --- |
| `GET /push/key` | `{"public_key"}`. Base64url uncompressed P-256 key for `PushManager.subscribe`. |
| `GET /push/preferences` | `{"enabled", "share", "exchange", "demand", "lang"}`. |
| `PUT /push/preferences` | The same object. `lang` is `en`, `ru`, `pt`, `zh`, `ja`, or `ko`. |
| `POST /push/subscriptions` | `204`. Registers one device. |
| `DELETE /push/subscriptions` | `204`. Removes one device. Body is `{"endpoint"}` or `{"token"}`. |

```json
{
  "platform": "windows",
  "transport": "webpush",
  "endpoint": "https://push.example/subscription",
  "p256dh": "base64url",
  "auth": "base64url",
  "open_path": "/netlazy/inbox",
  "origin": "https://example.com",
  "lang": "en"
}
```

`platform` is `windows`, `android`, or `web`. `transport` is `webpush` or `fcm`. Web Push needs `endpoint`, `p256dh`, and `auth`, and the endpoint host must be a known push service. Android app registration sends `transport: "fcm"` and `token` instead of those three fields. `open_path` is a same-site path opened from the notification.

Android app delivery reads `FCM_SERVICE_ACCOUNT` (a file path or the account JSON). Without it, Android tokens are stored and Web Push still works. `VAPID_PRIVATE_PEM` overrides the key the server would otherwise keep for Web Push. `VAPID_SUBJECT` is the `mailto:` contact in the Web Push token.

**Tags, status, and the web client**

| Method and path | Result |
| --- | --- |
| `GET /tags/search?q=` | Unsigned tag catalog. An empty `q` returns the browsable tags. Each item has `name`, `aliases`, `hidden`, and `i18n`. |
| `GET /api/health` | `{"status": "ok", "auth_type": "per-request-signature", "database": "connected"}`, or `503` when the database is down. |
| `GET /api/ui` | `{"interface_version": "1"\|"2"}`. |
| `GET /api/app-version` | `{"version", "url"}` for the native build. |
| `POST /security/ban?user={user_id}` | Admin only, header `X-Admin-Key`. This is not a client route. |

### A minimal client

1. Generate the two key pairs and register with a proof of work. Store `user_id` and `genesis_anchor`.
2. Sign reads with `PQDA-READ-v1`. Sign changes with `PQDA-v1` and the current anchor, then replace the anchor from `X-Next-Anchor`.
3. On `409`, refresh the anchor and retry that chain request once, with a new nonce and timestamp.
4. List people with `POST /feed/search`. Pass the returned `id` values back in `seen_ids`. Open one person with `GET /feed/form/{slug}` or start a handshake with their `id`.
5. Decrypt media with `media_key`. Do not expect `user_id`, private contacts, or a creation time on someone else's profile.