from __future__ import annotations

import io
import os
import re
import time
import uuid
import zipfile
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import auth, db


ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
ALLOWED_LEAD_PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_LEAD_PHOTOS = int(os.getenv("MAX_LEAD_PHOTOS", "5"))
MAX_LEAD_PHOTO_BYTES = int(os.getenv("MAX_LEAD_PHOTO_BYTES", str(8 * 1024 * 1024)))
MAX_ADMIN_IMAGE_BYTES = int(os.getenv("MAX_ADMIN_IMAGE_BYTES", str(8 * 1024 * 1024)))
MAX_CONTACT_FIELD_LENGTH = int(os.getenv("MAX_CONTACT_FIELD_LENGTH", "4000"))
LOGIN_RATE_LIMIT = int(os.getenv("LOGIN_RATE_LIMIT", "10"))
CONTACT_RATE_LIMIT = int(os.getenv("CONTACT_RATE_LIMIT", "5"))
RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))
FORM_FIELD_TYPES = {"text", "email", "tel", "textarea"}
GA_ID_RE = re.compile(r"^G-[A-Z0-9]+$")
ROOT_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT_DIR / "static"
UPLOADS_DIR = ROOT_DIR / "uploads"
UPLOADS_DIR.mkdir(exist_ok=True)
PRIVATE_UPLOADS_DIR = ROOT_DIR / "private_uploads"
LEAD_UPLOADS_DIR = PRIVATE_UPLOADS_DIR / "leads"
LEAD_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title="Streza CMS",
    docs_url=None if auth.IS_PRODUCTION else "/docs",
    redoc_url=None if auth.IS_PRODUCTION else "/redoc",
    openapi_url=None if auth.IS_PRODUCTION else "/openapi.json",
)
templates = Jinja2Templates(directory="templates")
templates.env.filters["format_dt"] = db.format_dt
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")
rate_limit_buckets: dict[str, list[float]] = {}


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; img-src 'self' data:; style-src 'self' https://fonts.googleapis.com 'unsafe-inline'; font-src https://fonts.gstatic.com; script-src 'self' https://www.googletagmanager.com 'unsafe-inline'; connect-src 'self' http://89.187.159.11:8100; frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
    )
    if auth.IS_PRODUCTION:
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


def _detect_image_extension(contents: bytes) -> str | None:
    if contents.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if contents.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if contents.startswith(b"RIFF") and len(contents) >= 12 and contents[8:12] == b"WEBP":
        return ".webp"
    if contents.startswith((b"GIF87a", b"GIF89a")):
        return ".gif"
    return None


def _extension_matches_detected(extension: str, detected: str) -> bool:
    if detected == ".jpg":
        return extension in {".jpg", ".jpeg"}
    return extension == detected


def _client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    return request.client.host if request.client else "unknown"


def _rate_limited(name: str, key: str, limit: int) -> bool:
    now = time.monotonic()
    bucket_key = f"{name}:{key}"
    attempts = [
        timestamp
        for timestamp in rate_limit_buckets.get(bucket_key, [])
        if now - timestamp < RATE_LIMIT_WINDOW_SECONDS
    ]
    if len(attempts) >= limit:
        rate_limit_buckets[bucket_key] = attempts
        return True
    attempts.append(now)
    rate_limit_buckets[bucket_key] = attempts
    return False


