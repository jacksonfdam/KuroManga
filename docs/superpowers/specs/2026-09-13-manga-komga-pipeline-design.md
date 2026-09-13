# Pipeline de download de mangá com sincronia MAL/AniList e biblioteca Komga

Data: 2026-09-13
Status: aprovado para planejamento

## Problema

As listas de leitura vivem no MyAnimeList e no AniList. Os arquivos precisam viver numa
biblioteca Komga, que já resolve leitura em web e mobile. Entre as duas pontas não existe
nada: as listas dão títulos, e o `manga-downloader` (github.com/elboletaire/manga-downloader)
exige a URL de um site de origem. Falta a camada que resolve título para URL, decide o que
ainda não foi baixado, executa downloads em paralelo com controle de falha, e entrega os
arquivos no formato e no layout que o Komga entende.

O sistema também deve aceitar CBZ que o usuário já possui, colocados direto no volume da
biblioteca: o Komga os indexa igual, e o pipeline não os sobrescreve.

## Escopo

Dentro:

- Leitura das listas de mangá no MyAnimeList e no AniList.
- Mapeamento confirmado pelo usuário entre entrada de lista e URL do site de origem.
- Descoberta de capítulos e cálculo do delta contra o que a biblioteca já tem.
- Download paralelo com fila persistente, retry com backoff e progresso ao vivo.
- Geração de CBZ com `ComicInfo.xml` preenchido.
- Criação e varredura da biblioteca no Komga via API.
- Escrita do progresso de leitura do Komga de volta nas duas listas.
- Interface web de quatro telas e infraestrutura completa em `docker-compose`.

Fora:

- Leitor próprio. O Komga entrega leitura web e mobile.
- Autenticação na interface de gerenciamento. Rede local apenas.
- Listas de anime. Somente mangá.
- Suporte a formatos além de CBZ.

## Decisões

| Decisão | Escolha | Razão |
|---|---|---|
| Resolução título → URL | Confirmação manual na interface, par persistido | Zero download errado; custo de um clique por série nova |
| Provedores de lista | MyAnimeList e AniList no v1 | Ambos em uso; adaptadores atrás de uma interface comum |
| Gatilhos de download | Cron de delta, botão manual, sincronia automática de entradas novas | Cobre uso diário, backfill e reprocesso |
| Fila e progresso | Postgres apenas | Já necessário para domínio e histórico; `SKIP LOCKED` basta |
| Integração Komga | Volume compartilhado, varredura via API, `ComicInfo.xml`, progresso de volta, Komga como fonte de verdade do que existe | Biblioteca completa sem trabalho manual |
| Stack | Python (FastAPI, SQLAlchemy, asyncio) e React (Vite) | Melhor ecossistema para scraping, metadata e OAuth |
| Arquitetura | Imagem única, processos separados: `api` e `worker` | `api` reinicia sem matar download; `worker` escala |
| Implantação | Homelab na rede local, sem autenticação, amd64 | Simplicidade; Tailscale depois não muda nada |

O `manga-downloader` é invocado como subprocesso do binário Go, não importado como
biblioteca. O worker lê o stdout linha a linha e converte em eventos de progresso.

## Modelo de dados

O conceito central é a separação entre *entrada de lista* e *série canônica*. Duas entradas,
uma do MyAnimeList e outra do AniList, apontam para a mesma `series`: uma confirmação de
mapeamento, uma pasta no disco, um download.

```
list_entry   (provider, provider_media_id, title_romaji, title_english, synonyms jsonb,
              status, user_progress_chapter, total_chapters, raw jsonb, updated_at)
   └─ series_id ──> series  (canonical_title, slug, komga_series_id, needs_review,
                             metadata jsonb, created_at)
                       ├──> source_mapping  (source_site, source_url, confirmed_at, active)
                       └──> chapter  (number numeric, title, source_url, state,
                                      file_path, komga_book_id, discovered_at)

job        (type, payload jsonb, state, priority, attempts, max_attempts,
            lease_until, last_error, series_id, created_at, started_at, finished_at)
job_event  (job_id, ts, level, message, pct)
provider_token (provider, access_token, refresh_token, expires_at)
setting    (key, value)
series_candidate (series_id, source_site, source_url, title, cover_url,
                  chapter_count, year, score)
```

Enumerações:

- `list_entry.status`: `reading`, `plan_to_read`, `completed`, `on_hold`, `dropped`
- `chapter.state`: `known`, `queued`, `downloading`, `downloaded`, `failed`, `skipped`
  (`skipped` é o capítulo que a fonte não publica no idioma pedido; não volta para retry)
