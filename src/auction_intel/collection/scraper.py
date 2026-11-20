import logging
import re
import time

import requests
from typing import List, Dict, Any
from playwright.sync_api import sync_playwright, Page
from auction_intel.config import settings
from auction_intel.schemas.output import ImovelPreview

logger = logging.getLogger(__name__)

# ==============================================================================
# ESTATÍSTICAS DE MERCADO
# ==============================================================================
AREA_STATS = {
    20: {'bedrooms': 1, 'bathrooms': 1, 'garage': 1},
    30: {'bedrooms': 1, 'bathrooms': 1, 'garage': 1},
    40: {'bedrooms': 1, 'bathrooms': 1, 'garage': 1},
    50: {'bedrooms': 2, 'bathrooms': 1, 'garage': 1},
    60: {'bedrooms': 2, 'bathrooms': 2, 'garage': 1},
    70: {'bedrooms': 2, 'bathrooms': 2, 'garage': 1},
    80: {'bedrooms': 2, 'bathrooms': 2, 'garage': 2},
    90: {'bedrooms': 3, 'bathrooms': 2, 'garage': 2},
    100: {'bedrooms': 3, 'bathrooms': 3, 'garage': 2},
    110: {'bedrooms': 3, 'bathrooms': 3, 'garage': 2},
    120: {'bedrooms': 3, 'bathrooms': 3, 'garage': 2},
    130: {'bedrooms': 3, 'bathrooms': 3, 'garage': 2},
    140: {'bedrooms': 3, 'bathrooms': 3, 'garage': 2},
    150: {'bedrooms': 3, 'bathrooms': 3, 'garage': 2},
    160: {'bedrooms': 3, 'bathrooms': 4, 'garage': 2},
    170: {'bedrooms': 3, 'bathrooms': 4, 'garage': 3},
    180: {'bedrooms': 3, 'bathrooms': 4, 'garage': 3},
    190: {'bedrooms': 3, 'bathrooms': 4, 'garage': 3},
    200: {'bedrooms': 4, 'bathrooms': 4, 'garage': 3},
    210: {'bedrooms': 3, 'bathrooms': 4, 'garage': 3},
    220: {'bedrooms': 4, 'bathrooms': 4, 'garage': 3},
    230: {'bedrooms': 3, 'bathrooms': 4, 'garage': 3},
    240: {'bedrooms': 3, 'bathrooms': 4, 'garage': 3},
    250: {'bedrooms': 4, 'bathrooms': 4, 'garage': 4},
    260: {'bedrooms': 4, 'bathrooms': 4, 'garage': 3},
    270: {'bedrooms': 4, 'bathrooms': 4, 'garage': 4},
    280: {'bedrooms': 4, 'bathrooms': 4, 'garage': 3},
    290: {'bedrooms': 4, 'bathrooms': 5, 'garage': 3},
    300: {'bedrooms': 4, 'bathrooms': 4, 'garage': 4},
    310: {'bedrooms': 4, 'bathrooms': 5, 'garage': 4},
    320: {'bedrooms': 4, 'bathrooms': 4, 'garage': 4},
    330: {'bedrooms': 4, 'bathrooms': 4, 'garage': 4},
    340: {'bedrooms': 4, 'bathrooms': 4, 'garage': 3},
    350: {'bedrooms': 4, 'bathrooms': 5, 'garage': 3},
    360: {'bedrooms': 4, 'bathrooms': 4, 'garage': 4},
    370: {'bedrooms': 4, 'bathrooms': 5, 'garage': 5},
    380: {'bedrooms': 4, 'bathrooms': 4, 'garage': 4},
    390: {'bedrooms': 4, 'bathrooms': 4, 'garage': 4},
    400: {'bedrooms': 4, 'bathrooms': 4, 'garage': 4},
    410: {'bedrooms': 3, 'bathrooms': 5, 'garage': 4},
    420: {'bedrooms': 4, 'bathrooms': 4, 'garage': 7},
    430: {'bedrooms': 3, 'bathrooms': 6, 'garage': 6},
    440: {'bedrooms': 4, 'bathrooms': 5, 'garage': 3},
    450: {'bedrooms': 4, 'bathrooms': 5, 'garage': 3},
    460: {'bedrooms': 3, 'bathrooms': 5, 'garage': 3},
    470: {'bedrooms': 4, 'bathrooms': 6, 'garage': 5},
    480: {'bedrooms': 4, 'bathrooms': 5, 'garage': 4},
    490: {'bedrooms': 4, 'bathrooms': 5, 'garage': 2},
    500: {'bedrooms': 4, 'bathrooms': 5, 'garage': 4},
    510: {'bedrooms': 4, 'bathrooms': 5, 'garage': 3},
    530: {'bedrooms': 3, 'bathrooms': 5, 'garage': 4},
    540: {'bedrooms': 4, 'bathrooms': 6, 'garage': 4},
    550: {'bedrooms': 3, 'bathrooms': 5, 'garage': 5},
    560: {'bedrooms': 3, 'bathrooms': 6, 'garage': 5},
    570: {'bedrooms': 4, 'bathrooms': 6, 'garage': 8},
    590: {'bedrooms': 6, 'bathrooms': 3, 'garage': 5},
    600: {'bedrooms': 1, 'bathrooms': 3, 'garage': 1},
    630: {'bedrooms': 4, 'bathrooms': 6, 'garage': 4},
    640: {'bedrooms': 3, 'bathrooms': 6, 'garage': 6},
    660: {'bedrooms': 4, 'bathrooms': 6, 'garage': 5},
    670: {'bedrooms': 4, 'bathrooms': 3, 'garage': 2},
}
# ==============================================================================


