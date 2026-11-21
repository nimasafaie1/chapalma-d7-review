"""
جاب‌های زمان‌بندی‌شده‌ی ربات:
- بک‌آپ روزانه‌ی دیتابیس (ارسال به گروه)
- گزارش فروش روزانه (ارسال به گروه)
- یادآوری پرداخت‌های تاییدنشده
- پاک‌سازی سفارش‌های یتیم (بدون پرداخت و قدیمی)

این جاب‌ها با JobQueue (بخشی از python-telegram-bot) اجرا می‌شن.
نکته: JobQueue به‌صورت پیش‌فرض ساعت‌ها رو بر اساس UTC حساب می‌کنه، نه ساعت ایران.
ایران (تهران) UTC+3:30 هست، پس اگه می‌خوای یه جاب ساعت ۲۳:۵۹ به وقت تهران اجرا بشه،
باید توی bot.py مقدار time رو با احتساب همین اختلاف تنظیم کنی.
"""

import logging
import os
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone

from config import GROUP_ID
from database import (
    DB_NAME,
    get_unconfirmed_payments_older_than,
    mark_payment_reminded,
    get_orphan_orders_older_than,
    delete_order_if_orphan,
    expire_unpaid_orders,
    EXPIRY_ORDER_MIN_AGE_HOURS,
    get_order,
    get_tracking_case_by_order,
    get_user,
    ORDER_STATUS_EXPIRED,
)

logger = logging.getLogger(__name__)

def _tehran_now():
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Asia/Tehran"))
    except Exception:
        return datetime.now(timezone(timedelta(hours=3, minutes=30)))

# حداقل سن سفارش برای اینکه «یتیمِ رهاشده» حساب شود (ساعت).
# از ۲۴ به ۷۲ ساعت افزایش یافت: کاربر ممکن است فیش را با تأخیر بفرستد و
# کاربری که سریع فیش می‌فرستد نباید به‌خاطر تأخیر چند ساعته، سفارشش پاک شود.
ORPHAN_ORDER_MIN_AGE_HOURS = 72

# سقف تعداد حذف در هر اجرا، تا یک باگ در شرط‌ها کل جدول را خالی نکند
ORPHAN_ORDER_MAX_DELETE_PER_RUN = 200

# حالت خشک (dry-run).
#
# تا وقتی این True است، هیچ سطری از دیتابیس واقعی حذف نمی‌شود و جاب فقط
# نامزدها را گزارش می‌کند. برای فعال‌کردن حذف واقعی، بعد از تأیید صریح
# مالک پروژه این را False کنید.
#
# توجه: حتی با dry-run=False هم شرط‌های سخت‌گیرانه‌ی توابع database اعمال
# می‌شود، یعنی سفارشی که آیتم یا اطلاعات مشتری دارد حذف نمی‌شود.
ORPHAN_CLEANUP_DRY_RUN = True


async def daily_backup(context):
    """هر روز یک نسخه از فایل دیتابیس رو به گروه می‌فرسته."""
    if not os.path.exists(DB_NAME):
        return

    today = _tehran_now().strftime("%Y-%m-%d")

    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            backup_path = os.path.join(tmp_dir, f"backup_{today}.db")
            src = sqlite3.connect(DB_NAME)
            try:
                dst = sqlite3.connect(backup_path)
                try:
                    src.backup(dst)
                finally:
                    dst.close()
            finally:
                src.close()
            with open(backup_path, "rb") as f:
                await context.bot.send_document(
                    chat_id=GROUP_ID,
                    document=f,
                    filename=f"backup_{today}.db",
                    caption=f"🗄️ بک‌آپ خودکار دیتابیس — {today}"
                )
    except Exception as exc:
        logger.error(
            "ارسال بک‌آپ روزانه ناموفق بود: %s: %s", type(exc).__name__, exc
        )


