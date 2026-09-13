# Discovery: sugestão de mangá a partir da lista de anime, com sincronia nos quatro destinos

Data: 2026-09-13
Status: aprovado para planejamento

## Problema

As listas de anime e de mangá são listas separadas no MyAnimeList e no AniList, e não
conversam. Um anime assistido até o fim não coloca o mangá correspondente em lugar nenhum:
ou o usuário lembra de procurar o título e adicionar à mão, nos dois provedores, ou a
história simplesmente para onde a adaptação parou.

O pipeline atual só enxerga o que já está na lista de mangá. Ele resolve título para URL de
origem, baixa capítulo em CBZ e entrega ao Komga, mas a entrada precisa existir antes. Falta
a camada anterior: olhar a lista de anime, descobrir qual mangá cada anime adapta, descartar
o que já está sendo lido, e oferecer o resto como sugestão — com a razão à vista, para a
decisão ser de um clique.

Aprovar uma sugestão precisa ter o mesmo efeito que adicionar o mangá à mão em quatro
lugares: MyAnimeList, AniList, MangaDex e a biblioteca Komga.

## Escopo

Dentro:

- Leitura da lista de anime no MyAnimeList e no AniList, com as relações que ligam anime a
  mangá.
- Materialização de sugestões, deduplicadas por identidade de mangá, com ranking e razão.
- Tela Discovery: aprovar com status escolhido, com controle de baixar agora por item, ou
  dispensar em definitivo.
- Escrita do status no MyAnimeList, no AniList e no MangaDex.
- Integração do `comick-source-api` como camada de busca e listagem de capítulos para sites
  fora do MangaDex.

Fora:

- Recomendação por gosto, gênero ou similaridade. A única razão para uma sugestão aparecer é
  existir um anime na lista que adapta aquele mangá.
- Novo extrator de páginas. O `manga-downloader` já suporta 84 sites, incluindo os que
  entram aqui; o download não muda.
- Sincronia de progresso. Progresso continua sendo assunto exclusivo do `progress_push`.

## Decisões e razões

**AniList primeiro, MyAnimeList como reserva.** O AniList expõe o grafo de relações da mídia
(`relations { edges { relationType node { ... } } }`) na mesma query que devolve a lista, então
resolver anime para mangá não custa request nenhum além do que já seria feito. O MyAnimeList
tem `related_manga`, mas só no detalhe de cada anime (`/anime/{id}`), um request por título.
Buscar esse detalhe apenas para o que o AniList não resolveu transforma a preferência por
precisão em economia de request.

**Subsistema próprio, não extensão do que existe.** Sugestão não é série. Guardar sugestão em
`series` com uma flag obrigaria toda consulta de Library, do downloader e do Komga a carregar
um `where not suggested` — acoplamento que cobra juros em cada feature futura. Duas tabelas
novas isolam o que ainda não é biblioteca daquilo que já é.

**Estado persistido, não cálculo ao vivo.** Uma lista de anime grande gasta rate limit a cada
abertura de tela, e "dispensar" precisa de onde morar. O estado teria que existir de qualquer
forma; materializar resolve as duas coisas.

**Comick busca, o binário baixa.** O `comick-source-api` devolve, por capítulo, apenas
`{id, number, title, url, group, lastUpdated}` (`src/types/index.ts`): a URL da página no
site, nunca a imagem. Não existe endpoint de páginas — o companion oficial é um userscript
que extrai imagem no browser. Isso tornaria o comick inútil como fonte de download, se o
`manga-downloader` já não baixasse dos mesmos sites. O conjunto usável é a interseção dos dois
catálogos: o comick acha e lista, o binário baixa.

**Comick auto-hospedado.** Colocar scraping de terceiro no caminho crítico do pipeline
significa depender da disponibilidade de uma instância mantida por cortesia. O serviço não
exige variável de ambiente nenhuma e sobe em Docker.

## Modelo de dados

Duas tabelas novas, nenhuma coluna alterada nas existentes.