- `job.state`: `pending`, `leased`, `done`, `failed`
- `job.type`: `list_sync`, `match_search`, `chapter_discover`, `download_batch`,
  `download_chapter`, `komga_scan`, `progress_push`

`chapter.state` é a fonte de verdade do que falta baixar, e é reconciliado contra os books
do Komga, não contra o disco. Assim, mexer nos arquivos por fora não causa redownload.

Índices necessários: `job (state, priority, created_at)` para o lease;
`job (state, lease_until)` para recuperação de lease expirado;
`chapter (series_id, number)` único; `list_entry (provider, provider_media_id)` único;
`job_event (job_id, ts)`.

## Módulos

Cada módulo tem um contrato e uma dependência. As quatro bordas são puras: recebem
argumentos, devolvem valores, não tocam no banco. Somente `handlers/` escreve.

| Módulo | Responsabilidade | Não conhece |
|---|---|---|
| `providers/` | `base.py` define `ListSource`; `mal.py` e `anilist.py` implementam `fetch_list()` e `push_progress()`, devolvendo DTOs | Postgres |
| `sources/` | `search(title, synonyms) -> [Candidate]`, `list_chapters(url) -> [ChapterRef]` | Fila, Komga |
| `downloader/` | Subprocesso do binário, parse de stdout, escrita de CBZ, injeção de `ComicInfo.xml` | Origem do pedido |
| `komga/` | `ensure_library()`, `scan_library()`, `books_of(series)`, `read_progress()` | Domínio |
| `queue/` | `enqueue`, `lease`, `complete`, `fail`, `notify` | Tipos de job |
| `handlers/` | Um handler por tipo de job; costura os módulos acima | HTTP |
| `api/` | Rotas FastAPI e SSE | Regra de negócio |

## Fluxo

Cada handler enfileira o próximo. O pipeline é uma cadeia, não um orquestrador central.

```
cron 6h ──> list_sync(provider)
              upsert de list_entry a partir da lista remota
              entrada nova sem series  -> cria series + enfileira match_search
              entrada nova com series  -> nada (dedupe entre provedores)

match_search(series)
              sources.search(títulos + sinônimos) -> series_candidate
              marca series.needs_review = true
              PARA. Usuário confirma na interface -> cria source_mapping
                                                  -> enfileira chapter_discover

cron 2h ──> chapter_discover(series)      [somente séries com mapping ativo]
              sources.list_chapters(url) -> upsert chapter (state = known)
              komga.books_of(series)     -> marca existentes como downloaded
              delta -> enfileira download_batch SOMENTE se series.auto_download
                       caso contrário, para aqui e a Biblioteca mostra o que falta

download_batch(capítulos)                 [N em paralelo]
              subprocesso manga-downloader --format cbz, faixa "1-20,22,25-30"
              progresso = arquivos escritos sobre total do lote
              injeta ComicInfo.xml, escreve .part, renomeia para o caminho final
              state = downloaded -> enfileira komga_scan (com debounce)

komga_scan    dispara varredura da library, aguarda indexação, casa komga_book_id

progress_push lê read-progress do Komga, escreve em MyAnimeList e AniList
```

O botão manual da interface enfileira `download_batch` ou `chapter_discover` com
`priority = 0`, à frente dos jobs de cron, sem código adicional.

**Por que em lotes.** O `manga-downloader` lê o índice completo de capítulos da obra a cada
invocação. Um job por capítulo significava reler setecentas entradas para baixar um arquivo, e
sob paralelismo o MangaDex passou a responder com erro 400. O binário aceita faixa
(`1-10,12,15-20`), então um lote custa uma leitura de índice. O tamanho do lote fica em
`setting` (padrão 20): um job único para a obra inteira seria um lease segurado por horas e
tudo-ou-nada em caso de falha.

Quando a fonte entrega parte do lote, os capítulos que chegaram são gravados e os que faltaram
voltam para a fila num lote menor, de modo que nada é baixado duas vezes. Um capítulo que a
fonte não publica no idioma pedido acaba isolado em lotes cada vez menores até ser marcado
`skipped`.

Há duas paradas deliberadas, e ambas existem para que nada saia pela rede sem decisão do
usuário.

A primeira é `match_search`: mangá novo na lista não baixa sozinho até o usuário confirmar o
mapeamento uma vez.

