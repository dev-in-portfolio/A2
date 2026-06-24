# A2 Deployment Notes

Expected public URL:

`https://happy-alex-2.netlify.app/`

## Publish Checklist

1. Deploy the site to Netlify.
2. Confirm `data/manifest.json` loads in the browser.
3. Confirm `data/history-eras.json` loads in the browser.
4. Confirm album image URLs resolve under `/media/albums/...`.
5. Confirm the Alex site points at this base URL.
6. Re-run the media build whenever the source ZIPs change.
7. Keep the Netlify CORS headers in place so the Alex gallery can fetch the manifest from the browser.

## Notes

- This repo is static only.
- No backend, database, or secrets are required.
- The public media files are optimized and metadata stripped.
