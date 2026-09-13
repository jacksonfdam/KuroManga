# manga pipeline

Lê suas listas de mangá no MyAnimeList e no AniList, resolve cada entrada para uma
URL de site de origem com a sua confirmação, baixa os capítulos que faltam em CBZ
com metadata embutida, e entrega tudo para o Komga ler no navegador e no celular.

Desenho completo em [`docs/superpowers/specs/2026-09-13-manga-komga-pipeline-design.md`](docs/superpowers/specs/2026-09-13-manga-komga-pipeline-design.md).

## Como funciona

```
lista (MAL / AniList)  ->  series canônica  ->  você confirma a fonte  ->  capítulos
                                                                              |
                                                       CBZ + ComicInfo.xml  <-+
                                                                |
                                                        /manga  ->  Komga  ->  leitor
```

Uma entrada nova entra na tela **Review** e para ali. Você confirma qual mangá do
site de origem corresponde, uma vez, e a partir daí o cron cuida do resto: descobre
capítulos novos, calcula o que falta, baixa em paralelo e avisa o Komga.

## Subir

```bash
cp .env.example .env      # preencha as credenciais
docker compose up -d --build
```

- Interface: <http://localhost:8080>
- Komga: <http://localhost:25600>

Ajuste `PUID` e `PGID` no `.env` para o seu usuário (`id -u`, `id -g`). O worker
escreve na biblioteca e o Komga lê; com uids diferentes o Komga encontra arquivos
que não consegue abrir, e o erro que ele mostra não aponta para permissão.

### Credenciais das listas

| Provedor | Onde registrar | Redirect URI |
|---|---|---|
| MyAnimeList | <https://myanimelist.net/apiconfig> | `http://localhost:8080/api/auth/mal/callback` |
| AniList | <https://anilist.co/settings/developer> | `http://localhost:8080/api/auth/anilist/callback` |

Se você acessar por outro endereço, ajuste `PUBLIC_BASE_URL` no `.env` — é dele que
o redirect URI é montado.

Depois de subir, vá em **Settings**, conecte os dois provedores e clique em
**Sync now**.

## Desenvolvimento

```bash
cd backend
uv venv && uv pip install -e ".[dev]" alembic
docker run -d --name manga-pg-dev -e POSTGRES_USER=manga -e POSTGRES_PASSWORD=manga \
  -e POSTGRES_DB=manga -p 5433:5432 postgres:17-alpine

POSTGRES_HOST=localhost POSTGRES_PORT=5433 .venv/bin/python -m pytest tests -q
POSTGRES_HOST=localhost POSTGRES_PORT=5433 .venv/bin/python -m uvicorn app.api.main:app --reload

cd ../frontend && npm install && npm run dev
```

Os testes das bordas puras rodam de fixtures gravadas e não tocam a rede. Os da
fila rodam contra o Postgres de verdade, porque lease concorrente, expiração de
lease e backoff são exatamente o que um mock erraria.

## Estado

Fases 1 a 4 implementadas: infraestrutura, listas, matching e download.

Falta da spec:

- **Fase 5 — Komga.** O serviço já sobe no compose e lê a biblioteca, mas a criação
  automática da library pela API, a varredura disparada após cada download e a
  reconciliação de `chapter.state` contra os books do Komga ainda não existem. Hoje
  a reconciliação olha o disco, e a library você cria uma vez pela interface do Komga.
- **Fase 6 — progresso de volta.** Ler read-status do Komga e escrever em
  MyAnimeList e AniList. As duas escritas (`push_progress`) já estão implementadas
  nos provedores; falta o handler que as chama.

Um ponto a confirmar no primeiro uso real: as flags do binário `manga-downloader`.
O comando é montado em `app/downloader/runner.py:build_command` e o parse da saída
fica no mesmo módulo, cobertos por testes — se a versão instalada usar outras flags,
a correção é local.
