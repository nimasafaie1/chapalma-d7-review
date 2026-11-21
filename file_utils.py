"""ابزار شمارش تعداد صفحات فایل ورد و پی‌دی‌اف."""

import zipfile
from xml.etree import ElementTree as ET

# حداکثر حجم فایلی که ربات می‌تونه از تلگرام دانلود کنه.
# نکته فنی: طبق مستندات رسمی Bot API تلگرام (api.telegram.org)، سقف واقعی
# دانلود فایل توسط ربات ۲۰ مگابایته (نه ۵۰) — عدد ۵۰ مگابایت مربوط به
# آپلود/ارسال فایل از طرف رباته، نه دریافتش. برای اینکه کاربر با یه خطای
# فنی گیج‌کننده مواجه نشه، همینجا قبل از تلاش برای دانلود جلوش رو می‌گیریم.
MAX_FILE_SIZE_MB = 20
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024


class PageCountError(Exception):
    pass


def count_docx_pages(path: str) -> int:
    """
    تعداد صفحات فایل ورد (.docx) را از روی متادیتای داخلی فایل می‌خواند.
    این عدد همان چیزی است که Word خودش هنگام ذخیره فایل محاسبه و ذخیره کرده،
    پس فقط برای فایل‌هایی که حداقل یک‌بار با Word باز و ذخیره شده‌اند دقیق است.
    """
    try:
        with zipfile.ZipFile(path) as z:
            with z.open("docProps/app.xml") as f:
                tree = ET.parse(f)
    except (KeyError, zipfile.BadZipFile):
        raise PageCountError(
            "نتونستم تعداد صفحات این فایل ورد رو تشخیص بدم. "
            "لطفاً یک‌بار فایل رو با نرم‌افزار Word باز و ذخیره کن و دوباره بفرست."
        )

    ns = {"ep": "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"}
    pages_el = tree.find("ep:Pages", ns)

    if pages_el is None or not pages_el.text or not pages_el.text.isdigit():
        raise PageCountError(
            "نتونستم تعداد صفحات این فایل ورد رو تشخیص بدم. "
            "لطفاً یک‌بار فایل رو با نرم‌افزار Word باز و ذخیره کن و دوباره بفرست."
        )

    return int(pages_el.text)


def count_pdf_pages(path: str) -> int:
    try:
        from pypdf import PdfReader
    except ImportError:
        raise PageCountError(
            "کتابخانه pypdf روی سرور نصب نیست. برای شمارش صفحات pdf باید "
            "دستور `pip install pypdf --break-system-packages` رو اجرا کنی."
        )

    try:
        reader = PdfReader(path)
        return len(reader.pages)
    except Exception:
        raise PageCountError(
            "این فایل PDF قابل خواندن نبود (ممکنه خراب یا رمزگذاری‌شده باشه)."
        )


def count_pages(path: str, file_name: str) -> int:
    lower = file_name.lower()

    if lower.endswith(".pdf"):
        return count_pdf_pages(path)

    if lower.endswith(".docx"):
        return count_docx_pages(path)

    raise PageCountError(
        "فقط فایل‌های Word (.docx) و PDF (.pdf) پذیرفته می‌شن. "
        "لطفاً فایل رو با یکی از این دو فرمت بفرست."
    )
