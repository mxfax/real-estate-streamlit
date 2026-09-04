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
# CONFIG & NETWORK HEADERS
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

# ==============================================================================
# DATA NORMALIZATION HELPERS
# ==============================================================================

def clean_num(val):
    """Extracts positive float numbers from text."""
    if val is None:
        return None
    cleaned = (
        str(val)
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
    """Extracts standard Portuguese room codes (T0 to T6+)."""
    if not text:
        return "N/A"
    match = re.search(r"\b(T\d\+?)\b", str(text), re.IGNORECASE)
    return match.group(1).upper() if match else "N/A"

def extract_area(text):
    """Extracts surface area in m²."""
    if not text:
        return None
    match = re.search(r"(\d+[\d\s.,]*)\s*(?:m2|m²)", str(text), re.IGNORECASE)
    if match:
        return clean_num(match.group(1))
    return None

# ==============================================================================
# 1. IMOVIRTUAL (Next.js Hydration JSON + Fallback)
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
                        if items:
                            extracted_json = True
                    except Exception:
                        pass

                if not extracted_json:
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
                        parsed_price = clean_num(price_elem.get_text() if hasattr(price_elem, "get_text") else str(price_elem))

                        if parsed_price and parsed_price >= 10000:
                            results.append({
                                "portal": "Imovirtual",
                                "title": title_elem.get_text(strip=True) if title_elem else f"Apartamento em {query.title()}",
                                "price": parsed_price,
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
# 2. OLX IMÓVEIS (HTML Architecture)
# ==============================================================================

def scrape_olx_imoveis(query, max_pages=1):
    results = []
    slug = query.strip().lower().replace(" ", "-")

    with requests.Session() as session:
        for page in range(1, max_pages + 1):
            url = f"https://www.olx.pt/imoveis/apartamentos-casas-venda/{slug}/?page={page}"
            try:
                r = session.get(url, headers=COMMON_HEADERS, impersonate=BROWSER_IMPERSONATE, timeout=REQUEST_TIMEOUT)
                if r.status_code != 200:
                    # Generic query fallback
                    url = f"https://www.olx.pt/imoveis/apartamentos-casas-venda/q-{slug}/?page={page}"
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
                    parsed_price = clean_num(price_elem.get_text()) if price_elem else None

                    if parsed_price is None or parsed_price < 10000:
                        continue

                    href = link_elem["href"]
                    full_link = f"https://www.olx.pt{href}" if href.startswith("/") else href
                    card_text = card.get_text(" ", strip=True)

                    results.append({
                        "portal": "OLX Imóveis",
                        "title": title,
                        "price": parsed_price,
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
# 3. CUSTOJUSTO (Clean Regional Search)
# ==============================================================================

def scrape_custojusto(query, max_pages=1):
    results = []
    slug = query.strip().lower().replace(" ", "-")

    with requests.Session() as session:
        for page in range(1, max_pages + 1):
            url = f"https://www.custojusto.pt/{slug}/imobiliario/comprar-casas?o={page}"
            try:
                r = session.get(url, headers=COMMON_HEADERS, impersonate=BROWSER_IMPERSONATE, timeout=REQUEST_TIMEOUT)
                if r.status_code != 200:
                    url = f"https://www.custojusto.pt/portugal/imobiliario/comprar-casas?q={urllib.parse.quote(query)}&o={page}"
                    r = session.get(url, headers=COMMON_HEADERS, impersonate=BROWSER_IMPERSONATE, timeout=REQUEST_TIMEOUT)
                    if r.status_code != 200:
                        break

                soup = BeautifulSoup(r.text, "lxml")
                cards = soup.select(".container_list, .listing_item, a[href*='/imobiliario/']")
                for c in cards:
                    link_elem = c if c.name == "a" else c.find("a", href=True)
                    if not link_elem or not link_elem.get("href"):
                        continue

                    href = link_elem["href"]
                    if "/imobiliario/" not in href or href == "/imobiliario/":
                        continue

                    title_elem = c.find(["h2", "h3"]) or link_elem
                    price_elem = c.find(string=re.compile(r"€"))
                    parsed_price = clean_num(str(price_elem)) if price_elem else None

                    # Ignore accessory items, parking spaces, and placeholder prices
                    if parsed_price is None or parsed_price < 10000:
                        continue

                    card_text = c.get_text(" ", strip=True)
                    results.append({
                        "portal": "CustoJusto",
                        "title": title_elem.get_text(strip=True) if title_elem else f"Imóvel em {query.title()}",
                        "price": parsed_price,
                        "typology": extract_typology(card_text),
                        "area_m2": extract_area(card_text),
                        "location": query.title(),
                        "link": href if href.startswith("http") else f"https://www.custojusto.pt{href}"
                    })
                time.sleep(0.3)
            except Exception:
                break
    return results

# ==============================================================================
# 4. BPI EXPRESSO IMOBILIÁRIO (Server-Side HTML)
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
                cards = soup.select(".card-imovel, .imovel-card, div[class*='property-card'], .card")
                for card in cards:
                    link_elem = card.find("a", href=True)
                    if not link_elem:
                        continue

                    price_elem = card.find(string=re.compile(r"€"))
                    parsed_price = clean_num(str(price_elem)) if price_elem else None
                    if parsed_price is None or parsed_price < 10000:
                        continue

                    title_elem = card.find(["h2", "h3", "h4"])
                    card_text = card.get_text(" ", strip=True)
                    href = link_elem["href"]
                    full_link = href if href.startswith("http") else f"https://bpiexpressoimobiliario.pt{href}"

                    results.append({
                        "portal": "BPI Expresso",
                        "title": title_elem.get_text(strip=True) if title_elem else f"Imóvel em {query.title()}",
                        "price": parsed_price,
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
# 5. SUPERCASA (Direct HTML Query)
# ==============================================================================

def scrape_supercasa(query, max_pages=1):
    results = []
    slug = query.strip().lower().replace(" ", "-")

    with requests.Session() as session:
        for page in range(1, max_pages + 1):
            url = f"https://supercasa.pt/comprar-casas/{slug}?pagina={page}"
            try:
                r = session.get(url, headers=COMMON_HEADERS, impersonate=BROWSER_IMPERSONATE, timeout=REQUEST_TIMEOUT)
                if r.status_code != 200:
                    url = f"https://supercasa.pt/comprar-casas?s={urllib.parse.quote(query)}&pagina={page}"
                    r = session.get(url, headers=COMMON_HEADERS, impersonate=BROWSER_IMPERSONATE, timeout=REQUEST_TIMEOUT)
                    if r.status_code != 200:
                        break

                soup = BeautifulSoup(r.text, "lxml")
                cards = soup.select(".property-list-item, .property-card, div[class*='property']")
                for card in cards:
                    link_elem = card.select_one("a[href*='/imovel/'], a[href*='/comprar-'], a.property-link")
                    if not link_elem or not link_elem.get("href"):
                        link_elem = card.find("a", href=True)

                    if not link_elem:
                        continue

                    title_elem = card.find(["h2", "h3"]) or link_elem
                    price_elem = card.find(string=re.compile(r"€"))
                    parsed_price = clean_num(str(price_elem)) if price_elem else None

                    if parsed_price is None or parsed_price < 10000:
                        continue

                    href = link_elem["href"]
                    full_link = href if href.startswith("http") else f"https://supercasa.pt{href}"
                    card_text = card.get_text(" ", strip=True)

                    results.append({
                        "portal": "SuperCasa",
                        "title": title_elem.get_text(strip=True) if title_elem else f"Imóvel em {query.title()}",
                        "price": parsed_price,
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
# MULTI-THREAD DISPATCHER
# ==============================================================================

PORTAL_MAP = {
    "Imovirtual": scrape_imovirtual,
    "OLX Imóveis": scrape_olx_imoveis,
    "CustoJusto": scrape_custojusto,
    "BPI Expresso": scrape_bpi_expresso,
    "SuperCasa": scrape_supercasa,
}

def run_multi_scraper(selected_portals, location, pages):
    all_data = []
    with ThreadPoolExecutor(max_workers=len(selected_portals)) as executor:
        future_to_portal = {
            executor.submit(PORTAL_MAP[p], location, pages): p
            for p in selected_portals if p in PORTAL_MAP
        }
        for fut in as_completed(future_to_portal):
            portal_name = future_to_portal[fut]
            try:
                res = fut.result()
                all_data.extend(res)
            except Exception as e:
                st.error(f"Error scraping {portal_name}: {e}")

    # Deduplicate matches
    seen = set()
    deduped = []
    for item in all_data:
        key = (item["portal"], item["link"])
        if key not in seen:
            seen.add(key)
            deduped.append(item)
    return deduped

# ==============================================================================
# STREAMLIT UI & INTERACTION
# ==============================================================================

st.set_page_config(page_title="Portugal Real Estate Intelligence | By Max", page_icon="🇵🇹", layout="wide")

st.markdown(
    """
    <style>
    .banner-container {
        background: radial-gradient(circle at 10% 20%, #1e3c72 0%, #172a4d 90%);
        border-radius: 18px;
        padding: 34px;
        color: #ffffff;
        box-shadow: 0 12px 30px rgba(0,0,0,0.3);
        margin-bottom: 25px;
        border: 1px solid rgba(255, 255, 255, 0.12);
        position: relative;
    }
    .banner-container::after {
        content: "🇵🇹";
        position: absolute;
        right: 25px;
        top: 15px;
        font-size: 6.5rem;
        opacity: 0.15;
    }
    .banner-title {
        font-size: 2.3rem;
        font-weight: 800;
        margin: 0;
        letter-spacing: -0.5px;
    }
    .banner-sub {
        font-size: 1.05rem;
        color: #d1d5db;
        margin-top: 8px;
        max-width: 680px;
        line-height: 1.5;
    }
    .badge-author {
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
    }
    .footer {
        text-align: center;
        padding: 40px 0 20px 0;
        color: #9ca3af;
        font-size: 0.85rem;
    }
    </style>

    <div class="banner-container">
        <div class="banner-title">Portugal Real Estate Intelligence Hub</div>
        <div class="banner-sub">
            Aggregating real-time listings across Portugal with automated Deal Scoring (€/m²), ROI calculators, and cross-portal analytics.
        </div>
        <div class="badge-author">
            ⚡ Engineered & Designed by Max
        </div>
    </div>
    """,
    unsafe_allow_html=True
)

# Sidebar
with st.sidebar:
    st.markdown("### 🔍 Search Target")
    location_input = st.text_input("City or Municipality", value="Lisboa", help="e.g. Lisboa, Porto, Cascais, Sintra, Coimbra")

    selected_portals = st.multiselect(
        "Select Portals",
        ["Imovirtual", "OLX Imóveis", "CustoJusto", "BPI Expresso", "SuperCasa"],
        default=["Imovirtual", "OLX Imóveis", "CustoJusto"]
    )

    pages_per_portal = st.slider("Pages to scrape per site", 1, 4, 2)

    st.markdown("---")
    st.markdown("### 🎯 Listing Filters")
    min_price = st.number_input("Min Price (€)", min_value=10000, value=50000, step=15000)
    max_price = st.number_input("Max Price (€)", min_value=10000, value=1500000, step=25000)

    typology_filter = st.multiselect(
        "Typology",
        ["T0", "T1", "T2", "T3", "T4", "T5+"],
        default=[]
    )

    only_deals = st.checkbox("🔥 Show only Bargain Deals (>15% below median €/m²)")

    sort_choice = st.selectbox(
        "Sort By",
        ["Lowest Price First (€ ↑)", "Highest Price First (€ ↓)", "Best Price/m² (Lowest €/m²)", "Portal Default"]
    )

    search_btn = st.button("🚀 Fetch Properties", use_container_width=True, type="primary")

# Execution
if search_btn:
    if not selected_portals:
        st.warning("Please select at least one portal from the sidebar.")
    else:
        with st.spinner(f"Aggregating live data across {len(selected_portals)} portals for '{location_input}'..."):
            raw_results = run_multi_scraper(selected_portals, location_input, pages_per_portal)

        counts = {}
        for it in raw_results:
            counts[it["portal"]] = counts.get(it["portal"], 0) + 1

        if not raw_results:
            st.error("No listings returned. The selected sites might have temporarily blocked requests or returned 0 matches for this keyword.")
        else:
            status_text = ", ".join([f"{k}: {v}" for k, v in counts.items()])
            st.success(f"Successfully aggregated {len(raw_results)} listings: ({status_text})")

        # Feature: Calculate Price per m² & Market Deal Score
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
                    it["deal_status"] = "🔥 Bargain (-15%+)"
                elif diff >= 25:
                    it["deal_status"] = "⚠️ High Premium"
                else:
                    it["deal_status"] = "Fair Market"
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
            if only_deals and "🔥 Bargain" not in r["deal_status"]:
                continue
            filtered.append(r)

        # Apply Sorting
        if sort_choice == "Lowest Price First (€ ↑)":
            filtered.sort(key=lambda x: x["price"] if x["price"] is not None else float("inf"))
        elif sort_choice == "Highest Price First (€ ↓)":
            filtered.sort(key=lambda x: x["price"] if x["price"] is not None else float("-inf"), reverse=True)
        elif sort_choice == "Best Price/m² (Lowest €/m²)":
            filtered.sort(key=lambda x: x["price_per_m2"] if x["price_per_m2"] is not None else float("inf"))

        st.session_state["real_estate_data"] = filtered
        st.session_state["median_m2"] = median_m2

# Display & Analytics
if "real_estate_data" in st.session_state:
    data = st.session_state["real_estate_data"]

    if data:
        df = pd.DataFrame(data)

        # KPIs
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Available Listings", len(df))
        valid_prices = df["price"].dropna()
        c2.metric("Median Listing Price", f"{valid_prices.median():,.0f} €" if not valid_prices.empty else "N/A")
        c3.metric("Median Market €/m²", f"{st.session_state.get('median_m2', 0):,.0f} €/m²")
        c4.metric("Active Portals Reporting", df["portal"].nunique())

        st.markdown("<br>", unsafe_allow_html=True)

        tab1, tab2, tab3 = st.tabs(["📋 Listings Grid", "📊 Market Analytics", "💰 Mortgage & Investment Simulator"])

        with tab1:
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine="openpyxl") as writer:
                df.to_excel(writer, index=False, sheet_name="Imoveis")

            st.download_button(
                label="📥 Export Filtered Results to Excel (.xlsx)",
                data=buf.getvalue(),
                file_name=f"imoveis_{location_input.lower().replace(' ', '_')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )

            st.dataframe(
                df[["portal", "deal_status", "title", "price", "typology", "area_m2", "price_per_m2", "link"]],
                column_config={
                    "portal": st.column_config.TextColumn("Portal", width="small"),
                    "deal_status": st.column_config.TextColumn("Deal Score", width="medium"),
                    "title": st.column_config.TextColumn("Title", width="large"),
                    "price": st.column_config.NumberColumn("Price (€)", format="%.0f €"),
                    "typology": st.column_config.TextColumn("Tipologia", width="small"),
                    "area_m2": st.column_config.NumberColumn("Area (m²)", format="%.0f m²"),
                    "price_per_m2": st.column_config.NumberColumn("Price/m²", format="%.0f €/m²"),
                    "link": st.column_config.LinkColumn("Direct Listing", display_text="Open Listing")
                },
                use_container_width=True,
                hide_index=True
            )

        with tab2:
            st.subheader("Market Visualizations")
            col_a, col_b = st.columns(2)
            with col_a:
                st.write("**Listings Breakdown by Portal**")
                st.bar_chart(df["portal"].value_counts())
            with col_b:
                st.write("**Listings Breakdown by Typology**")
                valid_types = df[df["typology"] != "N/A"]["typology"].value_counts()
                st.bar_chart(valid_types)

        with tab3:
            st.subheader("Interactive Mortgage & Yield Calculator")
            st.caption("Calculate your estimated monthly payment and rental yield on any property in your results.")

            calc_col1, calc_col2 = st.columns(2)
            with calc_col1:
                # Guaranteed to satisfy min_value=10000
                default_price = max(10000, int(valid_prices.median())) if not valid_prices.empty else 250000
                selected_price = st.number_input(
                    "Property Price (€)",
                    min_value=10000,
                    value=default_price,
                    step=5000
                )
                down_payment_pct = st.slider("Down Payment (%)", 10, 50, 20)
                interest_rate = st.slider("Interest Rate (%)", 1.0, 7.0, 3.5, step=0.1)
                loan_years = st.slider("Loan Duration (Years)", 10, 40, 30)

            # Standard French amortization formula: M = P * [ i(1 + i)^n ] / [ (1 + i)^n – 1]
            loan_amount = selected_price * (1 - down_payment_pct / 100)
            monthly_rate = (interest_rate / 100) / 12
            num_payments = loan_years * 12

            if monthly_rate > 0:
                monthly_mortgage = loan_amount * (monthly_rate * (1 + monthly_rate)**num_payments) / ((1 + monthly_rate)**num_payments - 1)
            else:
                monthly_mortgage = loan_amount / num_payments

            with calc_col2:
                est_monthly_rent = st.number_input("Estimated Monthly Rent (€)", min_value=100, value=int(selected_price * 0.005), step=50)
                gross_yield = (est_monthly_rent * 12 / selected_price) * 100

                st.markdown("#### Financial Breakdown")
                st.write(f"**Financed Amount:** {loan_amount:,.2f} €")
                st.write(f"**Estimated Monthly Mortgage:** `{monthly_mortgage:,.2f} € / month`")
                st.write(f"**Gross Annual Rental Yield:** `{gross_yield:.2f}%`")

                net_cashflow = est_monthly_rent - monthly_mortgage
                cashflow_color = "green" if net_cashflow > 0 else "red"
                st.markdown(f"**Estimated Cashflow:** <span style='color:{cashflow_color}; font-weight:bold;'>{net_cashflow:,.2f} € / month</span>", unsafe_allow_html=True)

    else:
        st.warning("No listings matched your active price or typology filters.")

st.markdown(
    """
    <div class="footer">
        Portugal Real Estate Multi-Scraper Platform • Built with Python & Streamlit • Made by Max
    </div>
    """,
    unsafe_allow_html=True
)
