from __future__ import annotations

import json
import os
import re
import unicodedata
from datetime import datetime

from passlib.context import CryptContext
from sqlalchemy import select, text

from .database import Base, SessionLocal, engine, ensure_data_dir
from .models import (
    AdminUser,
    ContactRequest,
    FormField,
    GalleryImage,
    LeadActivity,
    LeadAttachment,
    NewsItem,
    Popup,
    SiteContent,
)


IMAGE_SLOTS = {
    "gallery": "Galerie Realizace",
    "hero": "Hero carousel (homepage)",
    "materials": "Sekce Materiály",
    "popup": "Popup",
}

LEAD_STATUSES = {
    "new": "Nová",
    "contacted": "Kontaktováno",
    "survey": "Prohlídka",
    "priced": "Nabídka odeslána",
    "won": "Vyhráno",
    "lost": "Ztraceno",
}


pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

def _env_admin_username() -> str:
    return (os.getenv("ADMIN_USERNAME") or "admin").strip() or "admin"


def _env_admin_password() -> str:
    return (os.getenv("ADMIN_PASSWORD") or "streza-admin").strip() or "streza-admin"


DEFAULT_ADMIN_USERNAME = _env_admin_username()
DEFAULT_ADMIN_PASSWORD = _env_admin_password()
APP_ENV = (os.getenv("APP_ENV", "development") or "development").strip().lower().split()[0]
# Development fallback is rejected before startup when APP_ENV=production.
if APP_ENV in {"prod", "production"} and (
    not os.getenv("ADMIN_PASSWORD") or DEFAULT_ADMIN_PASSWORD == "streza-admin"  # nosec B105
):
    raise RuntimeError("ADMIN_PASSWORD must be set to a non-default value when APP_ENV=production.")

DEFAULT_SETTINGS = {
    "site_title": "Streza | Střechy bez starostí",
    "meta_description": "Jednostránkový web pro firmu dodávající střechy, rekonstrukce, klempířské práce a servis.",
    "brand_name": "Streza",
    "nav_location": "Vysočina, jižní Morava, střední Čechy, po domluvě celá ČR",
    "hero_eyebrow": "STŘECHY NA KLÍČ | VYSOČINA, JIŽNÍ MORAVA, STŘEDNÍ ČECHY, po domluvě celá ČR",
    "hero_title": "Poctivá střecha, která odolá počasí i času.",
    "hero_text": "Navrhneme, dodáme a zrealizujeme střechu pro rodinný dům, rekonstrukci i firemní objekt. Od první prohlídky po čisté předání stavby.",
    "hero_primary_cta": "Chci nezávaznou nabídku",
    "hero_secondary_cta": "Co děláme",
    "stat_1_value": "15+",
    "stat_1_label": "let praxe",
    "stat_2_value": "420",
    "stat_2_label": "hotových střech",
    "stat_3_value": "24 h",
    "stat_3_label": "reakce na poptávku",
    "services_eyebrow": "Naše služby",
    "services_title": "Kompletní péče o střechu od návrhu po servis.",
    "service_1_title": "Nové střechy",
    "service_1_text": "Pokládka střešních krytin pro novostavby, montáž střešních oken a zajištění montáže krovů.",
    "service_2_title": "Rekonstrukce",
    "service_2_text": "Výměna krytiny, opravy konstrukcí, zateplení a modernizace starších střech.",
    "service_3_title": "Klempířské práce",
    "service_3_text": "Žlaby, svody, oplechování komínů, atik a detailů proti zatékání.",
    "service_4_title": "Servis a havárie",
    "service_4_text": "Rychlá diagnostika závad a lokální opravy střech.",
    "process_eyebrow": "Jak pracujeme",
    "process_title": "Jasný postup, férová cena a průběžná komunikace.",
    "process_1_title": "Prohlídka a zaměření",
    "process_1_text": "Přijedeme na místo, zhodnotíme stav střechy a projdeme vaše priority.",
    "process_2_title": "Nabídka na míru",
    "process_2_text": "Dostanete srozumitelný rozpočet, doporučené materiály a termín realizace.",
    "process_3_title": "Realizace",
    "process_3_text": "Stavbu vedeme čistě, bezpečně a s ohledem na provoz domu.",
    "process_4_title": "Předání a záruka",
    "process_4_text": "Vše zkontrolujeme, předáme dílo a zůstáváme k dispozici pro případný servis.",
    "quote_text": "Streza nám během dvou týdnů vyměnila starou krytinu, opravila klempířské prvky a nechala po sobě perfektně uklizeno. Oceňujeme hlavně komunikaci a dodržení ceny.",
    "quote_name": "Jana H.",
    "quote_detail": "rekonstrukce střechy, Říčany",
    "materials_eyebrow": "Materiály",
    "materials_title": "Pracujeme s pálenou i betonovou taškou, plechem a plochými střechami.",
    "materials_text": "Pomůžeme vybrat řešení podle sklonu, rozpočtu, životnosti a vzhledu domu. Každý detail řešíme tak, aby střecha fungovala jako celek.",
    "contact_eyebrow": "Kontakt",
    "contact_title": "Pošlete nám pár informací a ozveme se s dalším postupem.",
    "contact_text": "V poptávce stačí uvést lokalitu, typ střechy a přibližný rozsah prací. Fotky současného stavu nám pomohou připravit se na prohlídku.",
    "contact_phone": "+420 777 123 456",
    "contact_email": "info@streza.cz",
    "company_name": "Streza s.r.o.",
    "company_ico": "IČO: 12345678",
    "company_dic": "DIČ: CZ12345678",
    "company_address": "Řemeslnická 12, 251 01 Říčany",
    "gallery_eyebrow": "Realizace",
    "gallery_title": "Ukázky střech, které jsme dodali.",
    "footer_text": "© 2026 Streza. Střechy, klempířina a servis.",
    "seo_og_title": "Streza | Střechy bez starostí",
    "seo_og_description": "Střechy na klíč, rekonstrukce, klempířské práce a servis. Vysočina, jižní Morava, střední Čechy a po domluvě celá ČR.",
    "seo_og_image": "/static/img/logo.png",
    "seo_canonical_url": "",
    "seo_robots": "index, follow",
    "seo_keywords": "střechy, pokrývačství, klempířství, rekonstrukce střechy, Praha",
    "ga_measurement_id": "",
}

