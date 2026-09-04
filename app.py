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
# CONFIG & HELPERS
# ==============================================================================

BROWSER_IMPERSONATE = "chrome124"
REQUEST_TIMEOUT = 14

COMMON_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "pt-PT,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}

def clean_number(text):
    if text is None:
        return None
    cleaned = (
        str(text)
        .replace("€", "")
        .replace("m²", "")
        .replace("m2", "")
        .replace("\xa0", " ")
        .replace(".", "")
        .replace(",", ".")
        .strip()
    )
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
        return clean_number(match.group(1))
    return None

# ==============================================================================
# 1. IMOVIRTUAL
# ==============================================================================

def scrape_imovirtual(query, max_pages=1):
    results = []
    slug = query.strip().lower().replace(" ", "-")

    with requests.Session() as session:
        for page in range(1, max_pages + 1):
            url = f"https://www.imovirtual.com/pt/resultados/comprar/apartamento/{slug}?page={page}"
            try:
                r = session.get(url, headers=COMMON_HEADERS, impersonate=BROWSER_IMPERSONATE, timeout=REQUEST_TIMEOUT)
                if r.status_code != 200:
                    break

                soup = BeautifulSoup(r.text, "lxml")
                next_data = soup.find("script", id="__NEXT_DATA__")
                if next_data and next_data.string:
                    try:
                        data = json.loads(next_data.string)
                        items = data.get("props", {}).get("pageProps", {}).get("data", {}).get("searchAds", {}).get("items", [])
                        for it in items:
                            title = it.get("title", f"Imóvel em {query.title()}")
                            price_val = it.get("totalPrice", {}).get("value")
                            slug_val = it.get("slug")
                            area_val = it.get("areaInSquareMeters")

                            results.append({
                                "portal": "Imovirtual",
                                "title": title,
                                "price": float(price_val) if price_val else None,
                                "typology": extract_typology(title),
                                "area_m2": clean_number(area_val),
                                "location": query.title(),
                                "link": f"https://www.imovirtual.com/pt/anuncio/{slug_val}" if slug_val else url,
                            })
                        if items:
                            continue
                    except Exception:
                        pass
                time.sleep(0.3)
            except Exception:
                break
    return results

# ==============================================================================
# 2. OLX IMÓVEIS (Direct OLX Real Estate Sub-section)
# ==============================================================================

def scrape_olx_imoveis(query, max_pages=1):
    results = []
    encoded_q = query.strip().replace(" ", "-")

    with requests.Session() as session:
        for page in range(1, max_pages + 1):
            url = f"https://www.olx.pt/imoveis/apartamentos-casas-venda/q-{encoded_q}/?page={page}"
            try:
                r = session.get(url, headers=COMMON_HEADERS, impersonate=BROWSER_IMPERSONATE, timeout=REQUEST_TIMEOUT)
                if r.status_code != 200:
                    break

                soup = BeautifulSoup(r.text, "lxml")
                cards = soup.find_all(attrs={"data-cy": "l-card"})
                for card in cards:
                    link_elem = card.find("a", href=re.compile(r"/(?:d/)?anuncio/"))
                    if not link_elem or not link_elem.get("href"):
                        continue

                    title_elem = card.find("h4") or card.find("h6") or link_elem.find(["h4", "h6"])
                    title = title_elem.get_text(strip=True) if title_elem else "Imóvel OLX"

                    price_elem = card.find(attrs={"data-testid": "ad-price"}) or card.find("p")
                    price = clean_number(price_elem.get_text()) if price_elem else None

                    href = link_elem["href"]
                    full_link = f"https://www.olx.pt{href}" if href.startswith("/") else href
                    card_text = card.get_text(" ", strip=True)

                    results.append({
                        "portal": "OLX Imóveis",
                        "title": title,
                        "price": price,
                        "typology": extract_typology(title + " " + card_text),
                        "area_m2": extract_area(card_text),
                        "location": query.title(),
                        "link": full_link.split("?")[0]
                    })
                time.sleep(0.3)
            except Exception:
                break
    return results

# ==============================================================================
# 3. CUSTOJUSTO (Portugal's #2 Classifieds - Pure SSR HTML)
# ==============================================================================

