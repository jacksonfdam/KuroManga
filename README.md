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
site de origem corresponde, uma vez, e a partir daí o pipeline descobre quais
capítulos existem e mostra na Biblioteca quantos faltam.

**Nada é baixado até você pedir.** Na Biblioteca, cada série tem uma faixa
(deixe vazia para tudo que falta) e um botão *Follow new chapters*. Só as séries
que você marca como acompanhadas entram no cron de download; as outras ficam
catalogadas, sem consumir disco.

## Subir

```bash
cp .env.example .env      # preencha as credenciais
docker compose up -d --build
```

- Interface: <http://localhost:8080>
- Komga: <http://localhost:25600>

Ajuste `PUID` e `PGID` no `.env` para o seu usuário (`id -u`, `id -g`). Isso vale
só para o worker, que é quem escreve na biblioteca. O Komga roda com o usuário da
própria imagem: sobrescrever o usuário dele quebra o `/config`, que é onde ele
guarda o banco SQLite — o sintoma é um `SQLITE_CANTOPEN` em loop de restart, que
não menciona permissão em lugar nenhum. A biblioteca ele só lê, e arquivos com
leitura para todos bastam.

O serviço `bootstrap` roda sozinho a cada `up`: espera o Komga responder, cria o
administrador inicial se ninguém criou ainda, e cria a biblioteca apontando para
`/manga` se ela não existir. É idempotente.

### Credenciais do Komga

Preencha `KOMGA_API_KEY` no `.env` (no Komga: Settings, Account, API keys). É a
forma normal de autenticar, e a chave pode ser revogada sozinha.

`KOMGA_USER` e `KOMGA_PASS` só são necessários uma vez, para reivindicar uma
instância recém-criada: sem usuário não existe chave, e o endpoint de claim só
aceita email e senha. Com isso preenchido o `bootstrap` faz o claim para você.

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

As seis fases da spec estão implementadas: infraestrutura, listas, matching,
download, integração com o Komga e progresso de volta para as listas.

Downloads são feitos em lotes. O `manga-downloader` relê o índice inteiro da obra
a cada invocação, então um job por capítulo fazia setecentas leituras de índice
para baixar setecentos arquivos, e o MangaDex passava a responder 400. Um lote
usa a sintaxe de faixa do binário (`1-20,22,25-30`) e custa uma leitura. O
tamanho está em Settings, padrão 20.

As flags do binário `manga-downloader` foram conferidas contra o `--help` da versão
1.9.0 (`--format`, `--language`, `--output-dir`). O comando é montado em
`app/downloader/runner.py:build_command` e o parse da saída fica no mesmo módulo,
cobertos por testes — se uma versão futura mudar as flags, a correção é local.

O que ainda não foi exercido contra a rede: uma busca real no MangaDex, um
download real, e a escrita de progresso no MyAnimeList e no AniList. Essas três
bordas rodam de fixtures nos testes. O loop do Komga foi verificado contra uma
instância real: claim, criação da biblioteca, varredura, casamento de série por
pasta e de book por caminho, e leitura do progresso de leitura de volta.