async def daily_report(context):
    """هر شب خلاصه‌ی فروش امروز رو به‌صورت فایل اکسل به گروه می‌فرسته."""
    from export_excel import build_orders_excel

    today = _tehran_now().strftime("%Y-%m-%d")

    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = os.path.join(tmp_dir, f"report_{today}.xlsx")
            count = build_orders_excel(path, date_str=today)

            if count == 0:
                await context.bot.send_message(
                    chat_id=GROUP_ID,
                    text=f"📭 امروز ({today}) هیچ سفارشی ثبت نشده."
                )
                return

            with open(path, "rb") as f:
                await context.bot.send_document(
                    chat_id=GROUP_ID,
                    document=f,
                    filename=f"report_{today}.xlsx",
                    caption=f"📊 گزارش پایان روز — {today} ({count} سفارش)"
                )
    except Exception as exc:
        logger.error(
            "ارسال گزارش پایان روز ناموفق بود: %s: %s", type(exc).__name__, exc
        )


async def check_unconfirmed_payments(context):
    """اگه یه فیش بیش از حد معینی (مثلاً ۲ ساعت) بدون تایید مونده، یه یادآوری می‌فرسته."""
    pending = get_unconfirmed_payments_older_than(hours=2)

    if not pending:
        return

    lines = ["⏰ یادآوری: این پرداخت‌ها هنوز تایید نشدن:"]
    for p in pending:
        lines.append(f"• سفارش {p['order_id']} (ثبت‌شده: {p['created_at']})")

    try:
        await context.bot.send_message(chat_id=GROUP_ID, text="\n".join(lines))
    except Exception as exc:
        logger.error(
            "ارسال یادآوری پرداخت به گروه ناموفق بود: %s: %s", type(exc).__name__, exc
        )
        return

    for p in pending:
        mark_payment_reminded(p["id"])


# ---------------------------------------------------------------------------
# پاک‌سازی سفارش‌های یتیم
# ---------------------------------------------------------------------------

def _active_receipt_order_ids(application):
    """
    شماره‌ی سفارش‌هایی که همین الان در جریان فعال یک کاربر هستند.

    این‌ها را عمداً محافظه‌کارانه محافظت می‌کنیم: تا وقتی کاربر فیشش را دوباره
    نفرستاده، نباید سفارشش پاک شود؛ چون اگر پاک شود و کاربر بعداً فیش بفرستد،
    رکورد پرداخت به سفارش ناموجود وصل می‌شود.

    فقط خواندنی است؛ هیچ تغییری در user_data داده نمی‌شود.
    """
    active = set()

    try:
        user_data = application.user_data
    except AttributeError:
        return active

    for _user_id, data in list(user_data.items()):
        if not data:
            continue
        try:
            order_id = data.get("receipt_order_id")
        except AttributeError:
            continue
        if order_id is None:
            continue
        try:
            active.add(int(order_id))
        except (TypeError, ValueError):
            continue

    return active


