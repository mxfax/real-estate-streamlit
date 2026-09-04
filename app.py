import io
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import urllib.parse

from bs4 import BeautifulSoup
from curl_cffi import requests
import pandas as pd
import streamlit as st

# ==============================================================================
# TRANSLATION DICTIONARY (EN, PT, UA)
# ==============================================================================

TRANSLATIONS = {
    "EN": {
        "title": "Portugal Real Estate Intelligence Hub",
        "subtitle": "Real-time listings across Portugal with automated Deal Scoring (€/m²), ROI calculators, and cross-portal analytics.",
        "author": "⚡ Engineered & Designed by Max",
        "search_setup": "🔍 Search Target",
        "location": "City or Municipality",
        "portals": "Select Active Portals",
        "pages": "Pages per site",
        "filters": "🎯 Listing Filters",
        "min_price": "Min Price (€)",
        "max_price": "Max Price (€)",
        "typology": "Typology",
        "bargain_only": "🔥 Show only Bargains (>15% below median €/m²)",
        "sort_by": "Sort By",
        "sort_lowest": "Lowest Price First (€ ↑)",
        "sort_highest": "Highest Price First (€ ↓)",
        "sort_m2": "Best Price/m² (Lowest €/m²)",
        "sort_default": "Portal Default",
        "btn_search": "🚀 Fetch Properties",
        "warning_select": "Please select at least one portal from the sidebar.",
        "fetching": "Aggregating live listings across {count} portals for '{loc}'...",
        "no_results": "No listings returned. The selected sites might have temporarily blocked requests or returned 0 matches.",
        "success_status": "Aggregated {total} total listings ({status})",
        "kpi_total": "Available Listings",
        "kpi_median_price": "Median Listing Price",
        "kpi_median_m2": "Median Market €/m²",
        "kpi_portals": "Active Portals",
        "tab_grid": "📋 Listings Grid",
        "tab_analytics": "📊 Market Analytics",
        "tab_simulator": "💰 Mortgage & Investment Simulator",
        "tab_diagnostics": "🛠️ Scraper Diagnostics",
        "btn_export": "📥 Export Results to Excel (.xlsx)",
        "col_portal": "Portal",
        "col_deal": "Deal Score",
        "col_title": "Title",
        "col_price": "Price (€)",
        "col_typology": "Typology",
        "col_area": "Area (m²)",
        "col_m2": "Price/m²",
        "col_link": "Direct Link",
        "link_text": "Open Listing",
        "sim_title": "Interactive Mortgage & Yield Calculator",
        "sim_caption": "Calculate your estimated monthly payment and rental yield on any property in your results.",
        "prop_price": "Property Price (€)",
        "down_payment": "Down Payment (%)",
        "interest_rate": "Interest Rate (%)",
        "loan_years": "Loan Duration (Years)",
        "monthly_rent": "Estimated Monthly Rent (€)",
        "fin_breakdown": "Financial Breakdown",
        "fin_amount": "Financed Amount",
        "fin_monthly": "Estimated Monthly Mortgage",
        "fin_yield": "Gross Annual Rental Yield",
        "fin_cashflow": "Estimated Cashflow",
        "footer": "Portugal Real Estate Multi-Scraper Platform • Built with Python & Streamlit • Made by Max",
        "bargain_badge": "🔥 Bargain (-15%+)",
        "premium_badge": "⚠️ High Premium",
        "fair_badge": "Fair Market"
    },
    "PT": {
        "title": "Hub de Inteligência Imobiliária de Portugal",
        "subtitle": "Pesquisa em tempo real com avaliação automática (€/m²), simulador de crédito habitação e métricas de mercado.",
        "author": "⚡ Criado & Desenvolvido por Max",
        "search_setup": "🔍 Configuração da Pesquisa",
        "location": "Cidade ou Município",
        "portals": "Portais Ativos",
        "pages": "Páginas por portal",
        "filters": "🎯 Filtros de Anúncios",
        "min_price": "Preço Mínimo (€)",
        "max_price": "Preço Máximo (€)",
        "typology": "Tipologia",
        "bargain_only": "🔥 Apenas Oportunidades (>15% abaixo da mediana €/m²)",
        "sort_by": "Ordenar Por",
        "sort_lowest": "Mais Baratos Primeiro (€ ↑)",
        "sort_highest": "Mais Caros Primeiro (€ ↓)",
        "sort_m2": "Melhor Preço/m² (Menor €/m²)",
        "sort_default": "Ordem Padrão",
        "btn_search": "🚀 Pesquisar Imóveis",
        "warning_select": "Por favor, selecione pelo menos um portal na barra lateral.",
        "fetching": "A recolher imóveis em direto em {count} portais para '{loc}'...",
        "no_results": "Nenhum imóvel encontrado nos portais selecionados. Verifique o separador Diagnósticos.",
        "success_status": "Encontrados {total} imóveis no total ({status})",
        "kpi_total": "Imóveis Disponíveis",
        "kpi_median_price": "Preço Mediano",
        "kpi_median_m2": "Mediana de Mercado €/m²",
        "kpi_portals": "Portais a Responder",
        "tab_grid": "📋 Grelha de Imóveis",
        "tab_analytics": "📊 Análise de Mercado",
        "tab_simulator": "💰 Simulador de Crédito & ROI",
        "tab_diagnostics": "🛠️ Diagnóstico dos Scrapers",
        "btn_export": "📥 Descarregar Resultados em Excel (.xlsx)",
        "col_portal": "Portal",
        "col_deal": "Classificação",
        "col_title": "Título",
        "col_price": "Preço (€)",
        "col_typology": "Tipologia",
        "col_area": "Área (m²)",
        "col_m2": "Preço/m²",
        "col_link": "Link Direto",
        "link_text": "Ver Anúncio",
        "sim_title": "Simulador Interativo de Crédito e Rentabilidade",
        "sim_caption": "Calcule a mensalidade estimada e a rentabilidade bruta para qualquer imóvel.",
        "prop_price": "Preço do Imóvel (€)",
        "down_payment": "Entrada Inicial (%)",
        "interest_rate": "Taxa de Juro (%)",
        "loan_years": "Duração do Empréstimo (Anos)",
        "monthly_rent": "Renda Mensal Estimada (€)",
        "fin_breakdown": "Resumo Financeiro",
        "fin_amount": "Capital Financiado",
        "fin_monthly": "Prestação Mensal Estimada",
        "fin_yield": "Yield Bruta Anual",
        "fin_cashflow": "Cashflow Estimado",
        "footer": "Plataforma de Agregação Imobiliária em Portugal • Desenvolvido com Streamlit • Criado por Max",
        "bargain_badge": "🔥 Oportunidade (-15%+)",
        "premium_badge": "⚠️ Acima da Média",
        "fair_badge": "Preço Justo"
    },
    "UA": {
        "title": "Портал аналітики нерухомості Португалії",
        "subtitle": "Пошук оголошень у реальному часі з автоматичним оцінюванням (€/м²), іпотечним калькулятором та аналітикою.",
        "author": "⚡ Розроблено та створено Max",
        "search_setup": "🔍 Налаштування пошуку",
        "location": "Місто або муніципалітет",
        "portals": "Обрані портали",
        "pages": "Сторінок на портал",
        "filters": "🎯 Фільтри оголошень",
        "min_price": "Мін. ціна (€)",
        "max_price": "Макс. ціна (€)",
        "typology": "Типологія (кімнати)",
        "bargain_only": "🔥 Тільки вигідні пропозиції (>15% нижче медіани €/м²)",
        "sort_by": "Сортувати за",
        "sort_lowest": "Спочатку дешевші (€ ↑)",
        "sort_highest": "Спочатку дорожчі (€ ↓)",
        "sort_m2": "Найкраща ціна за м² (найменша €/м²)",
        "sort_default": "За замовчуванням",
        "btn_search": "🚀 Шукати нерухомість",
        "warning_select": "Будь ласка, оберіть хоча б один портал на панелі збоку.",
        "fetching": "Збір актуальних пропозицій із {count} порталів для '{loc}'...",
        "no_results": "Нічого не знайдено. Перевірте вкладку Діагностика для деталей.",
        "success_status": "Зібрано {total} оголошень ({status})",
        "kpi_total": "Знайдено об'єктів",
        "kpi_median_price": "Медіанна ціна",
        "kpi_median_m2": "Медіана ринку €/м²",
        "kpi_portals": "Активних порталів",
        "tab_grid": "📋 Список оголошень",
        "tab_analytics": "📊 Аналітика ринку",
        "tab_simulator": "💰 Іпотека та дохідність",
        "tab_diagnostics": "🛠️ Діагностика парсерів",
        "btn_export": "📥 Завантажити в Excel (.xlsx)",
        "col_portal": "Портал",
        "col_deal": "Оцінка угоди",
        "col_title": "Заголовок",
        "col_price": "Ціна (€)",
        "col_typology": "Тип",
        "col_area": "Площа (м²)",
        "col_m2": "Ціна/м²",
        "col_link": "Посилання",
        "link_text": "Відкрити",
        "sim_title": "Інтерактивний калькулятор іпотеки та доходу",
        "sim_caption": "Розрахуйте щомісячний внесок та річний дохід від оренди для обраного житла.",
        "prop_price": "Вартість об'єкта (€)",
        "down_payment": "Початковий внесок (%)",
        "interest_rate": "Відсоткова ставка (%)",
        "loan_years": "Термін кредиту (років)",
        "monthly_rent": "Орієнтовна оренда/місяць (€)",
        "fin_breakdown": "Фінансовий підсумок",
        "fin_amount": "Сума кредиту",
        "fin_monthly": "Щомісячний платіж",
        "fin_yield": "Річна валова дохідність",
        "fin_cashflow": "Чистий грошовий потік",
        "footer": "Платформа моніторингу нерухомості Португалії • Побудовано на Streamlit • Автор Max",
        "bargain_badge": "🔥 Вигідна ціна (-15%+)",
        "premium_badge": "⚠️ Вище ринку",
        "fair_badge": "Ринкова ціна"
    }
}