```
anime_entry                          -- espelho da lista de anime, um por provedor
  id                bigint pk
  provider          varchar(20)      -- unique(provider, provider_media_id)
  provider_media_id varchar(50)
  title_romaji, title_english
  synonyms          jsonb
  status            varchar(20)      -- ListStatus; READING significa assistindo
  progress_episode  int
  total_episodes    int null
  cover_url         text null
  related_manga     jsonb            -- [{provider, media_id, relation, format}]
  raw               jsonb
  updated_at        timestamptz

suggestion                           -- um mangá candidato, não uma linha de anime
  id                bigint pk
  provider          varchar(20)      -- unique(provider, provider_media_id)
  provider_media_id varchar(50)      -- identidade do mangá; AniList vence quando há os dois
  alt_ids           jsonb            -- {mal: "123"} quando o outro provedor conhece o título
  title             varchar(500)
  cover_url         text null
  total_chapters    int null
  year              int null
  publishing_status varchar(20) null -- RELEASING / FINISHED / HIATUS
  state             varchar(20)      -- new | dismissed | added
  rank_score        numeric(5,4)
  series_id         bigint null fk series(id) on delete set null
  meta              jsonb
  created_at, updated_at timestamptz
```

`suggestion.meta` carrega o que a tela e a escrita precisam sem consultar nada: anime de
origem (id, título, status, episódios), tipo de relação, sinais que formaram o ranking, UUID
do MangaDex quando encontrado, fontes achadas no comick
(`[{site, url, chapters, score}]`) e o resultado da última escrita por alvo
(`write_results: [{target, ok, error, at}]`).

Enums: `SuggestionState` novo; `JobType` ganha `ANIME_LIST_SYNC`, `SUGGEST_BUILD` e
`LIST_WRITE`. `ListStatus` fica intocado — anime e mangá compartilham os cinco estados, e só
o rótulo na interface muda.

**Identidade.** A sugestão é do mangá, não do anime. Dois `anime_entry` do mesmo título, um em
cada provedor, colapsam numa linha só; quando os dois conhecem o mangá, o id do AniList vira
a identidade e o do MyAnimeList vai para `alt_ids`. É esse par que a escrita de status usa
depois, sem busca adicional.

**Exclusão.** Não vira sugestão o mangá cujo `provider_media_id` já está em `list_entry`, cujo
título casa com `series.meta -> aliases` pela mesma função de alias do `list_sync`, ou cuja
sugestão está `dismissed`. Dispensar é permanente: a linha permanece com o estado justamente
para o próximo ciclo não a ressuscitar.

## Jobs

### `ANIME_LIST_SYNC`

Cron novo, `cron_anime_list_sync`, default `0 */12 * * *`. Por provedor conectado:

- AniList: `MediaListCollection(type: ANIME)` com `relations` embutido. Uma query para a lista
  inteira, relações incluídas.
- MyAnimeList: `/users/@me/animelist` para a lista; `/anime/{id}` apenas para os títulos que o
  AniList não resolveu.
- Upsert em `anime_entry` por `(provider, provider_media_id)`.
- Ao terminar, enfileira `SUGGEST_BUILD` com chave de deduplicação, como o `list_sync` já faz
  com `match_search`.

### `SUGGEST_BUILD`

Cálculo sobre o que já está no banco, mais metadados do mangá:

1. Lê `anime_entry` com status diferente de dropado.
2. Extrai de `related_manga` as arestas `SOURCE` e `ADAPTATION` cujo nó é mangá; descarta
   `LIGHT_NOVEL`, `NOVEL` e `ONE_SHOT`.
3. Colapsa por identidade de mangá e preenche `alt_ids`.
4. Descarta o que já está em `list_entry`, o que já é `series` e o que está `dismissed`.
5. Busca metadados em lote (`Page(media: ids)` no AniList, 50 por query): capa, contagem de
   capítulos, status de publicação. Busca também o UUID do MangaDex e as fontes no comick.
6. Calcula `rank_score` e faz upsert preservando `state`.