async def cleanup_orphan_orders(context):
    """
    سفارش‌های قدیمیِ بدون پرداخت را پاک می‌کند.

    شرط‌های حذف (همه باید برقرار باشند — در database تعریف شده‌اند):
      ۱) وضعیت سفارش «در انتظار پرداخت» باشد،
      ۲) قدیمی‌تر از ORPHAN_ORDER_MIN_AGE_HOURS (۷۲ ساعت) باشد،
      ۳) هیچ رکورد پرداختی نداشته باشد — حتی confirmed=0 هم پرداخت محسوب می‌شود،
      ۴) هیچ آیتمی در order_items نداشته باشد،
      ۵) هیچ اطلاعات مشتری/سفارشی نداشته باشد (تلفن، آدرس، ارسال، مبلغ،
         تعداد، نام فایل، صفحه، کد تخفیف) — یعنی یک پوسته‌ی خالی و بی‌مصرف،
      ۶) در PROTECTED_ORDER_IDS نباشد (سفارش‌های ۲ و ۳ هرگز حذف نمی‌شوند)،
      ۷) در user_data هیچ کاربری همین حالا در حال ارسال فیش آن سفارش نیست.

    بنابراین یک سفارش واقعیِ مشتری — که آیتم یا مشخصات دارد — صرفاً به
    دلیل «پرداخت‌نشدن» هرگز حذف نمی‌شود.

    اگر ORPHAN_CLEANUP_DRY_RUN فعال باشد، هیچ حذفی انجام نمی‌شود و فقط
    گزارش خشک تولید می‌شود.

    توجه: این کار «تأیید/رد پرداخت» نیست؛ فقط رکوردهای بلااستفاده‌ی قدیمی را
    از دیتابیس جمع می‌کند. اگر خطایی پیش بیاید، نباید JobQueue را بشکند.
    """
    try:
        candidates = get_orphan_orders_older_than(hours=ORPHAN_ORDER_MIN_AGE_HOURS)
    except Exception as exc:
        logger.error("پیدا کردن سفارش‌های یتیم ناموفق بود: %s: %s", type(exc).__name__, exc)
        return

    if not candidates:
        logger.info("پاک‌سازی سفارش‌های یتیم: موردی برای بررسی نبود.")
        return

    protected = _active_receipt_order_ids(context.application)

    deleted = []
    skipped_active = []
    skipped_race = []
    skipped_dry_run = []

    for order in candidates:
        # سقف ایمنی: در یک اجرا بیش از این تعداد حذف نمی‌شود تا یک خطای منطقی
        # در شرط‌ها به از دست رفتن دسته‌ای داده منجر نشود.
        if len(deleted) >= ORPHAN_ORDER_MAX_DELETE_PER_RUN:
            logger.warning(
                "پاک‌سازی سفارش‌های یتیم به سقف %s رسید؛ %s نامزد دیگر در اجرای بعدی بررسی می‌شود.",
                ORPHAN_ORDER_MAX_DELETE_PER_RUN, len(candidates) - len(deleted),
            )
            break

        if order["id"] in protected:
            skipped_active.append(order["id"])
            continue

        if ORPHAN_CLEANUP_DRY_RUN:
            skipped_dry_run.append(order["id"])
            continue

        try:
            result = delete_order_if_orphan(order["id"], hours=ORPHAN_ORDER_MIN_AGE_HOURS)
        except Exception as exc:
            logger.error(
                "حذف سفارش یتیم %s ناموفق بود: %s: %s",
                order["id"], type(exc).__name__, exc,
            )
            continue

        if result["deleted"]:
            deleted.append(order)
            # فعلاً هیچ چیزی در discount_codes تغییر نمی‌کند؛ فقط ثبت می‌شود
            # تا بعداً بتوان تصمیم گرفت. علت: increment_discount_usage موقع وارد
            # کردن کد اجرا می‌شود، نه موقع ساخت سفارش.
            if order.get("discount_code"):
                logger.warning(
                    "سفارش یتیم %s کد تخفیف «%s» داشت (مبلغ تخفیف: %s) و حذف شد؛ "
                    "used_count کد تخفیف تغییر نکرد.",
                    order["id"], order["discount_code"], order.get("discount_amount"),
                )
        else:
            skipped_race.append(order["id"])

    logger.info(
        "پاک‌سازی سفارش‌های یتیم (dry_run=%s) — نامزد: %s | حذف‌شده: %s | "
        "رد‌شده (کاربر فعال): %s | رد‌شده (شرط تغییر کرده): %s | رد‌شده (dry-run): %s",
        ORPHAN_CLEANUP_DRY_RUN, len(candidates), [o["id"] for o in deleted],
        skipped_active, skipped_race, skipped_dry_run,
    )

    if not deleted and not skipped_dry_run:
        return

    mode = "گزارش خشک (چیزی حذف نشد)" if ORPHAN_CLEANUP_DRY_RUN else "حذف واقعی"

    lines = [
        f"🧹 پاک‌سازی سفارش‌های یتیم — حالت: {mode}",
        f"شرط: قدیمی‌تر از {ORPHAN_ORDER_MIN_AGE_HOURS} ساعت، وضعیت «در انتظار پرداخت»، "
        "بدون پرداخت، بدون آیتم و بدون اطلاعات مشتری.",
    ]
    if deleted:
        lines.append(
            f"حذف‌شده: {len(deleted)} سفارش — شماره‌ها: "
            f"{', '.join(str(o['id']) for o in deleted)}"
        )
    if skipped_dry_run:
        lines.append(
            f"نامزدهایی که به‌دلیل حالت خشک حذف نشدند: {', '.join(map(str, skipped_dry_run))}"
        )
    if skipped_active:
        lines.append(f"محافظت‌شده چون کاربرشان در جریان ارسال فیش است: {', '.join(map(str, skipped_active))}")

    try:
        await context.bot.send_message(chat_id=GROUP_ID, text="\n".join(lines))
    except Exception as exc:
        logger.error("ارسال گزارش پاک‌سازی به گروه ناموفق بود: %s: %s", type(exc).__name__, exc)


