"""
Scrapers for Brazilian pharmacy price comparison.
Confirmed working as of 2026-03:
  - Pague Menos        (VTEX API) — national
  - Drogaria São Paulo (VTEX API) — national
  - Farmácia Indiana   (VTEX API) — national
  - Drogaria Globo     (VTEX API) — RJ
  - Ultrafarma         (HTML data attributes) — national
  - Drogasil           (Next.js pageProps JSON, requires python-httpx UA) — national
  - Droga Raia         (Next.js pageProps JSON, requires python-httpx UA) — national
  - Panvel             (Angular SWR cache: search page + product pages, pricePerUnit × qty) — RS/SC/PR
  - Farmácia São João  (VTEX API) — RS
"""

# State coverage map: which states each pharmacy delivers to.
# None means nationwide (all states).
PHARMACY_STATES: dict[str, list[str] | None] = {
    "Ultrafarma":         None,           # nationwide
    "Drogasil":           None,
    "Droga Raia":         None,
    "Pague Menos":        None,
    "Drogaria São Paulo": None,
    "Farmácia Indiana":   None,
    "Drogaria Globo":     ["RJ"],
    "Panvel":             ["RS", "SC", "PR"],
    "Farmácia São João":  ["RS"],
}

import asyncio
import re
import httpx
from bs4 import BeautifulSoup
from typing import Optional

# Matches pack-size units (tablets, capsules, etc.) — NOT dosage units (mg, ml, mcg)
_PACK_UNIT_RE = re.compile(
    r'(\d+(?:[.,]\d+)?)\s*'
    r'(comprimidos?|cápsulas?|capsulas?|comp\.?|caps?\.?|drágeas?|grageas?|'
    r'bisnagas?|sachês?|envelopes?|supositórios?|unidades?|ampolas?|'
    r'pastilhas?|óvulos?|adesivos?|tabletes?)',
    re.IGNORECASE,
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    "Accept": "application/json, text/html, */*",
}

# Drogasil/Droga Raia block browser UAs but allow httpx default UA
HEADERS_RAIADROGASIL = {
    "User-Agent": "python-httpx/0.27.2",
    "Accept-Language": "pt-BR,pt;q=0.9",
    "Accept": "text/html,*/*",
}


def parse_pack_qty(name: str) -> float:
    """Extract pack quantity (number of tablets/capsules) from product name.
    Returns 1.0 if no recognisable pack unit is found."""
    matches = _PACK_UNIT_RE.findall(name)
    if matches:
        qty_str = matches[-1][0].replace(",", ".")
        try:
            return float(qty_str)
        except ValueError:
            pass
    return 1.0


def format_price(value: float) -> str:
    """Format float as Brazilian currency string."""
    formatted = f"{value:,.2f}"  # e.g. "21.39" or "1,234.56"
    # Convert to Brazilian format: dot → comma, comma → dot
    formatted = formatted.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {formatted}"


def _parse_vtex_item(item: dict, base_url: str, pharmacy: str, logo: str) -> Optional[dict]:
    """Extract product info from a VTEX catalog API item."""
    try:
        name = item.get("productName", "")
        link = item.get("link", "")
        if not link:
            return None
        if not link.startswith("http"):
            link = base_url.rstrip("/") + "/" + link.lstrip("/")

        items_list = item.get("items", [])
        if not items_list:
            return None

        sellers = items_list[0].get("sellers", [])
        if not sellers:
            return None

        offer = sellers[0].get("commertialOffer", {})
        price = offer.get("Price")
        available = offer.get("IsAvailable", True)

        if not price or not available or price <= 0:
            return None

        name_str = str(name)[:80]
        brand = str(item.get("brand", ""))[:60]
        generico_spec = item.get("Generico", [])
        if not isinstance(generico_spec, list):
            generico_spec = []
        is_generic = ("Sim" in generico_spec) or bool(
            re.search(r"gen[eé]rico", name_str, re.I)
        )
        qty = parse_pack_qty(name_str)
        p = float(price)

        return {
            "pharmacy": pharmacy,
            "name": name_str,
            "price": p,
            "price_str": format_price(p),
            "price_per_unit": round(p / qty, 4),
            "qty": qty,
            "brand": brand,
            "is_generic": is_generic,
            "url": link,
            "logo": logo,
        }
    except Exception:
        return None


