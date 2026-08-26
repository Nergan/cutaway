# `infra/generic-vps/` — заготовка без конкретного провайдера

VPS в инвентаре **пока нет**. Модуль выдаёт `cloud-init` user-data, которое
поднимает **тот же** Docker-образ, что HF и Render (`deploy/origin/Dockerfile`).

## Reality / xHTTP (фаза 4)

Код сервера готов (`core/cmd/reality-origin`, round-trip тест зелёный).
В проде включается, когда есть стабильный IP. **Не деплоить**, пока оператор
не скажет.

1. Ключи:
   ```bash
   cd core
   go run ./cmd/reality-origin -keygen
   ```
   Priv — только на VPS (`ANOTHER_REALITY_PRIVATE_KEY`). Pub — в nodes JSON
   клиента (`reality_public_key`), не в бинарник как identity key.

2. SNI-донор **в той же /24 или хотя бы AS**, что и VPS. Не `google.com`
   (на облаке probe сразу палит Reality).
   - Одно рукопожатие (полуавтомат):
     `go run ./cmd/reality-origin -probe www.microsoft.com:443`
     Смотреть: `TLS1.3`, `alpn=h2` желателен, CN/DNS совпадает с SNI,
     `not_after` не на днях.
   - Подсеть: внешний [RealiTLScanner](https://github.com/XTLS/RealiTLScanner)
     (GPL, **не вендорим**, не копируем в дерево). Пример:
     ```bash
     RealiTLScanner -addr <VPS_IP> -port 443
     ```
     Из кандидатов снова прогнать `-probe`, затем прописать dest/server_names.

3. Terraform: `run_reality=true`, `reality_dest`, `reality_server_names`,
   ключи — в tfvars. Снаружи 443 → контейнер 8443.

4. Сборка клиента из админки: `transport: vless-reality`, тот же
   `reality_public_key` и `short_id`.

```bash
cd infra/generic-vps
terraform init
terraform validate   # у оператора: в агенте нет registry.terraform.io
```

Деплой — только когда оператор скажет.
