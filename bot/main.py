import asyncio
from pathlib import Path
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from dotenv import load_dotenv
import os
import re

from app.config import WELCOME_TEXT, PAYMENT_METHODS_TEXT, BASE_URL, OPENAI_API_KEY, UPLOAD_DIR
from openai import OpenAI
from app.db import init_db, ensure_user, ensure_page, redeem_voucher_for_user, get_conn
from app.security import sanitize_text, valid_http_url
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
UPLOAD_DIR = Path(UPLOAD_DIR)
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


def main_menu_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🚀 إنشاء الصفحة"), KeyboardButton(text="📤 نشر")],
            [KeyboardButton(text="🔗 الروابط"), KeyboardButton(text="📊 الإحصائيات")],
            [KeyboardButton(text="💳 خطتي"), KeyboardButton(text="✏️ تعديل سريع")],
        ],
        resize_keyboard=True,
    )


def quick_choice_kb(labels: list[str]):
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=l)] for l in labels],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def is_done_text(text: str) -> bool:
    return (text or "").strip().lower() in {"/done", "done", "تم", "خلص", "انتهيت"}


def is_skip_text(text: str) -> bool:
    return (text or "").strip().lower() in {"/skip", "skip", "تخطي", "تجاوز"}


def infer_title_from_url(url: str) -> tuple[str, str]:
    u = (url or "").lower()
    if "instagram.com" in u:
        return "Instagram", "instagram"
    if "youtube.com" in u or "youtu.be" in u:
        return "YouTube", "youtube"
    if "tiktok.com" in u:
        return "TikTok", "tiktok"
    if "snapchat.com" in u:
        return "Snapchat", "snapchat"
    if "facebook.com" in u:
        return "Facebook", "facebook"
    if "wa.me" in u or "whatsapp" in u:
        return "WhatsApp", "whatsapp"
    if "t.me" in u or "telegram" in u:
        return "Telegram", "telegram"
    return "Website", "website"


@dp.message(Command("start"))
async def start(m: Message):
    me(m)
    await m.answer(WELCOME_TEXT, reply_markup=main_menu_kb())


@dp.message(Command("help"))
async def help_cmd(m: Message):
    await m.answer(
        "الأوامر: /create /edit /links /publish /stats /plan /redeem CODE /post /bio /lang",
        reply_markup=main_menu_kb(),
    )


@dp.message(Command("menu"))
async def menu_cmd(m: Message):
    await m.answer("اختر الإجراء", reply_markup=main_menu_kb())


@dp.message(F.text == "🚀 إنشاء الصفحة")
async def menu_to_create(m: Message, state: FSMContext):
    await create_start(m, state)


@dp.message(F.text == "📤 نشر")
async def menu_to_publish(m: Message):
    await publish_cmd(m)


@dp.message(F.text == "🔗 الروابط")
async def menu_to_links(m: Message, state: FSMContext):
    await links_cmd(m, state)


@dp.message(F.text == "📊 الإحصائيات")
async def menu_to_stats(m: Message):
    await stats_cmd(m)


@dp.message(F.text == "💳 خطتي")
async def menu_to_plan(m: Message):
    await plan_cmd(m)


@dp.message(F.text == "✏️ تعديل سريع")
async def menu_to_edit(m: Message):
    await edit_cmd(m)


@dp.message(Command("create"))
async def create_start(m: Message, state: FSMContext):
    me(m)
    await state.set_state(CreateWizard.name)
    await m.answer("ممتاز 👌 خلينا نبدأ بسرعة.\nاكتب اسم العرض (مثال: متجر سامر):", reply_markup=ReplyKeyboardRemove())


@dp.message(CreateWizard.name)
async def create_name(m: Message, state: FSMContext):
    user, page = me(m)
    upsert_page_field(page["id"], "display_name", sanitize_text(m.text or "", 60))
    await state.set_state(CreateWizard.bio)
    await m.answer("اكتب نبذة قصيرة (سطر واحد يكفي):")


@dp.message(CreateWizard.bio)
async def create_bio(m: Message, state: FSMContext):
    user, page = me(m)
    upsert_page_field(page["id"], "bio", sanitize_text(m.text or "", 200))
    await state.set_state(CreateWizard.avatar)
    await m.answer("إذا بدك صورة بعتلي صورة هلأ، أو اختار تخطي 👇", reply_markup=quick_choice_kb(["تخطي"]))