# ==============================================================================
# BROWSER CLIENT & DATA NORMALIZATION
# ==============================================================================

BROWSER_IMPERSONATE = "chrome124"
SAFARI_IMPERSONATE = "safari15_5"
REQUEST_TIMEOUT = 16

COMMON_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "pt-PT,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Upgrade-Insecure-Requests": "1"
}

def clean_num(val):
    if val is None:
        return None
    cleaned = str(val).replace("€", "").replace("m²", "").replace("m2", "").replace("\xa0", " ").replace(".", "").replace(",", ".").strip()
    cleaned = re.sub(r"(\d)\s+(\d)", r"\1\2", cleaned)
    match = re.search(r"\d+(?:\.\d+)?", cleaned)
    return float(match.group()) if match else None

def extract_typology(text):
    if not text:
        return "N/A"
    match = re.search(r"\b(T\d\+?)\b", str(text), re.IGNORECASE)
    return match.group(1).upper() if match else "N/A"

def extract_area(text):
    if not text:
        return None
    match = re.search(r"(\d+[\d\s.,]*)\s*(?:m2|m²)", str(text), re.IGNORECASE)
    if match:
        return clean_num(match.group(1))
    return None

# ==============================================================================
# 1. IMOVIRTUAL SCRAPER
# ==============================================================================

