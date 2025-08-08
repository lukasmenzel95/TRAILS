import os
import requests
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv

# === Load .env ===
load_dotenv()

# === Config ===
BBOX_FILE = "data/bounding_boxes.csv"
META_FILE = "data/images_metadata.csv"
IMAGES_DIR = "data/images"
MAPILLARY_TOKEN = os.getenv("MAPILLARY_TOKEN")

# Ensure directories exist
os.makedirs(IMAGES_DIR, exist_ok=True)

def fetch_images_for_bbox(bbox, limit=100):
    """Fetch images metadata from Mapillary API within a bounding box."""
    url = "https://graph.mapillary.com/images"
    params = {
        "access_token": MAPILLARY_TOKEN,
        "bbox": ",".join(map(str, bbox)),
        "fields": "id,computed_geometry,captured_at",
        "limit": limit
    }
    response = requests.get(url, params=params)
    response.raise_for_status()
    return response.json().get("data", [])

def download_image(image_id):
    """Download image by ID from Mapillary."""
    url = f"https://graph.mapillary.com/{image_id}"
    params = {
        "access_token": MAPILLARY_TOKEN,
        "fields": "thumb_2048_url"
    }
    r = requests.get(url, params=params)
    r.raise_for_status()
    img_url = r.json()["thumb_2048_url"]

    img_data = requests.get(img_url)
    img_data.raise_for_status()

    img_path = os.path.join(IMAGES_DIR, f"{image_id}.jpg")
    with open(img_path, "wb") as f:
        f.write(img_data.content)
    return img_path

def load_metadata():
    """Load or create metadata CSV."""
    if os.path.exists(META_FILE) and os.path.getsize(META_FILE) > 0:
        return pd.read_csv(META_FILE, dtype=str).fillna("")
    else:
        return pd.DataFrame(columns=["id","location_name","longitude","latitude","captured_at","file_path"])

def save_metadata(df):
    """Save metadata DataFrame to CSV."""
    df.to_csv(META_FILE, index=False)

def main():
    if not MAPILLARY_TOKEN:
        print("Error: MAPILLARY_TOKEN not set in environment.")
        return

    if not os.path.exists(BBOX_FILE):
        print(f"Error: {BBOX_FILE} not found.")
        return

    bbox_df = pd.read_csv(BBOX_FILE)
    meta_df = load_metadata()
    existing_ids = set(meta_df["id"].tolist())

    for _, row in bbox_df.iterrows():
        location_name = row["location_name"]
        bbox = [row["min_lon"], row["min_lat"], row["max_lon"], row["max_lat"]]

        print(f"\n=== {location_name} (added {row['date_added']}) ===")

        # Ask user how many images to fetch
        try:
            max_images = int(input(f"How many images do you want for {location_name}? "))
        except ValueError:
            print("Invalid number. Skipping.")
            continue

        # Get images metadata
        images = fetch_images_for_bbox(bbox, limit=max_images)
        print(f"Found {len(images)} images in Mapillary for {location_name} (requested {max_images})")

        new_entries = []
        for img in images:
            if len(new_entries) >= max_images:
                break

            image_id = img["id"]
            if image_id in existing_ids:
                continue

            coords = img["computed_geometry"]["coordinates"]
            lon, lat = coords
            captured_at = datetime.utcfromtimestamp(img["captured_at"] / 1000).isoformat()

            try:
                img_path = download_image(image_id)
                print(f"Downloaded {img_path}")

                new_entries.append({
                    "id": image_id,
                    "location_name": location_name,
                    "longitude": lon,
                    "latitude": lat,
                    "captured_at": captured_at,
                    "file_path": img_path
                })
                existing_ids.add(image_id)
            except Exception as e:
                print(f"Failed to download image {image_id}: {e}")

        if new_entries:
            meta_df = pd.concat([meta_df, pd.DataFrame(new_entries)], ignore_index=True)
            save_metadata(meta_df)
            print(f"Saved metadata for {len(new_entries)} new images at {location_name}")
        else:
            print("No new images downloaded.")

if __name__ == "__main__":
    main()