@dp.message(CreateWizard.avatar, Command("skip"))
async def create_avatar_skip(m: Message, state: FSMContext):
    await state.set_state(CreateWizard.links)
    await m.answer("ابعث روابطك بسهولة 👇\n- فيك تبعت الرابط لحاله (مثال: https://instagram.com/username)\n- أو: العنوان | الرابط\nلما تخلص اكتب: تم", reply_markup=quick_choice_kb(["تم"]))


@dp.message(CreateWizard.avatar, F.text)
async def create_avatar_skip_text(m: Message, state: FSMContext):
    if is_skip_text(m.text or ""):
        await create_avatar_skip(m, state)
        return
    await m.answer("إما أرسل صورة، أو اضغط تخطي")


@dp.message(CreateWizard.avatar, F.photo)
async def create_avatar_photo(m: Message, state: FSMContext):
    user, page = me(m)
    photo = m.photo[-1]
    file = await bot.get_file(photo.file_id)
    path = UPLOAD_DIR / f"avatar_{user['id']}_{photo.file_id[-8:]}.jpg"
    await bot.download_file(file.file_path, destination=path)
    upsert_page_field(page["id"], "avatar_path", f"/uploads/{path.name}")
    await state.set_state(CreateWizard.links)
    await m.answer("تم حفظ الصورة ✅\nالآن ابعث روابطك (رابط فقط أو العنوان | الرابط)\nولما تخلص اكتب: تم", reply_markup=quick_choice_kb(["تم"]))


@dp.message(CreateWizard.links, Command("done"))
async def create_links_done(m: Message, state: FSMContext):
    await state.set_state(CreateWizard.offer)
    await m.answer("بدك تضيف عرض اليوم؟\nالصيغة: العنوان | الرابط\nأو اختار تخطي", reply_markup=quick_choice_kb(["تخطي"]))


@dp.message(CreateWizard.links)
async def create_links_add(m: Message, state: FSMContext):
    text = (m.text or "").strip()
    if is_done_text(text):
        await create_links_done(m, state)
        return

    user, page = me(m)
    limits = plan_limits(user)
    links = list_links(page["id"])
    if len(links) >= limits["max_links"]:
        await m.answer("وصلت للحد الأقصى لعدد الروابط في خطتك الحالية. اكتب تم للمتابعة.")
        return

    # support multi-line paste for easier onboarding
    lines = [x.strip() for x in text.splitlines() if x.strip()]
    if not lines:
        await m.answer("ابعث رابط واحد أو أكثر، وكل رابط بسطر")
        return

    added = 0
    for line in lines:
        if added + len(links) >= limits["max_links"]:
            break
        if "|" in line:
            title, url = [x.strip() for x in line.split("|", 1)]
        else:
            url = line
            title, _platform = infer_title_from_url(url)

        if not valid_http_url(url):
            continue
        try:
            add_link(page["id"], title, url)
            added += 1
        except ValueError:
            continue

    if added == 0:
        await m.answer("ما قدرت أضيف روابط من الرسالة. تأكد كل رابط يبدأ بـ http:// أو https://")
        return

    await m.answer(f"تمت إضافة {added} رابط ✅\nابعث روابط زيادة أو اكتب: تم")


@dp.message(CreateWizard.offer, Command("skip"))
async def create_offer_skip(m: Message, state: FSMContext):
    await state.clear()
    await m.answer("تم حفظ الصفحة ✅\nالآن اضغط 📤 نشر", reply_markup=main_menu_kb())


@dp.message(CreateWizard.offer, F.text)
async def create_offer_skip_text(m: Message, state: FSMContext):
    if is_skip_text(m.text or ""):
        await create_offer_skip(m, state)
        return
    if "|" not in (m.text or ""):
        await m.answer("اكتب العرض هكذا: العنوان | الرابط أو اضغط تخطي")
        return
    await create_offer_set(m, state)


@dp.message(CreateWizard.offer)
async def create_offer_set(m: Message, state: FSMContext):
    user, page = me(m)
    if "|" not in (m.text or ""):
        await m.answer("الصيغة: العنوان | الرابط")
        return
    title, url = [x.strip() for x in m.text.split("|", 1)]
    if not valid_http_url(url):
        await m.answer("رابط العرض غير صالح")
        return
    upsert_page_field(page["id"], "offer_title", sanitize_text(title, 80))
    upsert_page_field(page["id"], "offer_url", url)
    await state.clear()
    await m.answer("تم حفظ العرض ✅\nالآن اضغط 📤 نشر", reply_markup=main_menu_kb())