def scrape_imovirtual(query, max_pages=1):
    results = []
    slug = query.strip().lower().replace(" ", "-")

    with requests.Session() as session:
        for page in range(1, max_pages + 1):
            url = f"https://www.imovirtual.com/pt/resultados/comprar/apartamento/{slug}?page={page}"
            try:
                r = session.get(url, headers=COMMON_HEADERS, impersonate=BROWSER_IMPERSONATE, timeout=REQUEST_TIMEOUT)
                if r.status_code != 200: break
                soup = BeautifulSoup(r.text, "lxml")
                next_data = soup.find("script", id="__NEXT_DATA__")
                if next_data and next_data.string:
                    data = json.loads(next_data.string)
                    items = data.get("props", {}).get("pageProps", {}).get("data", {}).get("searchAds", {}).get("items", [])
                    for it in items:
                        title = it.get("title", f"Imóvel em {query.title()}")
                        price_val = it.get("totalPrice", {}).get("value")
                        slug_val = it.get("slug")
                        area_val = it.get("areaInSquareMeters")
                        parsed_price = float(price_val) if price_val else None

                        if parsed_price and parsed_price >= 10000:
                            results.append({
                                "portal": "Imovirtual",
                                "title": title,
                                "price": parsed_price,
                                "typology": extract_typology(title),
                                "area_m2": clean_num(area_val),
                                "location": query.title(),
                                "link": f"https://www.imovirtual.com/pt/anuncio/{slug_val}" if slug_val else url,
                            })
                time.sleep(0.3)
            except Exception:
                break
    return results

