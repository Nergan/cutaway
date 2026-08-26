# Локальные крипто-библиотеки админки

`noble-crypto.js` — это собранный в один файл ESM-модуль, из которого `app.js`
берёт две функции:

| Экспорт | Откуда | Зачем в админке |
| --- | --- | --- |
| `sha3_256` | `@noble/hashes` 1.8.0 | хеш-цепочка команд (поле `chain`), от которой считается `prev`/`head` |
| `ml_dsa65` | `@noble/post-quantum` 0.4.1 | вторая, постквантовая подпись команды (первая — Ed25519 через WebCrypto) |

## Почему файл лежит в репозитории

Раньше `app.js` тянул обе библиотеки с `cdn.jsdelivr.net`. Это плохо по трём
причинам:

1. **Админка перестаёт работать, если CDN недоступен.** Без `ml_dsa65` нельзя
   подписать ни одну команду, то есть панель становится бесполезной. А jsdelivr
   в ряде сетей блокируется — ровно там, где VPN-панель и нужна.
2. **CDN может подменить код.** Файл, который подписывает команды приватным
   ключом администратора, приезжает с чужого сервера без проверки целостности.
   Скомпрометированный CDN = утёкший ключ.
3. **Утечка метаданных.** Каждое открытие панели light-ит запрос на сторонний
   домен.

Собранный файл не минифицирован специально — так его можно читать и
диффать при обновлении.

## Как пересобрать

Нужен Node.js. Версии в командах ниже совпадают с тем, что собрано сейчас;
меняйте их при обновлении.

```powershell
# 1. Отдельная временная папка, чтобы node_modules не попал в репозиторий
$work = "$env:TEMP\noble-vendor"
New-Item -ItemType Directory -Force $work | Out-Null
Set-Location $work

# 2. Ставим ровно те пакеты, что нужны
npm init -y
npm install "@noble/hashes@1.8.0" "@noble/post-quantum@0.4.1"

# 3. Точка входа: перечисляем только то, что реально используется в app.js
Set-Content entry.js -Encoding utf8 -Value @'
export { sha3_256 } from "@noble/hashes/sha3";
export { ml_dsa65 } from "@noble/post-quantum/ml-dsa";
'@

# 4. Собираем один ESM-файл
npx esbuild entry.js --bundle --format=esm --target=es2022 --outfile=bundle.js
```

Дальше скопируйте `bundle.js` в `noble-crypto.js`, сохранив шапку с лицензией
из текущего файла, и обновите номера версий в шапке, в этом README и в
таблице выше.

## Как проверить, что сборка не сломана

Размеры ключей и подписи у ML-DSA-65 фиксированы стандартом FIPS 204, так что
достаточно сверить их:

```powershell
Copy-Item bundle.js bundle.mjs -Force
Set-Content check.mjs -Encoding utf8 -Value @'
import { sha3_256, ml_dsa65 } from "./bundle.mjs";
const kp = ml_dsa65.keygen(new Uint8Array(32).fill(7));
const msg = new TextEncoder().encode("hello");
const sig = ml_dsa65.sign(kp.secretKey, msg);
console.log("sha3_256:", sha3_256(msg).length, "(ожидается 32)");
console.log("publicKey:", kp.publicKey.length, "(ожидается 1952)");
console.log("secretKey:", kp.secretKey.length, "(ожидается 4032)");
console.log("signature:", sig.length, "(ожидается 3309)");
console.log("verify:", ml_dsa65.verify(kp.publicKey, msg, sig), "(ожидается true)");
'@
node check.mjs
```

Промежуточный файл `bundle.mjs` нужен только потому, что Node без
`"type": "module"` в `package.json` считает `.js` за CommonJS. Браузеру
расширение безразлично — там модульность задаётся через
`<script type="module">` и `import`.

## Лицензия

Оба пакета — MIT, Copyright (c) 2024 Paul Miller (https://paulmillr.com).
Полный текст в `./LICENSE`. При обновлении версий проверьте, не сменилась ли
лицензия в апстриме.

---

# Шрифты (`fonts/`)

Там же лежат Inter и JetBrains Mono — раньше они подключались с
`fonts.googleapis.com`. Это была не такая критичная зависимость, как крипта
(при недоступности CDN панель просто рисовалась системным шрифтом), но домен
внешний, поэтому убран тоже.

Подробности — в `fonts/fonts.css` и `fonts/NOTICE.md`.

## Как обновить шрифты

Google Fonts отдаёт разные файлы в зависимости от `User-Agent`: современному
браузеру — `woff2`, старому — `ttf`. Поэтому UA нужно подставлять явно, иначе
скачается формат крупнее и хуже поддерживаемый.

```powershell
$ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " +
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

# Диапазон весов через "300..600", а не "300;400;500;600" — так Google отдаёт
# один вариативный файл на набор символов вместо отдельного файла на каждый вес.
$url = "https://fonts.googleapis.com/css2?family=Inter:wght@300..600" +
       "&family=JetBrains+Mono:wght@400..500&display=swap"

curl.exe -s -A $ua $url
```

В выдаче будет по блоку `@font-face` на каждый набор символов
(`latin`, `cyrillic`, `greek`, `vietnamese` и так далее). Нужны только `latin`
и `cyrillic`: скачайте четыре файла по ссылкам из этих блоков, положите в
`fonts/` под именами вида `inter-latin.woff2` и перенесите в `fonts/fonts.css`
соответствующие `unicode-range` — именно они говорят браузеру, какой файл
качать для какого символа, и без них он скачает все четыре сразу.

Проверить, что файлы не побились по пути:

```powershell
Get-ChildItem fonts -Filter *.woff2 | ForEach-Object {
  $magic = [System.Text.Encoding]::ASCII.GetString(
    [System.IO.File]::ReadAllBytes($_.FullName)[0..3])
  "$($_.Name): $magic"   # у настоящего woff2 здесь wOF2
}
```
