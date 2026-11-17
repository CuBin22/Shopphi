"""Copy local product photos to the Shopphi public Neon Storage bucket."""

from getpass import getpass
from mimetypes import guess_type
from pathlib import Path
from urllib.parse import urlparse

import boto3
from botocore.config import Config


ROOT = Path(__file__).resolve().parents[1]
MEDIA = ROOT / "media"
BUCKET = "shopphi-products"


def main():
    endpoint = input("AWS_ENDPOINT_URL_S3 (Neon Storage): ").strip().strip('"\'').rstrip("/")
    parsed = urlparse(endpoint)
    if parsed.scheme != "https" or not (parsed.hostname or "").endswith(".neon.tech") or parsed.path:
        raise SystemExit("Nhap endpoint HTTPS cua Neon, khong them ten bucket hoac duong dan.")

    access_key = input("AWS_ACCESS_KEY_ID: ").strip().strip('"\'')
    secret_key = getpass("AWS_SECRET_ACCESS_KEY (an khi nhap): ").strip()
    if not access_key or not secret_key:
        raise SystemExit("Thieu thong tin truy cap Storage.")

    files = sorted(path for path in (MEDIA / "products").rglob("*") if path.is_file())
    if not files:
        raise SystemExit("Khong tim thay tep trong media/products.")

    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name="ap-southeast-1",
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )

    print(f"Dang tai {len(files)} anh len bucket {BUCKET}...")
    for index, path in enumerate(files, 1):
        key = path.relative_to(MEDIA).as_posix()
        with path.open("rb") as content:
            client.put_object(
                Bucket=BUCKET,
                Key=key,
                Body=content,
                ContentType=guess_type(path.name)[0] or "application/octet-stream",
            )
        if index % 20 == 0 or index == len(files):
            print(f"Da tai {index}/{len(files)} anh")


if __name__ == "__main__":
    main()