# Frase institucional que NÃO se refere à ocupação do imóvel (evita falso positivo)
_OCCUPANCY_BOILERPLATE = re.compile(r"im[óo]veis\s+desocupados", re.IGNORECASE)


def parse_detail_fields(text: str) -> Dict[str, Any]:
    """Extrai campos estruturados do TEXTO da página de detalhe do leilão.

    Função pura (só regex sobre texto) — separada da parte de rede para ser
    testável sem navegador. Retorna dict com chaves sempre presentes:
    full_address, occupancy, appraisal_value, cadastral_sql (None quando ausente).
    """
    out: Dict[str, Any] = {
        "full_address": None, "occupancy": None,
        "appraisal_value": None, "cadastral_sql": None,
    }
    if not text:
        return out

    flat = re.sub(r"\s+", " ", text)

    # ── Endereço completo (campo "Localização") ────────────────────────────
    m = re.search(r"Localiza[çc][ãa]o\s+(.+?)\s+(?:Comitente|Leiloeiro|Valor de Avalia)", flat)
    if not m:
        m = re.search(r"Localiza[çc][ãa]o\s+(.+?(?:S[ãa]o Paulo(?:,?\s*SP)?|,\s*SP))\b", flat)
    if m:
        addr = m.group(1).strip(" .,")
        if len(addr) > 5:
            out["full_address"] = addr

    # ── Ocupação (prioriza o padrão da descrição "..., Ocupado.") ──────────
    m = re.search(r",\s*(Ocupad[oa]|Desocupad[oa]|Desabitad[oa]|Livre)\b", flat, re.IGNORECASE)
    if not m:
        cleaned = _OCCUPANCY_BOILERPLATE.sub("", flat)
        m = re.search(r"\b(OCUPADO|DESOCUPAD[OA]|DESABITAD[OA])\b", cleaned)
    if m:
        v = m.group(1).lower()
        if v.startswith("deso") or v.startswith("desa"):
            out["occupancy"] = "Desocupado"
        elif v.startswith("ocup"):
            out["occupancy"] = "Ocupado"
        else:
            out["occupancy"] = m.group(1).title()

    # ── Valor de avaliação (None quando "R$ 0,00 / Não informado") ─────────
    m = re.search(r"Valor de Avalia[çc][ãa]o\s*R\$\s*([\d.]+,\d{2})", flat)
    if m:
        val = float(m.group(1).replace(".", "").replace(",", "."))
        out["appraisal_value"] = val if val > 0 else None

    # ── SQL cadastral (permite join com IPTU) ──────────────────────────────
    # Os editais usam rótulos variados: "Inscrição da Prefeitura", "Contribuinte
    # nº" etc. Tentamos os rótulos e, por fim, o padrão puro SSS.QQQ.LLLL-D.
    m = (re.search(r"Inscri[çc][ãa]o da Prefeitura:?\s*(\d{3}\.\d{3}\.\d{4}-\d)", flat)
         or re.search(r"Contribuinte\s*n?[ºo.]*\s*(\d{3}\.\d{3}\.\d{4}-\d)", flat, re.IGNORECASE)
         or re.search(r"\b(\d{3}\.\d{3}\.\d{4}-\d)\b", flat))
    if m:
        out["cadastral_sql"] = m.group(1)

    return out


