# Toadcode

[Читать на русском (README.ru.md)](README.ru.md)

Toadcode is a browser workspace for a small text project. The page at `/toadcode` is a file tree and an editor: add files and folders, drop in a zip, or import a public GitHub or Hugging Face repository archive. Publishing stores the tree in MongoDB and opens a read-only page at `/toadcode/{id}`.

The same stored workspace can be created, read, and edited over HTTP.

## API

Routes are served by the hub under `/toadcode`. `GET /toadcode/api` returns the route map.

A file is a JSON object:

```json
{"path": "src/hello.txt", "content": "hi", "is_dir": false}
```

A directory has `"is_dir": true`, empty `content`, and a path ending in `/`. Sending `"path": "box"` with `"is_dir": true` stores `box/`. Paths use forward slashes. A path that contains `..` or an empty segment is rejected.

Limits on one workspace: 2000 files, 512 KiB of characters in a single file, and 8 MiB of text in total. Writes are limited to 20 requests per minute from one client.

### Create

`POST /toadcode/api/repos`

```json
{"files": [{"path": "hello.txt", "content": "hi", "is_dir": false}]}
```

`201` response:

```json
{"id": "...", "token": "...", "editable": true, "files": [...]}
```

The token is returned only from this call. Later writes send it as `Authorization: Bearer <token>` or as the `X-Toadcode-Token` header.

An empty `files` array creates an empty workspace you can fill with single-file writes.

### Read

`GET /toadcode/api/repos/{id}` returns `id`, `editable`, and `files`. It does not return the token.

`GET /toadcode/api/repos/{id}/files/{path}` returns one file. The path may contain slashes, for example `box/b.txt`.

### Replace, write, and delete

These calls require the token.

`PUT /toadcode/api/repos/{id}` with `{"files": [...]}` replaces the whole tree.

`PUT /toadcode/api/repos/{id}/files/{path}` with `{"content": "updated", "is_dir": false}` creates or overwrites that path. For a directory, send `{"content": "", "is_dir": true}`.

`DELETE /toadcode/api/repos/{id}/files/{path}` removes a file. Deleting a directory removes that directory and every path under it.

`DELETE /toadcode/api/repos/{id}` returns `204` and removes the workspace.

A missing or wrong token is `401`. An unknown id or path is `404`. A path or body that breaks the rules above is `400`. A body past the size limit is `413`.

### Publish from the page

The publish button calls `POST /toadcode/api/save`:

```json
{"id": "client-chosen-id", "files": [...]}
```

Response: `{"status": "success", "id": "..."}`. An identical tree is stored once, and a later identical save returns the existing id. The read-only page is `/toadcode/{id}`.

That workspace can be read with `GET /toadcode/api/repos/{id}`. It has no edit token, so a write is `403`.

### Example

```bash
curl -s -X POST "$ORIGIN/toadcode/api/repos" \
  -H "Content-Type: application/json" \
  -d '{"files":[{"path":"hello.txt","content":"hi","is_dir":false}]}'
```

Use the `id` from the response for `GET $ORIGIN/toadcode/api/repos/{id}`. Use the `token` on `PUT` and `DELETE`.

The page also calls `GET /toadcode/api/backgrounds` for its video list and `GET /toadcode/api/proxy-zip?url=` to download an allowed public archive.
