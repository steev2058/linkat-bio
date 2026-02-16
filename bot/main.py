import asyncio
from pathlib import Path
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message
from dotenv import load_dotenv
import os

from app.config import WELCOME_TEXT, PAYMENT_METHODS_TEXT, BASE_URL, OPENAI_API_KEY
from openai import OpenAI
from app.db import init_db, ensure_user, ensure_page, redeem_voucher_for_user, get_conn
from app.services import (
    add_link,
    list_links,
    remove_link,
    reorder_link,
    upsert_page_field,
    generate_unique_slug,
    plan_limits,
    stats_for_user,
)

load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
UPLOAD_DIR = Path(__file__).resolve().parent.parent / "static" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

bot = Bot(token=TOKEN)
dp = Dispatcher()
openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None


async def llm_text(prompt: str, fallback: str) -> str:
    if not openai_client:
        return fallback
    try:
        resp = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.8,
        )
        return (resp.choices[0].message.content or fallback).strip()
    except Exception:
        return fallback


class CreateWizard(StatesGroup):
    name = State()
    bio = State()
    avatar = State()
    links = State()
    offer = State()


class EditWizard(StatesGroup):
    menu = State()


class LinksWizard(StatesGroup):
    menu = State()


def me(message: Message):
    user = ensure_user(message.from_user.id, message.from_user.username)
    page = ensure_page(user["id"])
    return user, page


@dp.message(Command("start"))
async def start(m: Message):
    me(m)
    await m.answer(WELCOME_TEXT)


@dp.message(Command("help"))
async def help_cmd(m: Message):
    await m.answer(
        "الأوامر: /create /edit /links /publish /stats /plan /redeem CODE /post /bio /lang"
    )


@dp.message(Command("create"))
async def create_start(m: Message, state: FSMContext):
    me(m)
    await state.set_state(CreateWizard.name)
    await m.answer("اكتب اسم العرض:")


@dp.message(CreateWizard.name)
async def create_name(m: Message, state: FSMContext):
    user, page = me(m)
    upsert_page_field(page["id"], "display_name", m.text.strip())
    await state.set_state(CreateWizard.bio)
    await m.answer("اكتب نبذة قصيرة:")


@dp.message(CreateWizard.bio)
async def create_bio(m: Message, state: FSMContext):
    user, page = me(m)
    upsert_page_field(page["id"], "bio", m.text.strip())
    await state.set_state(CreateWizard.avatar)
    await m.answer("أرسل صورة (Avatar) أو اكتب /skip")


@dp.message(CreateWizard.avatar, Command("skip"))
async def create_avatar_skip(m: Message, state: FSMContext):
    await state.set_state(CreateWizard.links)
    await m.answer("أرسل الروابط بهذا الشكل:\nالعنوان | الرابط\nأرسل /done عند الانتهاء")


@dp.message(CreateWizard.avatar, F.photo)
async def create_avatar_photo(m: Message, state: FSMContext):
    user, page = me(m)
    photo = m.photo[-1]
    file = await bot.get_file(photo.file_id)
    path = UPLOAD_DIR / f"avatar_{user['id']}.jpg"
    await bot.download_file(file.file_path, destination=path)
    upsert_page_field(page["id"], "avatar_path", f"/static/uploads/{path.name}")
    await state.set_state(CreateWizard.links)
    await m.answer("تم حفظ الصورة. الآن أرسل الروابط (العنوان | الرابط) ثم /done")


@dp.message(CreateWizard.links, Command("done"))
async def create_links_done(m: Message, state: FSMContext):
    await state.set_state(CreateWizard.offer)
    await m.answer("أرسل عرض اليوم بهذا الشكل: العنوان | الرابط أو /skip")


@dp.message(CreateWizard.links)
async def create_links_add(m: Message, state: FSMContext):
    user, page = me(m)
    limits = plan_limits(user)
    links = list_links(page["id"])
    if len(links) >= limits["max_links"]:
        await m.answer("وصلت للحد الأقصى لعدد الروابط في خطتك الحالية.")
        return
    if "|" not in (m.text or ""):
        await m.answer("صيغة غير صحيحة. استخدم: العنوان | الرابط")
        return
    title, url = [x.strip() for x in m.text.split("|", 1)]
    add_link(page["id"], title, url)
    await m.answer("تمت إضافة الرابط ✅")


@dp.message(CreateWizard.offer, Command("skip"))
async def create_offer_skip(m: Message, state: FSMContext):
    await state.clear()
    await m.answer("تم حفظ الصفحة. نفّذ /publish للنشر.")