async def _search_vtex(
    client: httpx.AsyncClient,
    base_url: str,
    pharmacy: str,
    logo: str,
    medicine: str,
    count: int = 5,
) -> list[dict]:
    """Generic VTEX catalog search."""
    results = []
    try:
        import urllib.parse
        query = urllib.parse.quote(medicine)
        url = (
            f"{base_url}/api/catalog_system/pub/products/search"
            f"?ft={query}&_from=0&_to={count - 1}"
        )
        r = await client.get(url, timeout=15)
        if r.status_code not in (200, 206):
            return []
        data = r.json()
        if not isinstance(data, list):
            return []
        for item in data:
            parsed = _parse_vtex_item(item, base_url, pharmacy, logo)
            if parsed:
                results.append(parsed)
    except Exception as e:
        print(f"[{pharmacy}] error: {e}")
    return results


async def search_paguemenos(client: httpx.AsyncClient, medicine: str) -> list[dict]:
    return await _search_vtex(
        client,
        "https://www.paguemenos.com.br",
        "Pague Menos",
        "🟡",
        medicine,
    )


async def search_drogariasaopaulo(client: httpx.AsyncClient, medicine: str) -> list[dict]:
    return await _search_vtex(
        client,
        "https://www.drogariasaopaulo.com.br",
        "Drogaria São Paulo",
        "🔵",
        medicine,
    )


async def search_farmaciaindiana(client: httpx.AsyncClient, medicine: str) -> list[dict]:
    return await _search_vtex(
        client,
        "https://www.farmaciaindiana.com.br",
        "Farmácia Indiana",
        "🟠",
        medicine,
    )


async def search_drogariaglobo(client: httpx.AsyncClient, medicine: str) -> list[dict]:
    return await _search_vtex(
        client,
        "https://www.drogariaglobo.com.br",
        "Drogaria Globo",
        "🟣",
        medicine,
    )


async def _search_raiadrogasil(
    medicine: str,
    base_url: str,
    pharmacy: str,
    logo: str,
) -> list[dict]:
    """
    Drogasil and Droga Raia share the RaiaDrogasil platform.
    They embed product data in a Next.js __NEXT_DATA__-style script tag.
    Browser user-agents are blocked; python-httpx UA passes through.
    """
    results = []
    try:
        import urllib.parse
        query = urllib.parse.quote(medicine)
        url = f"{base_url}/search?w={query}"
        # Use a separate client with the non-browser UA
        async with httpx.AsyncClient(
            headers=HEADERS_RAIADROGASIL,
            follow_redirects=True,
            timeout=20,
        ) as client:
            r = await client.get(url, timeout=15)
        if r.status_code != 200:
            return []

        soup = BeautifulSoup(r.text, "lxml")
        # Find the largest script tag — it contains the Next.js page data
        big_script = max(
            (s.string for s in soup.find_all("script") if s.string),
            key=len,
            default=None,
        )
        if not big_script or len(big_script) < 1000:
            return []

        import json as _json
        data = _json.loads(big_script)
        products = (
            data.get("props", {})
            .get("pageProps", {})
            .get("pageProps", {})
            .get("results", {})
            .get("products", [])
        )
        if not isinstance(products, list):
            return []

        for p in products:
            name = p.get("name", "")
            price = p.get("priceService")
            rel_url = p.get("url", "")
            if not name or not price or not rel_url or float(price) <= 0:
                continue
            # Strip ?origin=search tracking param
            rel_url = rel_url.split("?")[0]
            full_url = base_url + rel_url
            name_str = str(name)[:80]
            brand = str(p.get("brand", ""))[:60]
            is_generic = bool(p.get("isGeneric", False)) or bool(
                re.search(r"gen[eé]rico", name_str, re.I)
            )
            qty = parse_pack_qty(name_str)
            pf = float(price)
            results.append({
                "pharmacy": pharmacy,
                "name": name_str,
                "price": pf,
                "price_str": format_price(pf),
                "price_per_unit": round(pf / qty, 4),
                "qty": qty,
                "brand": brand,
                "is_generic": is_generic,
                "url": full_url,
                "logo": logo,
            })
    except Exception as e:
        print(f"[{pharmacy}] error: {e}")
    return results