SEO_SETTING_KEYS = [
    "site_title",
    "meta_description",
    "seo_keywords",
    "seo_robots",
    "seo_canonical_url",
    "seo_og_title",
    "seo_og_description",
    "seo_og_image",
    "ga_measurement_id",
]

DEFAULT_FORM_FIELDS = [
    {"field_key": "name", "label": "Jméno", "field_type": "text", "placeholder": "Jan Novák", "is_required": True},
    {"field_key": "contact", "label": "Telefon nebo e-mail", "field_type": "text", "placeholder": "+420 777 123 456", "is_required": True},
    {"field_key": "message", "label": "Co potřebujete?", "field_type": "textarea", "placeholder": "Nová střecha, rekonstrukce, oprava...", "is_required": False},
]

REQUESTED_SETTING_UPDATES = {
    "nav_location": DEFAULT_SETTINGS["nav_location"],
    "hero_eyebrow": DEFAULT_SETTINGS["hero_eyebrow"],
    "hero_title": DEFAULT_SETTINGS["hero_title"],
    "service_1_text": DEFAULT_SETTINGS["service_1_text"],
    "service_3_text": DEFAULT_SETTINGS["service_3_text"],
    "service_4_text": DEFAULT_SETTINGS["service_4_text"],
    "process_4_text": DEFAULT_SETTINGS["process_4_text"],
    "seo_og_description": DEFAULT_SETTINGS["seo_og_description"],
}

REMOVED_SEEDED_NEWS_TITLES = {
    "Nově nabízíme pravidelné kontroly střech",
}


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")
    return slug or "polozka"


def format_dt(value: datetime | None) -> str:
    return value.strftime("%Y-%m-%d %H:%M") if value else ""


