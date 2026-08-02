# Deploy — Vercel (frontend) + Fly.io (backend)

Runbook testado contra o estado atual do repositório. Os passos marcados com 🔑
exigem login interativo e só você pode executar.

| Item | Valor |
|---|---|
| App Fly.io | `delivery-route-optimizer-api` → `https://delivery-route-optimizer-api.fly.dev` |
| Banco | `delivery-optimizer-db` (Postgres no Fly) |
| Frontend | Vercel, root directory `apps/web` |
| Custo | ~US$5/mês (Fly) + Vercel grátis |

> **Não crie `services/api/.env.production`.** O Fly não lê esse arquivo — ele usa
> `fly secrets`. O `.gitignore` agora bloqueia qualquer `.env*` (menos os
> `.example` e o `apps/web/.env.production`, que só tem a URL pública da API),
> justamente para uma `SECRET_KEY` não vazar num repositório público.

---

## 1. GitHub 🔑

O repositório local já tem o commit inicial e nenhum remote. Crie o repo **vazio**
em https://github.com/new (nome `delivery-route-optimizer`, público, sem README)
e depois:

```bash
cd /home/caixam1/routes
git remote add origin https://github.com/marcosck123/delivery-route-optimizer.git
git branch -M main
git push -u origin main
```

Se o push pedir senha, use um Personal Access Token (Settings → Developer
settings → Tokens) ou instale o `gh` e rode `gh auth login`.

---

## 2. Backend no Fly.io

O `flyctl` já está instalado em `~/.fly/bin`. Adicione ao PATH:

```bash
export PATH="$HOME/.fly/bin:$PATH"          # coloque no ~/.bashrc para persistir
fly version
```

### 2.1 Login 🔑

```bash
fly auth login      # abre o navegador
```

### 2.2 Criar o app — **sem `fly launch`**

O `fly launch` sobrescreve o `fly.toml` que já está no repositório (com região
`gru`, healthcheck em `/health`, porta 8080 e VM de 256 MB). Use:

```bash
cd /home/caixam1/routes/services/api
fly apps create delivery-route-optimizer-api
```

### 2.3 Postgres

```bash
fly postgres create --name delivery-optimizer-db --region gru
fly postgres attach delivery-optimizer-db --app delivery-route-optimizer-api
```

O `attach` grava a `DATABASE_URL` automaticamente. Ela vem no formato
`postgres://`, que o SQLAlchemy 2.0 rejeita — a aplicação já normaliza para
`postgresql://` em `app/config.py` (coberto por teste).

### 2.4 Secrets

```bash
fly secrets set SECRET_KEY="$(openssl rand -hex 32)" --app delivery-route-optimizer-api
fly secrets list --app delivery-route-optimizer-api      # confere sem revelar valores
```

Depois que o frontend estiver no ar, feche o CORS (passo 4).

### 2.5 Deploy

```bash
fly deploy --app delivery-route-optimizer-api
```

Sem Docker local, o `flyctl` usa o builder remoto automaticamente. Esta é a
primeira vez que o `Dockerfile` roda de verdade — se falhar, o erro aparece no
build log.

### 2.6 Testar

```bash
curl https://delivery-route-optimizer-api.fly.dev/health
# {"status":"ok","version":"0.1.0"}

fly logs --app delivery-route-optimizer-api
```

Swagger: https://delivery-route-optimizer-api.fly.dev/docs

---

## 3. Frontend na Vercel 🔑

1. https://vercel.com → **Add New → Project** → importe `delivery-route-optimizer`.
2. **Root Directory: `apps/web`** e marque **"Include source files outside of the
   Root Directory"** — o `pnpm-workspace.yaml` e o `pnpm-lock.yaml` ficam na raiz;
   sem isso o install falha.
3. Framework Preset: **Next.js** (Build `pnpm build`, Output `.next`, Install
   `pnpm install` — tudo default). A Vercel usa pnpm 9 por causa do campo
   `packageManager` na raiz.
4. Environment Variables:

   | Nome | Valor |
   |---|---|
   | `NEXT_PUBLIC_API_URL` | `https://delivery-route-optimizer-api.fly.dev` |

5. **Deploy**.

---

## 3.5. Geocodificação (Google) — antes de esperar que funcione

A busca de endereços só responde com a key configurada. No dashboard do Google
Cloud: criar projeto → ativar **Geocoding API** → criar credencial → restringir
a key **por API** (só Geocoding) e definir um **alerta de orçamento**. Depois:

```bash
fly secrets set GOOGLE_MAPS_API_KEY="..." -a delivery-route-optimizer-api
```

Sem a key o app sobe normalmente e responde "Busca de endereços não
configurada" — todos os pins podem ser marcados à mão no mapa.

A migração de colunas roda sozinha a cada deploy: o `fly.toml` tem
`release_command = "python -m migrations.001_address_fields"`, executado numa
máquina temporária com a imagem nova **antes** de a versão entrar no ar. Ela é
idempotente. Para rodar à mão:

```bash
fly ssh console -a delivery-route-optimizer-api -C "python -m migrations.001_address_fields"
```

## 4. Fechar o CORS depois que souber a URL da Vercel

Por padrão a API aceita qualquer origem (`CORS_ORIGINS=*`). Com o frontend no ar:

```bash
fly secrets set CORS_ORIGINS="https://SEU-APP.vercel.app" --app delivery-route-optimizer-api
```

O `fly secrets set` reinicia o app sozinho. A autenticação usa Bearer token
(não cookie), então nada quebra ao restringir a origem.

---

## 5. Teste E2E em produção

1. Abra a URL da Vercel → **Registrar** com email e senha (mínimo 6 caracteres).
2. Crie uma rota — importe `examples/entregas-exemplo.csv` (5 endereços de Vilhena).
3. **Otimizar Rota** → os marcadores renumeram e o traçado do OSRM aparece.
4. Confira a distância total no rodapé verde do mapa.

Se o OSRM público estiver com rate limit, a rota ainda é otimizada e o app mostra
a estimativa em linha reta com traçado tracejado — é comportamento esperado, não
erro.

---

## 6. Problemas prováveis

| Sintoma | Causa provável | Correção |
|---|---|---|
| App reinicia em loop no boot | `DATABASE_URL` ausente ou banco não anexado | `fly postgres attach delivery-optimizer-db` |
| `NoSuchModuleError: postgres` | rodando código antigo, sem a normalização | `fly deploy` de novo |
| CORS bloqueado no browser | `CORS_ORIGINS` sem a URL da Vercel | passo 4 |
| Build da Vercel: lockfile/workspace | Root Directory sem "include files outside" | passo 3.2 |
| Chamada à API vai para `localhost:8000` | `NEXT_PUBLIC_API_URL` não setada no build | setar na Vercel e **redeploy** (a var entra no bundle em build time) |
| Cold start de ~2s na 1ª visita | `auto_stop_machines = true` | normal; troque para `false` se incomodar (custa mais) |

---

## 7. Comandos úteis

```bash
export PATH="$HOME/.fly/bin:$PATH"

fly status  --app delivery-route-optimizer-api
fly logs -a delivery-route-optimizer-api
fly apps restart delivery-route-optimizer-api
fly secrets list -a delivery-route-optimizer-api
fly deploy -a delivery-route-optimizer-api

fly apps destroy delivery-route-optimizer-api     # cancelar tudo
fly apps destroy delivery-optimizer-db
```