class GeocodingService:
    BASE_URL = "https://nominatim.openstreetmap.org/search"
    _cache = {}

    def get_coordinates(self, query: str) -> Dict[str, float]:
        """Busca coordenadas com cache e múltiplas tentativas de formatação."""
        if query in self._cache: return self._cache[query]
        
        # Default: Marco Zero (Sé)
        default = {'lat': -23.5505, 'lon': -46.6333}
        if not query or len(query) < 2: return default

        # Limpeza: Remove "Bairro" para não confundir a API
        clean_query = query.replace("Bairro", "").strip()
        
        # Estratégias de busca (do mais específico para o geral)
        attempts = [
            f"{clean_query}, São Paulo, Brazil",  # Ex: Santana, São Paulo, Brazil
            f"{clean_query}, SP, Brazil",         # Ex: Santana, SP, Brazil
            f"{clean_query}, Brazil"              # Ex: Santana, Brazil
        ]
        
        headers = {'User-Agent': 'AuctionSniper_Bot/5.0'} 

        for q in attempts:
            try:
                # Delay para evitar bloqueio da API (Rate Limit)
                time.sleep(0.5)
                
                resp = requests.get(
                    self.BASE_URL, 
                    params={'q': q, 'format': 'json', 'limit': 1}, 
                    headers=headers, 
                    timeout=3
                )
                
                if resp.ok and resp.json():
                    data = resp.json()[0]
                    lat, lon = float(data['lat']), float(data['lon'])
                    
                    # Filtro Geográfico: Garante que caiu dentro do estado de SP aprox.
                    if -26 < lat < -19:
                        res = {'lat': lat, 'lon': lon}
                        self._cache[query] = res
                        return res
            except Exception:
                continue
        
        # Se falhar tudo, salva o default no cache para não tentar de novo
        self._cache[query] = default
        return default

    def get_coordinates_for_address(self, address: str) -> Dict[str, float]:
        """Geocoding PRECISO a partir do endereço completo (página de detalhe).

        Diferente de `get_coordinates` (que resolve por bairro), aqui usamos a
        rua+número → coordenada por imóvel. Cai no marco zero (Sé) se falhar.
        """
        default = {'lat': -23.5505, 'lon': -46.6333}
        if not address or len(address) < 6:
            return default

        key = f"addr::{address}"
        if key in self._cache:
            return self._cache[key]

        # Nominatim frequentemente NÃO resolve o endereço com complemento
        # ("Conjunto Residencial X"). Geramos variantes progressivas, isolando
        # "rua, número, São Paulo, SP" — que resolve na coordenada do imóvel.
        parts = [p.strip() for p in address.split(",") if p.strip()]
        street = parts[0] if parts else address
        number = parts[1] if len(parts) > 1 and re.search(r"\d", parts[1]) else None
        street_num = f"{street}, {number}" if number else street

        raw = [
            address if ("bra" in address.lower()) else f"{address}, Brazil",
            f"{street_num}, São Paulo, SP, Brazil",
            f"{street}, São Paulo, SP, Brazil",
        ]
        attempts = list(dict.fromkeys(raw))  # remove duplicatas preservando ordem

        headers = {'User-Agent': 'AuctionSniper_Bot/5.0'}
        for q in attempts:
            try:
                time.sleep(0.5)  # respeita o rate limit do Nominatim
                resp = requests.get(
                    self.BASE_URL,
                    params={'q': q, 'format': 'json', 'limit': 1},
                    headers=headers, timeout=5,
                )
                if resp.ok and resp.json():
                    d = resp.json()[0]
                    lat, lon = float(d['lat']), float(d['lon'])
                    # Bounding box aproximado da RMSP
                    if -24.5 < lat < -23.0 and -47.3 < lon < -46.0:
                        res = {'lat': lat, 'lon': lon}
                        self._cache[key] = res
                        return res
            except Exception:
                continue

        self._cache[key] = default
        return default