async def search_drogasil(medicine: str) -> list[dict]:
    return await _search_raiadrogasil(
        medicine,
        "https://www.drogasil.com.br",
        "Drogasil",
        "🔴",
    )


async def search_drogaraia(medicine: str) -> list[dict]:
    return await _search_raiadrogasil(
        medicine,
        "https://www.drogaraia.com.br",
        "Droga Raia",
        "🟢",
    )


async def search_ultrafarma(client: httpx.AsyncClient, medicine: str) -> list[dict]:
    """Ultrafarma uses Angular with data attributes for product info."""
    results = []
    try:
        import urllib.parse
        query = urllib.parse.quote(medicine)
        url = f"https://www.ultrafarma.com.br/busca?q={query}"
        r = await client.get(url, timeout=15)
        if r.status_code != 200:
            return []

        soup = BeautifulSoup(r.text, "lxml")
        items = soup.select("[data-product-id]")

        for item in items:
            name = item.get("data-product-name", "").strip()
            price_raw = item.get("data-product-price", "")
            link_el = item.select_one("a[href]")

            if not name or not price_raw or not link_el:
                continue

            href = link_el["href"]
            full_url = href if href.startswith("http") else f"https://www.ultrafarma.com.br{href}"

            try:
                price = float(price_raw)
            except ValueError:
                continue

            if price <= 0:
                continue

            name_str = name[:80]
            brand = item.get("data-product-brand", "").strip()[:60]
            is_generic = bool(re.search(r"gen[eé]rico", name_str, re.I))
            qty = parse_pack_qty(name_str)
            results.append({
                "pharmacy": "Ultrafarma",
                "name": name_str,
                "price": price,
                "price_str": format_price(price),
                "price_per_unit": round(price / qty, 4),
                "qty": qty,
                "brand": brand,
                "is_generic": is_generic,
                "url": full_url,
                "logo": "💊",
            })
    except Exception as e:
        print(f"[Ultrafarma] error: {e}")
    return results


async def _panvel_product_price(client: httpx.AsyncClient, url: str) -> Optional[float]:
    """Fetch a Panvel product page and return pricePerUnit (the total unit price for SSR store)."""
    try:
        r = await client.get(url, timeout=12)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, "lxml")
        big = max((s.string for s in soup.find_all("script") if s.string), key=len, default=None)
        if not big:
            return None
        import json as _json
        data = _json.loads(big)
        ps = data.get("productState", {})
        return ps.get("pricePerUnit")
    except Exception:
        return None


def _panvel_parse_qty(presentation_title: str) -> float:
    """
    Extract numeric quantity from Panvel's presentationTitle field.
    e.g. "30 comprimido(s)" → 30.0, "20 mililitro(s)" → 20.0
    """
    import re as _re
    nums = _re.findall(r"[\d]+(?:[,.][\d]+)?", presentation_title)
    if nums:
        return float(nums[0].replace(",", "."))
    return 1.0


async def search_saojoao(client: httpx.AsyncClient, medicine: str) -> list[dict]:
    return await _search_vtex(
        client,
        "https://www.saojoaofarmacias.com.br",
        "Farmácia São João",
        "🟩",
        medicine,
    )


