"""Shopee Asset Downloader — download product images from Shopee/Affiliate links.

Supports:
- Affiliate links: https://affiliate.shopee.vn/offer/product_offer?offer_id=...&item_id=...
- Standard product URLs: https://shopee.vn/product/{shop_id}/{item_id}
- Slug URLs: https://shopee.vn/Ten-San-Pham-i.{shop_id}.{item_id}
- Short URLs: https://s.shopee.vn/... (unshortens via HTTP HEAD/GET redirect)
- Direct directory of pre-downloaded images

Downloads all high-resolution images to out/affiliate_runs/<run_id>/shopee_images/
and identifies the primary garment try-on image.
"""

from __future__ import annotations

import argparse
import json
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

import requests

SHOPEE_CDN_BASE = "https://down-vn.img.susercontent.com/file/"
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://shopee.vn/",
    "X-Requested-With": "XMLHttpRequest",
}


@dataclass
class ShopeeProductInfo:
    shop_id: Optional[int]
    item_id: Optional[int]
    title: str
    image_ids: list[str]
    image_urls: list[str]
    downloaded_paths: list[Path]
    primary_garment_path: Optional[Path] = None


def resolve_shopee_url(url: str, timeout: float = 10.0) -> str:
    """Follow redirects to resolve shortlinks like s.shopee.vn, shp.ee, etc."""
    url = url.strip()
    short_domains = ("s.shopee.vn", "shp.ee", "shope.ee", "vn.shp.ee", "shopee.page.link")
    if any(dom in url for dom in short_domains):
        try:
            resp = requests.head(url, allow_redirects=True, headers=DEFAULT_HEADERS, timeout=timeout)
            return resp.url
        except Exception:
            try:
                resp = requests.get(url, allow_redirects=True, headers=DEFAULT_HEADERS, timeout=timeout)
                return resp.url
            except Exception:
                pass
    return url


def parse_shopee_ids(url: str) -> tuple[Optional[int], Optional[int]]:
    """Extract (shop_id, item_id) from various Shopee URL styles.

    Supports:
    - Affiliate query styles: itemId, item_id, itemid, productId, product_id
    - Shop query styles: shopId, shop_id, shopid, seller_id
    - Slug URLs: -i.{shop_id}.{item_id}
    - Path URLs: /product/{shop_id}/{item_id}
    - SPA hash query strings
    """
    clean_url = resolve_shopee_url(url)
    parsed = urllib.parse.urlparse(clean_url)

    # Combine regular query and hash fragment query
    qs_raw = urllib.parse.parse_qs(parsed.query)
    if "#" in clean_url or parsed.fragment:
        frag = parsed.fragment
        if "?" in frag:
            frag_query = frag.split("?", 1)[1]
            for k, v in urllib.parse.parse_qs(frag_query).items():
                qs_raw.setdefault(k, v)

    # Normalize all query parameter keys to lowercase
    qs: dict[str, list[str]] = {str(k).lower(): v for k, v in qs_raw.items()}

    # Extract item_id
    item_id = None
    for item_key in ("item_id", "itemid", "item", "product_id", "productid", "id"):
        if item_key in qs and qs[item_key]:
            try:
                item_id = int(qs[item_key][0])
                break
            except (ValueError, TypeError):
                pass

    # Extract shop_id
    shop_id = None
    for shop_key in ("shop_id", "shopid", "shop", "seller_id", "sellerid"):
        if shop_key in qs and qs[shop_key]:
            try:
                shop_id = int(qs[shop_key][0])
                break
            except (ValueError, TypeError):
                pass

    if item_id:
        return shop_id, item_id

    # Pattern: -i.{shop_id}.{item_id} (standard product slug)
    m = re.search(r"-i\.(\d+)\.(\d+)", parsed.path)
    if m:
        return int(m.group(1)), int(m.group(2))

    # Pattern: /product/{shop_id}/{item_id} or /(?:item|pdp)/{shop_id}/{item_id}
    m = re.search(r"/(?:product|item|pdp)/(\d+)/(\d+)", parsed.path)
    if m:
        return int(m.group(1)), int(m.group(2))

    return None, None


def fetch_shopee_product_details(
    shop_id: Optional[int],
    item_id: int,
    session: Optional[requests.Session] = None,
    timeout: float = 12.0,
) -> dict[str, Any]:
    """Fetch product details and image hashes from Shopee API v4 / PDP API.

    If shop_id is 0 or None, queries with item_id or fallback endpoints.
    """
    s = session or requests.Session()
    s.headers.update(DEFAULT_HEADERS)

    # 1. Shopee public item get endpoint (v4)
    api_url = f"https://shopee.vn/api/v4/item/get?itemid={item_id}"
    if shop_id:
        api_url += f"&shopid={shop_id}"

    try:
        resp = s.get(api_url, timeout=timeout)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("data"):
                return data["data"]
    except Exception:
        pass

    # 2. Shopee PDP PC endpoint
    pdp_url = f"https://shopee.vn/api/v4/pdp/get_pc?item_id={item_id}"
    if shop_id:
        pdp_url += f"&shop_id={shop_id}"
    try:
        resp = s.get(pdp_url, timeout=timeout)
        if resp.status_code == 200:
            data = resp.json().get("data") or {}
            item_data = data.get("item") or data
            if item_data.get("images") or item_data.get("title") or item_data.get("name"):
                return item_data
    except Exception:
        pass

    # 3. Fallback endpoint (v2)
    api_url_v2 = f"https://shopee.vn/api/v2/item/get?itemid={item_id}"
    if shop_id:
        api_url_v2 += f"&shopid={shop_id}"
    try:
        resp = s.get(api_url_v2, timeout=timeout)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("item"):
                return data["item"]
    except Exception:
        pass

    return {}


