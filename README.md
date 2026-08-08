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

Pak upravte `ADMIN_PASSWORD` a `SECRET_KEY`.

Pro přístup přes `http://` nech `COOKIE_SECURE=false` (výchozí v Docker compose).
Pro HTTPS nastav `COOKIE_SECURE=true`.

```powershell
docker compose up --build
```

Docker publikovaný port je `8443`, kontejner uvnitř dál poslouchá na `8000`.
Admin login: `http://localhost:8443/admin/login`

`ADMIN_PASSWORD` z env se při startu synchronizuje do databáze.

Perzistentní data (Docker named volumes):

- `streza_data` → SQLite databáze (texty, poptávky, novinky, admin účet)
- `streza_uploads` → veřejné obrázky webu (hero, galerie, …)
- `streza_private_uploads` → neveřejné fotky z poptávek

Při update/redeploy stacku v Portaineru volumes **nemaž**.
Obsah upravený v adminu zůstane, protože start už nepřepisuje existující texty.

Fotky v poptávce: na webu v kontaktním formuláři (JPG/PNG/WEBP, max 5).
V adminu se zobrazí v detailu poptávky.