def _migrate() -> None:
    with engine.connect() as connection:
        columns = [row[1] for row in connection.execute(text("PRAGMA table_info(contact_requests)"))]
        if columns and "data" not in columns:
            connection.execute(text("ALTER TABLE contact_requests ADD COLUMN data TEXT NOT NULL DEFAULT '{}'"))
        if columns and "follow_up_at" not in columns:
            connection.execute(text("ALTER TABLE contact_requests ADD COLUMN follow_up_at DATETIME"))
        image_columns = [row[1] for row in connection.execute(text("PRAGMA table_info(gallery_images)"))]
        if image_columns and "slot" not in image_columns:
            connection.execute(text("ALTER TABLE gallery_images ADD COLUMN slot TEXT NOT NULL DEFAULT 'gallery'"))
        connection.commit()


def init_db() -> None:
    ensure_data_dir()
    Base.metadata.create_all(bind=engine)
    _migrate()

    with SessionLocal() as session:
        for key, value in DEFAULT_SETTINGS.items():
            if not session.get(SiteContent, key):
                session.add(SiteContent(key=key, value=value))

        for key, value in REQUESTED_SETTING_UPDATES.items():
            item = session.get(SiteContent, key)
            if item:
                item.value = value

        if not session.get(Popup, 1):
            session.add(
                Popup(
                    id=1,
                    title="Jarní kontrola střechy",
                    body="Objednejte si kontrolu střechy před další sezónou.",
                    cta_label="Chci kontrolu",
                    cta_url="#kontakt",
                    is_enabled=False,
                )
            )

        for title in REMOVED_SEEDED_NEWS_TITLES:
            seeded_news = session.scalar(select(NewsItem).where(NewsItem.title == title))
            if seeded_news:
                session.delete(seeded_news)

        has_fields = session.scalar(select(FormField.id).limit(1))
        if not has_fields:
            for position, field in enumerate(DEFAULT_FORM_FIELDS, start=1):
                session.add(FormField(position=position, is_active=True, **field))

        username = _env_admin_username()
        password = _env_admin_password()
        admin = session.scalar(select(AdminUser).where(AdminUser.username == username))
        if not admin:
            session.add(
                AdminUser(
                    username=username,
                    password_hash=pwd_context.hash(password),
                )
            )
        elif os.getenv("ADMIN_PASSWORD"):
            # Keep Docker/Portainer ADMIN_PASSWORD as the source of truth.
            admin.password_hash = pwd_context.hash(password)

        session.commit()


def get_settings() -> dict[str, str]:
    with SessionLocal() as session:
        items = session.scalars(select(SiteContent).order_by(SiteContent.key)).all()
        return {item.key: item.value for item in items}


def update_settings(values: dict[str, str]) -> None:
    with SessionLocal() as session:
        for key, value in values.items():
            item = session.get(SiteContent, key)
            if item:
                item.value = value
        session.commit()


def create_lead(data: dict[str, str]) -> int:
    values = [value for value in data.values() if value]
    name = data.get("name") or (values[0] if values else "Bez jména")
    contact = (
        data.get("contact")
        or data.get("email")
        or data.get("phone")
        or (values[1] if len(values) > 1 else "")
    )
    with SessionLocal() as session:
        lead = ContactRequest(
            name=name.strip(),
            contact=contact.strip(),
            message=data.get("message", "").strip(),
            data=json.dumps(data, ensure_ascii=False),
        )
        session.add(lead)
        session.flush()
        lead_id = lead.id
        session.add(LeadActivity(lead_id=lead.id, body="Poptávka přijata z webu."))
        session.commit()
        return lead_id


def add_lead_attachment(
    lead_id: int,
    filename: str,
    original_name: str,
    content_type: str,
) -> None:
    with SessionLocal() as session:
        session.add(
            LeadAttachment(
                lead_id=lead_id,
                filename=filename,
                original_name=original_name.strip(),
                content_type=content_type.strip(),
            )
        )
        session.commit()


def list_lead_attachments(lead_id: int) -> list[LeadAttachment]:
    with SessionLocal() as session:
        return session.scalars(
            select(LeadAttachment)
            .where(LeadAttachment.lead_id == lead_id)
            .order_by(LeadAttachment.created_at, LeadAttachment.id)
        ).all()


def get_lead_attachment(lead_id: int, attachment_id: int) -> LeadAttachment | None:
    with SessionLocal() as session:
        return session.scalar(
            select(LeadAttachment)
            .where(LeadAttachment.lead_id == lead_id)
            .where(LeadAttachment.id == attachment_id)
        )


