import os
from dotenv import load_dotenv

load_dotenv()

APP_NAME = "Linkat"
APP_ENV = os.getenv("APP_ENV", "dev")
BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8000").rstrip("/")
DB_PATH = os.getenv("DB_PATH", "./linkat.db")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "change-me")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
BOT_USERNAME = os.getenv("BOT_USERNAME", "YourBotUsername")
SUPPORT_TELEGRAM = os.getenv("SUPPORT_TELEGRAM", "https://t.me/YourBotUsername")
BUSINESS_EMAIL = os.getenv("BUSINESS_EMAIL", "business@pety.company")
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "/var/www/linkat/uploads" if APP_ENV == "prod" else "./data/uploads")

PAYMENT_METHODS_TEXT = """طرق الدفع للحصول على كود التفعيل:
- سيرياتيل كاش
- MTN Cash
- ShamCash
- تحويل حساب بنك البركة رقم الحساب 1087714
- بنك الدولي الإسلامي
- شحن Visa أو MasterCard"""

WELCOME_TEXT = """أهلاً في Linkat 🔗
أنشئ رابط واحد يجمع كل حساباتك: يوتيوب – إنستغرام – تيك توك – سناب – واتساب – فيسبوك
ابدأ الآن: اضغط /create وأنشئ صفحتك خلال دقيقة 🚀
الخطة المجانية:
• 3 روابط
• صفحة واحدة
لإزالة العلامة المائية والحصول على روابط غير محدودة: استخدم كود التفعيل عبر /redeem"""
