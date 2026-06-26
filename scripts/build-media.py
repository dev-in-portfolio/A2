#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageOps


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
IGNORED_NAMES = {".ds_store", "thumbs.db", "desktop.ini"}
DEFAULT_FULL_LIMIT = (1600, 1600)
DEFAULT_THUMB_LIMIT = (420, 420)
JPEG_QUALITY_FULL = 86
JPEG_QUALITY_THUMB = 80


@dataclass
class PhotoRecord:
    id: str
    title: str
    year: str
    src: str
    thumb: str
    originalName: str
    width: int
    height: int
    aspectRatio: float | None = None
    sortIndex: int | None = None


@dataclass
class AlbumRecord:
    id: str
    title: str
    year: str
    cover: str
    photoCount: int
    photos: list[PhotoRecord]
    sortKey: tuple[int, str] | None = None


def slugify(text: str) -> str:
    text = text.strip().lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[()]+", " ", text)
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text or "album"


def clean_label(text: str) -> str:
    text = text.replace("_", " ").strip()
    text = re.sub(r"\s*-?\s*upscaled\s+jpe?gs?$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*-?\s*jpe?gs?$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text)
    text = text.replace("c. ", "c.")
    text = text.replace(" - ", " - ")
    return text


def parse_year_token(text: str) -> tuple[int, str]:
    normalized = text.replace("_", " ")
    lower = normalized.lower()
    tokens = []
    for match in re.finditer(r"c\.\s*([\d.]+)(?:\s*m)?\s*(bce|ce)|([\d.]+)(?:\s*m)?\s*(bce|ce)", lower):
        num = match.group(1) or match.group(3)
        era = match.group(2) or match.group(4)
        if num is None or era is None:
            continue
        try:
            value = float(num)
        except ValueError:
            continue
        if "m" in match.group(0):
            value *= 1_000_000
        year = int(round(value))
        if era == "bce":
            year = -year
        tokens.append(year)
    if tokens:
        return min(tokens), normalized.strip()
    # fall back to first 4-digit year-like token if present
    m = re.search(r"(19\d{2}|20\d{2})", lower)
    if m:
        return int(m.group(1)), normalized.strip()
    return 999999, normalized.strip()


def parse_album_name(folder_name: str) -> tuple[str, str, tuple[int, str]]:
    parts = folder_name.split("_")
    year_parts: list[str] = []
    title_parts: list[str] = []
    seen_title = False
    for part in parts:
        lower = part.lower()
        looks_like_year = (
            not seen_title
            and (
                bool(re.search(r"\d", part))
                or lower in {"bce", "ce"}
                or "bce" in lower
                or "ce" in lower and re.search(r"(?:^|[^a-z])ce(?:[^a-z]|$)", lower)
                or lower.startswith("c.")
                or "-" in part
            )
        )
        if looks_like_year:
            year_parts.append(part)
            continue
        seen_title = True
        title_parts.append(part)

    if not title_parts:
        title_parts = parts

    title = clean_label("_".join(title_parts))
    year_sort, raw_year = parse_year_token(folder_name)
    # Make the year field informative without inventing data.
    if year_sort == 999999:
        year = "unknown-year"
    else:
        year = re.sub(r"\s*-\s*", " - ", " ".join(year_parts) or raw_year)
    return title, year, (year_sort, title)


def iter_inputs(items: list[str]) -> list[Path]:
    if not items:
        default_dir = Path.home() / "Downloads"
        items = [str(default_dir)]
    paths: list[Path] = []
    for item in items:
        p = Path(item)
        if p.is_dir():
            for child in sorted(p.iterdir()):
                if child.suffix.lower() == ".zip":
                    paths.append(child)
        else:
            paths.append(p)
    return paths


def extract_archive(archive: Path, dest: Path) -> bool:
    dest.mkdir(parents=True, exist_ok=True)
    try:
        shutil.unpack_archive(str(archive), str(dest))
        return True
    except Exception:
        result = subprocess.run(["tar", "-xf", str(archive), "-C", str(dest)], capture_output=True, text=True)
        if result.returncode != 0:
            print(f"[warn] archive extraction returned {result.returncode} for {archive.name}")
            if result.stderr.strip():
                print(result.stderr.strip())
        return result.returncode == 0


def is_image(path: Path) -> bool:
    return path.suffix.lower() in IMAGE_EXTS


def safe_name(base: str, index: int, original: str) -> str:
    stem = slugify(Path(original).stem)
    return f"{base}-{index:03d}-{stem}.jpg"


def hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_exif_year(img: Image.Image) -> str | None:
    exif = img.getexif()
    if not exif:
        return None
    date = exif.get(36867) or exif.get(36868) or exif.get(306)
    if not date:
        return None
    text = str(date)
    m = re.search(r"(19\d{2}|20\d{2})", text)
    return m.group(1) if m else None


def prepare_image(src: Path, out_path: Path, limit: tuple[int, int], quality: int) -> tuple[int, int]:
    with Image.open(src) as img:
        img = ImageOps.exif_transpose(img)
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        elif img.mode == "L":
            img = img.convert("RGB")
        width, height = img.size
        img.thumbnail(limit, Image.Resampling.LANCZOS)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(out_path, format="JPEG", quality=quality, optimize=True, progressive=True)
        return width, height


def build() -> int:
    parser = argparse.ArgumentParser(description="Build Alex birthday media manifests and image outputs.")
    parser.add_argument("sources", nargs="*", help="ZIP files or source directory containing the ZIPs.")
    parser.add_argument("--repo-root", default=Path(__file__).resolve().parents[1], type=Path)
    args = parser.parse_args()

    repo_root: Path = args.repo_root
    sources = iter_inputs(args.sources)
    if not sources:
        print("No source ZIPs found.")
        return 1

    # Rebuild from a clean slate so stale files from a previous run do not survive.
    media_root = repo_root / "media" / "albums"
    data_dir = repo_root / "data"
    if media_root.exists():
        shutil.rmtree(media_root)
    data_dir.mkdir(parents=True, exist_ok=True)
    for data_file in (data_dir / "albums.json", data_dir / "manifest.json"):
        if data_file.exists():
            data_file.unlink()

    tmp_root = repo_root / "tmp" / f"extract-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    extracted_root = tmp_root / "extracted"
    extracted_root.mkdir(parents=True, exist_ok=True)

    extracted_sources: list[tuple[Path, str]] = []
    source_summaries = []
    for archive in sources:
        if archive.suffix.lower() != ".zip":
            continue
        dest = extracted_root / slugify(archive.stem)
        ok = extract_archive(archive, dest)
        extracted_sources.append((dest, archive.stem))
        source_summaries.append({"archive": archive.name, "ok": ok, "destination": str(dest)})

    image_entries: list[dict] = []
    supported = unsupported = unreadable = duplicates = 0
    seen_hashes: set[str] = set()
    album_map: dict[str, dict] = {}

    for extracted, archive_stem in extracted_sources:
        for path in sorted(extracted.rglob("*")):
            if path.is_dir():
                continue
            if path.name.lower() in IGNORED_NAMES or any(part.lower() == "__macosx" for part in path.parts):
                continue
            if path.suffix.lower() == ".csv":
                unsupported += 1
                continue
            if not is_image(path):
                unsupported += 1
                continue

            supported += 1
            try:
                file_hash = hash_file(path)
            except Exception:
                unreadable += 1
                continue
            if file_hash in seen_hashes:
                duplicates += 1
                continue
            seen_hashes.add(file_hash)

            rel_parts = path.relative_to(extracted).parts
            album_folder = rel_parts[1] if len(rel_parts) >= 2 else archive_stem
            title, year, sort_key = parse_album_name(album_folder)
            album_id = slugify(album_folder)
            if album_id not in album_map:
                album_map[album_id] = {
                    "id": album_id,
                    "title": title,
                    "year": year,
                    "cover": "",
                    "photoCount": 0,
                    "photos": [],
                    "sortKey": sort_key,
                }

            photo_id = f"{album_id}-{len(album_map[album_id]['photos']) + 1:03d}"
            out_base = album_id
            full_rel = Path("media") / "albums" / album_id / "full" / safe_name(out_base, len(album_map[album_id]["photos"]) + 1, path.name)
            thumb_rel = Path("media") / "albums" / album_id / "thumbs" / full_rel.name
            full_abs = repo_root / full_rel
            thumb_abs = repo_root / thumb_rel

            try:
                with Image.open(path) as img:
                    img = ImageOps.exif_transpose(img)
                    width, height = img.size
                    exif_year = read_exif_year(img)
                prepare_image(path, full_abs, DEFAULT_FULL_LIMIT, JPEG_QUALITY_FULL)
                prepare_image(path, thumb_abs, DEFAULT_THUMB_LIMIT, JPEG_QUALITY_THUMB)
            except Exception:
                unreadable += 1
                continue

            record = PhotoRecord(
                id=photo_id,
                title=f"Photo {len(album_map[album_id]['photos']) + 1:03d}",
                year=exif_year or year,
                src=str(full_rel.as_posix()),
                thumb=str(thumb_rel.as_posix()),
                originalName=path.name,
                width=width,
                height=height,
                aspectRatio=round(width / height, 4) if height else None,
                sortIndex=len(album_map[album_id]["photos"]) + 1,
            )
            album_map[album_id]["photos"].append(record)
            image_entries.append(record)

    albums: list[AlbumRecord] = []
    for album in album_map.values():
        album["photos"].sort(key=lambda p: (p.sortIndex or 999999, p.originalName))
        album["photoCount"] = len(album["photos"])
        if album["photos"]:
            album["cover"] = album["photos"][0].thumb
        albums.append(
            AlbumRecord(
                id=album["id"],
                title=album["title"],
                year=album["year"],
                cover=album["cover"],
                photoCount=album["photoCount"],
                photos=album["photos"],
                sortKey=album["sortKey"],
            )
        )

    def album_sort_key(album: AlbumRecord):
        sort_key = album.sortKey or (999999, album.title)
        return sort_key[0], sort_key[1].lower(), album.id

    albums.sort(key=album_sort_key)
    if any(a.id == "unknown-year" for a in albums):
        albums.sort(key=lambda a: (a.id == "unknown-year", album_sort_key(a)))

    # Reassign covers after sorting so the displayed cover matches the final album order.
    for album in albums:
        if album.photos:
            album.cover = album.photos[0].thumb

    generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    total_photos = len(image_entries)

    albums_payload = {
        "generatedAt": generated_at,
        "albumCount": len(albums),
        "photoCount": total_photos,
        "albums": [
            {
                "id": album.id,
                "title": album.title,
                "year": album.year,
                "cover": album.cover,
                "photoCount": album.photoCount,
            }
            for album in albums
        ],
    }

    manifest_payload = {
        "generatedAt": generated_at,
        "photoCount": total_photos,
        "albums": [
            {
                "id": album.id,
                "title": album.title,
                "year": album.year,
                "cover": album.cover,
                "photoCount": album.photoCount,
                "photos": [asdict(photo) for photo in album.photos],
            }
            for album in albums
        ],
    }

    (data_dir / "albums.json").write_text(json.dumps(albums_payload, indent=2), encoding="utf-8")
    (data_dir / "manifest.json").write_text(json.dumps(manifest_payload, indent=2), encoding="utf-8")

    print(json.dumps({
        "sourceArchives": [s["archive"] for s in source_summaries],
        "archivesExtracted": len(source_summaries),
        "albums": len(albums),
        "photos": total_photos,
        "supportedImageFilesSeen": supported,
        "duplicatesSkipped": duplicates,
        "unsupportedFilesSkipped": unsupported,
        "unreadableFilesSkipped": unreadable,
        "generatedAt": generated_at,
        "sourceResults": source_summaries,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(build())