def lead_data(lead: ContactRequest) -> dict[str, str]:
    try:
        parsed = json.loads(lead.data or "{}")
    except ValueError:
        parsed = {}
    if not parsed:
        parsed = {"name": lead.name, "contact": lead.contact, "message": lead.message}
    return parsed


def list_leads(status: str | None = None, query: str | None = None) -> list[ContactRequest]:
    statement = select(ContactRequest)
    if status:
        statement = statement.where(ContactRequest.status == status)
    if query:
        pattern = f"%{query.strip()}%"
        statement = statement.where(
            ContactRequest.name.ilike(pattern)
            | ContactRequest.contact.ilike(pattern)
            | ContactRequest.data.ilike(pattern)
            | ContactRequest.note.ilike(pattern)
        )
    statement = statement.order_by(ContactRequest.created_at.desc(), ContactRequest.id.desc())
    with SessionLocal() as session:
        return session.scalars(statement).all()


def get_lead(lead_id: int) -> ContactRequest | None:
    with SessionLocal() as session:
        return session.get(ContactRequest, lead_id)


def update_lead(lead_id: int, status: str, note: str, follow_up_at: datetime | None) -> None:
    with SessionLocal() as session:
        lead = session.get(ContactRequest, lead_id)
        if lead:
            if status != lead.status:
                old_label = LEAD_STATUSES.get(lead.status, lead.status)
                new_label = LEAD_STATUSES.get(status, status)
                session.add(
                    LeadActivity(lead_id=lead_id, body=f"Stav změněn: {old_label} → {new_label}")
                )
            lead.status = status
            lead.note = note.strip()
            lead.follow_up_at = follow_up_at
            session.commit()


def add_lead_activity(lead_id: int, body: str) -> None:
    with SessionLocal() as session:
        session.add(LeadActivity(lead_id=lead_id, body=body.strip()))
        session.commit()


def list_lead_activities(lead_id: int) -> list[LeadActivity]:
    with SessionLocal() as session:
        return session.scalars(
            select(LeadActivity)
            .where(LeadActivity.lead_id == lead_id)
            .order_by(LeadActivity.created_at.desc(), LeadActivity.id.desc())
        ).all()


def lead_pipeline() -> dict[str, int]:
    counts = {status: 0 for status in LEAD_STATUSES}
    with SessionLocal() as session:
        for lead in session.scalars(select(ContactRequest)).all():
            counts[lead.status] = counts.get(lead.status, 0) + 1
    return counts


def overdue_follow_ups() -> list[ContactRequest]:
    with SessionLocal() as session:
        return session.scalars(
            select(ContactRequest)
            .where(ContactRequest.follow_up_at.is_not(None))
            .where(ContactRequest.follow_up_at <= datetime.now())
            .where(ContactRequest.status.not_in(["won", "lost"]))
            .order_by(ContactRequest.follow_up_at)
        ).all()


def list_news(include_unpublished: bool = False) -> list[NewsItem]:
    statement = select(NewsItem)
    if not include_unpublished:
        statement = statement.where(NewsItem.is_published.is_(True))
    statement = statement.order_by(NewsItem.created_at.desc(), NewsItem.id.desc())
    with SessionLocal() as session:
        return session.scalars(statement).all()


def get_news_item(news_id: int) -> NewsItem | None:
    with SessionLocal() as session:
        return session.get(NewsItem, news_id)


def _unique_slug(session, title: str, news_id: int | None = None) -> str:
    base_slug = slugify(title)
    slug = base_slug
    counter = 2
    while True:
        existing = session.scalar(select(NewsItem).where(NewsItem.slug == slug))
        if not existing or existing.id == news_id:
            return slug
        slug = f"{base_slug}-{counter}"
        counter += 1


def save_news_item(news_id: int | None, title: str, body: str, is_published: bool) -> None:
    with SessionLocal() as session:
        if news_id:
            item = session.get(NewsItem, news_id)
            if item:
                item.title = title.strip()
                item.slug = _unique_slug(session, title, news_id)
                item.body = body.strip()
                item.is_published = is_published
        else:
            session.add(
                NewsItem(
                    title=title.strip(),
                    slug=_unique_slug(session, title),
                    body=body.strip(),
                    is_published=is_published,
                )
            )
        session.commit()