def _sanitize_public_url(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        return "#kontakt"
    if stripped.startswith(("#", "/")):
        return stripped
    if re.match(r"^https?://", stripped, flags=re.IGNORECASE):
        return stripped
    return "#kontakt"


def _sanitize_ga_measurement_id(value: str) -> str:
    stripped = value.strip().upper()
    return stripped if not stripped or GA_ID_RE.fullmatch(stripped) else ""


@app.on_event("startup")
def startup() -> None:
    db.init_db()


def render(request: Request, template: str, context: dict | None = None) -> HTMLResponse:
    admin = auth.current_admin(request)
    data = {"admin": admin}
    if admin:
        data["csrf_token"] = auth.create_csrf_token(admin)
    if context:
        data.update(context)
    return templates.TemplateResponse(request, template, data)


def require_admin(request: Request) -> str | RedirectResponse:
    admin = auth.current_admin(request)
    if not admin:
        return RedirectResponse("/admin/login", status_code=303)
    return admin


def require_admin_action(request: Request, csrf_token: str) -> str | RedirectResponse:
    admin = require_admin(request)
    if isinstance(admin, RedirectResponse):
        return admin
    if not auth.verify_csrf_token(admin, csrf_token):
        raise HTTPException(status_code=403, detail="Neplatný bezpečnostní token.")
    return admin


@app.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    settings = db.get_settings()
    settings["ga_measurement_id"] = _sanitize_ga_measurement_id(settings.get("ga_measurement_id", ""))
    popup = db.get_popup()
    return render(
        request,
        "site/index.html",
        {
            "s": settings,
            "news": db.list_news(),
            "popup": popup,
            "popup_cta_url": _sanitize_public_url(popup.cta_url),
            "images": db.list_images(slot="gallery"),
            "hero_image": db.get_slot_image("hero"),
            "materials_image": db.get_slot_image("materials"),
            "popup_image": db.get_slot_image("popup"),
            "form_fields": db.list_form_fields(active_only=True),
            "success": request.query_params.get("success") == "1",
        },
    )


@app.post("/kontakt")
async def submit_contact(request: Request):
    if _rate_limited("contact", _client_ip(request), CONTACT_RATE_LIMIT):
        raise HTTPException(status_code=429, detail="Příliš mnoho pokusů. Zkuste to prosím později.")
    form = await request.form()
    fields = db.list_form_fields(active_only=True)
    data: dict[str, str] = {}
    for field in fields:
        value = str(form.get(field.field_key, "")).strip()
        if len(value) > MAX_CONTACT_FIELD_LENGTH:
            raise HTTPException(status_code=400, detail=f"Pole „{field.label}“ je příliš dlouhé.")
        if field.is_required and not value:
            raise HTTPException(status_code=400, detail=f"Pole „{field.label}“ je povinné.")
        data[field.field_key] = value

    lead_id = db.create_lead(data)

    for file in form.getlist("photos")[:MAX_LEAD_PHOTOS]:
        if not hasattr(file, "filename") or not hasattr(file, "read") or not file.filename:
            continue
        extension = Path(file.filename).suffix.lower()
        if extension not in ALLOWED_LEAD_PHOTO_EXTENSIONS:
            continue
        contents = await file.read()
        if not contents or len(contents) > MAX_LEAD_PHOTO_BYTES:
            continue
        detected_extension = _detect_image_extension(contents)
        if not detected_extension or detected_extension not in ALLOWED_LEAD_PHOTO_EXTENSIONS:
            continue
        if not _extension_matches_detected(extension, detected_extension):
            continue
        filename = f"leads/{lead_id}-{uuid.uuid4().hex}{extension}"
        (PRIVATE_UPLOADS_DIR / filename).write_bytes(contents)
        db.add_lead_attachment(
            lead_id=lead_id,
            filename=filename,
            original_name=file.filename,
            content_type=file.content_type or "",
        )

    if request.headers.get("x-requested-with") == "fetch":
        return JSONResponse({"ok": True, "message": "Děkujeme, ozveme se co nejdříve."})
    return RedirectResponse("/?success=1#kontakt", status_code=303)


@app.get("/admin/login", response_class=HTMLResponse)
def login_form(request: Request) -> HTMLResponse:
    if auth.current_admin(request):
        return RedirectResponse("/admin", status_code=303)
    return render(request, "admin/login.html", {"error": None})


@app.post("/admin/login")
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    if _rate_limited("login", _client_ip(request), LOGIN_RATE_LIMIT):
        return render(request, "admin/login.html", {"error": "Příliš mnoho pokusů. Zkuste to prosím později."})
    if not auth.verify_credentials(username, password):
        return render(request, "admin/login.html", {"error": "Nesprávné přihlašovací údaje."})

    response = RedirectResponse("/admin", status_code=303)
    auth.login_response(response, username)
    return response


@app.post("/admin/logout")
def logout(request: Request, csrf_token: str = Form("")):
    guard = require_admin_action(request, csrf_token)
    if isinstance(guard, RedirectResponse):
        return guard
    response = RedirectResponse("/admin/login", status_code=303)
    auth.logout_response(response)
    return response


@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request):
    guard = require_admin(request)
    if isinstance(guard, RedirectResponse):
        return guard
    leads = db.list_leads()
    return render(
        request,
        "admin/dashboard.html",
        {
            "leads": leads[:5],
            "lead_count": len(leads),
            "news_count": len(db.list_news(include_unpublished=True)),
            "popup": db.get_popup(),
            "pipeline": db.lead_pipeline(),
            "statuses": db.LEAD_STATUSES,
            "overdue": db.overdue_follow_ups(),
        },
    )