# ==============================================================================
# 2. OLX IMÓVEIS (Excludes Imovirtual Links)
# ==============================================================================

def scrape_olx_imoveis(query, max_pages=1):
    results = []
    clean_loc = query.strip().lower().replace(" ", "-")

    with requests.Session() as session:
        for page in range(1, max_pages + 1):
            url = f"https://www.olx.pt/imoveis/q-{clean_loc}/?page={page}"
            try:
                r = session.get(url, headers=COMMON_HEADERS, impersonate=BROWSER_IMPERSONATE, timeout=REQUEST_TIMEOUT)
                if r.status_code != 200: break
                soup = BeautifulSoup(r.text, "lxml")
                cards = soup.find_all(attrs={"data-cy": "l-card"})
                for card in cards:
                    link_elem = card.find("a", href=True)
                    if not link_elem or not link_elem.get("href"):
                        continue
                    href = link_elem["href"]
                    
                    # BLOCK IMOVIRTUAL LINKS - Keep Native OLX Only
                    if "imovirtual.com" in href:
                        continue

                    full_link = f"https://www.olx.pt{href}" if href.startswith("/") else href
                    title_elem = card.find(["h4", "h6"])
                    title = title_elem.get_text(strip=True) if title_elem else "Imóvel OLX"
                    
                    text = card.get_text(" ", strip=True)
                    price_match = re.search(r"(\d[\d\s.,]*)\s*€", text)
                    if price_match:
                        parsed_price = clean_num(price_match.group(1))
                        if parsed_price and parsed_price >= 10000:
                            results.append({
                                "portal": "OLX Imóveis",
                                "title": title[:80],
                                "price": parsed_price,
                                "typology": extract_typology(title + " " + text),
                                "area_m2": extract_area(text),
                                "location": query.title(),
                                "link": full_link.split("?")[0]
                            })
                time.sleep(0.3)
            except Exception:
                break
    return results

# ==============================================================================
# 3. CUSTOJUSTO (Bottom-Up Extractor)
# ==============================================================================

def scrape_custojusto(query, max_pages=1):
    results = []
    clean_query = urllib.parse.quote(query.strip())

    with requests.Session() as session:
        for page in range(1, max_pages + 1):
            url = f"https://www.custojusto.pt/portugal/imobiliario/apartamentos-venda?q={clean_query}&o={page}"
            try:
                r = session.get(url, headers=COMMON_HEADERS, impersonate=BROWSER_IMPERSONATE, timeout=REQUEST_TIMEOUT)
                if r.status_code != 200: break
                soup = BeautifulSoup(r.text, "lxml")
                
                # Resilient extractor based on link pattern
                links = soup.find_all("a", href=re.compile(r"-\d{7,10}$"))
                for a in links:
                    href = a["href"]
                    if "/imobiliario/" not in href: continue
                    
                    # Traverse up to find the card container
                    container = a.parent
                    for _ in range(3):
                        if container and "€" in container.get_text(): break
                        if container: container = container.parent
                    
                    if not container: continue
                    text = container.get_text(" ", strip=True)
                    price_match = re.search(r"(\d[\d\s.]*)\s*€", text)
                    
                    if price_match:
                        parsed_price = clean_num(price_match.group(1))
                        if parsed_price and parsed_price >= 10000:
                            title = a.get_text(strip=True)
                            if len(title) < 5:
                                h_tag = container.find(["h2", "h3"])
                                title = h_tag.get_text(strip=True) if h_tag else f"Imóvel em {query.title()}"
                            
                            results.append({
                                "portal": "CustoJusto",
                                "title": title[:80],
                                "price": parsed_price,
                                "typology": extract_typology(text),
                                "area_m2": extract_area(text),
                                "location": query.title(),
                                "link": href
                            })
                time.sleep(0.3)
            except Exception:
                break
    return results