def delete_news_item(news_id: int) -> None:
    with SessionLocal() as session:
        item = session.get(NewsItem, news_id)
        if item:
            session.delete(item)
            session.commit()


def get_popup() -> Popup:
    with SessionLocal() as session:
        popup = session.get(Popup, 1)
        if popup:
            return popup
    init_db()
    with SessionLocal() as session:
        return session.get(Popup, 1)


def update_popup(title: str, body: str, cta_label: str, cta_url: str, is_enabled: bool) -> None:
    with SessionLocal() as session:
        popup = session.get(Popup, 1)
        if popup:
            popup.title = title.strip()
            popup.body = body.strip()
            popup.cta_label = cta_label.strip()
            popup.cta_url = cta_url.strip()
            popup.is_enabled = is_enabled
            session.commit()


def list_images(slot: str | None = None) -> list[GalleryImage]:
    statement = select(GalleryImage)
    if slot:
        statement = statement.where(GalleryImage.slot == slot)
    statement = statement.order_by(GalleryImage.created_at.desc(), GalleryImage.id.desc())
    with SessionLocal() as session:
        return session.scalars(statement).all()


def get_slot_image(slot: str) -> GalleryImage | None:
    with SessionLocal() as session:
        return session.scalar(
            select(GalleryImage)
            .where(GalleryImage.slot == slot)
            .order_by(GalleryImage.created_at.desc(), GalleryImage.id.desc())
            .limit(1)
        )


def add_image(filename: str, title: str, slot: str = "gallery") -> None:
    if slot not in IMAGE_SLOTS:
        slot = "gallery"
    with SessionLocal() as session:
        session.add(GalleryImage(filename=filename, title=title.strip(), slot=slot))
        session.commit()


def update_image(image_id: int, title: str, slot: str) -> None:
    if slot not in IMAGE_SLOTS:
        slot = "gallery"
    with SessionLocal() as session:
        image = session.get(GalleryImage, image_id)
        if image:
            image.title = title.strip()
            image.slot = slot
            session.commit()


def delete_image(image_id: int) -> str | None:
    with SessionLocal() as session:
        image = session.get(GalleryImage, image_id)
        if not image:
            return None
        filename = image.filename
        session.delete(image)
        session.commit()
        return filename


def list_form_fields(active_only: bool = False) -> list[FormField]:
    statement = select(FormField)
    if active_only:
        statement = statement.where(FormField.is_active.is_(True))
    statement = statement.order_by(FormField.position, FormField.id)
    with SessionLocal() as session:
        return session.scalars(statement).all()


def _unique_field_key(session, label: str) -> str:
    base_key = slugify(label).replace("-", "_")
    key = base_key
    counter = 2
    while session.scalar(select(FormField).where(FormField.field_key == key)):
        key = f"{base_key}_{counter}"
        counter += 1
    return key


def create_form_field(label: str, field_type: str, placeholder: str, is_required: bool) -> None:
    with SessionLocal() as session:
        max_position = max((field.position for field in session.scalars(select(FormField)).all()), default=0)
        session.add(
            FormField(
                field_key=_unique_field_key(session, label),
                label=label.strip(),
                field_type=field_type,
                placeholder=placeholder.strip(),
                is_required=is_required,
                is_active=True,
                position=max_position + 1,
            )
        )
        session.commit()


def update_form_field(
    field_id: int,
    label: str,
    field_type: str,
    placeholder: str,
    is_required: bool,
    is_active: bool,
    position: int,
) -> None:
    with SessionLocal() as session:
        field = session.get(FormField, field_id)
        if field:
            field.label = label.strip()
            field.field_type = field_type
            field.placeholder = placeholder.strip()
            field.is_required = is_required
            field.is_active = is_active
            field.position = position
            session.commit()


def delete_form_field(field_id: int) -> None:
    with SessionLocal() as session:
        field = session.get(FormField, field_id)
        if field:
            session.delete(field)
            session.commit()


def verify_admin(username: str, password: str) -> bool:
    with SessionLocal() as session:
        admin = session.scalar(select(AdminUser).where(AdminUser.username == username))
        return bool(admin and pwd_context.verify(password, admin.password_hash))
