# Alex Birthday Media Store

This repo holds the public, static media library for the Alex birthday site.

It is meant to be deployed as GitHub Pages and consumed by the `Alex` repo.

## What lives here

- Optimized full-size photos
- Thumbnails
- Album manifests
- A reusable media build script

## What does not live here

- Source ZIP uploads
- Raw extraction folders
- Private metadata
- Backend code

## Build

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

Build from the source archives:

```bash
python scripts/build-media.py "C:\\Users\\dtoro\\Downloads"
```

You can also pass individual ZIP files or an alternate source folder.

## Output

- `data/albums.json` powers album cards.
- `data/manifest.json` powers the full gallery.
- `media/albums/.../full/` stores optimized full images.
- `media/albums/.../thumbs/` stores thumbnails.

## Safety

- EXIF and GPS metadata are stripped.
- Paths inside JSON stay relative to this repo root.
- Exact duplicate images are skipped.

## Deployment

See `DEPLOYMENT_NOTES.md` for GitHub Pages steps and expected URLs.