async def search_panvel(medicine: str) -> list[dict]:
    """
    Panvel uses an Angular app. Prices are NOT in the search results —
    they only appear as `pricePerUnit` on individual product pages (in
    the SSR SWR cache embedded as a JSON script).

    Strategy:
      1. GET buscarProduto.do?termoPesquisa=<q>  → searchResponse.items (name, link, qty)
      2. Fetch each product page concurrently    → pricePerUnit
      3. total = pricePerUnit × qty_from_presentationTitle
    """
    results = []
    try:
        import urllib.parse, json as _json
        query = urllib.parse.quote(medicine)
        search_url = f"https://www.panvel.com/panvel/buscarProduto.do?termoPesquisa={query}"

        async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=20) as client:
            r = await client.get(search_url, timeout=15)
            if r.status_code != 200:
                return []

            soup = BeautifulSoup(r.text, "lxml")
            big = max((s.string for s in soup.find_all("script") if s.string), key=len, default=None)
            if not big:
                return []

            data = _json.loads(big)
            items = data.get("searchResponse", {}).get("items", [])
            if not isinstance(items, list):
                return []

            # Take top 5 unique items with valid links
            candidates = []
            seen = set()
            for item in items:
                link = item.get("link", "")
                name = item.get("name", "")
                if link and name and link not in seen:
                    seen.add(link)
                    candidates.append(item)
                if len(candidates) >= 5:
                    break

            # Fetch product pages concurrently
            price_tasks = [_panvel_product_price(client, c["link"]) for c in candidates]
            prices = await asyncio.gather(*price_tasks, return_exceptions=True)

        for item, price_per_unit in zip(candidates, prices):
            if not isinstance(price_per_unit, float) or not price_per_unit or price_per_unit <= 0:
                continue
            qty = _panvel_parse_qty(item.get("presentationTitle", ""))
            total_price = round(price_per_unit * qty, 2)
            if total_price <= 0:
                continue
            name_str = str(item.get("name", ""))[:80]
            brand = str(item.get("brandName", "")).strip()[:60]
            is_generic = bool(re.search(r"gen[eé]rico", name_str, re.I))
            results.append({
                "pharmacy": "Panvel",
                "name": name_str,
                "price": total_price,
                "price_str": format_price(total_price),
                "price_per_unit": round(price_per_unit, 4),
                "qty": qty,
                "brand": brand,
                "is_generic": is_generic,
                "url": item["link"],
                "logo": "🟤",
            })
    except Exception as e:
        print(f"[Panvel] error: {e}")
    return results


async def search_all(medicine: str) -> list[dict]:
    """Search all pharmacies concurrently and return results sorted by price."""
    async with httpx.AsyncClient(
        headers=HEADERS,
        follow_redirects=True,
        timeout=20,
    ) as client:
        tasks = [
            search_paguemenos(client, medicine),
            search_drogariasaopaulo(client, medicine),
            search_farmaciaindiana(client, medicine),
            search_drogariaglobo(client, medicine),
            search_ultrafarma(client, medicine),
            search_saojoao(client, medicine),
            search_drogasil(medicine),
            search_drogaraia(medicine),
            search_panvel(medicine),
        ]
        all_results = await asyncio.gather(*tasks, return_exceptions=True)

    merged: list[dict] = []
    for r in all_results:
        if isinstance(r, list):
            merged.extend(r)

    # Attach state coverage and deduplicate by URL, sorted by price ascending
    seen_urls: set[str] = set()
    unique: list[dict] = []
    for item in sorted(merged, key=lambda x: x["price"]):
        if item["url"] not in seen_urls:
            seen_urls.add(item["url"])
            coverage = PHARMACY_STATES.get(item["pharmacy"])
            item["states"] = coverage  # None = nationwide
            unique.append(item)

    return unique