# ==============================================================================
# 4. CASA SAPO (Safari Impersonation + Bottom-Up Extractor)
# ==============================================================================

def scrape_casasapo(query, max_pages=1):
    results = []
    # Safari headers generally bypass strict cloudflare walls much better than Chrome
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "pt-PT,pt;q=0.9",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.5 Safari/605.1.15",
        "Referer": "https://www.google.pt/"
    }
    
    with requests.Session() as session:
        for page in range(1, max_pages + 1):
            url = f"https://casa.sapo.pt/venda-apartamentos/?q={urllib.parse.quote(query)}&pn={page}"
            try:
                r = session.get(url, headers=headers, impersonate=SAFARI_IMPERSONATE, timeout=REQUEST_TIMEOUT)
                soup = BeautifulSoup(r.text, "lxml")
                
                links = soup.find_all("a", href=True)
                for a in links:
                    href = a["href"]
                    if "/comprar-" not in href and "/imovel/" not in href: continue
                        
                    container = a.parent
                    for _ in range(4):
                        if container and "€" in container.get_text(): break
                        if container: container = container.parent
                    
                    if not container: continue
                    text = container.get_text(" ", strip=True)
                    price_match = re.search(r"(\d[\d\s.,]*)\s*€", text)
                    if price_match:
                        parsed_price = clean_num(price_match.group(1))
                        if parsed_price and parsed_price >= 10000:
                            title = a.get_text(strip=True) or container.find(["h2","h3","span"]).get_text(strip=True) if container.find(["h2","h3","span"]) else f"Imóvel em {query.title()}"
                            results.append({
                                "portal": "Casa Sapo",
                                "title": title[:80],
                                "price": parsed_price,
                                "typology": extract_typology(text),
                                "area_m2": extract_area(text),
                                "location": query.title(),
                                "link": href if href.startswith("http") else f"https://casa.sapo.pt{href}"
                            })
                time.sleep(0.3)
            except Exception:
                break
    return results

# ==============================================================================
# 5. SUPERCASA (Safari Impersonation + Bottom-Up Extractor)
# ==============================================================================

def scrape_supercasa(query, max_pages=1):
    results = []
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "pt-PT,pt;q=0.9",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.5 Safari/605.1.15",
        "Referer": "https://supercasa.pt/"
    }

    with requests.Session() as session:
        for page in range(1, max_pages + 1):
            url = f"https://supercasa.pt/comprar-casas?s={urllib.parse.quote(query)}&pagina={page}"
            try:
                r = session.get(url, headers=headers, impersonate=SAFARI_IMPERSONATE, timeout=REQUEST_TIMEOUT)
                soup = BeautifulSoup(r.text, "lxml")
                
                links = soup.find_all("a", href=re.compile(r"/imovel/|/comprar-"))
                for a in links:
                    container = a.parent
                    for _ in range(4):
                        if container and "€" in container.get_text(): break
                        if container: container = container.parent
                    
                    if not container: continue
                    text = container.get_text(" ", strip=True)
                    price_match = re.search(r"(\d[\d\s.,]*)\s*€", text)
                    if price_match:
                        parsed_price = clean_num(price_match.group(1))
                        if parsed_price and parsed_price >= 10000:
                            href = a["href"] if a["href"].startswith("http") else f"https://supercasa.pt{a['href']}"
                            title = a.get_text(strip=True) or container.find(["h2","h3"]).get_text(strip=True) if container.find(["h2","h3"]) else f"Imóvel em {query.title()}"
                            results.append({
                                "portal": "SuperCasa",
                                "title": title[:80],
                                "price": parsed_price,
                                "typology": extract_typology(text),
                                "area_m2": extract_area(text),
                                "location": query.title(),
                                "link": href
                            })
                time.sleep(0.3)
            except Exception:
                break
    return results

