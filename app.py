import io
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from bs4 import BeautifulSoup
from curl_cffi import requests
import pandas as pd
import streamlit as st

# ==============================================================================
# CONFIG & NETWORK CLIENT
# ==============================================================================

BROWSER_IMPERSONATE = "chrome124"
REQUEST_TIMEOUT = 15

COMMON_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
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

# ==============================================================================
# NORMALIZATION HELPERS
# ==============================================================================

def clean_number(text):
    """Extracts first valid integer/float from a string representation."""
    if not text:
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
    """Extracts standard Portuguese typology tags (T0 to T5+)."""
    if not text:
        return "N/A"
    match = re.search(r"\b(T\d\+?)\b", str(text), re.IGNORECASE)
    return match.group(1).upper() if match else "N/A"

def extract_area(text):
    """Extracts square meter values."""
    if not text:
        return None
    match = re.search(r"(\d+[\d\s.,]*)\s*(?:m2|m²)", str(text), re.IGNORECASE)
    if match:
        return clean_number(match.group(1))
    return None

# ==============================================================================
# 1. IMOVIRTUAL SCRAPER (Next.js Data + Selectors)
# ==============================================================================

def scrape_imovirtual(query, max_pages=1):
    results = []
    slug = query.strip().lower().replace(" ", "-")

    with requests.Session() as session:
        for page in range(1, max_pages + 1):
            url = f"https://www.imovirtual.com/pt/resultados/comprar/apartamento/{slug}?page={page}"
            try:
                r = session.get(
                    url,
                    headers=COMMON_HEADERS,
                    impersonate=BROWSER_IMPERSONATE,
                    timeout=REQUEST_TIMEOUT,
                )
                if r.status_code != 200:
                    break

                soup = BeautifulSoup(r.text, "lxml")

                # Strategy A: Extract from embedded __NEXT_DATA__ JSON script
                next_data = soup.find("script", id="__NEXT_DATA__")
                extracted_json = False
                if next_data and next_data.string:
                    try:
                        data = json.loads(next_data.string)
                        items = (
                            data.get("props", {})
                            .get("pageProps", {})
                            .get("data", {})
                            .get("searchAds", {})
                            .get("items", [])
                        )
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
                            extracted_json = True
                    except Exception:
                        pass

                if extracted_json:
                    continue

                # Strategy B: DOM element fallback
                cards = soup.select('article[data-cy="listing-item"], article')
                for card in cards:
                    link_elem = card.select_one('a[href*="/anuncio/"]') or card.find("a", href=True)
                    price_elem = card.select_one('[data-cy="listing-item-price"]') or card.find(string=re.compile(r"€"))
                    title_elem = card.select_one('[data-cy="listing-item-title"]') or card.find(["h3", "h2"])

                    if not link_elem:
                        continue

                    href = link_elem.get("href", "")
                    full_link = href if href.startswith("http") else f"https://www.imovirtual.com{href}"
                    card_text = card.get_text(" ", strip=True)

                    results.append({
                        "portal": "Imovirtual",
                        "title": title_elem.get_text(strip=True) if title_elem else f"Apartamento em {query.title()}",
                        "price": clean_number(price_elem.get_text() if hasattr(price_elem, "get_text") else str(price_elem)),
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
# 2. CASA SAPO SCRAPER
# ==============================================================================

def scrape_casa_sapo(query, max_pages=1):
    results = []
    slug = query.strip().lower().replace(" ", "-")

    with requests.Session() as session:
        for page in range(1, max_pages + 1):
            url = f"https://casa.sapo.pt/comprar-apartamentos/{slug}/?pn={page}"
            try:
                r = session.get(
                    url,
                    headers=COMMON_HEADERS,
                    impersonate=BROWSER_IMPERSONATE,
                    timeout=REQUEST_TIMEOUT,
                )
                if r.status_code != 200:
                    break

                soup = BeautifulSoup(r.text, "lxml")
                cards = soup.select(".propertyCard, [class*='propertyCard'], .listCard, div[data-id]")

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
# 3. SUPERCASA SCRAPER
# ==============================================================================

def scrape_supercasa(query, max_pages=1):
    results = []
    slug = query.strip().lower().replace(" ", "-")

    with requests.Session() as session:
        for page in range(1, max_pages + 1):
            url = f"https://supercasa.pt/comprar-casas/{slug}?pagina={page}"
            try:
                r = session.get(
                    url,
                    headers=COMMON_HEADERS,
                    impersonate=BROWSER_IMPERSONATE,
                    timeout=REQUEST_TIMEOUT,
                )
                if r.status_code != 200:
                    break

                soup = BeautifulSoup(r.text, "lxml")
                cards = soup.select(".property-list-item, .property-card, div[class*='property']")

                for card in cards:
                    link_elem = card.select_one("a[href*='/imovel/'], a[href*='/comprar-']")
                    if not link_elem or not link_elem.get("href"):
                        continue

                    title_elem = card.find(["h2", "h3"]) or link_elem
                    price_elem = card.find(string=re.compile(r"€"))

                    href = link_elem["href"]
                    full_link = href if href.startswith("http") else f"https://supercasa.pt{href}"
                    card_text = card.get_text(" ", strip=True)

                    results.append({
                        "portal": "SuperCasa",
                        "title": title_elem.get_text(strip=True) if title_elem else "Imóvel SuperCasa",
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
# 4. ERA IMOBILIÁRIA SCRAPER
# ==============================================================================

def scrape_era(query, max_pages=1):
    results = []
    slug = query.strip().lower().replace(" ", "-")

    with requests.Session() as session:
        for page in range(1, max_pages + 1):
            url = f"https://www.era.pt/imoveis/comprar/{slug}?pagina={page}"
            try:
                r = session.get(
                    url,
                    headers=COMMON_HEADERS,
                    impersonate=BROWSER_IMPERSONATE,
                    timeout=REQUEST_TIMEOUT,
                )
                if r.status_code != 200:
                    break

                soup = BeautifulSoup(r.text, "lxml")
                cards = soup.select(".property-item, .imovel-item, div[class*='card']")

                for card in cards:
                    link_elem = card.find("a", href=re.compile(r"/imovel/|/comprar/"))
                    if not link_elem or not link_elem.get("href"):
                        continue

                    title_elem = card.find(["h3", "h2"]) or card.find("div", class_=re.compile(r"title"))
                    price_elem = card.find(string=re.compile(r"€"))

                    title = title_elem.get_text(strip=True) if title_elem else "Anúncio ERA"
                    href = link_elem["href"]
                    full_link = href if href.startswith("http") else f"https://www.era.pt{href}"
                    card_text = card.get_text(" ", strip=True)

                    results.append({
                        "portal": "ERA",
                        "title": title,
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
# 5. IDEALISTA CONNECTOR
# ==============================================================================

def scrape_idealista(query, max_pages=1, proxy_url=None):
    results = []
    slug = query.strip().lower().replace(" ", "-")
    target_url = f"https://www.idealista.pt/comprar-casas/{slug}/"
    proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None

    try:
        r = requests.get(
            target_url,
            impersonate=BROWSER_IMPERSONATE,
            proxies=proxies,
            timeout=REQUEST_TIMEOUT,
            headers={
                "Accept-Language": "pt-PT,pt;q=0.9,en-US;q=0.8",
                "Referer": "https://www.google.pt/",
            },
        )
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "lxml")
            articles = soup.find_all("article", class_=re.compile(r"item-multimedia"))
            for art in articles:
                link_elem = art.find("a", class_="item-link")
                price_elem = art.find("span", class_="item-price")
                if link_elem:
                    card_text = art.get_text(" ", strip=True)
                    href = link_elem.get("href", "")
                    results.append({
                        "portal": "Idealista",
                        "title": link_elem.get_text(strip=True),
                        "price": clean_number(price_elem.get_text()) if price_elem else None,
                        "typology": extract_typology(card_text),
                        "area_m2": extract_area(card_text),
                        "location": query.title(),
                        "link": f"https://www.idealista.pt{href}" if href.startswith("/") else href,
                    })
    except Exception:
        pass
    return results

# ==============================================================================
# DISPATCHER
# ==============================================================================

PORTAL_MAP = {
    "Imovirtual": scrape_imovirtual,
    "Casa Sapo": scrape_casa_sapo,
    "SuperCasa": scrape_supercasa,
    "ERA": scrape_era,
    "Idealista": scrape_idealista,
}

def run_multi_scraper(selected_portals, location, pages, idealista_proxy=None):
    all_data = []
    with ThreadPoolExecutor(max_workers=len(selected_portals)) as executor:
        future_to_portal = {}
        for p in selected_portals:
            fn = PORTAL_MAP[p]
            if p == "Idealista":
                fut = executor.submit(fn, location, pages, idealista_proxy)
            else:
                fut = executor.submit(fn, location, pages)
            future_to_portal[fut] = p

        for fut in as_completed(future_to_portal):
            portal_name = future_to_portal[fut]
            try:
                res = fut.result()
                all_data.extend(res)
            except Exception as e:
                st.error(f"Error executing scraper for {portal_name}: {e}")

    # Remove duplicates matching portal and link
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
    page_title="Portugal Real Estate Portal | By Max",
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
            Real-time live multi-portal property search engine querying Imovirtual, Casa Sapo, SuperCasa, ERA, and Idealista simultaneously.
        </div>
        <div class="badge-author">
            ⚡ Engineered & Crafted by Max
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# Sidebar
with st.sidebar:
    st.markdown("### 🔍 Search Setup")
    location_input = st.text_input("City or Region", value="Lisboa", help="e.g. Lisboa, Porto, Cascais, Sintra, Coimbra")

    selected_portals = st.multiselect(
        "Target Portals",
        ["Imovirtual", "Casa Sapo", "SuperCasa", "ERA", "Idealista"],
        default=["Imovirtual", "Casa Sapo", "SuperCasa", "ERA"],
    )

    pages_per_portal = st.slider("Pages per site", min_value=1, max_value=5, value=2)

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

    with st.expander("🛡️ Idealista Proxy Setup"):
        proxy_input = st.text_input(
            "Proxy Address",
            placeholder="http://user:pass@gate.proxy.com:8080",
            help="Idealista blocks datacenter IPs. Supply an authenticated residential proxy if enabling Idealista.",
        )

    search_btn = st.button("🚀 Fetch Properties", use_container_width=True, type="primary")

# Application Run State
if search_btn:
    if not selected_portals:
        st.warning("Please select at least one portal from the sidebar.")
    else:
        with st.spinner(f"Querying {len(selected_portals)} Portuguese portals concurrently for '{location_input}'..."):
            raw_results = run_multi_scraper(
                selected_portals,
                location_input,
                pages_per_portal,
                idealista_proxy=proxy_input if "Idealista" in selected_portals else None,
            )

        # Telemetry check to verify incoming data
        portal_counts = {}
        for it in raw_results:
            portal_counts[it["portal"]] = portal_counts.get(it["portal"], 0) + 1

        if not raw_results:
            st.error("No listings returned by the scrapers. The target sites may have blocked the IP or changed structures.")
        else:
            status_text = ", ".join([f"{k}: {v}" for k, v in portal_counts.items()])
            st.info(f"Fetched {len(raw_results)} total listings ({status_text}).")

        # Apply Filters
        filtered = []
        for r in raw_results:
            p = r["price"]
            if p is not None and (p < min_price or (max_price > 0 and p > max_price)):
                continue
            if typology_filter and r["typology"] not in typology_filter:
                continue
            filtered.append(r)

        # Apply Sorting
        if sort_choice == "Lowest Price First (€ ↑)":
            filtered.sort(key=lambda x: x["price"] if x["price"] is not None else float("inf"))
        elif sort_choice == "Highest Price First (€ ↓)":
            filtered.sort(key=lambda x: x["price"] if x["price"] is not None else float("-inf"), reverse=True)

        st.session_state["real_estate_data"] = filtered

# Render Output Data
if "real_estate_data" in st.session_state:
    data = st.session_state["real_estate_data"]

    if data:
        df = pd.DataFrame(data)

        # Metrics display
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

        # Grid view
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

# Footer
st.markdown(
    """
    <div class="footer-container">
        Portugal Real Estate Multi-Scraper Platform • Designed & Created by <span class="footer-badge">Max</span>
    </div>
    """,
    unsafe_allow_html=True,
)
