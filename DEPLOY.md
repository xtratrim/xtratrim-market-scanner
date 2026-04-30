# Deploy the Market Scanner

The app is now ready to run on a hosted URL. It supports cloud-provided ports and optional password protection.

## Private Login

Set this environment variable on your host:

```text
SCANNER_PASSWORD=your-private-password
```

When you open the site, log in with:

```text
Username: trader
Password: your SCANNER_PASSWORD
```

If `SCANNER_PASSWORD` is not set, the app is public.

## Render

1. Create a GitHub repo and upload this folder.
2. Go to Render and create a new Web Service from that repo.
3. Use:
   - Build command: `pip install -r requirements.txt`
   - Start command: `python app.py --host 0.0.0.0`
4. Add environment variable:
   - `SCANNER_PASSWORD`
5. Deploy, then open the Render URL from your phone.

The included `render.yaml` can also be used as a Render Blueprint.

## Railway / Other Python Hosts

Use:

```text
pip install -r requirements.txt
python app.py --host 0.0.0.0
```

Make sure the host provides a `PORT` environment variable. The app reads it automatically.

## Files Needed

Keep these files together:

- `app.py`
- `scanner.py`
- `scanner_config.json`
- `penny_stock_universe.txt`
- `meme_coin_universe.txt`
- `requirements.txt`
- `static/`