@dp.message(CreateWizard.offer)
async def create_offer_set(m: Message, state: FSMContext):
    user, page = me(m)
    if "|" not in (m.text or ""):
        await m.answer("الصيغة: العنوان | الرابط")
        return
    title, url = [x.strip() for x in m.text.split("|", 1)]
    upsert_page_field(page["id"], "offer_title", title)
    upsert_page_field(page["id"], "offer_url", url)
    await state.clear()
    await m.answer("تم حفظ العرض ✅ نفّذ /publish للنشر")


@dp.message(Command("publish"))
async def publish_cmd(m: Message):
    user, page = me(m)
    if not page["display_name"]:
        await m.answer("أكمل البيانات أولاً عبر /create")
        return
    slug = page["slug"] or generate_unique_slug(page["display_name"])
    with get_conn() as conn:
        conn.execute("UPDATE pages SET slug=?, is_published=1, updated_at=datetime('now') WHERE id=?", (slug, page["id"]))
    await m.answer(f"تم النشر ✅\n{BASE_URL}/u/{slug}")


@dp.message(Command("links"))
async def links_cmd(m: Message, state: FSMContext):
    user, page = me(m)
    links = list_links(page["id"])
    text = "روابطك الحالية:\n"
    if not links:
        text += "(لا يوجد)\n"
    for i, l in enumerate(links, start=1):
        text += f"{i}) {l['title']} -> {l['url']}\n"
    text += "\nللإضافة: add العنوان | الرابط\nللحذف: remove رقم\nلإعادة الترتيب (مدفوع): move من إلى\nللخروج: /done"
    await state.set_state(LinksWizard.menu)
    await m.answer(text)


@dp.message(LinksWizard.menu, Command("done"))
async def links_done(m: Message, state: FSMContext):
    await state.clear()
    await m.answer("تم")


@dp.message(LinksWizard.menu)
async def links_actions(m: Message):
    user, page = me(m)
    txt = (m.text or "").strip()
    if txt.startswith("add "):
        body = txt[4:]
        if "|" not in body:
            await m.answer("صيغة add: add العنوان | الرابط")
            return
        limits = plan_limits(user)
        if len(list_links(page["id"])) >= limits["max_links"]:
            await m.answer("لا يمكن إضافة أكثر من 3 روابط في الخطة المجانية.")
            return
        t, u = [x.strip() for x in body.split("|", 1)]
        add_link(page["id"], t, u)
        await m.answer("تمت الإضافة ✅")
        return
    if txt.startswith("remove "):
        try:
            idx = int(txt.split()[1])
        except Exception:
            await m.answer("استخدم: remove رقم")
            return
        ok = remove_link(page["id"], idx)
        await m.answer("تم الحذف ✅" if ok else "رقم غير صحيح")
        return
    if txt.startswith("move "):
        limits = plan_limits(user)
        if not limits["reorder"]:
            await m.answer("إعادة الترتيب متاحة فقط في الباقات المدفوعة.")
            return
        try:
            _, a, b = txt.split()
            ok = reorder_link(page["id"], int(a), int(b))
            await m.answer("تمت إعادة الترتيب ✅" if ok else "قيم غير صحيحة")
        except Exception:
            await m.answer("استخدم: move من إلى")
        return
    await m.answer("أمر غير معروف. استخدم add/remove/move أو /done")


@dp.message(Command("edit"))
async def edit_cmd(m: Message):
    await m.answer(
        "للتعديل السريع:\n"
        "- الاسم: /setname Your Name\n"
        "- النبذة: /setbio نص\n"
        "- اللون (مدفوع): /settheme #112233\n"
        "- الفيديو المميز (PRO_3): /setvideo رابط\n"
        "- العرض: /setoffer العنوان | الرابط"
    )


@dp.message(Command("setname"))
async def set_name(m: Message, command: CommandObject):
    user, page = me(m)
    if not command.args:
        await m.answer("استخدم: /setname الاسم")
        return
    upsert_page_field(page["id"], "display_name", command.args.strip())
    await m.answer("تم تحديث الاسم")


@dp.message(Command("setbio"))
async def set_bio(m: Message, command: CommandObject):
    user, page = me(m)
    if not command.args:
        await m.answer("استخدم: /setbio النبذة")
        return
    upsert_page_field(page["id"], "bio", command.args.strip())
    await m.answer("تم تحديث النبذة")


@dp.message(Command("settheme"))
async def set_theme(m: Message, command: CommandObject):
    user, page = me(m)
    limits = plan_limits(user)
    if not limits["custom_theme"]:
        await m.answer("تخصيص الألوان متاح في الباقات المدفوعة فقط.")
        return
    if not command.args:
        await m.answer("استخدم: /settheme #112233")
        return
    upsert_page_field(page["id"], "theme_color", command.args.strip())
    await m.answer("تم تحديث اللون")


