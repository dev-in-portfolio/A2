# A2 Deployment Notes

Expected public URL:

`https://dev-in-portfolio.github.io/A2/`

## Publish Checklist

1. Enable GitHub Pages from the `main` branch.
2. Confirm `data/manifest.json` loads in the browser.
3. Confirm album image URLs resolve under `/media/albums/...`.
4. Confirm the Alex site points at this base URL.
5. Re-run the media build whenever the source ZIPs change.

## Notes

- This repo is static only.
- No backend, database, or secrets are required.
- The public media files are optimized and metadata stripped.