@app.get("/admin/poptavky", response_class=HTMLResponse)
def admin_leads(request: Request):
    guard = require_admin(request)
    if isinstance(guard, RedirectResponse):
        return guard
    status = request.query_params.get("stav") or None
    query = request.query_params.get("q") or None
    return render(
        request,
        "admin/leads.html",
        {
            "leads": db.list_leads(status=status, query=query),
            "statuses": db.LEAD_STATUSES,
            "active_status": status,
            "search_query": query or "",
            "pipeline": db.lead_pipeline(),
        },
    )


@app.get("/admin/poptavky/{lead_id}", response_class=HTMLResponse)
def admin_lead_detail(request: Request, lead_id: int):
    guard = require_admin(request)
    if isinstance(guard, RedirectResponse):
        return guard
    lead = db.get_lead(lead_id)
    if not lead:
        raise HTTPException(status_code=404)
    all_fields = {field.field_key: field.label for field in db.list_form_fields()}
    return render(
        request,
        "admin/lead_detail.html",
        {
            "lead": lead,
            "lead_data": db.lead_data(lead),
            "field_labels": all_fields,
            "statuses": db.LEAD_STATUSES,
            "activities": db.list_lead_activities(lead_id),
            "attachments": db.list_lead_attachments(lead_id),
            "now": datetime.now(),
        },
    )


@app.get("/admin/poptavky/{lead_id}/prilohy/{attachment_id}")
def admin_lead_attachment(request: Request, lead_id: int, attachment_id: int):
    guard = require_admin(request)
    if isinstance(guard, RedirectResponse):
        return guard
    attachment = db.get_lead_attachment(lead_id, attachment_id)
    if not attachment:
        raise HTTPException(status_code=404)
    path = (PRIVATE_UPLOADS_DIR / attachment.filename).resolve()
    if not path.is_file() or PRIVATE_UPLOADS_DIR.resolve() not in path.parents:
        raise HTTPException(status_code=404)
    return FileResponse(
        path,
        media_type=attachment.content_type or None,
        filename=attachment.original_name or path.name,
        content_disposition_type="inline",
    )


@app.get("/admin/leaky", response_class=HTMLResponse)
def admin_leak_browser(request: Request):
    guard = require_admin(request)
    if isinstance(guard, RedirectResponse):
        return guard
    return render(request, "admin/leak_browser.html")


@app.post("/admin/poptavky/{lead_id}")
def admin_lead_update(
    request: Request,
    lead_id: int,
    status: str = Form(...),
    note: str = Form(""),
    follow_up_at: str = Form(""),
    csrf_token: str = Form(""),
):
    guard = require_admin_action(request, csrf_token)
    if isinstance(guard, RedirectResponse):
        return guard
    if status not in db.LEAD_STATUSES:
        raise HTTPException(status_code=400, detail="Neplatný stav poptávky.")
    follow_up = None
    if follow_up_at:
        try:
            follow_up = datetime.fromisoformat(follow_up_at)
        except ValueError:
            follow_up = None
    db.update_lead(lead_id, status, note, follow_up)
    return RedirectResponse(f"/admin/poptavky/{lead_id}", status_code=303)