@dp.message(Command("setvideo"))
async def set_video(m: Message, command: CommandObject):
    user, page = me(m)
    limits = plan_limits(user)
    if not limits["featured_video"]:
        await m.answer("الفيديو المميز متاح فقط في PRO_3")
        return
    if not command.args:
        await m.answer("استخدم: /setvideo الرابط")
        return
    upsert_page_field(page["id"], "featured_video_url", command.args.strip())
    await m.answer("تم تحديث الفيديو")


@dp.message(Command("setoffer"))
async def set_offer(m: Message, command: CommandObject):
    user, page = me(m)
    if not command.args or "|" not in command.args:
        await m.answer("استخدم: /setoffer العنوان | الرابط")
        return
    t, u = [x.strip() for x in command.args.split("|", 1)]
    upsert_page_field(page["id"], "offer_title", t)
    upsert_page_field(page["id"], "offer_url", u)
    await m.answer("تم تحديث عرض اليوم")


@dp.message(Command("redeem"))
async def redeem_cmd(m: Message, command: CommandObject):
    user, page = me(m)
    if not command.args:
        await m.answer("استخدم: /redeem CODE")
        return
    ok, msg = redeem_voucher_for_user(user["id"], command.args.strip())
    await m.answer(msg)


@dp.message(Command("plan"))
async def plan_cmd(m: Message):
    user, page = me(m)
    limits = plan_limits(user)
    exp = user["plan_expires_at"] or "-"
    await m.answer(
        f"خطتك الحالية: {limits['plan']}\n"
        f"الانتهاء: {exp}\n"
        f"الحد الأقصى للروابط: {limits['max_links']}\n"
        f"Watermark: {'نعم' if limits['watermark'] else 'لا'}\n\n"
        + PAYMENT_METHODS_TEXT
    )


@dp.message(Command("stats"))
async def stats_cmd(m: Message):
    user, page = me(m)
    s = stats_for_user(user["id"])
    lines = [
        f"إجمالي المشاهدات: {s['views_total']}",
        f"إجمالي النقرات: {s['clicks_total']}",
        f"مشاهدات آخر 7 أيام: {s['views_7d']}",
        f"نقرات آخر 7 أيام: {s['clicks_7d']}",
        "Top 5 روابط:",
    ]
    for t in s["top_links"]:
        lines.append(f"- {t['title']} ({t['c']})")
    await m.answer("\n".join(lines))


@dp.message(Command("post"))
async def post_cmd(m: Message):
    fallback = (
        "🚀 جاهزين ننطلق؟\n"
        "صفحتي الجديدة على Linkat تجمع كل حساباتي بمكان واحد 🔗\n"
        "زوروني الآن!\n"
        "#Linkat #سوريا #تسويق #بيزنس"
    )
    txt = await llm_text(
        "اكتب منشور تسويقي قصير باللهجة السورية لصفحة Linkat مع هاشتاغات وكول تو أكشن.",
        fallback,
    )
    await m.answer(txt)


@dp.message(Command("bio"))
async def bio_cmd(m: Message, command: CommandObject):
    field = (command.args or "صانع محتوى").strip()
    fallback = "\n\n".join([
        f"1) {field} محترف أشارك محتوى عملي يومياً وأساعد المتابعين على نتائج حقيقية.",
        f"2) أنا {field}، خبرتي بالسوق السوري والعربي، وهذا رابط كل أعمالي.",
        f"3) {field} | حلول بسيطة ونتائج واضحة | تواصل مباشر من الروابط بالأسفل.",
        f"4) أبني حضور رقمي قوي بصفتي {field} مع تركيز على الجودة والثقة.",
        f"5) {field} شغوف، أقدم محتوى مفيد وخدمات عملية للمهتمين بالتطوير والنمو.",
    ])
    txt = await llm_text(
        f"اكتب 5 bio احترافية قصيرة باللغة العربية لشخص مجاله {field}. اكتبها كقائمة مرقمة.",
        fallback,
    )
    await m.answer(txt)


@dp.message(Command("lang"))
async def lang_cmd(m: Message, command: CommandObject):
    user, _ = me(m)
    val = (command.args or "ar").strip().lower()
    if val not in {"ar", "en"}:
        await m.answer("استخدم: /lang ar أو /lang en")
        return
    with get_conn() as conn:
        conn.execute("UPDATE users SET language=? WHERE id=?", (val, user["id"]))
    await m.answer("تم تغيير اللغة")


async def main():
    if not TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is missing")
    init_db()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
