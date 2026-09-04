import io
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import streamlit as st
import pandas as pd
from bs4 import BeautifulSoup
from curl_cffi import requests

# ==============================================================================
# CONFIG & HELPERS
# ==============================================================================

BROWSER_IMPERSONATE = "chrome124"
REQUEST_TIMEOUT = 14

def clean_number(text):
    if not text:
        return None
    cleaned = (
        text.replace("€", "")
        .replace("m²", "")
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
    match = re.search(r"\b(T\d\+?)\b", text, re.IGNORECASE)
    return match.group(1).upper() if match else "N/A"

def extract_area(text):
    if not text:
        return None
    match = re.search(r"(\d+[\d\s.,]*)\s*(?:m2|m²)", text, re.IGNORECASE)
    return clean_number(match.group(1)) if match else None

# ==============================================================================
# 1. IMOVIRTUAL SCRAPER
# ==============================================================================

def scrape_imovirtual(query, max_pages=1):
    results = []
    base_url = "https://www.imovirtual.com/pt/resultados/comprar/apartamento"
    slug = query.strip().lower().replace(" ", "-")

    with requests.Session() as session:
        for page in range(1, max_pages + 1):
            url = f"{base_url}/{slug}?page={page}"
            try:
                r = session.get(url, impersonate=BROWSER_IMPERSONATE, timeout=REQUEST_TIMEOUT)
                if r.status_code != 200:
                    break
                soup = BeautifulSoup(r.text, "lxml")
                articles = soup.find_all("article")
                for art in articles:
                    title_elem = art.find("h3") or art.find("span", {"data-cy": "listing-item-title"})
                    link_elem = art.find("a", href=True)
                    price_elem = art.find("span", {"data-cy": "listing-item-price"}) or art.find(string=re.compile(r"€"))

                    if not link_elem or not title_elem:
                        continue

                    title = title_elem.get_text(strip=True)
                    href = link_elem["href"]
                    full_link = href if href.startswith("http") else f"https://www.imovirtual.com{href}"
                    full_link = full_link.split("?")[0]

                    all_text = art.get_text(" ", strip=True)
                    results.append({
                        "portal": "Imovirtual",
                        "title": title,
                        "price": clean_number(price_elem.get_text()) if price_elem else None,
                        "typology": extract_typology(title + " " + all_text),
                        "area_m2": extract_area(all_text),
                        "location": query.title(),
                        "link": full_link
                    })
                time.sleep(0.4)
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
                r = session.get(url, impersonate=BROWSER_IMPERSONATE, timeout=REQUEST_TIMEOUT)
                if r.status_code != 200:
                    break
                soup = BeautifulSoup(r.text, "lxml")
                cards = soup.find_all("div", class_=re.compile(r"propertyCard|property-card")) or soup.find_all("div", attrs={"data-id": True})

                for card in cards:
                    link_elem = card.find("a", href=True)
                    title_elem = card.find("span", class_=re.compile(r"title|name")) or card.find("h2")
                    price_elem = card.find(string=re.compile(r"€"))

                    if not link_elem:
                        continue

                    title = title_elem.get_text(strip=True) if title_elem else f"Apartamento em {query.title()}"
                    href = link_elem["href"]
                    full_link = href if href.startswith("http") else f"https://casa.sapo.pt{href}"

                    card_text = card.get_text(" ", strip=True)
                    results.append({
                        "portal": "Casa Sapo",
                        "title": title,
                        "price": clean_number(price_elem) if price_elem else None,
                        "typology": extract_typology(title + " " + card_text),
                        "area_m2": extract_area(card_text),
                        "location": query.title(),
                        "link": full_link.split("?")[0]
                    })
                time.sleep(0.4)
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
                r = session.get(url, impersonate=BROWSER_IMPERSONATE, timeout=REQUEST_TIMEOUT)
                if r.status_code != 200:
                    break
                soup = BeautifulSoup(r.text, "lxml")
                cards = soup.find_all("div", class_=re.compile(r"property-list-item|property-card"))

                for card in cards:
                    link_elem = card.find("a", href=True)
                    title_elem = card.find("h2") or card.find("a", class_=re.compile(r"title"))
                    price_elem = card.find("div", class_=re.compile(r"price")) or card.find(string=re.compile(r"€"))

                    if not link_elem:
                        continue

                    href = link_elem["href"]
                    full_link = href if href.startswith("http") else f"https://supercasa.pt{href}"
                    title = title_elem.get_text(strip=True) if title_elem else "Imóvel SuperCasa"
                    card_text = card.get_text(" ", strip=True)

                    results.append({
                        "portal": "SuperCasa",
                        "title": title,
                        "price": clean_number(price_elem.get_text() if hasattr(price_elem, "get_text") else str(price_elem)),
                        "typology": extract_typology(title + " " + card_text),
                        "area_m2": extract_area(card_text),
                        "location": query.title(),
                        "link": full_link.split("?")[0]
                    })
                time.sleep(0.4)
            except Exception:
                break
    return results

# ==============================================================================
# 4. ERA IMMOBILIÁRIA SCRAPER
# ==============================================================================

def scrape_era(query, max_pages=1):
    results = []
    slug = query.strip().lower().replace(" ", "-")

    with requests.Session() as session:
        for page in range(1, max_pages + 1):
            url = f"https://www.era.pt/imoveis/comprar/{slug}?pagina={page}"
            try:
                r = session.get(url, impersonate=BROWSER_IMPERSONATE, timeout=REQUEST_TIMEOUT)
                if r.status_code != 200:
                    break
                soup = BeautifulSoup(r.text, "lxml")
                cards = soup.find_all("div", class_=re.compile(r"property-item|imovel-item|card"))

                for card in cards:
                    link_elem = card.find("a", href=re.compile(r"/imovel/|/comprar/"))
                    if not link_elem:
                        continue

                    title_elem = card.find("h3") or card.find("div", class_=re.compile(r"title"))
                    price_elem = card.find(string=re.compile(r"€"))

                    title = title_elem.get_text(strip=True) if title_elem else "ERA Listing"
                    href = link_elem["href"]
                    full_link = href if href.startswith("http") else f"https://www.era.pt{href}"
                    card_text = card.get_text(" ", strip=True)

                    results.append({
                        "portal": "ERA",
                        "title": title,
                        "price": clean_number(price_elem),
                        "typology": extract_typology(title + " " + card_text),
                        "area_m2": extract_area(card_text),
                        "location": query.title(),
                        "link": full_link.split("?")[0]
                    })
                time.sleep(0.4)
            except Exception:
                break
    return results

# ==============================================================================
# 5. IDEALISTA PROXY / CONNECTOR
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
            timeout=18,
            headers={"Accept-Language": "pt-PT,pt;q=0.9,en-US;q=0.8", "Referer": "https://www.google.pt/"}
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
                        "link": f"https://www.idealista.pt{href}" if href.startswith("/") else href
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
    "Idealista": scrape_idealista
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
                st.error(f"Error loading {portal_name}: {e}")

    seen = set()
    deduped = []
    for item in all_data:
        key = (item["portal"], item["link"])
        if key not in seen:
            seen.add(key)
            deduped.append(item)
    return deduped

# ==============================================================================
# UI SETUP & CUSTOM STYLING
# ==============================================================================

st.set_page_config(page_title="Portugal Real Estate Portal | By Max", page_icon="🇵🇹", layout="wide")

# Custom Banner, Card Styling & Creator Watermark
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
    unsafe_allow_html=True
)