def scrape_custojusto(query, max_pages=1):
    results = []
    encoded_q = urllib.parse.quote(query.strip())

    with requests.Session() as session:
        for page in range(1, max_pages + 1):
            url = f"https://www.custojusto.pt/portugal/imobiliario/comprar-casas?q={encoded_q}&o={page}"
            try:
                r = session.get(url, headers=COMMON_HEADERS, impersonate=BROWSER_IMPERSONATE, timeout=REQUEST_TIMEOUT)
                if r.status_code != 200:
                    break

                soup = BeautifulSoup(r.text, "lxml")
                cards = soup.find_all("div", class_=re.compile(r"container_list|listing-item")) or soup.find_all("a", href=re.compile(r"/comprar-casas/"))

                for card in cards:
                    link_elem = card if card.name == "a" else card.find("a", href=True)
                    if not link_elem or not link_elem.get("href"):
                        continue

                    title_elem = card.find("h2") or card.find("h3") or link_elem
                    price_elem = card.find(string=re.compile(r"€"))

                    card_text = card.get_text(" ", strip=True)
                    href = link_elem["href"]
                    full_link = href if href.startswith("http") else f"https://www.custojusto.pt{href}"

                    results.append({
                        "portal": "CustoJusto",
                        "title": title_elem.get_text(strip=True) if title_elem else f"Imóvel em {query.title()}",
                        "price": clean_number(str(price_elem)) if price_elem else None,
                        "typology": extract_typology(card_text),
                        "area_m2": extract_area(card_text),
                        "location": query.title(),
                        "link": full_link.split("?")[0]
                    })
                time.sleep(0.3)
            except Exception:
                break
    return results

# ==============================================================================
# 4. BPI EXPRESSO IMOBILIÁRIO (Direct Server-Rendered Feeds)
# ==============================================================================

def scrape_bpi_expresso(query, max_pages=1):
    results = []
    slug = query.strip().lower().replace(" ", "-")

    with requests.Session() as session:
        for page in range(1, max_pages + 1):
            url = f"https://bpiexpressoimobiliario.pt/comprar/apartamentos/{slug}?pagina={page}"
            try:
                r = session.get(url, headers=COMMON_HEADERS, impersonate=BROWSER_IMPERSONATE, timeout=REQUEST_TIMEOUT)
                if r.status_code != 200:
                    break

                soup = BeautifulSoup(r.text, "lxml")
                cards = soup.select(".card-imovel, .imovel-card, div[class*='property-card']")

                for card in cards:
                    link_elem = card.find("a", href=True)
                    if not link_elem:
                        continue

                    price_elem = card.find(string=re.compile(r"€"))
                    title_elem = card.find(["h2", "h3", "h4"])
                    card_text = card.get_text(" ", strip=True)
                    href = link_elem["href"]
                    full_link = href if href.startswith("http") else f"https://bpiexpressoimobiliario.pt{href}"

                    results.append({
                        "portal": "BPI Expresso",
                        "title": title_elem.get_text(strip=True) if title_elem else f"Imóvel em {query.title()}",
                        "price": clean_number(str(price_elem)) if price_elem else None,
                        "typology": extract_typology(card_text),
                        "area_m2": extract_area(card_text),
                        "location": query.title(),
                        "link": full_link.split("?")[0]
                    })
                time.sleep(0.3)
            except Exception:
                break
    return results

# ==============================================================================
# 5. CASA SAPO (Mobile User-Agent Endpoint)
# ==============================================================================

def scrape_casa_sapo(query, max_pages=1):
    results = []
    encoded_q = urllib.parse.quote(query.strip())
    # Sapo's mobile feed has lower bot threshold restrictions
    mobile_headers = {
        **COMMON_HEADERS,
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Mobile/15E148 Safari/604.1",
        "Sec-Ch-Ua-Mobile": "?1",
    }

    with requests.Session() as session:
        for page in range(1, max_pages + 1):
            url = f"https://casa.sapo.pt/venda-apartamentos/?q={encoded_q}&pn={page}"
            try:
                r = session.get(url, headers=mobile_headers, impersonate="safari15_5", timeout=REQUEST_TIMEOUT)
                if r.status_code != 200:
                    break

                soup = BeautifulSoup(r.text, "lxml")
                cards = soup.select(".propertyCard, [class*='propertyCard'], div[data-id]")

                for card in cards:
                    link_elem = card.find("a", href=True)
                    if not link_elem:
                        continue

                    price_elem = card.find(string=re.compile(r"€"))
                    title_elem = card.find(["h2", "h3", "span"])
                    href = link_elem["href"]
                    full_link = href if href.startswith("http") else f"https://casa.sapo.pt{href}"
                    card_text = card.get_text(" ", strip=True)

                    results.append({
                        "portal": "Casa Sapo",
                        "title": title_elem.get_text(strip=True) if title_elem else f"Apartamento em {query.title()}",
                        "price": clean_number(str(price_elem)) if price_elem else None,
                        "typology": extract_typology(card_text),
                        "area_m2": extract_area(card_text),
                        "location": query.title(),
                        "link": full_link.split("?")[0],
                    })
                time.sleep(0.3)
            except Exception:
                break
    return results