**Ranking**, três sinais somados: anime completo com mangá ainda publicando (peso maior),
anime em andamento, e mangá com capítulos além do que a adaptação cobriu. A estimativa de
episódio para capítulo entra como peso e como frase no card, nunca como filtro: ela erra, e
errar não pode esconder título.

### `LIST_WRITE`

Escreve o status escolhido nos provedores. Job, não chamada dentro do request: são três APIs
externas que falham de forma independente, e o request precisa voltar rápido enquanto a tela
acompanha o resultado pelos eventos.

Os alvos são independentes, o resultado de cada um é registrado em `meta.write_results` e o
retry refaz apenas os que falharam. Escrever status é idempotente, então repetir não custa
nada. Alvo sem conta conectada levanta `PermanentError` nomeando o provedor, em vez de
retentar para sempre.

## Aprovação

`POST /api/suggestions/{id}/add` com `{status, download}`:

1. Cria `series` com o mesmo `reserve_slug` e o mesmo conjunto de aliases do `list_sync`, e
   cria as linhas `list_entry` locais — sem elas, o próximo `list_sync` traria o mesmo mangá
   como entrada nova, para revisão.
2. Enfileira `LIST_WRITE`.
3. Mapeamento: a sugestão já carrega o melhor candidato de fonte. Com confiança alta, grava
   `source_mapping` direto e a tela Review é dispensada; caso contrário `needs_review` fica
   verdadeiro e o fluxo é o de hoje.
4. `download: true` enfileira `CHAPTER_DISCOVER` imediatamente. O toggle vem pré-marcado pelo
   status — ligado em Lendo e Planejo Ler, desligado em Completo, Em espera e Dropado — e é
   invertido por item na tela.
5. Marca `state = added` e preenche `series_id`.

## Sincronia por destino

| interno | MyAnimeList | AniList | MangaDex | Komga |
|---|---|---|---|---|
| READING | `reading` | `CURRENT` | `reading` | — |
| PLAN_TO_READ | `plan_to_read` | `PLANNING` | `plan_to_read` | — |
| COMPLETED | `completed` | `COMPLETED` | `completed` | marca livros baixados como lidos |
| ON_HOLD | `on_hold` | `PAUSED` | `on_hold` | — |
| DROPPED | `dropped` | `DROPPED` | `dropped` | — |

**MyAnimeList**: `PATCH /manga/{id}/my_list_status` com `status`. É o mesmo endpoint que o
`push_progress` já usa, então o escopo de escrita já está concedido e o fluxo OAuth não muda.

**AniList**: a mutation `SaveMediaListEntry` existente ganha a variável `status`. Nos dois
provedores, adicionar e mudar status são a mesma chamada: criar a entrada é efeito de
escrever status em mídia que ainda não está na lista.

**MangaDex**: `POST /manga/{uuid}/status`, que exige o UUID do MangaDex. Ele pode não existir
se a fonte escolhida for outra, por isso o `SUGGEST_BUILD` guarda o UUID sempre que a busca o
encontra, independente de ser a fonte de download. Sem UUID, o alvo é pulado e registrado
como ausência, não como falha.

**Komga** não é lista, é biblioteca: não existe adicionar sem baixar. Sincronizar com ele são
dois efeitos, ambos já implementados — o CBZ chegar em `/manga` com o `komga_scan` em
seguida, e, quando o status é Completo, marcar os livros baixados como lidos via
`set_read_progress`.

**Fronteira que não pode borrar**: `LIST_WRITE` escreve status, nunca progresso. Progresso
continua exclusivo do `progress_push`, que só move para frente. Sem essa separação, marcar um
título como Completo zeraria o capítulo lido na volta.

## Integração com o comick

Serviço `comick` no `docker-compose.yml`, a partir da imagem do repositório, sem variável de
ambiente. Setting nova `COMICK_API_URL`, default `http://comick:3000`.

`app/sources/comick_client.py` é HTTP puro — `search(query, sources)`, `chapters(url, source)`,
`sources()`, `health()` — testável por fixture como os demais clientes.