A segunda é o download em si. Confirmar o mapeamento diz ao pipeline *o que* a série é, não que
o acervo inteiro deva ser buscado. A descoberta continua rodando, para que a Biblioteca mostre
quantos capítulos existem e quantos faltam, mas o download começa quando o usuário pede uma
faixa ou marca a série como acompanhada (`series.auto_download`). Sem isso, confirmar 45
mapeamentos enfileirava dezenas de milhares de capítulos de uma vez.

## Fila, concorrência e falha

O lease usa `SELECT ... FOR UPDATE SKIP LOCKED` ordenado por `priority, created_at`, e grava
`lease_until = now() + 15 minutos`. Um job com lease expirado volta a `pending`
automaticamente: worker morto não perde trabalho.

Cada worker roda N tarefas asyncio, com N vindo de `setting` (padrão 3). Acima disso há um
semáforo por `source_site`: downloads paralelos demais no mesmo host geram 429 e bloqueio de
IP.

Na falha: `attempts + 1`, backoff exponencial de 1, 5 e 25 minutos, `max_attempts = 3`, e
então `state = failed`, visível na interface com `last_error` e as últimas linhas de
`job_event`. O retry manual zera `attempts`.

Erro de rede e capítulo inexistente na origem são tratados de forma diferente: o segundo
marca o capítulo como `skipped` em vez de entrar em ciclo de retry.

O progresso ao vivo não usa polling. O handler insere em `job_event` e chama
`pg_notify('jobs', job_id)`. A `api` escuta o canal numa conexão dedicada e empurra por SSE.

## Interface

Quatro telas.

**Biblioteca.** Grade de `series`. Cada card traz capa, título canônico, selos indicando de
quais listas a série vem, contagem de capítulos baixados sobre o total, e estado: mapeada,
precisa de revisão, baixando ou falhou. Filtro por estado. Aqui fica o botão de baixar uma
faixa de capítulos.

**Revisão de mapeamento.** Fila das séries com `needs_review`. Para cada uma: títulos e
sinônimos da lista de um lado, candidatos do site de origem do outro, com capa, contagem de
capítulos e ano. Um clique confirma e dispara o pipeline. Há campo para colar a URL à mão
quando a busca não encontra. Esta tela é o gargalo do sistema e recebe atalhos de teclado:
confirmar avança direto para a próxima série.

**Downloads.** Lista ao vivo por SSE, uma linha por job ativo com série, capítulo, barra de
progresso e velocidade. Seção de falhas com `last_error` e botão de retry. Seção de
pendentes com contagem. Clicar numa linha abre o `job_event` daquele job.

**Ajustes.** Conectar MyAnimeList por OAuth2 PKCE e AniList, concorrência, expressões cron,
caminho da biblioteca, e disparo manual de sincronia.

### API

```
GET  /api/series?state=              POST /api/series/{id}/mapping   {source_url}
GET  /api/series/{id}/candidates     POST /api/series/{id}/download  {from, to}
GET  /api/jobs?state=                POST /api/jobs/{id}/retry
GET  /api/jobs/{id}/events           POST /api/sync/{provider}
GET  /api/events                     (SSE: job.progress, job.done, job.failed, series.updated)
GET  /api/settings                   PUT  /api/settings
GET  /api/auth/{provider}/start      GET  /api/auth/{provider}/callback
```

A interface não fala com nada além desta API. Em particular, não fala direto com o Komga.

## Disco e metadata

Volume `manga_library`, montado com escrita no `worker` e somente leitura no `komga`:

```
/manga/{slug}/{slug} - Ch.0012 - Título do capítulo.cbz
```

O número do capítulo tem quatro casas com zero à esquerda, o que ordena corretamente e é
reconhecido pelo Komga. A escrita ocorre em arquivo `.part` no mesmo volume, seguida de
`rename` atômico: o Komga nunca indexa arquivo pela metade.

Cada CBZ recebe um `ComicInfo.xml` preenchido a partir dos dados de MyAnimeList e AniList:
`Series`, `Number`, `Title`, `Summary`, `Writer`, `Penciller`, `Genre`, `Year`, `Count`,
`LanguageISO` e `Web`. O Komga lê na indexação, o que dispensa trabalho manual de metadata e
faz o leitor mobile exibir a informação completa.

## Infraestrutura

```
postgres    postgres:17, volume pgdata, healthcheck pg_isready
komga       gotson/komga, /config em volume, /manga somente leitura, porta 25600
api         build ., alembic upgrade seguido de uvicorn, porta 8000,
            depends_on postgres com condition service_healthy
worker      mesma imagem, command worker, /manga com escrita, réplicas ajustáveis
caddy       serve o build React e faz proxy de /api para api, porta 8080
bootstrap   one-shot: aguarda o Komga responder, cria a library se não existir, encerra
```