# ==============================================================================
# DISPATCHER
# ==============================================================================

PORTAL_MAP = {
    "Imovirtual": scrape_imovirtual,
    "OLX Imóveis": scrape_olx_imoveis,
    "CustoJusto": scrape_custojusto,
    "Casa Sapo": scrape_casasapo,
    "SuperCasa": scrape_supercasa,
}

def run_multi_scraper(selected_portals, location, pages):
    all_data = []
    diagnostics = {}
    with ThreadPoolExecutor(max_workers=len(selected_portals)) as executor:
        future_to_portal = {
            executor.submit(PORTAL_MAP[p], location, pages): p
            for p in selected_portals if p in PORTAL_MAP
        }
        for fut in as_completed(future_to_portal):
            portal_name = future_to_portal[fut]
            try:
                res = fut.result()
                diagnostics[portal_name] = len(res)
                all_data.extend(res)
            except Exception as e:
                diagnostics[portal_name] = f"Error: {e}"

    seen = set()
    deduped = []
    for item in all_data:
        key = (item["portal"], item["link"])
        if key not in seen:
            seen.add(key)
            deduped.append(item)
    return deduped, diagnostics

# ==============================================================================
# STREAMLIT UI SETUP
# ==============================================================================

st.set_page_config(page_title="Portugal Real Estate Intelligence | By Max", page_icon="🇵🇹", layout="wide")

if "lang" not in st.session_state:
    st.session_state["lang"] = "EN"

with st.sidebar:
    lang_col1, lang_col2 = st.columns([1, 2])
    with lang_col1:
        st.markdown("**🌐 Lang**")
    with lang_col2:
        selected_lang = st.selectbox(
            "Language",
            ["EN", "PT", "UA"],
            index=["EN", "PT", "UA"].index(st.session_state["lang"]),
            label_visibility="collapsed"
        )
        st.session_state["lang"] = selected_lang

L = TRANSLATIONS[st.session_state["lang"]]

st.markdown(
    f"""
    <style>
    .banner-container {{
        background: radial-gradient(circle at 10% 20%, #1e3c72 0%, #172a4d 90%);
        border-radius: 18px;
        padding: 34px;
        color: #ffffff;
        box-shadow: 0 12px 30px rgba(0,0,0,0.3);
        margin-bottom: 25px;
        border: 1px solid rgba(255, 255, 255, 0.12);
        position: relative;
    }}
    .banner-container::after {{
        content: "🇵🇹";
        position: absolute;
        right: 25px;
        top: 15px;
        font-size: 6.5rem;
        opacity: 0.15;
    }}
    .banner-title {{
        font-size: 2.3rem;
        font-weight: 800;
        margin: 0;
        letter-spacing: -0.5px;
    }}
    .banner-sub {{
        font-size: 1.05rem;
        color: #d1d5db;
        margin-top: 8px;
        max-width: 680px;
        line-height: 1.5;
    }}
    .badge-author {{
        display: inline-flex;
        align-items: center;
        background: rgba(255, 255, 255, 0.15);
        backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 255, 255, 0.25);
        padding: 5px 14px;
        border-radius: 30px;
        font-size: 0.85rem;
        font-weight: 600;
        color: #ffffff;
        margin-top: 14px;
    }}
    .footer {{
        text-align: center;
        padding: 40px 0 20px 0;
        color: #9ca3af;
        font-size: 0.85rem;
    }}
    </style>

    <div class="banner-container">
        <div class="banner-title">{L['title']}</div>
        <div class="banner-sub">{L['subtitle']}</div>
        <div class="badge-author">{L['author']}</div>
    </div>
    """,
    unsafe_allow_html=True
)