# Sidebar Controls
with st.sidebar:
    st.markdown("### 🔍 Search Setup")
    location_input = st.text_input("City or Region", value="Lisboa", help="e.g. Lisboa, Porto, Cascais, Sintra, Coimbra")
    
    selected_portals = st.multiselect(
        "Target Portals",
        ["Imovirtual", "Casa Sapo", "SuperCasa", "ERA", "Idealista"],
        default=["Imovirtual", "Casa Sapo", "SuperCasa", "ERA"]
    )
    
    pages_per_portal = st.slider("Pages per site", min_value=1, max_value=5, value=2)
    
    st.markdown("---")
    st.markdown("### 🎯 Listing Filters")
    min_price = st.number_input("Min Price (€)", min_value=0, value=0, step=15000)
    max_price = st.number_input("Max Price (€)", min_value=0, value=1500000, step=25000)
    
    typology_filter = st.multiselect(
        "Typology (Rooms)",
        ["T0", "T1", "T2", "T3", "T4", "T5+"],
        default=[]
    )
    
    sort_choice = st.selectbox(
        "Sort By",
        ["Lowest Price First (€ ↑)", "Highest Price First (€ ↓)", "Portal Default"]
    )
    
    with st.expander("🛡️ Idealista Proxy Setup"):
        proxy_input = st.text_input(
            "Proxy Address",
            placeholder="http://user:pass@gate.proxy.com:8080",
            help="Idealista flags public cloud datacenters (like Streamlit Cloud). Supply an authenticated residential proxy if enabling Idealista."
        )

    search_btn = st.button("🚀 Fetch Properties", use_container_width=True, type="primary")

# Search Trigger
if search_btn:
    if not selected_portals:
        st.warning("Please select at least one portal from the sidebar.")
    else:
        with st.spinner(f"Querying {len(selected_portals)} Portuguese portals concurrently for '{location_input}'..."):
            raw_results = run_multi_scraper(
                selected_portals,
                location_input,
                pages_per_portal,
                idealista_proxy=proxy_input if "Idealista" in selected_portals else None
            )

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

        # Highlight Metrics
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
            use_container_width=True
        )

        st.markdown("<br>", unsafe_allow_html=True)

        # Results Grid
        st.dataframe(
            df[["portal", "title", "price", "typology", "area_m2", "link"]],
            column_config={
                "portal": st.column_config.TextColumn("Portal", width="small"),
                "title": st.column_config.TextColumn("Listing Title", width="large"),
                "price": st.column_config.NumberColumn("Price (€)", format="%.0f €"),
                "typology": st.column_config.TextColumn("Typology", width="small"),
                "area_m2": st.column_config.NumberColumn("Area (m²)", format="%.0f m²"),
                "link": st.column_config.LinkColumn("Direct Ad Link", display_text="View on Site")
            },
            use_container_width=True,
            hide_index=True
        )
    else:
        st.warning("No listings matched your active price or typology filters.")

# Footer attribution
st.markdown(
    """
    <div class="footer-container">
        Portugal Real Estate Multi-Scraper Platform • Designed & Created by <span class="footer-badge">Max</span>
    </div>
    """,
    unsafe_allow_html=True
)