# ==============================================================================
# MULTI-THREAD DISPATCHER
# ==============================================================================

PORTAL_MAP = {
    "Imovirtual": scrape_imovirtual,
    "OLX Imóveis": scrape_olx_imoveis,
    "CustoJusto": scrape_custojusto,
    "BPI Expresso": scrape_bpi_expresso,
    "Casa Sapo": scrape_casa_sapo,
}

def run_multi_scraper(selected_portals, location, pages):
    all_data = []
    with ThreadPoolExecutor(max_workers=len(selected_portals)) as executor:
        future_to_portal = {
            executor.submit(PORTAL_MAP[p], location, pages): p
            for p in selected_portals
        }

        for fut in as_completed(future_to_portal):
            portal_name = future_to_portal[fut]
            try:
                res = fut.result()
                all_data.extend(res)
            except Exception as e:
                st.error(f"Error executing scraper for {portal_name}: {e}")

    seen = set()
    deduped = []
    for item in all_data:
        key = (item["portal"], item["link"])
        if key not in seen:
            seen.add(key)
            deduped.append(item)
    return deduped

# ==============================================================================
# UI SETUP & STYLING
# ==============================================================================

st.set_page_config(
    page_title="Portugal Real Estate Aggregator | By Max",
    page_icon="🇵🇹",
    layout="wide",
)