with st.sidebar:
    st.markdown(f"### {L['search_setup']}")
    location_input = st.text_input(L["location"], value="Lisboa")

    selected_portals = st.multiselect(
        L["portals"],
        ["Imovirtual", "OLX Imóveis", "CustoJusto", "Casa Sapo", "SuperCasa"],
        default=["Imovirtual", "OLX Imóveis", "CustoJusto", "Casa Sapo", "SuperCasa"]
    )

    pages_per_portal = st.slider(L["pages"], 1, 4, 2)

    st.markdown("---")
    st.markdown(f"### {L['filters']}")
    min_price = st.number_input(L["min_price"], min_value=10000, value=50000, step=15000)
    max_price = st.number_input(L["max_price"], min_value=10000, value=1500000, step=25000)

    typology_filter = st.multiselect(
        L["typology"],
        ["T0", "T1", "T2", "T3", "T4", "T5+"],
        default=[]
    )

    only_deals = st.checkbox(L["bargain_only"])

    sort_options_map = {
        L["sort_lowest"]: "lowest",
        L["sort_highest"]: "highest",
        L["sort_m2"]: "m2",
        L["sort_default"]: "default"
    }
    sort_label = st.selectbox(L["sort_by"], list(sort_options_map.keys()))
    sort_choice = sort_options_map[sort_label]

    search_btn = st.button(L["btn_search"], use_container_width=True, type="primary")

# Execution Engine
if search_btn:
    if not selected_portals:
        st.warning(L["warning_select"])
    else:
        with st.spinner(L["fetching"].format(count=len(selected_portals), loc=location_input)):
            raw_results, diag = run_multi_scraper(selected_portals, location_input, pages_per_portal)

        st.session_state["diagnostics"] = diag

        if not raw_results:
            st.error(L["no_results"])
        else:
            status_text = ", ".join([f"{k}: {v}" for k, v in diag.items() if isinstance(v, int)])
            st.success(L["success_status"].format(total=len(raw_results), status=status_text))

        # Price per m² & Market Deal Scoring
        for it in raw_results:
            if it["price"] and it["area_m2"] and it["area_m2"] > 10:
                it["price_per_m2"] = round(it["price"] / it["area_m2"], 1)
            else:
                it["price_per_m2"] = None

        valid_m2 = [it["price_per_m2"] for it in raw_results if it["price_per_m2"]]
        median_m2 = pd.Series(valid_m2).median() if valid_m2 else 0

        for it in raw_results:
            if it["price_per_m2"] and median_m2 > 0:
                diff = ((it["price_per_m2"] - median_m2) / median_m2) * 100
                if diff <= -15:
                    it["deal_status"] = L["bargain_badge"]
                elif diff >= 25:
                    it["deal_status"] = L["premium_badge"]
                else:
                    it["deal_status"] = L["fair_badge"]
            else:
                it["deal_status"] = "N/A"

        # Apply Filters
        filtered = []
        for r in raw_results:
            p = r["price"]
            if p is not None and (p < min_price or (max_price > 0 and p > max_price)):
                continue
            if typology_filter and r["typology"] not in typology_filter:
                continue
            if only_deals and L["bargain_badge"] not in r["deal_status"]:
                continue
            filtered.append(r)

        # Apply Sorting
        if sort_choice == "lowest":
            filtered.sort(key=lambda x: x["price"] if x["price"] is not None else float("inf"))
        elif sort_choice == "highest":
            filtered.sort(key=lambda x: x["price"] if x["price"] is not None else float("-inf"), reverse=True)
        elif sort_choice == "m2":
            filtered.sort(key=lambda x: x["price_per_m2"] if x["price_per_m2"] is not None else float("inf"))

        st.session_state["real_estate_data"] = filtered
        st.session_state["median_m2"] = median_m2