@app.post("/admin/poptavky/{lead_id}/aktivita")
def admin_lead_activity(
    request: Request,
    lead_id: int,
    body: str = Form(...),
    csrf_token: str = Form(""),
):
    guard = require_admin_action(request, csrf_token)
    if isinstance(guard, RedirectResponse):
        return guard
    if body.strip():
        db.add_lead_activity(lead_id, body)
    return RedirectResponse(f"/admin/poptavky/{lead_id}", status_code=303)


@app.get("/admin/texty", response_class=HTMLResponse)
def admin_settings(request: Request):
    guard = require_admin(request)
    if isinstance(guard, RedirectResponse):
        return guard
    settings = {
        key: value for key, value in db.get_settings().items() if key not in db.SEO_SETTING_KEYS
    }
    return render(request, "admin/settings.html", {"settings": settings})


@app.post("/admin/texty")
async def admin_settings_update(request: Request, csrf_token: str = Form("")):
    guard = require_admin_action(request, csrf_token)
    if isinstance(guard, RedirectResponse):
        return guard
    form = await request.form()
    current = db.get_settings()
    values = {
        key: str(form.get(key, current[key]))
        for key in current
        if key not in db.SEO_SETTING_KEYS
    }
    db.update_settings(values)
    return RedirectResponse("/admin/texty?saved=1", status_code=303)


@app.get("/admin/seo", response_class=HTMLResponse)
def admin_seo(request: Request):
    guard = require_admin(request)
    if isinstance(guard, RedirectResponse):
        return guard
    settings = db.get_settings()
    seo = {key: settings.get(key, "") for key in db.SEO_SETTING_KEYS}
    return render(request, "admin/seo.html", {"seo": seo})


@app.post("/admin/seo")
async def admin_seo_update(request: Request, csrf_token: str = Form("")):
    guard = require_admin_action(request, csrf_token)
    if isinstance(guard, RedirectResponse):
        return guard
    form = await request.form()
    current = db.get_settings()
    values = {
        key: str(form.get(key, current.get(key, "")))
        for key in db.SEO_SETTING_KEYS
    }
    values["ga_measurement_id"] = _sanitize_ga_measurement_id(values.get("ga_measurement_id", ""))
    db.update_settings(values)
    return RedirectResponse("/admin/seo?saved=1", status_code=303)


@app.get("/admin/novinky", response_class=HTMLResponse)
def admin_news(request: Request):
    guard = require_admin(request)
    if isinstance(guard, RedirectResponse):
        return guard
    return render(request, "admin/news.html", {"news": db.list_news(include_unpublished=True)})


@app.get("/admin/novinky/nova", response_class=HTMLResponse)
def admin_news_new(request: Request):
    guard = require_admin(request)
    if isinstance(guard, RedirectResponse):
        return guard
    return render(request, "admin/news_form.html", {"item": None})


@app.get("/admin/novinky/{news_id}", response_class=HTMLResponse)
def admin_news_edit(request: Request, news_id: int):
    guard = require_admin(request)
    if isinstance(guard, RedirectResponse):
        return guard
    item = db.get_news_item(news_id)
    if not item:
        raise HTTPException(status_code=404)
    return render(request, "admin/news_form.html", {"item": item})


@app.post("/admin/novinky")
def admin_news_create(
    request: Request,
    title: str = Form(...),
    body: str = Form(...),
    is_published: str | None = Form(None),
    csrf_token: str = Form(""),
):
    guard = require_admin_action(request, csrf_token)
    if isinstance(guard, RedirectResponse):
        return guard
    db.save_news_item(None, title, body, is_published == "on")
    return RedirectResponse("/admin/novinky", status_code=303)


@app.post("/admin/novinky/{news_id}")
def admin_news_update(
    request: Request,
    news_id: int,
    title: str = Form(...),
    body: str = Form(...),
    is_published: str | None = Form(None),
    csrf_token: str = Form(""),
):
    guard = require_admin_action(request, csrf_token)
    if isinstance(guard, RedirectResponse):
        return guard
    db.save_news_item(news_id, title, body, is_published == "on")
    return RedirectResponse("/admin/novinky", status_code=303)