@dp.message(Command("publish"))
async def publish_cmd(m: Message):
    user, page = me(m)
    if not page["display_name"]:
        await m.answer("أكمل البيانات أولاً عبر /create")
        return
    slug = page["slug"] or generate_unique_slug(page["display_name"])
    with get_conn() as conn:
        conn.execute("UPDATE pages SET slug=?, is_published=1, updated_at=datetime('now') WHERE id=?", (slug, page["id"]))
    await m.answer(f"تم النشر ✅\n{BASE_URL}/u/{slug}", reply_markup=main_menu_kb())


@dp.message(Command("links"))
async def links_cmd(m: Message, state: FSMContext):
    user, page = me(m)
    links = list_links(page["id"])
    text = "روابطك الحالية:\n"
    if not links:
        text += "(لا يوجد)\n"
    for i, l in enumerate(links, start=1):
        text += f"{i}) {l['title']} -> {l['url']}\n"
    text += "\nللإضافة السريعة: ابعث رابط مباشرة\nأو add العنوان | الرابط\nللحذف: remove رقم\nللترتيب (مدفوع): move من إلى\nللخروج: تم"
    await state.set_state(LinksWizard.menu)
    await m.answer(text, reply_markup=quick_choice_kb(["تم"]))


@dp.message(LinksWizard.menu, Command("done"))
async def links_done(m: Message, state: FSMContext):
    await state.clear()
    await m.answer("تم ✅", reply_markup=main_menu_kb())


@dp.message(LinksWizard.menu)
async def links_actions(m: Message, state: FSMContext):
    user, page = me(m)
    txt = (m.text or "").strip()

    if is_done_text(txt):
        await links_done(m, state)
        return

    if txt.startswith("add "):
        body = txt[4:]
        if "|" not in body:
            await m.answer("صيغة add: add العنوان | الرابط")
            return
        limits = plan_limits(user)
        if len(list_links(page["id"])) >= limits["max_links"]:
            await m.answer("وصلت لحد الروابط في خطتك.")
            return
        t, u = [x.strip() for x in body.split("|", 1)]
        if not valid_http_url(u):
            await m.answer("الرابط غير صالح. استخدم http/https")
            return
        try:
            add_link(page["id"], t, u)
        except ValueError:
            await m.answer("الرابط غير صالح")
            return
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

    # ultra-simple: allow direct URL add
    if valid_http_url(txt):
        limits = plan_limits(user)
        if len(list_links(page["id"])) >= limits["max_links"]:
            await m.answer("وصلت لحد الروابط في خطتك.")
            return
        title, _platform = infer_title_from_url(txt)
        try:
            add_link(page["id"], title, txt)
            await m.answer(f"تمت إضافة الرابط ✅ ({title})")
        except ValueError:
            await m.answer("الرابط غير صالح")
        return

    await m.answer("مو واضح. ابعث رابط مباشر، أو add/remove/move، أو تم")


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
    upsert_page_field(page["id"], "display_name", sanitize_text(command.args, 60))
    await m.answer("تم تحديث الاسم")


@dp.message(Command("setbio"))
async def set_bio(m: Message, command: CommandObject):
    user, page = me(m)
    if not command.args:
        await m.answer("استخدم: /setbio النبذة")
        return
    upsert_page_field(page["id"], "bio", sanitize_text(command.args, 200))
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
    color = command.args.strip()
    if not re.match(r"^#[0-9a-fA-F]{6}$", color):
        await m.answer("صيغة اللون يجب أن تكون مثل #112233")
        return
    upsert_page_field(page["id"], "theme_color", color)
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
    url = command.args.strip()
    if not valid_http_url(url):
        await m.answer("رابط الفيديو غير صالح")
        return
    upsert_page_field(page["id"], "featured_video_url", url)
    await m.answer("تم تحديث الفيديو")


@dp.message(Command("setoffer"))
async def set_offer(m: Message, command: CommandObject):
    user, page = me(m)
    if not command.args or "|" not in command.args:
        await m.answer("استخدم: /setoffer العنوان | الرابط")
        return
    t, u = [x.strip() for x in command.args.split("|", 1)]
    if not valid_http_url(u):
        await m.answer("رابط العرض غير صالح")
        return
    upsert_page_field(page["id"], "offer_title", sanitize_text(t, 80))
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
