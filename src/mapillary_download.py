import os
import time
import requests
import pandas as pd
from datetime import datetime, UTC
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# === Load .env ===
load_dotenv()
TOKEN = os.getenv("MAPILLARY_TOKEN")

# Paths
BBOX_FILE = "data/bounding_boxes.csv"
META_FILE = "data/images_metadata.csv"
IMAGES_DIR = "data/images"

# Ensure dirs
os.makedirs("data", exist_ok=True)
os.makedirs(IMAGES_DIR, exist_ok=True)

# === Robust HTTP session with retries/backoff ===
def build_session():
    sess = requests.Session()
    retry = Retry(
        total=5,                # up to 5 retries
        connect=5,
        read=5,
        backoff_factor=1.0,     # 1s, 2s, 4s, ...
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=20, pool_maxsize=50)
    sess.mount("https://", adapter)
    sess.mount("http://", adapter)
    return sess

SESSION = build_session()

# Timeouts: (connect, read)
HTTP_TIMEOUT = (10, 60)

def fetch_images_for_bbox(bbox_str: str, token: str, limit: int):
    """Fetch up to `limit` images for a bbox in one call."""
    url = "https://graph.mapillary.com/images"
    params = {
        "access_token": token,
        "bbox": bbox_str,
        # request both; some items only have `geometry`
        "fields": "id,computed_geometry,geometry,captured_at",
        "limit": limit,
    }
    r = SESSION.get(url, params=params, timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    return r.json().get("data", [])

def fetch_thumb_url(img_id: str, token: str):
    """Return a thumbnail URL (try 2048, then 1024)."""
    base = f"https://graph.mapillary.com/{img_id}"
    for field in ("thumb_2048_url", "thumb_1024_url"):
        try:
            r = SESSION.get(base, params={"access_token": token, "fields": field}, timeout=HTTP_TIMEOUT)
            if r.status_code == 200:
                url = r.json().get(field)
                if url:
                    return url
        except requests.RequestException:
            # let retry/backoff happen via SESSION; if still failing, fall through
            pass
    return None

def download_image(url: str, dest_path: str):
    """Stream download an image with retries/backoff handled by SESSION."""
    tmp_path = dest_path + ".part"
    with SESSION.get(url, stream=True, timeout=HTTP_TIMEOUT) as r:
        r.raise_for_status()
        with open(tmp_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 64):
                if chunk:
                    f.write(chunk)
    os.replace(tmp_path, dest_path)

def load_meta_df():
    if os.path.exists(META_FILE) and os.path.getsize(META_FILE) > 0:
        return pd.read_csv(META_FILE, dtype=str).fillna("")
    return pd.DataFrame(columns=["id","location_name","longitude","latitude","captured_at","file_path","image_url"])

def safe_coords(img: dict):
    """Return (lon, lat) or None if unavailable."""
    geom = img.get("computed_geometry") or img.get("geometry")
    if not geom:
        return None
    coords = geom.get("coordinates")
    if not coords or len(coords) < 2:
        return None
    return coords[0], coords[1]

def safe_timestamp_ms(ms_val):
    """Return ISO UTC string from ms since epoch, or '' if missing."""
    if ms_val is None or str(ms_val).strip() == "":
        return ""
    try:
        return datetime.fromtimestamp(int(ms_val)/1000, UTC).isoformat()
    except Exception:
        return ""

def main():
    if not TOKEN:
        print("❌ MAPILLARY_TOKEN not set in .env")
        return
    if not os.path.exists(BBOX_FILE):
        print(f"❌ {BBOX_FILE} not found")
        return

    bbox_df = pd.read_csv(BBOX_FILE, dtype=str).fillna("")
    # trim spaces just in case
    for col in ("min_lon","min_lat","max_lon","max_lat","location_name","downloaded","limit"):
        if col in bbox_df.columns:
            bbox_df[col] = bbox_df[col].astype(str).str.strip()

    meta_df = load_meta_df()
    existing_ids = set(meta_df["id"].astype(str)) if not meta_df.empty else set()

    total_new = 0

    for idx, row in bbox_df.iterrows():
        if row.get("downloaded","").lower() == "yes":
            continue

        loc = row["location_name"]
        try:
            limit = int(row.get("limit","") or "60")
        except ValueError:
            limit = 60

        try:
            min_lon = float(row["min_lon"]); min_lat = float(row["min_lat"])
            max_lon = float(row["max_lon"]); max_lat = float(row["max_lat"])
        except Exception:
            print(f"⚠️  Skipping {loc}: invalid bbox numbers")
            continue

        bbox_str = f"{min_lon},{min_lat},{max_lon},{max_lat}"
        print(f"\n📍 {loc}: requesting up to {limit} images")

        try:
            images = fetch_images_for_bbox(bbox_str, TOKEN, limit)
        except requests.RequestException as e:
            print(f"   ❌ API error for {loc}: {e}")
            # don’t flip to yes; try again next run
            continue

        print(f"   Found {len(images)} candidates")

        new_rows = []
        for img in images:
            img_id = str(img.get("id","")).strip()
            if not img_id or img_id in existing_ids:
                continue

            # robust coord & time
            c = safe_coords(img)
            if not c:
                print(f"   ⚠️  {img_id}: no coordinates; skipping")
                continue
            lon, lat = c
            ts_iso = safe_timestamp_ms(img.get("captured_at"))

            # get thumbnail URL
            url = fetch_thumb_url(img_id, TOKEN)
            if not url:
                print(f"   ⚠️  {img_id}: no thumbnail URL; skipping")
                continue

            img_path = os.path.join(IMAGES_DIR, f"{img_id}.jpg")
            if not os.path.exists(img_path):
                try:
                    download_image(url, img_path)
                    print(f"   ✅ {img_id}.jpg")
                    # be nice to the API (tiny pause)
                    time.sleep(0.05)
                except requests.RequestException as e:
                    print(f"   ❌ failed {img_id}: {e}")
                    # skip this id; continue with others
                    continue

            new_rows.append({
                "id": img_id,
                "location_name": loc,
                "longitude": lon,
                "latitude": lat,
                "captured_at": ts_iso,
                "file_path": os.path.relpath(img_path),
                "image_url": url,
            })
            existing_ids.add(img_id)

        if new_rows:
            meta_df = pd.concat([meta_df, pd.DataFrame(new_rows)], ignore_index=True)
            total_new += len(new_rows)

        # Mark bbox as downloaded now that we've attempted it.
        # If you prefer only flip to yes when >=1 success, gate on `if new_rows:`
        bbox_df.at[idx, "downloaded"] = "yes"

    # Save outputs
    bbox_df.to_csv(BBOX_FILE, index=False)
    if total_new > 0:
        meta_df.to_csv(META_FILE, index=False)

    print(f"\n✅ Done. Added {total_new} new images total.")
    print(f"   Updated {BBOX_FILE}")
    print(f"   Metadata at {META_FILE}")

if __name__ == "__main__":
    main()