@app.post("/admin/novinky/{news_id}/smazat")
def admin_news_delete(request: Request, news_id: int, csrf_token: str = Form("")):
    guard = require_admin_action(request, csrf_token)
    if isinstance(guard, RedirectResponse):
        return guard
    db.delete_news_item(news_id)
    return RedirectResponse("/admin/novinky", status_code=303)


@app.get("/admin/obrazky", response_class=HTMLResponse)
def admin_images(request: Request):
    guard = require_admin(request)
    if isinstance(guard, RedirectResponse):
        return guard
    return render(
        request,
        "admin/images.html",
        {"images": db.list_images(), "slots": db.IMAGE_SLOTS},
    )


@app.post("/admin/obrazky")
async def admin_image_upload(
    request: Request,
    file: UploadFile = File(...),
    title: str = Form(""),
    slot: str = Form("gallery"),
    csrf_token: str = Form(""),
):
    guard = require_admin_action(request, csrf_token)
    if isinstance(guard, RedirectResponse):
        return guard

    extension = Path(file.filename or "").suffix.lower()
    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        return render(
            request,
            "admin/images.html",
            {
                "images": db.list_images(),
                "slots": db.IMAGE_SLOTS,
                "error": "Podporované formáty jsou JPG, PNG, WEBP a GIF.",
            },
        )

    contents = await file.read()
    detected_extension = _detect_image_extension(contents)
    if (
        not contents
        or len(contents) > MAX_ADMIN_IMAGE_BYTES
        or not detected_extension
        or detected_extension not in ALLOWED_IMAGE_EXTENSIONS
        or not _extension_matches_detected(extension, detected_extension)
    ):
        return render(
            request,
            "admin/images.html",
            {
                "images": db.list_images(),
                "slots": db.IMAGE_SLOTS,
                "error": "Soubor není platný obrázek nebo překračuje povolenou velikost.",
            },
        )

    filename = f"{uuid.uuid4().hex}{extension}"
    (UPLOADS_DIR / filename).write_bytes(contents)
    db.add_image(filename, title, slot)
    return RedirectResponse("/admin/obrazky?saved=1", status_code=303)


@app.post("/admin/obrazky/{image_id}")
def admin_image_update(
    request: Request,
    image_id: int,
    title: str = Form(""),
    slot: str = Form("gallery"),
    csrf_token: str = Form(""),
):
    guard = require_admin_action(request, csrf_token)
    if isinstance(guard, RedirectResponse):
        return guard
    db.update_image(image_id, title, slot)
    return RedirectResponse("/admin/obrazky?saved=2", status_code=303)


@app.post("/admin/obrazky/{image_id}/smazat")
def admin_image_delete(request: Request, image_id: int, csrf_token: str = Form("")):
    guard = require_admin_action(request, csrf_token)
    if isinstance(guard, RedirectResponse):
        return guard
    filename = db.delete_image(image_id)
    if filename:
        (UPLOADS_DIR / filename).unlink(missing_ok=True)
    return RedirectResponse("/admin/obrazky", status_code=303)


@app.get("/admin/formular", response_class=HTMLResponse)
def admin_form_fields(request: Request):
    guard = require_admin(request)
    if isinstance(guard, RedirectResponse):
        return guard
    return render(request, "admin/form_fields.html", {"fields": db.list_form_fields()})


@app.post("/admin/formular")
def admin_form_field_create(
    request: Request,
    label: str = Form(...),
    field_type: str = Form("text"),
    placeholder: str = Form(""),
    is_required: str | None = Form(None),
    csrf_token: str = Form(""),
):
    guard = require_admin_action(request, csrf_token)
    if isinstance(guard, RedirectResponse):
        return guard
    if field_type not in FORM_FIELD_TYPES:
        raise HTTPException(status_code=400, detail="Neplatný typ pole.")
    db.create_form_field(label, field_type, placeholder, is_required == "on")
    return RedirectResponse("/admin/formular", status_code=303)