st.markdown(
    """
    <style>
    .banner-container {
        background: linear-gradient(135deg, #0d1b2a 0%, #1b263b 45%, #415a77 100%);
        border-radius: 16px;
        padding: 30px;
        color: #ffffff;
        box-shadow: 0 10px 25px rgba(0,0,0,0.25);
        margin-bottom: 24px;
        position: relative;
        overflow: hidden;
        border: 1px solid rgba(255, 255, 255, 0.1);
    }
    .banner-container::after {
        content: "🇵🇹";
        position: absolute;
        right: 20px;
        top: 10px;
        font-size: 7rem;
        opacity: 0.12;
        pointer-events: none;
    }
    .banner-title {
        font-size: 2.2rem;
        font-weight: 800;
        margin: 0;
        letter-spacing: -0.5px;
        background: linear-gradient(90deg, #ffffff, #e0e1dd);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    .banner-sub {
        font-size: 1.05rem;
        color: #e0e1dd;
        margin-top: 6px;
        font-weight: 300;
        max-width: 650px;
    }
    .badge-author {
        display: inline-flex;
        align-items: center;
        background: rgba(255, 255, 255, 0.14);
        backdrop-filter: blur(8px);
        border: 1px solid rgba(255, 255, 255, 0.2);
        padding: 5px 14px;
        border-radius: 30px;
        font-size: 0.85rem;
        font-weight: 600;
        color: #ffffff;
        margin-top: 14px;
    }
    .footer-container {
        text-align: center;
        padding: 30px 0 10px 0;
        color: #8d99ae;
        font-size: 0.9rem;
    }
    .footer-badge {
        background: #f1f3f5;
        color: #2b2d42;
        padding: 4px 10px;
        border-radius: 12px;
        font-weight: 700;
        margin-left: 4px;
    }
    </style>
    
    <div class="banner-container">
        <div class="banner-title">Portugal Real Estate Search Hub</div>
        <div class="banner-sub">
            Real-time live multi-portal property search engine querying Imovirtual, OLX Imóveis, CustoJusto, BPI Expresso, and Casa Sapo.
        </div>
        <div class="badge-author">
            ⚡ Engineered & Crafted by Max
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown("### 🔍 Search Setup")
    location_input = st.text_input("City or Municipality", value="Lisboa", help="e.g. Lisboa, Porto, Cascais, Leiria")

    selected_portals = st.multiselect(
        "Target Portals",
        ["Imovirtual", "OLX Imóveis", "CustoJusto", "BPI Expresso", "Casa Sapo"],
        default=["Imovirtual", "OLX Imóveis", "CustoJusto"]
    )

    pages_per_portal = st.slider("Pages per portal", min_value=1, max_value=4, value=2)

    st.markdown("---")
    st.markdown("### 🎯 Listing Filters")
    min_price = st.number_input("Min Price (€)", min_value=0, value=0, step=15000)
    max_price = st.number_input("Max Price (€)", min_value=0, value=1500000, step=25000)

    typology_filter = st.multiselect(
        "Typology (Rooms)",
        ["T0", "T1", "T2", "T3", "T4", "T5+"],
        default=[],
    )

    sort_choice = st.selectbox(
        "Sort By",
        ["Lowest Price First (€ ↑)", "Highest Price First (€ ↓)", "Portal Default"],
    )

    search_btn = st.button("🚀 Fetch Properties", use_container_width=True, type="primary")

# Execute Search
if search_btn:
    if not selected_portals:
        st.warning("Please select at least one portal from the sidebar.")
    else:
        with st.spinner(f"Querying {len(selected_portals)} Portuguese portals concurrently for '{location_input}'..."):
            raw_results = run_multi_scraper(
                selected_portals,
                location_input,
                pages_per_portal
            )

        # Telemetry breakdown
        portal_counts = {}
        for it in raw_results:
            portal_counts[it["portal"]] = portal_counts.get(it["portal"], 0) + 1

        if not raw_results:
            st.error("No listings returned. The selected sites did not return any records for this location.")
        else:
            status_text = ", ".join([f"{k}: {v}" for k, v in portal_counts.items()])
            st.info(f"Fetched {len(raw_results)} total listings ({status_text}).")

        # Filters
        filtered = []
        for r in raw_results:
            p = r["price"]
            if p is not None and (p < min_price or (max_price > 0 and p > max_price)):
                continue
            if typology_filter and r["typology"] not in typology_filter:
                continue
            filtered.append(r)

        # Sorting
        if sort_choice == "Lowest Price First (€ ↑)":
            filtered.sort(key=lambda x: x["price"] if x["price"] is not None else float("inf"))
        elif sort_choice == "Highest Price First (€ ↓)":
            filtered.sort(key=lambda x: x["price"] if x["price"] is not None else float("-inf"), reverse=True)

        st.session_state["real_estate_data"] = filtered

# Render Data
if "real_estate_data" in st.session_state:
    data = st.session_state["real_estate_data"]

    if data:
        df = pd.DataFrame(data)

        # Summary KPIs
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Available Listings", len(df))
        valid_prices = df["price"].dropna()
        col2.metric("Average Price", f"{valid_prices.mean():,.0f} €" if not valid_prices.empty else "N/A")
        col3.metric("Cheapest Found", f"{valid_prices.min():,.0f} €" if not valid_prices.empty else "N/A")
        col4.metric("Active Portals", df["portal"].nunique())

        # Excel Export
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Imoveis")

        st.download_button(
            label="📥 Download Data as Excel (.xlsx)",
            data=buffer.getvalue(),
            file_name=f"imoveis_{location_input.lower().replace(' ', '_')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

        st.markdown("<br>", unsafe_allow_html=True)

        # Grid
        st.dataframe(
            df[["portal", "title", "price", "typology", "area_m2", "link"]],
            column_config={
                "portal": st.column_config.TextColumn("Portal", width="small"),
                "title": st.column_config.TextColumn("Listing Title", width="large"),
                "price": st.column_config.NumberColumn("Price (€)", format="%.0f €"),
                "typology": st.column_config.TextColumn("Typology", width="small"),
                "area_m2": st.column_config.NumberColumn("Area (m²)", format="%.0f m²"),
                "link": st.column_config.LinkColumn("Direct Ad Link", display_text="View on Site"),
            },
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.warning("No listings matched your active price or typology filters.")

st.markdown(
    """
    <div class="footer-container">
        Portugal Real Estate Multi-Scraper Platform • Designed & Created by <span class="footer-badge">Max</span>
    </div>
    """,
    unsafe_allow_html=True,
)
