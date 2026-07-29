# Streza FastAPI web

Jednostránkový web pro firmu dodávající střechy s jednoduchou administrací.

## Spuštění lokálně

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Web poběží na `http://127.0.0.1:8000`.

## Administrace

Admin sekce je na `http://127.0.0.1:8000/admin`.

Výchozí lokální přístup pro vývojové prostředí:

- uživatel: `admin`
- heslo: `streza-admin`

Pro vlastní přístup nastavte před spuštěním proměnné:

```powershell
$env:ADMIN_USERNAME="admin"
$env:ADMIN_PASSWORD="silne-heslo"
$env:SECRET_KEY="nahodny-dlouhy-tajny-klic"
uvicorn app.main:app --reload
```

SQLite databáze se vytvoří automaticky v `data/streza.sqlite3`.

V produkci nastavte `APP_ENV=production`. Aplikace pak odmítne start bez `SECRET_KEY` a bez silného `ADMIN_PASSWORD`.

## Docker

Vytvořte `.env` podle `.env.example` a nastavte alespoň:

```powershell
Copy-Item .env.example .env
```

Pak upravte `ADMIN_PASSWORD`, `SECRET_KEY` a podle typu nasazení `COOKIE_SECURE`.

```powershell
docker compose up --build
```

Docker publikovaný port je `8443`, kontejner uvnitř dál poslouchá na `8000`.

Perzistentní data:

- `data/` obsahuje SQLite databázi.
- `uploads/` obsahuje veřejné obrázky webu.
- `private_uploads/` obsahuje neveřejné fotky z poptávek a nesmí se publikovat jako statický obsah.