class BrowserService:
    def __init__(self):
        self.headless = settings.HEADLESS_BROWSER
    
    def run_task(self, url: str, callback_func, **kwargs) -> Any:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless, args=["--start-maximized"])
            # Contexto com User-Agent real para evitar detecção básica
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            )
            page = context.new_page()
            try:
                page.goto(url, timeout=60000)
                return callback_func(self, page, **kwargs)
            except Exception as e:
                logger.error("Erro crítico no navegador: %s", e)
                return None
            finally:
                browser.close()

class AuctionTools:
    def __init__(self):
        self.browser_service = BrowserService()
        self.geocoder = GeocodingService()

    def _extract_number(self, text: str) -> float:
        if not text: return 0.0
        clean = re.sub(r'[^\d,]', '', text)
        try: return float(clean.replace(',', '.'))
        except: return 0.0

    def _infer_features_from_area(self, area: float) -> dict:
        """
        Consulta o mapa estatístico (AREA_STATS) para preencher dados faltantes.
        """
        if area <= 0: return {'bedrooms': 1, 'bathrooms': 1, 'garage': 0}
        
        # Binning: Arredonda para a dezena mais próxima para bater com as chaves do dict
        area_bin = int((area // 10) * 10)
        
        # Garante que está dentro dos limites do nosso dicionário
        if not AREA_STATS: return {'bedrooms': 2, 'bathrooms': 1, 'garage': 1} # Fallback se dict vazio
        
        min_bin = min(AREA_STATS.keys())
        max_bin = max(AREA_STATS.keys())
        
        if area_bin < min_bin: area_bin = min_bin
        if area_bin > max_bin: area_bin = max_bin
        
        return AREA_STATS.get(area_bin, {'bedrooms': 2, 'bathrooms': 1, 'garage': 1})

    def _scrape_listings_logic(self, _service, page: Page) -> List[ImovelPreview]:
        """Extrai dados dos cards da listagem."""
        try: 
            page.wait_for_selector(".card-content", timeout=5000)
        except: 
            pass

        cards = page.query_selector_all(".card-content")
        logger.info("Processando %d cards...", len(cards))
        
        results = []
        for card in cards:
            title_debug = "Desconhecido"
            try:
                title_el = card.query_selector(".card-title")
                price_el = card.query_selector(".card-price")
                
                if not title_el or not price_el: continue

                title = title_el.inner_text().strip()
                title_debug = title # Para log de erro
                
                link = title_el.get_attribute("href")
                if link and link.startswith("/"): link = f"https://www.megaleiloes.com.br{link}"
                
                price = self._extract_number(price_el.inner_text().strip())
                
                # 1. Extração de Área (Regex)
                area = 0.0
                area_match = re.search(r'(\d+)\s*m²', title, re.IGNORECASE)
                if area_match: area = float(area_match.group(1))

                # 2. Extração de Bairro (Lógica de Hífen)
                district = "São Paulo"
                # Limpa sufixos comuns
                clean_title = title.replace(" - SP", "").replace(" - São Paulo", "").replace(" / SP", "")
                if "-" in clean_title:
                    # Pega o último pedaço após o traço
                    district = clean_title.split("-")[-1].strip().title()

                # 3. Tenta Regex para Vagas e Quartos
                garage = 0
                bedrooms = 0
                
                garage_match = re.search(r'(\d+)\s*(?:vaga|garagem|auto)', title, re.IGNORECASE)
                if garage_match: garage = int(garage_match.group(1))
                
                bed_match = re.search(r'(\d+)\s*(?:dorm|quarto|suíte|suite)', title, re.IGNORECASE)
                if bed_match: bedrooms = int(bed_match.group(1))

                # 4. Inferência Estatística (Preenche o que faltou)
                # Banheiros quase nunca tem no título, então sempre inferimos ou usamos default
                bathrooms = 1
                
                if area > 10:
                    stats = self._infer_features_from_area(area)
                    if bedrooms == 0: bedrooms = stats['bedrooms']
                    if garage == 0: garage = stats['garage']
                    bathrooms = stats['bathrooms']

                # Extração da imagem (data-bg do elemento .card-image irmão)
                image_url = card.evaluate(
                    "el => { const img = el.parentElement.querySelector('.card-image'); return img ? img.getAttribute('data-bg') : null; }"
                )

                # Filtro de qualidade e criação do objeto
                if price > 1000 and area > 10:
                    item = ImovelPreview(
                        title=title,
                        link=link,
                        district=district,
                        area_m2=area,
                        auction_price=price,
                        bedrooms=bedrooms,
                        parking_spaces=garage,
                        bathrooms=bathrooms,
                        image_url=image_url,
                    )
                    results.append(item)

            except Exception as e:
                # AGORA O ERRO É MOSTRADO NO TERMINAL
                logger.warning("Erro ao processar card '%s': %s", title_debug, e)
                continue
        
        return results

    def _scrape_all_pages_logic(self, _service, page: Page, base_url: str) -> List[ImovelPreview]:
        """Percorre as páginas da vitrine (?pagina=N) até esgotar.

        A vitrine do Mega Leilões é paginada; o robô lê a página 1 (já carregada),
        depois navega para pagina=2, 3, … acumulando. Para quando uma página não
        traz nenhum imóvel NOVO (vazia ou repetida) ou atinge o teto de páginas.
        """
        MAX_PAGES = settings.VARREDURA_MAX_PAGES  # ambientes leves: defina 1
        todos, vistos = [], set()
        for pg in range(1, MAX_PAGES + 1):
            if pg > 1:
                sep = "&" if "?" in base_url else "?"
                try:
                    page.goto(f"{base_url}{sep}pagina={pg}", timeout=60000)
                except Exception:
                    break
            page_items = self._scrape_listings_logic(_service, page)
            novos = [it for it in page_items if it.link and it.link not in vistos]
            if not novos:
                break
            for it in novos:
                vistos.add(it.link)
            todos.extend(novos)
            logger.info("Página %d: +%d imóveis (total %d)", pg, len(novos), len(todos))
        return todos

    # --- MÉTODOS PÚBLICOS ---
    def fetch_listings(self, url: str) -> List[ImovelPreview]:
        return self.browser_service.run_task(url, self._scrape_all_pages_logic, base_url=url) or []

    def get_geo_location(self, district: str) -> Dict[str, float]:
        return self.geocoder.get_coordinates(district)

    def scrape_property_details(self, url: str) -> Dict[str, Any]:
        """Acessa a página interna para pegar texto completo (Fase 2)."""
        def logic(_s, p):
            p.wait_for_load_state("networkidle")
            return {"full_text_content": p.evaluate("() => document.body.innerText")}
        return self.browser_service.run_task(url, logic)

    def enrich_from_detail(self, item: ImovelPreview) -> ImovelPreview:
        """Enriquece um item da listagem com dados da PÁGINA DE DETALHE.

        Abre a página do imóvel, extrai endereço/ocupação/avaliação (parsing puro)
        e, havendo endereço, geocodifica de forma PRECISA (por imóvel, não por
        bairro). Preenche item.full_address / occupancy / appraisal_value /
        latitude / longitude. Em caso de falha, devolve o item inalterado.
        """
        detail = self.scrape_property_details(item.link)
        if not detail or not detail.get("full_text_content"):
            return item

        fields = parse_detail_fields(detail["full_text_content"])
        item.full_address = fields.get("full_address")
        item.occupancy = fields.get("occupancy")
        item.appraisal_value = fields.get("appraisal_value")
        item.cadastral_sql = fields.get("cadastral_sql")

        if fields.get("full_address"):
            coords = self.geocoder.get_coordinates_for_address(fields["full_address"])
            item.latitude = coords["lat"]
            item.longitude = coords["lon"]

        return item

    def fetch_cadastral_sql(self, url: str) -> str:
        """Pega SÓ o SQL (Inscrição/Contribuinte) da página de detalhe via HTTP.

        Rápido (sem navegador) — a página do Mega Leilões é server-side, então o
        SQL já vem no HTML. Usado para valorar todos os imóveis via ITBI sem o
        custo de abrir o navegador por imóvel. Retorna None se não encontrar.
        """
        try:
            resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
            fields = parse_detail_fields(resp.text)
            return fields.get("cadastral_sql")
        except Exception:
            return None