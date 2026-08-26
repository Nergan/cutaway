# `infra/` — инфраструктура как код

## Статус верификации

**Не прогонялось через `terraform validate`/`plan`/`apply`** — в среде
разработки этого репозитория нет доступа к `registry.terraform.io`
(проверено: `403 host_not_allowed`) и не установлен terraform CLI. Тот же
класс честно задокументированного ограничения, что для Xcode (`core/`),
реального MongoDB (`control-plane-admin/`) и Flutter SDK (`app/`) в
предыдущих частях.

Перед реальным использованием:

```bash
cd infra/cloudflare
terraform init
terraform validate
cp terraform.tfvars.example terraform.tfvars   # заполнить реальными значениями
terraform plan
terraform apply
```

Особое внимание: Cloudflare Terraform-провайдер (`cloudflare/cloudflare`)
менял схему атрибутов между мажорными версиями, особенно в части
Workers-биндингов. Атрибут `ech` в `cloudflare_zone_settings_override`
(main.tf) — не проверен против реального провайдера; если `apply` падает
на этом атрибуте, в `main.tf` есть закомментированный fallback через
`null_resource` + `local-exec` (`curl`), буквально переносящий команду из
§9.3 архитектурной спецификации.

## Что здесь есть

- `cloudflare/` — KV namespace для бан-кэша, DNS-запись маршрута к Worker'у,
  отключение ECH.
- `generic-vps/` — cloud-init + тот же origin-образ, что HF/Render
  (`deploy/origin/Dockerfile`). Без привязки к провайдеру VPS.
- **Намеренно не здесь**: деплой самого кода Worker'а (`wrangler deploy`
  справляется с bundling+upload лучше, чем `cloudflare_workers_script`,
  ожидающий уже собранный файл) — см. комментарий в `cloudflare/main.tf` и
  `.github/workflows/edge-deploy.yml`, где оба шага (Terraform → wrangler)
  идут последовательно в одном пайплайне.

## CI/CD

См. `.github/workflows/`:

| Файл | Триггер | Что делает |
|---|---|---|
| `core-ci.yml` | push/PR, изменения в `core/` | gofmt, vet, test, кросс-компиляция под 6 платформ |
| `edge-ci.yml` | push/PR, изменения в `edge/` | typecheck (2 прохода), vitest, `wrangler deploy --dry-run` |
| `edge-deploy.yml` | push в `main`, изменения в `edge/` | те же проверки + реальный `wrangler deploy` |
| `admin-ci.yml` | push/PR, изменения в `control-plane-admin/` | pytest |
| `app-ci.yml` | push/PR, изменения в `app/` | `flutter analyze`, `flutter test` (не верифицировано локально — см. `app/README.md`) |

Все YAML-файлы синтаксически провалидированы (`yaml.safe_load`), но сами
пайплайны не запускались (нет доступа к реальному GitHub Actions
раннеру/секретам в этой среде).
