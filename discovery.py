import requests
import pandas as pd
import os

DATA_URL = "http://data.insideairbnb.com/portugal/lisbon/2024-03-15/data/listings.csv.gz"
OUTPUT_DIR = "raw_data"
RAW_FILE = "listings_lisbon.csv.gz"


def download_dataset():
    print("Downloading dataset...")
    response = requests.get(DATA_URL)
    response.raise_for_status()

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    file_path = os.path.join(OUTPUT_DIR, RAW_FILE)

    with open(file_path, "wb") as f:
        f.write(response.content)

    print(f"Saved dataset to {file_path}")
    return file_path


def inspect_dataset(file_path):
    print("Loading dataset into pandas...")
    df = pd.read_csv(file_path, compression="gzip")

    print("\nDataset shape:")
    print(df.shape)

    print("\nAvailable columns:")
    print(df.columns.tolist())

    return df


if __name__ == "__main__":
    path = download_dataset()
    df = inspect_dataset(path)