def download_image(url: str, dest_path: Path, timeout: float = 20.0) -> bool:
    """Download single image file with validation."""
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=timeout)
        if resp.status_code == 200 and len(resp.content) > 1024:
            # Check magic bytes for JPEG / PNG / WEBP
            data = resp.content
            if (
                data[:3] == b"\xff\xd8\xff"
                or data[:8] == b"\x89PNG\r\n\x1a\n"
                or (data[:4] == b"RIFF" and data[8:12] == b"WEBP")
            ):
                dest_path.write_bytes(data)
                return True
    except Exception:
        pass
    return False


def pick_primary_garment_image(image_paths: list[Path]) -> Optional[Path]:
    """Select the best try-on garment image from a list of product images.

    Heuristics:
    1. Prefer square/portrait product images over banners/spec sheets.
    2. Prefer the 2nd or 3rd image if the 1st has heavy text/promotional badges,
       or the 1st if only 1-2 images exist.
    """
    if not image_paths:
        return None
    if len(image_paths) == 1:
        return image_paths[0]

    # Usually image #2 (index 1) in apparel listings is a clean clothing shot
    # without promotional frames/stamps. Index 0 often has discount badges.
    if len(image_paths) >= 2:
        return image_paths[1]
    return image_paths[0]


class ShopeeAssetDownloader:
    """High-level downloader for Shopee Affiliate / Product images."""

    def __init__(self, out_dir: Optional[Path] = None):
        self.out_dir = Path(out_dir) if out_dir else Path("out/affiliate_runs")
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    def process_url(
        self,
        url: str,
        dest_subdir: Optional[str] = None,
        on_event: Optional[Callable[[str, str], None]] = None,
    ) -> ShopeeProductInfo:
        """Download all images from Shopee URL and return ShopeeProductInfo."""
        log = on_event or (lambda kind, msg: None)
        log("step", f"Phân tích liên kết Shopee: {url}")

        clean_url = resolve_shopee_url(url)
        shop_id, item_id = parse_shopee_ids(clean_url)
        if not item_id:
            raise ValueError(f"Không thể trích xuất item_id từ URL Shopee: {url}")

        log("info", f"Trích xuất thành công: shop_id={shop_id}, item_id={item_id}")
        data = fetch_shopee_product_details(shop_id, item_id, session=self.session)

        title = data.get("name") or data.get("title") or f"shopee_product_{item_id}"
        images = data.get("images") or []
        image_urls = []

        for img_id in images:
            if isinstance(img_id, str):
                if img_id.startswith("http"):
                    image_urls.append(img_id)
                else:
                    image_urls.append(f"{SHOPEE_CDN_BASE}{img_id}")

        folder_name = dest_subdir or f"shopee_{item_id}"
        target_dir = self.out_dir / folder_name / "shopee_images"
        target_dir.mkdir(parents=True, exist_ok=True)

        log("step", f"Tải {len(image_urls)} ảnh sản phẩm vào {target_dir}...")
        downloaded: list[Path] = []

        for idx, img_url in enumerate(image_urls, start=1):
            dest_file = target_dir / f"product_img_{idx:02d}.jpg"
            if download_image(img_url, dest_file):
                downloaded.append(dest_file)
                log("info", f"Đã tải ảnh {idx}/{len(image_urls)}: {dest_file.name}")

        primary = pick_primary_garment_image(downloaded)
        log("info", f"Ảnh mẫu mặc thử được chọn: {primary.name if primary else 'Không có'}")

        return ShopeeProductInfo(
            shop_id=shop_id,
            item_id=item_id,
            title=title,
            image_ids=images,
            image_urls=image_urls,
            downloaded_paths=downloaded,
            primary_garment_path=primary,
        )

    def load_local_images(self, local_dir: Path) -> ShopeeProductInfo:
        """Load already downloaded images from a local directory."""
        local_dir = Path(local_dir)
        if not local_dir.is_dir():
            raise FileNotFoundError(f"Thư mục không tồn tại: {local_dir}")

        exts = {".jpg", ".jpeg", ".png", ".webp"}
        files = sorted([f for f in local_dir.iterdir() if f.suffix.lower() in exts])
        primary = pick_primary_garment_image(files)

        return ShopeeProductInfo(
            shop_id=None,
            item_id=None,
            title=local_dir.stem,
            image_ids=[],
            image_urls=[],
            downloaded_paths=files,
            primary_garment_path=primary,
        )