As fontes registradas saem da interseção entre o que o comick sabe buscar e o que o
`manga-downloader` sabe baixar. O conjunto inicial é **asurascan** e **weebcentral**: estão
nos dois catálogos e são os dois que o comick já proxia via `/api/proxy/html`. Cada um vira um
`Source` registrado por uma subclasse parametrizada `ComickSource(site, domains)`, de modo que
`source_for_url` continue resolvendo URL colada à mão e o `download_chapter` não mude uma
linha. Acrescentar um terceiro site depois é uma entrada na tabela de registro.

O MangaDex continua preferido no desempate: API documentada, numeração de capítulo confiável e
autenticação pessoal já configurada.

**Degradação**: comick indisponível não derruba o Discovery. A sugestão continua nascendo do
grafo de relações, apenas sem a lista de fontes, e a aprovação cai em Review. O `/api/health`
do comick alimenta o estado exibido em Settings.

## Interface

Rotas em `app/api/routes_discovery.py`:

- `GET /api/suggestions?state=new&limit=&offset=`, ordenado por `rank_score` decrescente.
- `POST /api/suggestions/{id}/add` com `{status, download}`.
- `POST /api/suggestions/{id}/dismiss`.
- `POST /api/discovery/refresh`, que enfileira `ANIME_LIST_SYNC` para quem não quer esperar o
  cron.

Tela Discovery, quinto item do nav, com badge contando `state = new` no mesmo padrão do badge
de Review. Card por sugestão, em grade como a Library, contendo capa, título, ano e contagem
de capítulos; a razão da sugestão, que é o que distingue essa tela de uma lista qualquer
("de *Vinland Saga*, anime completo — mangá continua até o capítulo 210"); os chips das fontes
encontradas com a preferida destacada; o select de status; o toggle de baixar agora; e os
botões de adicionar e dispensar. `useJobEvents` atualiza o card quando o `LIST_WRITE` termina.

Settings ganha o cron novo e o estado de saúde do comick.

## Erros e limites

O AniList aceita cerca de 90 requests por minuto: a lista inteira sai em uma query e os
metadados de mangá em lotes de 50. O MyAnimeList só é consultado no detalhe dos animes que o
AniList não resolveu. Falha de rede em qualquer um deles é retentada pela fila que já existe,
com o mesmo backoff dos demais jobs. Comick fora do ar degrada a tela, não a quebra.

## Testes

Na divisão que o projeto já usa — parser puro por fixture, handler contra banco.

Fixtures: resposta do AniList com `relations`, `related_manga` do MyAnimeList, `search` e
`chapters` do comick.

Puros: extração das arestas de mangá do grafo; colapso de identidade entre provedores;
`rank_score`; mapa de status para os quatro destinos.

Handlers: `ANIME_LIST_SYNC` idempotente no upsert; `SUGGEST_BUILD` não ressuscita `dismissed`
nem sugere o que já está em `list_entry`; `LIST_WRITE` com um alvo falhando e dois passando,
e o retry tocando apenas o que falhou.

Fluxo: aprovar cria `series` e `list_entry`, marca `added`, e com `download: false` não
enfileira `CHAPTER_DISCOVER`.

## Critérios de aceite

1. A lista de anime dos dois provedores aparece em `anime_entry` após um ciclo de sync.
2. Um anime cujo mangá já está na lista de mangá não gera sugestão.
3. Uma sugestão dispensada não volta no ciclo seguinte.
4. Aprovar com status Lendo cria a entrada no MyAnimeList, no AniList e no MangaDex com o
   status correspondente.
5. Aprovar com `download: false` não baixa nada e mesmo assim registra o status nos três
   provedores.
6. Aprovar com `download: true` e candidato confiável baixa sem passar pela tela Review.
7. Falha em um provedor não impede a escrita nos outros dois, e o retry refaz só o que falhou.
8. Comick indisponível ainda produz sugestões, sem a lista de fontes.