@app.post("/admin/formular/{field_id}")
def admin_form_field_update(
    request: Request,
    field_id: int,
    label: str = Form(...),
    field_type: str = Form("text"),
    placeholder: str = Form(""),
    position: int = Form(0),
    is_required: str | None = Form(None),
    is_active: str | None = Form(None),
    csrf_token: str = Form(""),
):
    guard = require_admin_action(request, csrf_token)
    if isinstance(guard, RedirectResponse):
        return guard
    if field_type not in FORM_FIELD_TYPES:
        raise HTTPException(status_code=400, detail="Neplatný typ pole.")
    db.update_form_field(
        field_id,
        label,
        field_type,
        placeholder,
        is_required == "on",
        is_active == "on",
        position,
    )
    return RedirectResponse("/admin/formular?saved=1", status_code=303)


@app.post("/admin/formular/{field_id}/smazat")
def admin_form_field_delete(request: Request, field_id: int, csrf_token: str = Form("")):
    guard = require_admin_action(request, csrf_token)
    if isinstance(guard, RedirectResponse):
        return guard
    db.delete_form_field(field_id)
    return RedirectResponse("/admin/formular", status_code=303)


def _build_static_export(request: Request) -> bytes:
    html = home(request).body.decode("utf-8")

    # Přepis absolutních cest (včetně url_for s doménou) na relativní,
    # aby export fungoval z disku i z libovolné složky hostingu.
    html = re.sub(r'"(?:https?://[^"]*)?/static/', '"static/', html)
    html = re.sub(r'"(?:https?://[^"]*)?/uploads/', '"uploads/', html)

    # Statický hosting nemá backend; formulář se přepne na mailto na firemní e-mail.
    contact_email = db.get_settings().get("contact_email", "")
    html = re.sub(
        r'action="/kontakt"\s+method="post"',
        f'action="mailto:{contact_email}" method="get" data-static',
        html,
    )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("index.html", html)
        for path in STATIC_DIR.rglob("*"):
            if path.is_file():
                archive.write(path, f"static/{path.relative_to(STATIC_DIR).as_posix()}")
        for path in UPLOADS_DIR.rglob("*"):
            if path.is_file():
                relative_path = path.relative_to(UPLOADS_DIR)
                if relative_path.parts and relative_path.parts[0] == "leads":
                    continue
                archive.write(path, f"uploads/{relative_path.as_posix()}")
    return buffer.getvalue()


@app.get("/admin/export", response_class=HTMLResponse)
def admin_export(request: Request):
    guard = require_admin(request)
    if isinstance(guard, RedirectResponse):
        return guard
    upload_count = sum(
        1
        for path in UPLOADS_DIR.rglob("*")
        if path.is_file()
        and not (
            (relative_path := path.relative_to(UPLOADS_DIR)).parts
            and relative_path.parts[0] == "leads"
        )
    )
    return render(
        request,
        "admin/export.html",
        {"upload_count": upload_count, "contact_email": db.get_settings().get("contact_email", "")},
    )


@app.post("/admin/export")
def admin_export_download(request: Request, csrf_token: str = Form("")):
    guard = require_admin_action(request, csrf_token)
    if isinstance(guard, RedirectResponse):
        return guard
    archive = _build_static_export(request)
    filename = f"streza-web-{datetime.now().strftime('%Y%m%d-%H%M')}.zip"
    return Response(
        content=archive,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/admin/popup", response_class=HTMLResponse)
def admin_popup(request: Request):
    guard = require_admin(request)
    if isinstance(guard, RedirectResponse):
        return guard
    return render(request, "admin/popup.html", {"popup": db.get_popup()})


@app.post("/admin/popup")
def admin_popup_update(
    request: Request,
    title: str = Form(...),
    body: str = Form(...),
    cta_label: str = Form(...),
    cta_url: str = Form(...),
    is_enabled: str | None = Form(None),
    csrf_token: str = Form(""),
):
    guard = require_admin_action(request, csrf_token)
    if isinstance(guard, RedirectResponse):
        return guard
    db.update_popup(title, body, cta_label, _sanitize_public_url(cta_url), is_enabled == "on")
    return RedirectResponse("/admin/popup?saved=1", status_code=303)
