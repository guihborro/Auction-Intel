"""
edital_agent.py — Dossiê jurídico do lote a partir do edital + matrícula (LLM).

Pipeline (on-demand, por imóvel):
    página do lote -> links PDF (edital + matrícula)
      -> download -> texto (PyMuPDF)
      -> LLM (endpoint OpenAI-compatible; default Google Gemini Flash) estrutura
         os fatos ESPECÍFICOS do imóvel (ignorando boilerplate) em JSON tipado
      -> calcula o total de débitos por conta do arrematante.

Provider-agnóstico: `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` vêm do config/.env.
Sem chave configurada, devolve {ok: False, reason} de forma limpa.
"""
import json
import re

import fitz  # PyMuPDF (dependência do projeto)
import requests

from auction_intel.config import settings

HEADERS = {"User-Agent": "Mozilla/5.0"}
MAX_EDITAL_CHARS = 80_000
MAX_MATRICULA_CHARS = 40_000

_SCHEMA_HINT = """Responda APENAS com um objeto JSON (sem markdown, sem texto extra) neste formato:
{
  "tipo_leilao": "Judicial" | "Extrajudicial" | "Não informado",
  "tipo_direito": string,                // "Propriedade plena" ou "Somente direitos aquisitivos" (quando é 'direitos sobre' o imóvel) — explique curto
  "ocupacao": "Ocupado" | "Desocupado" | "Não informado",
  "prazo_desocupacao": string | null,    // se o edital falar de prazo/quem desocupa
  "valor_avaliacao": number | null,      // R$
  "debito_iptu": number | null,          // R$, só se o valor for informado
  "debito_condominio": number | null,    // R$
  "divida_ativa": number | null,         // R$
  "debitos_responsavel": "arrematante" | "vendedor" | "não informado",
  "condicoes_pagamento": string,         // à vista/parcelado, entrada, prazos — em linguagem SIMPLES
  "comissao_leiloeiro": string | null,   // ex.: "5%"
  "onus_gravames": [string],             // ônus REAIS na matrícula (hipoteca, penhora, usufruto, alienação fiduciária...) — [] se não houver
  "aceita_financiamento": true | false | null,
  "nivel_risco": "Baixo" | "Médio" | "Alto",
  "resumo_leigo": string,                // 2-4 frases explicando a situação do imóvel para uma pessoa LEIGA, sem juridiquês
  "pontos_positivos": [string],          // vantagens em linguagem simples
  "pontos_atencao": [string],            // riscos EXPLICADOS em linguagem simples (o que significa e por que importa)
  "glossario": [ {"termo": string, "explicacao": string} ],  // CADA termo jurídico/técnico que aparece neste lote (ex.: extrajudicial, ônus, hipoteca, usufruto, praça, arrematante, comissão, HIS/HMP, alienação fiduciária), explicado em 1 frase simples
  "recomendacao": string                 // veredito em linguagem simples + o porquê, como se explicasse a um amigo leigo
}"""

_SYSTEM = (
    "Você é um consultor de leilões de imóveis que explica tudo para uma pessoa LEIGA, sem "
    "conhecimento jurídico. A partir do EDITAL e da MATRÍCULA de um lote, extraia os fatos "
    "específicos DESTE imóvel (ignore cláusulas genéricas/boilerplate) E traduza tudo para "
    "linguagem simples e acessível. Regras: (1) nos campos de texto, NÃO use juridiquês — "
    "escreva como se explicasse a um amigo; (2) no 'glossario', explique TODO termo técnico "
    "que aparecer neste lote, em 1 frase clara; (3) quando um dado não estiver informado, use "
    "null (não invente valores). Responda só com JSON válido."
)


class EditalAgent:
    def __init__(self):
        self.model = settings.LLM_MODEL
        self.key = settings.LLM_API_KEY
        self.client = None
        if self.key:
            from openai import OpenAI
            self.client = OpenAI(api_key=self.key, base_url=settings.LLM_BASE_URL)

    # ── Coleta de PDFs ──────────────────────────────────────────────────────
    def _pdf_links(self, detail_url: str):
        html = requests.get(detail_url, headers=HEADERS, timeout=20).text
        pdfs = re.findall(r'https://[^\s"\'<>]+\.pdf', html)
        edital, matricula = None, None
        for p in dict.fromkeys(pdfs):
            low = p.lower()
            if "megaleiloes" not in low:
                continue
            if "edital" in low and not edital:
                edital = p
            elif "matricula" in low and not matricula:
                matricula = p
        return edital, matricula

    def _pdf_text(self, url: str, cap: int) -> str:
        try:
            data = requests.get(url, headers=HEADERS, timeout=60).content
            doc = fitz.open(stream=data, filetype="pdf")
            txt = " ".join(page.get_text() for page in doc)
            return re.sub(r"\s+", " ", txt)[:cap]
        except Exception:
            return ""

    # ── LLM ─────────────────────────────────────────────────────────────────
    @staticmethod
    def _parse_json(content: str) -> dict:
        content = re.sub(r"^```(?:json)?|```$", "", content.strip(), flags=re.MULTILINE).strip()
        a, b = content.find("{"), content.rfind("}")
        return json.loads(content[a:b + 1])

    def analisar(self, detail_url: str) -> dict:
        if not self.client:
            return {"ok": False, "reason": "LLM não configurada — defina LLM_API_KEY no .env."}

        edital_url, matricula_url = self._pdf_links(detail_url)
        fontes, corpus = [], []
        if edital_url:
            t = self._pdf_text(edital_url, MAX_EDITAL_CHARS)
            if t: corpus.append("=== EDITAL ===\n" + t); fontes.append(edital_url)
        if matricula_url:
            t = self._pdf_text(matricula_url, MAX_MATRICULA_CHARS)
            if t: corpus.append("=== MATRÍCULA ===\n" + t); fontes.append(matricula_url)
        if not corpus:
            return {"ok": False, "reason": "Nenhum PDF (edital/matrícula) encontrado no lote."}

        try:
            resp = self.client.chat.completions.create(
                model=self.model, temperature=0,
                messages=[
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user", "content": _SCHEMA_HINT + "\n\nDOCUMENTOS:\n" + "\n\n".join(corpus)},
                ],
            )
            data = self._parse_json(resp.choices[0].message.content)
        except Exception as e:
            return {"ok": False, "reason": f"Falha na análise: {str(e)[:120]}"}

        # Total de débitos por conta do arrematante (conservador quando indefinido)
        resp_ = str(data.get("debitos_responsavel") or "").lower()
        debitos = [data.get("debito_iptu"), data.get("debito_condominio"), data.get("divida_ativa")]
        total = sum(v for v in debitos if isinstance(v, (int, float)))
        data["debito_total_arrematante"] = round(total, 2) if "vendedor" not in resp_ else 0.0

        data["ok"] = True
        data["fonte_pdfs"] = fontes
        for k in ("onus_gravames", "pontos_positivos", "pontos_atencao", "glossario"):
            data.setdefault(k, [])
        return data