# ---------------------------------------------------------------------------
# انقضای خودکار سفارش‌های بدون پرداخت (D7)
# ---------------------------------------------------------------------------

EXPIRY_ORDER_JOB_INTERVAL_SECONDS = 30 * 60  # هر ۳۰ دقیقه


async def expire_unpaid_orders_job(context):
    """
    سفارش‌های قدیمی‌تر از ۴۸ ساعت بدون پرداخت را به وضعیت «منقضی شده» تغییر می‌دهد.
    - هر ۳۰ دقیقه دوره‌ای اجرا می‌شود.
    - بررسی و تغییر وضعیت در یک تراکنش BEGIN IMMEDIATE (database.expire_unpaid_orders)
      انجام می‌شود، پس هم‌زمان با ثبت فیش/تأیید پرداخت secure است.
    - خطای یک سفارش بقیه را متوقف نمی‌کند.
    - پس از commit، برای هر سفارش منقضی‌شده پیام به مشتری ارسال می‌شود
      (کد پیگیری در پیام نمایش داده می‌شود).
    """
    try:
        result = expire_unpaid_orders(hours=EXPIRY_ORDER_MIN_AGE_HOURS)
    except Exception as exc:
        logger.error(
            "انقضای خودکار سفارش‌های نام پرداخت‌شده ناموفق بود: %s: %s",
            type(exc).__name__, exc,
        )
        return

    expired_ids = result.get("expired", [])
    for order_id in expired_ids:
        try:
            order = get_order(order_id)
            if order is None:
                continue
            tc = get_tracking_case_by_order(order_id)
            user = get_user(order["user_id"]) if order.get("user_id") else None
            tracking_code = tc["tracking_code"] if tc else str(order_id)
            chat_id = user["telegram_id"] if user else None
            if not chat_id:
                logger.warning(
                    "سفارش منقضی %s کاربر telegram_id ندارد؛ پیام ارسال نشد.",
                    order_id,
                )
                continue
            text = (
                f"⏰ مهلت پرداخت سفارش #{order_id} به پایان رسیده است.\n"
                f"📌 کد پیگیری: {tracking_code}\n"
                "اگر فیش واریز را ارسال کرده‌اید و هنوز تایید نشده، "
                "لطفاً با پشتیبانی تماس بگیرید."
            )
            await context.bot.send_message(chat_id=chat_id, text=text)
        except Exception as exc:
            logger.error(
                "ارسال پیام انقضا به مشتری برای سفارش %s ناموفق بود: %s: %s",
                order_id, type(exc).__name__, exc,
            )

    for order_id, msg in result.get("errors", []):
        logger.error(
            "انقضای سفارش %s ناموفق بود: %s", order_id, msg
        )

    if expired_ids:
        logger.info(
            "انقضای خودکار سفارش‌ها: %s سفارش منقضی شده — %s",
            len(expired_ids), ", ".join(str(i) for i in expired_ids),
        )
