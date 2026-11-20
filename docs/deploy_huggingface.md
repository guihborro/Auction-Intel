# Deploy no Hugging Face Spaces (Docker)

O app inteiro (API + site + scraper + modelos + análise de edital) sobe numa
única imagem Docker. O Hugging Face Spaces tem tier **gratuito com 16 GB de RAM**,
que aguenta o Chromium + o stack de ML.

---

## 1. Crie a conta e o Space
1. Crie uma conta em https://huggingface.co (grátis).
2. Vá em **New → Space**.
3. Preencha:
   - **Owner / Space name:** ex. `seu-usuario/auction-intel`
   - **SDK:** selecione **Docker** (template *Blank*)
   - **Hardware:** *CPU basic* (free) · **Visibility:** Public (ou Private)
4. Crie. O HF gera um **repositório git** para o Space.

## 2. Metadados do Space (README)
O HF lê a configuração do **topo do `README.md`** do Space. Garanta que o
`README.md` que vai pro Space comece com este bloco (o `app_port` precisa bater
com a porta do Dockerfile, **7860**):

```yaml
---
title: Auction Intel
emoji: 🎯
colorFrom: indigo
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
---
```

> Se preferir manter o README do projeto limpo no GitHub, deixe este bloco só no
> README do **Space** (o HF cria um README com os metadados ao criar o Space —
> basta não sobrescrevê-lo, ou colar o bloco acima no topo dele).

## 3. Envie o código para o Space
No terminal, dentro do projeto, adicione o Space como um remoto e faça push
(use seu **token do HF** como senha — gere em *Settings → Access Tokens*, tipo
*Write*):

```bash
git remote add space https://huggingface.co/spaces/SEU_USUARIO/auction-intel
git push space main
```

O que vai junto (o Dockerfile copia): `src/`, `models/` (os `.pkl`), `web/`,
`pyproject.toml`, `uv.lock`, `README.md` e `Dockerfile`. Datasets e `.env` **não** vão (ver
`.dockerignore`).

## 4. Configure a chave do LLM (Secrets)
Na página do Space → **Settings → Variables and secrets**, adicione:

| Nome | Tipo | Valor |
|---|---|---|
| `LLM_API_KEY` | **Secret** | sua chave (a chave do provedor de LLM) |
| `LLM_BASE_URL` | Variable | `https://openrouter.ai/api/v1` |
| `LLM_MODEL` | Variable | `google/gemma-4-26b-a4b-it:free` |

Sem essas variáveis o app sobe normalmente — só o botão "Analisar edital"
responde "LLM não configurada".

## 5. Aguarde o build e abra
O HF constrói a imagem automaticamente (o primeiro build baixa o Chromium e pode
levar alguns minutos). Acompanhe em **Logs**. Quando ficar *Running*, o app abre
na própria página do Space.

---

## Notas importantes
- **Piso ITBI:** os arquivos `datasets/*.csv` (23 MB) **não** vão para a imagem.
  O piso continua funcionando no tier **estimado** (modelo geo, que está no
  `.pkl`) usando a coordenada do bairro. Para habilitar o tier **cadastral**
  (SQL exato), adicione `datasets/iptu_index.csv` e `datasets/quadra_coords.csv`
  ao repositório do Space e ajuste o `Dockerfile`/`.dockerignore` para copiá-los.
- **Banco (SQLite):** o disco do Space é efêmero — contas e watchlist são
  reiniciadas a cada rebuild. Suficiente para demonstração.
- **Cold start:** o Space "dorme" após inatividade; a primeira visita pode levar
  ~30–60 s para acordar.
- **Escala:** a varredura abre o Chromium ao vivo; em CPU free leva ~1–2 min.

## Testar a imagem localmente (opcional, precisa do Docker Desktop aberto)
```bash
docker compose up --build
```
Depois acesse **http://localhost:8000**.