# Render Output View
if "real_estate_data" in st.session_state:
    data = st.session_state["real_estate_data"]

    if data:
        df = pd.DataFrame(data)

        # Dashboard KPIs
        c1, c2, c3, c4 = st.columns(4)
        c1.metric(L["kpi_total"], len(df))
        valid_prices = df["price"].dropna()
        c2.metric(L["kpi_median_price"], f"{valid_prices.median():,.0f} €" if not valid_prices.empty else "N/A")
        c3.metric(L["kpi_median_m2"], f"{st.session_state.get('median_m2', 0):,.0f} €/m²")
        c4.metric(L["kpi_portals"], df["portal"].nunique())

        st.markdown("<br>", unsafe_allow_html=True)

        tab1, tab2, tab3, tab4 = st.tabs([
            L["tab_grid"],
            L["tab_analytics"],
            L["tab_simulator"],
            L["tab_diagnostics"]
        ])

        with tab1:
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine="openpyxl") as writer:
                df.to_excel(writer, index=False, sheet_name="Imoveis")

            st.download_button(
                label=L["btn_export"],
                data=buf.getvalue(),
                file_name=f"imoveis_{location_input.lower().replace(' ', '_')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )

            st.dataframe(
                df[["portal", "deal_status", "title", "price", "typology", "area_m2", "price_per_m2", "link"]],
                column_config={
                    "portal": st.column_config.TextColumn(L["col_portal"], width="small"),
                    "deal_status": st.column_config.TextColumn(L["col_deal"], width="medium"),
                    "title": st.column_config.TextColumn(L["col_title"], width="large"),
                    "price": st.column_config.NumberColumn(L["col_price"], format="%.0f €"),
                    "typology": st.column_config.TextColumn(L["col_typology"], width="small"),
                    "area_m2": st.column_config.NumberColumn(L["col_area"], format="%.0f m²"),
                    "price_per_m2": st.column_config.NumberColumn(L["col_m2"], format="%.0f €/m²"),
                    "link": st.column_config.LinkColumn(L["col_link"], display_text=L["link_text"])
                },
                use_container_width=True,
                hide_index=True
            )

        with tab2:
            st.subheader(L["tab_analytics"])
            col_a, col_b = st.columns(2)
            with col_a:
                st.write(f"**{L['col_portal']}**")
                st.bar_chart(df["portal"].value_counts())
            with col_b:
                st.write(f"**{L['col_typology']}**")
                valid_types = df[df["typology"] != "N/A"]["typology"].value_counts()
                st.bar_chart(valid_types)

        with tab3:
            st.subheader(L["sim_title"])
            st.caption(L["sim_caption"])

            calc_col1, calc_col2 = st.columns(2)
            with calc_col1:
                default_price = max(10000, int(valid_prices.median())) if not valid_prices.empty else 250000
                selected_price = st.number_input(
                    L["prop_price"],
                    min_value=10000,
                    value=default_price,
                    step=5000
                )
                down_payment_pct = st.slider(L["down_payment"], 10, 50, 20)
                interest_rate = st.slider(L["interest_rate"], 1.0, 7.0, 3.5, step=0.1)
                loan_years = st.slider(L["loan_years"], 10, 40, 30)

            loan_amount = selected_price * (1 - down_payment_pct / 100)
            monthly_rate = (interest_rate / 100) / 12
            num_payments = loan_years * 12

            if monthly_rate > 0:
                monthly_mortgage = loan_amount * (monthly_rate * (1 + monthly_rate)**num_payments) / ((1 + monthly_rate)**num_payments - 1)
            else:
                monthly_mortgage = loan_amount / num_payments

            with calc_col2:
                est_monthly_rent = st.number_input(L["monthly_rent"], min_value=100, value=int(selected_price * 0.005), step=50)
                gross_yield = (est_monthly_rent * 12 / selected_price) * 100

                st.markdown(f"#### {L['fin_breakdown']}")
                st.write(f"**{L['fin_amount']}:** {loan_amount:,.2f} €")
                st.write(f"**{L['fin_monthly']}:** `{monthly_mortgage:,.2f} €`")
                st.write(f"**{L['fin_yield']}:** `{gross_yield:.2f}%`")

                net_cashflow = est_monthly_rent - monthly_mortgage
                cashflow_color = "green" if net_cashflow > 0 else "red"
                st.markdown(f"**{L['fin_cashflow']}:** <span style='color:{cashflow_color}; font-weight:bold;'>{net_cashflow:,.2f} €</span>", unsafe_allow_html=True)

        with tab4:
            st.subheader(L["tab_diagnostics"])
            st.json(st.session_state.get("diagnostics", {}))

    else:
        st.warning(L["no_results"])

st.markdown(
    f"""
    <div class="footer">
        {L['footer']}
    </div>
    """,
    unsafe_allow_html=True
)