A porta 8080 do `caddy` é a única exposta para uso normal. A 25600 do Komga fica exposta
para os leitores mobile e web.

**Bootstrap do Komga.** O serviço `bootstrap` faz polling no endpoint de saúde do Komga e
então chama `komga.ensure_library()`, que cria de forma idempotente a library apontando para `/manga` com o nome definido em
`.env`, verificando antes se já existe. A forma de criação do usuário administrador no
primeiro boot deve ser verificada contra a documentação do Komga durante a implementação: se
o registro inicial só for possível pela interface web, o `bootstrap` pula a criação de
usuário, cria apenas a library após o registro, e o passo manual único fica documentado no
README.

**Permissões.** Apenas o `worker` roda com `user: "${PUID}:${PGID}"`, porque é quem escreve na
biblioteca. O `komga` mantém o usuário da própria imagem: sobrescrevê-lo impede a escrita em
`/config`, onde fica o banco SQLite, e o resultado é um `SQLITE_CANTOPEN` em loop de restart
cuja mensagem não menciona permissão. A biblioteca o Komga apenas lê, e arquivos legíveis por
todos são suficientes.

**Imagem compartilhada.** `api`, `worker` e `bootstrap` são o mesmo programa com entrypoints
diferentes e declaram a mesma `image:`. Sem isso, reconstruir um deixa os outros rodando
código antigo, e o sintoma é um job falhando com "no handler registered".

**Logs.** Todos os serviços usam driver `json-file` com `max-size: 10m` e `max-file: 3`, para
que o disco não encha silenciosamente. O log operacional relevante é `job_event`, exibido na
interface; o stdout dos containers serve para quando um container não sobe.

**Configuração.** Somente `.env`: `POSTGRES_*`, `KOMGA_URL`, `KOMGA_USER`, `KOMGA_PASS`,
`KOMGA_LIBRARY_NAME`, `MAL_CLIENT_ID`, `MAL_CLIENT_SECRET`, `ANILIST_CLIENT_ID`,
`ANILIST_CLIENT_SECRET`, `PUID`, `PGID`, `LIBRARY_PATH`, `DOWNLOAD_CONCURRENCY`. Um
`.env.example` é versionado e o `.env` fica no `.gitignore`. Os tokens OAuth obtidos em
runtime vivem na tabela `provider_token`, nunca no `.env`.

## Testes

As quatro bordas puras, `providers`, `sources`, `downloader` e `komga`, são testadas contra
respostas gravadas em fixtures, sem acesso de rede na integração contínua.

A `queue` é testada contra um Postgres real, cobrindo lease concorrente, expiração de lease e
backoff. Esses são os comportamentos que falham em produção e não em mock.

Os `handlers` são testados com implementações falsas das bordas.

Um teste de fumaça ponta a ponta sobe o `docker-compose`, cria uma série fictícia, confirma um
mapeamento, baixa um arquivo dummy e verifica que o CBZ está no caminho correto com um
`ComicInfo.xml` válido.

## Fases

Cada fase entrega algo utilizável sozinho.

1. **Esqueleto.** `docker-compose`, migrations, fila com lease e retry, um handler trivial,
   SSE ao vivo. Valida a infraestrutura antes de existir domínio.
2. **Listas.** AniList e MyAnimeList, OAuth, `list_sync`, dedupe em `series`. A tela
   Biblioteca passa a ler dados reais.
3. **Matching.** `sources.search`, tela de Revisão, `source_mapping`.
4. **Download.** Subprocesso, progresso, `ComicInfo.xml`, escrita atômica, tela de Downloads.
5. **Komga.** Bootstrap da library, varredura, reconciliação de `chapter.state` contra os
   books.
6. **Loop fechado.** `progress_push` do Komga para MyAnimeList e AniList.

As fases 1 a 5 formam o sistema completo para uso diário. A fase 6 é conveniência, e vem por
último porque depende de escopo de escrita nos dois provedores.

## Riscos

O contrato de saída do `manga-downloader` não é uma API estável; o parse de stdout quebra se o
formato mudar. O parser fica isolado num único módulo com fixtures, de modo que a correção
seja local.

Sites de origem mudam layout e bloqueiam por IP. O semáforo por host e o backoff reduzem o
problema, mas não o eliminam; a falha é visível na interface em vez de silenciosa.

A escrita de progresso no MyAnimeList e no AniList é o único caminho do desenho ainda não
exercido contra o serviço real, por depender de contas conectadas. A leitura do progresso no
Komga e todo o restante do laço foram verificados contra uma instância real.
