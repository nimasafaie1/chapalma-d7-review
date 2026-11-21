import asyncio
import logging
import math
import os
import re
import tempfile
from datetime import datetime

import httpx
from telegram import (
    ReplyKeyboardMarkup,
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)
from telegram.error import BadRequest, NetworkError, RetryAfter
from telegram.ext import ContextTypes, ConversationHandler, CallbackQueryHandler

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# پیام یکنواخت برای خطاهای پیش‌بینی‌نشده
#
# هیچ traceback، نام فایل یا جزئیات داخلی نباید به کاربر نشان داده شود؛ فقط
# یک پیام کوتاه فارسی. جزئیات کامل در لاگ سرور می‌ماند.
# ---------------------------------------------------------------------------
UNEXPECTED_ERROR_MESSAGE = (
    "⚠️ خطایی در پردازش پیام شما رخ داد و این مرحله انجام نشد.\n\n"
    "لطفاً دوباره تلاش کنید؛ اگر مشکل تکرار شد به پشتیبانی اطلاع دهید."
)


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    error handler سراسری.

    هر استثنایی که از هندلرها بیرون بزند اینجا می‌آید، به‌جای اینکه بی‌صدا
    از دست برود یا متن فنی به کاربر نشان داده شود.

    کارها:
      • ثبت کامل خطا (با traceback) فقط در لاگ سرور،
      • ارسال یک پیام فارسی کوتاه و بدون جزئیات فنی به کاربر،
      • بازگرداندن وضعیت ConversationHandler به END تا گفتگوی ناقص جا نماند،
      • خودِ handler هرگز نباید استثنا بدهد.
    """
    error = getattr(context, "error", None)

    logger.error(
        "خطای مدیریت‌نشده در پردازش آپدیت: %s: %s",
        type(error).__name__ if error else "UnknownError",
        error,
        exc_info=error,
    )

    # عمداً user_data پاک نمی‌شود: ممکن است سبد یا اطلاعات سفارشِ در جریان
    # (مثلاً فیش پرداختِ در انتظار بررسی) آنجا باشد و از دست رفتنش اشتباه است.
    message = getattr(update, "effective_message", None)
    if message is None:
        callback = getattr(update, "callback_query", None)
        message = getattr(callback, "message", None) if callback else None

    if message is None:
        return

    try:
        await message.reply_text(UNEXPECTED_ERROR_MESSAGE)
    except Exception as exc:
        logger.error(
            "ارسال پیام خطا به کاربر ناموفق بود: %s: %s", type(exc).__name__, exc
        )


from states import (
    NAME,
    CHOOSING_GRADE,
    CHOOSING_CHAPTER,
    CHOOSING_COLOR,
    CHOOSING_NAZARI_GRADE,
    CHOOSING_NAZARI_BOOKLET,
    CHOOSING_ADD_MORE,
    ORDER_ENTRY,
    CHOOSING_DISCOUNT,
    WAITING_DISCOUNT_CODE,
    CHOOSING_DELIVERY,
    CHOOSING_DELIVERY_LOCATION,
    WAITING_ADDRESS,
    WAITING_PHONE,
    WAITING_RECEIPT,
    WAITING_FILE,
    CHOOSING_FILE_OPTION,
    CHOOSING_BINDING,
    CHOOSING_EXAM_PROVIDER,
    CHOOSING_EXAM_SUBJECT,
    CHOOSING_EXAM_GRADE,
    CHOOSING_EXAM_DATE,
    CHOOSING_EXAM_ACTION,
    CHOOSING_EXAM_ANSWER_INCLUDE,
    CHOOSING_EXAM_QUANTITY,
    WAITING_EXAM_QUANTITY_CUSTOM,
    CHOOSING_EXAM_MAZ_TYPE,
    CHOOSING_EXAM_MAZ_FIELD,
    CHOOSING_EXAM_MAZ_GRADE,
    CHOOSING_EXAM_KHEILI_GRADE,
    CHOOSING_EXAM_KHEILI_FIELD,
    ADMIN_EXAM_PROVIDER,
    ADMIN_EXAM_FIELD,
    ADMIN_EXAM_SUBJECT,
    ADMIN_EXAM_GRADE,
    ADMIN_EXAM_DATE,
    ADMIN_EXAM_QUESTION_FILE,
    ADMIN_EXAM_ANSWER_FILE,
    ADMIN_BOOKLET_TEACHER,
    ADMIN_BOOKLET_SUBJECT,
    ADMIN_BOOKLET_GRADE,
    ADMIN_BOOKLET_CHAPTER,
    ADMIN_BOOKLET_TITLE,
    ADMIN_BOOKLET_VERSIONS,
    CHOOSING_KONKUR_TYPE,
    CHOOSING_KONKUR_YEAR,
    CHOOSING_KONKUR_SESSION,
    CHOOSING_KONKUR_SUBJECT,
    CHOOSING_KONKUR_ACTION,
    CHOOSING_EXAM_FINAL_ARCHIVE,
    CHOOSING_EXAM_AHRAM_GRADE,
)
from database import (
    save_user,
    get_user,
    update_user_phone,
    save_order_with_items,
    save_payment,
    confirm_payment,
    get_payment_by_group_message,
    record_review_result,
    advance_order_to_next_stage,
    save_chapter_interest,
    get_discount_code,
    get_orders_by_user,
    get_uninotified_interest,
    mark_interest_notified,
    save_exam,
    get_unique_exam_dates,
    get_maz_exams_by_field,
    get_exam,
    get_final_exam_archive,
    get_konkur_exam,
    get_konkur_years,
    get_konkur_sessions,
    save_konkur_exam,
    update_konkur_question_file,
    update_konkur_answer_file,
    save_booklet,
    booklet_exists,
    get_booklets_by_teacher_grade_chapter,
    get_booklet_price,
    get_booklet_options,
    count_total_users,
    count_users_with_phone,
    count_total_orders,
    count_orders_by_status,
    count_orders_today,
    count_dau,
    count_mau,
    count_new_users,
    record_user_activity,
    get_local_date,
    _delivery_is_in_person,
    ORDER_STATUS_WAITING_PAYMENT,
    ORDER_STATUS_PAYMENT_CONFIRMED,
    ORDER_STATUS_READY_HANDOVER,
    ORDER_STATUS_PREPARING,
    ORDER_STATUS_HANDOVER_DONE,
    ORDER_STATUS_SHIPPED,
    ORDER_STATUS_EXPIRED,
    PAYMENT_STATUS_WAITING,
    PAYMENT_STATUS_CONFIRMED,
    PAYMENT_STATUS_WAITING_LOW_AMOUNT,
    PAYMENT_STATUS_WAITING_UNREADABLE,
    PAYMENT_STATUS_WAITING_INVALID,
    PAYMENT_STATUS_WAITING_HIGH_AMOUNT,
)
from prices import (
    CHAPTERS,
    get_jozve_price,
    format_price,
    get_custom_print_price,
    get_delivery_fee,
    get_exam_print_price_per_page,
    is_final_exam_provider,
    FINAL_EXAM_GRADE,
    FINAL_EXAM_ARCHIVE_BUTTON,
    get_exam_subjects,
    MAZ_SUBJECTS,
    EXAM_PROVIDERS,
    KONKUR_PROVIDER,
    KONKUR_TYPES,
    KONKUR_SUBJECTS,
    KONKUR_SESSIONS,
    get_konkur_session_value,
    get_konkur_session_label,
)
from file_utils import count_pages, PageCountError, MAX_FILE_SIZE_MB, MAX_FILE_SIZE_BYTES
from keyboards import (
    main_keyboard,
    grade_keyboard,
    grade_from_label,
    chapter_keyboard,
    chapter_from_label,
    color_keyboard,
    color_from_label,
    delivery_keyboard,
    delivery_location_keyboard,
    file_option_keyboard,
    file_option_from_label,
    teacher_from_label,
    nazari_booklet_keyboard,
    nazari_booklet_from_label,
    RESTART_BUTTON,
    BACK_BUTTON,
    restart_keyboard,
    CUSTOM_FILE_BUTTON,
    is_chapter_locked_label,
    add_more_keyboard,
    ADD_MORE_BUTTON,
    FINISH_ORDER_BUTTON,
    binding_keyboard,
    binding_from_label,
    discount_prompt_keyboard,
    HAVE_DISCOUNT_BUTTON,
    NO_DISCOUNT_BUTTON,
    EXAMS_BUTTON,
    exam_provider_keyboard,
    provider_from_label,
    provider_label,
    exam_subject_keyboard,
    subject_from_label,
    subject_label,
    exam_grade_keyboard,
    exam_grade_from_label,
    exam_date_keyboard,
    exam_date_from_label,
    exam_after_file_keyboard,
    PRINT_THIS_FILE_BUTTON,
    exam_answer_keyboard,
    WITH_ANSWER_BUTTON,
    ONLY_QUESTION_BUTTON,
    exam_quantity_keyboard,
    quantity_from_label,
    CUSTOM_QUANTITY_BUTTON,
    admin_skip_keyboard,
    ADMIN_SKIP_BUTTON,
    remove_keyboard,
    exam_maz_type_keyboard,
    exam_field_keyboard,
    exam_admin_field_keyboard,
    exam_maz_grade_keyboard,
    konkur_type_keyboard,
    konkur_type_from_label,
    konkur_year_keyboard,
    konkur_year_from_label,
    konkur_session_keyboard,
    konkur_subject_keyboard,
    konkur_subject_from_label,
    konkur_action_keyboard,
    konkur_action_from_label,
    KONKUR_PROVIDER_BUTTON,
    FINAL_EXAM_ARCHIVE_BUTTON,
    final_exam_archive_keyboard,
    final_exam_archive_from_label,
    _nav_rows,
)
from config import GROUP_ID, is_admin_user, is_owner_user


# ---------------------------------------------------------------------------
# کنترل دسترسی ادمین
#
# مجوز بر اساس Telegram user ID است (نه Chat ID گروه). حتی اگر دستور از داخل
# گروه مجاز ارسال شود، فقط user ID های موجود در ADMIN_IDS اجازه‌ی اجرا دارند.
# پیام خطا هیچ اطلاعات حساسی افشا نمی‌کند.
# ---------------------------------------------------------------------------

ADMIN_DENIED_MESSAGE = (
    "⛔️ این دستور فقط برای ادمین‌های ربات مجاز است."
)


async def _require_admin(update: Update) -> bool:
    """
    اگر کاربر ادمین نباشد پیام مناسب می‌دهد و False برمی‌گرداند.
    هیچ داده‌ای در این مسیر نمایش داده نمی‌شود.
    """
    user = update.effective_user
    if user is not None and is_admin_user(user.id):
        return True

    message = getattr(update, "effective_message", None)
    if message is not None:
        try:
            await message.reply_text(ADMIN_DENIED_MESSAGE)
        except Exception:
            pass
    return False


async def _require_owner(update: Update) -> bool:
    """
    اگر کاربر مالک ربات نباشد پیام مناسب می‌دهد و False برمی‌گرداند.
    هیچ داده‌ای در این مسیر نمایش داده نمی‌شود.
    """
    user = update.effective_user
    if user is not None and is_owner_user(user.id):
        return True

    message = getattr(update, "effective_message", None)
    if message is not None:
        try:
            await message.reply_text("⛔️ این دستور فقط برای مالک ربات مجاز است.")
        except Exception:
            pass
    return False


# ---------------------------------------------------------------------------
# ثبت‌نام
# ---------------------------------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    try:
        record_user_activity(user.id, activity_type="start")
    except Exception:
        pass

    old_user = get_user(user.id)

    if old_user:
        await update.message.reply_text(
            "👋 خوش آمدید.\n\n"
            "لطفاً نوع سفارش را انتخاب کنید:",
            reply_markup=main_keyboard()
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "👋 به ربات چاپ آلما خوش آمدید.\n\n"
        "لطفاً نام و نام خانوادگی خود را وارد کنید:"
    )

    return NAME


async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    full_name = update.message.text
    user = update.effective_user

    try:
        record_user_activity(user.id, activity_type="start")
    except Exception:
        pass
    save_user(user.id, user.username, full_name, None)

    await update.message.reply_text(
        f"✅ نام شما ثبت شد:\n{full_name}\n\n"
        "حالا می‌توانید سفارش خود را شروع کنید:",
        reply_markup=main_keyboard()
    )

    return ConversationHandler.END


async def restart_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    شروع دوباره از وسط گفتگوی سفارش.

    نکته‌ی مهم: این تابع از داخل order_conv صدا زده می‌شود. اگر کاربر هنوز
    ثبت‌نام نکرده باشد، start() مقدار NAME (حالت ۱) را برمی‌گرداند؛ ولی
    order_conv برای حالت ۱ هیچ هندلری ندارد. در نتیجه ConversationHandler
    وضعیت ۱ را برای order_conv ذخیره می‌کرد و کاربر برای همیشه گیر می‌کرد و
    دیگر به هیچ پیامی پاسخی نمی‌گرفت.

    بنابراین ثبت‌نام از این مسیر انجام نمی‌شود و کاربر به /start هدایت می‌گردد
    (مرحله‌ی NAME متعلق به registration_conv است، نه order_conv).
    """
    context.user_data.clear()

    user = update.effective_user
    if user is not None and not get_user(user.id):
        await _safe_reply_text(
            update,
            "برای ثبت‌نام، لطفاً یک‌بار پیام /start را بفرستید.",
        )
        return ConversationHandler.END

    return await start(update, context)


async def _handle_restart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = getattr(update, "message", None)
    text = getattr(message, "text", None)

    if text == RESTART_BUTTON:
        return await restart_order(update, context)

    return None


async def start_order_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user is not None:
        try:
            record_user_activity(user.id, activity_type="message")
        except Exception:
            pass

    restart_state = await _handle_restart(update, context)
    if restart_state is not None:
        return restart_state

    text = getattr(update.message, "text", None)

    if text == BACK_BUTTON:
        cart = _get_cart(context)
        if cart:
            return await _show_add_more_prompt(update, context)
        return ConversationHandler.END

    if text == CUSTOM_FILE_BUTTON:
        return await start_custom_file(update, context)

    if text == EXAMS_BUTTON:
        return await start_exam_browse(update, context)

    if teacher_from_label(text) is not None:
        return await choose_teacher(update, context)

    return ConversationHandler.END


def _item_line(item: dict) -> str:
    if item.get("type") == "custom":
        title = f"📎 {item.get('file_name')}"
        if item.get("binding") and item["binding"] != "بدون صحافی":
            title += f" ({item['binding']})"
    elif item.get("type") == "nazari":
        title = f"📙 {item.get('chapter')}"
    elif item.get("type") == "exam":
        title = f"📚 {item.get('teacher')} - {item.get('grade')} - {item.get('chapter')}"
    else:
        title = f"{item.get('teacher')} - {item.get('grade')} - {item.get('chapter')}"

    quantity = item.get("quantity", 1)
    if quantity and quantity > 1:
        title += f" × {quantity}"

    return f"• {title} — {format_price(item.get('price'))}"


async def _show_add_more_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE, prefix: str = ""):
    cart = _get_cart(context)
    total = sum(item.get("price") or 0 for item in cart)
    items_text = "\n".join(_item_line(item) for item in cart)

    await update.message.reply_text(
        f"{prefix}"
        f"🧾 سفارش فعلی شما:\n{items_text}\n\n"
        f"💰 جمع فعلی: {format_price(total)}\n\n"
        "می‌خوای جزوه دیگه‌ای هم اضافه کنی؟",
        reply_markup=add_more_keyboard()
    )

    return CHOOSING_ADD_MORE


async def _finish_item(update: Update, context: ContextTypes.DEFAULT_TYPE):
    order = context.user_data.pop("order")
    cart = context.user_data.setdefault("cart", [])
    cart.append(order)

    return await _show_add_more_prompt(
        update, context,
        prefix=f"✅ به سفارش اضافه شد:\n{_item_line(order)}\n\n"
    )


async def choose_add_more(update: Update, context: ContextTypes.DEFAULT_TYPE):
    restart_state = await _handle_restart(update, context)
    if restart_state is not None:
        return restart_state

    text = update.message.text
    cart = _get_cart(context)

    if text == BACK_BUTTON:
        if not cart:
            await update.message.reply_text("سبدت خالیه.", reply_markup=add_more_keyboard())
            return CHOOSING_ADD_MORE

        removed = cart.pop()

        if cart:
            return await _show_add_more_prompt(
                update, context,
                prefix=f"↩️ حذف شد از سفارش:\n{_item_line(removed)}\n\n"
            )

        await update.message.reply_text(
            f"↩️ حذف شد از سفارش:\n{_item_line(removed)}\n\n"
            "سبد خرید خالی شد. یه جزوه جدید انتخاب کن:",
            reply_markup=main_keyboard()
        )
        return ORDER_ENTRY

    if text == ADD_MORE_BUTTON:
        await update.message.reply_text(
            "📚 جزوه بعدی رو انتخاب کن:",
            reply_markup=main_keyboard()
        )
        return ORDER_ENTRY

    if text == FINISH_ORDER_BUTTON:
        total = sum(item.get("price") or 0 for item in cart)
        context.user_data["checkout"] = {
            "price": total, "base_price": total, "discount_amount": 0,
            "discount_code": None, "discount_percent": None, "discount_amount_value": None,
        }

        await update.message.reply_text(
            f"💰 جمع کل سفارش: {format_price(total)}\n\n"
            "روش دریافت سفارش را انتخاب کنید:",
            reply_markup=delivery_keyboard()
        )
        return CHOOSING_DELIVERY

    await update.message.reply_text("لطفاً یکی از گزینه‌های زیر را انتخاب کنید.")
    return CHOOSING_ADD_MORE


def _recompute_price(checkout: dict):
    base = checkout.get("base_price", 0) or 0
    fee = checkout.get("delivery_fee", 0) or 0
    percent = checkout.get("discount_percent")
    amount = checkout.get("discount_amount_value")
    if percent:
        discount = round(base * percent / 100)
    elif amount:
        discount = amount
    else:
        discount = 0
    discount = max(0, min(discount, base))
    checkout["discount_amount"] = discount
    checkout["price"] = max(0, base - discount + fee)


async def choose_discount_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    restart_state = await _handle_restart(update, context)
    if restart_state is not None:
        return restart_state

    text = update.message.text
    checkout = _get_user_dict(context, "checkout")
    if checkout is None:
        return await _conversation_expired(update, context, ORDER_ENTRY)

    if text == BACK_BUTTON:
        return await _show_add_more_prompt(update, context)

    if text == HAVE_DISCOUNT_BUTTON:
        await update.message.reply_text(
            "🎟️ کد تخفیف رو بفرست:",
            reply_markup=restart_keyboard()
        )
        return WAITING_DISCOUNT_CODE

    if text == NO_DISCOUNT_BUTTON:
        await update.message.reply_text(
            "روش دریافت سفارش را انتخاب کنید:",
            reply_markup=delivery_keyboard()
        )
        return CHOOSING_DELIVERY

    await update.message.reply_text("لطفاً یکی از گزینه‌های زیر را انتخاب کنید.")
    return CHOOSING_DISCOUNT


async def receive_discount_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    restart_state = await _handle_restart(update, context)
    if restart_state is not None:
        return restart_state

    text = update.message.text
    checkout = _get_user_dict(context, "checkout")
    if checkout is None:
        return await _conversation_expired(update, context, ORDER_ENTRY)

    if text == BACK_BUTTON:
        await update.message.reply_text(
            "کد تخفیف داری؟",
            reply_markup=discount_prompt_keyboard()
        )
        return CHOOSING_DISCOUNT

    if text == NO_DISCOUNT_BUTTON:
        checkout.pop("discount_code", None)
        checkout.pop("discount_percent", None)
        checkout.pop("discount_amount_value", None)
        checkout["discount_amount"] = 0
        _recompute_price(checkout)
        await update.message.reply_text(
            "روش دریافت سفارش را انتخاب کنید:",
            reply_markup=delivery_keyboard()
        )
        return CHOOSING_DELIVERY

    code = text.strip()
    from database import normalize_discount_code
    norm_code = normalize_discount_code(code)
    discount = get_discount_code(norm_code)

    if discount is None:
        await update.message.reply_text(
            "❌ این کد تخفیف معتبر نیست یا منقضی شده.\n"
            "می‌تونی دوباره یه کد بفرستی، یا دکمه‌ی زیر رو بزن:",
            reply_markup=discount_prompt_keyboard()
        )
        return WAITING_DISCOUNT_CODE

    checkout["discount_code"] = norm_code
    checkout["discount_percent"] = discount.get("percent")
    checkout["discount_amount_value"] = discount.get("amount")
    _recompute_price(checkout)

    await update.message.reply_text(
        f"✅ کد تخفیف اعمال شد: {format_price(checkout.get('discount_amount', 0))} تخفیف\n"
        f"💰 مبلغ جدید: {format_price(checkout['price'])}\n\n"
        "روش دریافت سفارش را انتخاب کنید:",
        reply_markup=delivery_keyboard()
    )
    return CHOOSING_DELIVERY


# ---------------------------------------------------------------------------
# مسیر جزوه‌های آماده (استاد امامی / کوشکی / نظری)
# ---------------------------------------------------------------------------

async def choose_teacher(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    restart_state = await _handle_restart(update, context)
    if restart_state is not None:
        return restart_state

    teacher = teacher_from_label(text)

    if teacher is None:
        await update.message.reply_text(
            "لطفاً از دکمه‌های زیر انتخاب کنید.",
            reply_markup=main_keyboard()
        )
        return ConversationHandler.END

    context.user_data["order"] = {"type": "jozve", "teacher": teacher}

    if teacher == "نظری":
        await update.message.reply_text(
            "📚 جزوه استاد نظری\n\nلطفاً پایه تحصیلی را انتخاب کنید:",
            reply_markup=grade_keyboard()
        )
        return CHOOSING_NAZARI_GRADE

    await update.message.reply_text(
        f"📚 جزوه استاد {teacher}\n\nلطفاً پایه را انتخاب کنید:",
        reply_markup=grade_keyboard()
    )

    return CHOOSING_GRADE


async def choose_grade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    restart_state = await _handle_restart(update, context)
    if restart_state is not None:
        return restart_state

    text = update.message.text

    if text == BACK_BUTTON:
        await update.message.reply_text(
            "📚 نوع جزوه رو انتخاب کن:",
            reply_markup=main_keyboard()
        )
        return ORDER_ENTRY

    grade = grade_from_label(text)

    if grade is None:
        await update.message.reply_text("لطفاً پایه را از دکمه‌های زیر انتخاب کنید.")
        return CHOOSING_GRADE

    order = _get_user_dict(context, "order")
    if order is None:
        return await _conversation_expired(update, context, ORDER_ENTRY)

    order["grade"] = grade
    teacher = order["teacher"]

    await update.message.reply_text(
        "📚 فصل را انتخاب کنید:",
        reply_markup=chapter_keyboard(grade, teacher)
    )

    return CHOOSING_CHAPTER


async def choose_nazari_grade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    restart_state = await _handle_restart(update, context)
    if restart_state is not None:
        return restart_state

    text = update.message.text

    if text == BACK_BUTTON:
        await update.message.reply_text(
            "📚 نوع جزوه رو انتخاب کن:",
            reply_markup=main_keyboard()
        )
        return ORDER_ENTRY

    grade = grade_from_label(text)

    if grade is None:
        await update.message.reply_text("لطفاً پایه را از دکمه‌های زیر انتخاب کنید.")
        return CHOOSING_NAZARI_GRADE

    order = _get_user_dict(context, "order")
    if order is None:
        return await _conversation_expired(update, context, ORDER_ENTRY)

    order["grade"] = grade

    await update.message.reply_text(
        "📚 جزوه استاد نظری\n\nلطفاً یکی از جزوه‌های زیر را انتخاب کنید:",
        reply_markup=nazari_booklet_keyboard(grade)
    )
    return CHOOSING_NAZARI_BOOKLET


async def choose_nazari_booklet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    restart_state = await _handle_restart(update, context)
    if restart_state is not None:
        return restart_state

    text = update.message.text

    if text == BACK_BUTTON:
        await update.message.reply_text(
            "📚 جزوه استاد نظری\n\nلطفاً پایه تحصیلی را انتخاب کنید:",
            reply_markup=grade_keyboard()
        )
        return CHOOSING_NAZARI_GRADE

    order = _get_user_dict(context, "order")
    if order is None:
        return await _conversation_expired(update, context, ORDER_ENTRY)
    
    grade = order.get("grade")
    if not grade:
        await update.message.reply_text(
            "📚 جزوه استاد نظری\n\nلطفاً پایه تحصیلی را انتخاب کنید:",
            reply_markup=grade_keyboard()
        )
        return CHOOSING_NAZARI_GRADE

    result = nazari_booklet_from_label(text, grade)

    if result is None:
        # Check if it's the "no booklets" message
        if text == "❌ برای این پایه هنوز جزوه‌ای ثبت نشده است":
            await update.message.reply_text(
                "📚 جزوه استاد نظری\n\nلطفاً پایه تحصیلی را انتخاب کنید:",
                reply_markup=grade_keyboard()
            )
            return CHOOSING_NAZARI_GRADE
        await update.message.reply_text("لطفاً یکی از گزینه‌های زیر را انتخاب کنید.")
        return CHOOSING_NAZARI_BOOKLET

    booklet_name, price = result
    if price is None:
        await update.message.reply_text("قیمت برای این جزوه تنظیم نشده است. لطفاً با ادمین تماس بگیرید.")
        return CHOOSING_NAZARI_BOOKLET

    order["type"] = "nazari"
    order["chapter"] = booklet_name
    order["print_type"] = "سیاه‌وسفید"
    order["price"] = price

    return await _finish_item(update, context)


async def choose_chapter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    restart_state = await _handle_restart(update, context)
    if restart_state is not None:
        return restart_state

    order = _get_user_dict(context, "order")
    if order is None:
        return await _conversation_expired(update, context, ORDER_ENTRY)

    grade = order.get("grade")
    teacher = order.get("teacher")
    if not grade or not teacher:
        return await _conversation_expired(update, context, ORDER_ENTRY)

    text = update.message.text

    if text == BACK_BUTTON:
        await update.message.reply_text(
            "پایه رو انتخاب کن:",
            reply_markup=grade_keyboard()
        )
        return CHOOSING_GRADE

    chapter = chapter_from_label(text, grade)

    if chapter is None:
        await update.message.reply_text("لطفاً فصل را از دکمه‌های زیر انتخاب کنید.")
        return CHOOSING_CHAPTER

    if is_chapter_locked_label(text, grade):
        save_chapter_interest(update.effective_user.id, teacher, grade, chapter)
        await update.message.reply_text(
            "😔 این جزوه هنوز آماده نشده و به‌زودی اضافه می‌شود.\n"
            "به‌محض اینکه آماده بشه بهت خبر می‌دیم. 🔔\n\n"
            "لطفاً یکی از فصل‌های موجود رو انتخاب کن:",
            reply_markup=chapter_keyboard(grade, teacher)
        )
        return CHOOSING_CHAPTER

    order["chapter"] = chapter

    price_color = get_jozve_price(teacher, grade, chapter, "رنگی")
    price_bw = get_jozve_price(teacher, grade, chapter, "سیاه‌وسفید")

    await update.message.reply_text(
        "نوع چاپ را انتخاب کنید:",
        reply_markup=color_keyboard(price_color, price_bw)
    )

    return CHOOSING_COLOR


async def choose_color(update: Update, context: ContextTypes.DEFAULT_TYPE):
    restart_state = await _handle_restart(update, context)
    if restart_state is not None:
        return restart_state

    text = update.message.text
    order = _get_user_dict(context, "order")
    if order is None or not order.get("grade") or not order.get("teacher"):
        return await _conversation_expired(update, context, ORDER_ENTRY)

    if text == BACK_BUTTON:
        await update.message.reply_text(
            "فصل را انتخاب کنید:",
            reply_markup=chapter_keyboard(order["grade"], order["teacher"])
        )
        return CHOOSING_CHAPTER

    color = color_from_label(text)

    if color is None:
        await update.message.reply_text("لطفاً یکی از گزینه‌های زیر را انتخاب کنید.")
        return CHOOSING_COLOR

    order["print_type"] = color
    price = get_jozve_price(order["teacher"], order["grade"], order["chapter"], color)
    if price is None:
        await update.message.reply_text(
            "قیمت این مورد هنوز ثبت نشده، با ادمین هماهنگ کنید.",
            reply_markup=chapter_keyboard(order["grade"], order["teacher"])
        )
        return CHOOSING_CHAPTER
    order["price"] = price

    return await _finish_item(update, context)


# ================================================================
# 📚 مرور آزمون‌ها (قلمچی / ماز / امتحان نهایی)
# ================================================================

async def start_exam_browse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["exam_browse"] = {}

    await update.message.reply_text(
        "📚 آزمون‌ها\n\nمؤسسه رو انتخاب کن:",
        reply_markup=exam_provider_keyboard()
    )
    return CHOOSING_EXAM_PROVIDER


async def choose_exam_provider(update: Update, context: ContextTypes.DEFAULT_TYPE):
    restart_state = await _handle_restart(update, context)
    if restart_state is not None:
        return restart_state

    text = update.message.text

    if text == BACK_BUTTON:
        await update.message.reply_text(
            "📚 نوع جزوه رو انتخاب کن:",
            reply_markup=main_keyboard()
        )
        return ORDER_ENTRY

    # دکمه‌های ویژه (کنکور سراسری و آرشیو امتحان نهایی) جزو EXAM_PROVIDERS
    # نیستند، پس باید قبل از اعتبارسنجی مؤسسه بررسی شوند.
    if text == KONKUR_PROVIDER_BUTTON:
        context.user_data["konkur"] = {}
        await update.message.reply_text(
            "نوع کنکور را انتخاب کنید:",
            reply_markup=konkur_type_keyboard()
        )
        return CHOOSING_KONKUR_TYPE

    if text == FINAL_EXAM_ARCHIVE_BUTTON:
        await update.message.reply_text(
            "درس آرشیو جامع امتحان نهایی را انتخاب کنید:",
            reply_markup=final_exam_archive_keyboard()
        )
        return CHOOSING_EXAM_FINAL_ARCHIVE

    provider = provider_from_label(text)

    if provider is None:
        clean_text = re.sub(r'[^\w\s]', '', text).strip()
        for p in EXAM_PROVIDERS:
            if clean_text == p:
                provider = p
                break

    if provider is None:
        await update.message.reply_text(
            "لطفاً یکی از گزینه‌های زیر را انتخاب کنید.",
            reply_markup=exam_provider_keyboard()
        )
        return CHOOSING_EXAM_PROVIDER

    browse = _get_user_dict(context, "exam_browse")
    if browse is None:
        return await _conversation_expired(update, context, ORDER_ENTRY)

    browse["provider"] = provider

    # اگر کاربر مؤسسه‌ای غیر از کنکور را انتخاب کرد، داده‌های نیمه‌کاره‌ی کنکور
    # پاک می‌شود تا «داخلی/خارجی» به مسیرهای دیگر نشت نکند.
    context.user_data.pop("konkur", None)

    if provider == "ماز":
        await update.message.reply_text(
            "📚 نوع آزمون ماز را انتخاب کنید:",
            reply_markup=exam_maz_type_keyboard()
        )
        return CHOOSING_EXAM_MAZ_TYPE

    if provider == "خیلی سبز":
        await update.message.reply_text(
            "📚 پایه آزمون خیلی سبز را انتخاب کنید:",
            reply_markup=exam_grade_keyboard()
        )
        return CHOOSING_EXAM_KHEILI_GRADE

    if provider == "آرمان":
        await update.message.reply_text(
            "📚 پایه آزمون آرمان را انتخاب کنید:",
            reply_markup=exam_grade_keyboard()
        )
        return CHOOSING_EXAM_AHRAM_GRADE

    await update.message.reply_text(
        "درس رو انتخاب کن:",
        reply_markup=exam_subject_keyboard(provider)
    )
    return CHOOSING_EXAM_SUBJECT


async def choose_exam_subject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    restart_state = await _handle_restart(update, context)
    if restart_state is not None:
        return restart_state

    text = update.message.text
    browse = _get_user_dict(context, "exam_browse")
    if not browse:
        await update.message.reply_text(
            "لطفاً دوباره از منوی آزمون‌ها شروع کنید.",
            reply_markup=main_keyboard()
        )
        return ORDER_ENTRY

    provider = browse["provider"]

    if provider == "ماز":
        await update.message.reply_text(
            "لطفاً مسیر ماز را از ابتدا طی کنید.",
            reply_markup=exam_provider_keyboard()
        )
        return CHOOSING_EXAM_PROVIDER

    if text == BACK_BUTTON:
        await update.message.reply_text(
            "مؤسسه رو انتخاب کن:",
            reply_markup=exam_provider_keyboard()
        )
        return CHOOSING_EXAM_PROVIDER

    subject = subject_from_label(text, provider)
    if subject is None:
        await update.message.reply_text(
            "لطفاً یکی از گزینه‌های زیر را انتخاب کنید.",
            reply_markup=exam_subject_keyboard(provider)
        )
        return CHOOSING_EXAM_SUBJECT

    browse["subject"] = subject

    if is_final_exam_provider(provider):
        return await _load_exam_dates(update, context, grade=FINAL_EXAM_GRADE)

    await update.message.reply_text(
        "پایه رو انتخاب کن:",
        reply_markup=exam_grade_keyboard()
    )
    return CHOOSING_EXAM_GRADE


async def choose_exam_grade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    restart_state = await _handle_restart(update, context)
    if restart_state is not None:
        return restart_state

    text = update.message.text
    browse = _get_user_dict(context, "exam_browse")
    if not browse:
        await update.message.reply_text(
            "لطفاً دوباره از منوی آزمون‌ها شروع کنید.",
            reply_markup=main_keyboard()
        )
        return ORDER_ENTRY

    provider = browse.get("provider")

    if provider == "ماز":
        await update.message.reply_text(
            "لطفاً مسیر ماز را از ابتدا طی کنید.",
            reply_markup=exam_provider_keyboard()
        )
        return CHOOSING_EXAM_PROVIDER

    if text == BACK_BUTTON:
        await update.message.reply_text(
            "درس رو انتخاب کن:",
            reply_markup=exam_subject_keyboard(provider)
        )
        return CHOOSING_EXAM_SUBJECT

    grade = exam_grade_from_label(text)

    if grade is None:
        await update.message.reply_text("لطفاً یکی از گزینه‌های زیر را انتخاب کنید.")
        return CHOOSING_EXAM_GRADE

    return await _load_exam_dates(update, context, grade=grade)


async def _load_exam_dates(update: Update, context: ContextTypes.DEFAULT_TYPE, grade: str):
    browse = _get_user_dict(context, "exam_browse")
    if not browse:
        await update.message.reply_text(
            "لطفاً دوباره از منوی آزمون‌ها شروع کنید.",
            reply_markup=main_keyboard()
        )
        return ORDER_ENTRY

    browse["grade"] = grade
    
    provider = browse["provider"]
    
    if provider == "امتحان نهایی":
        db_provider = "نهایی"
    else:
        db_provider = provider
    
    subject = None if provider == "آرمان" else browse.get("subject")
    maz_type = browse.get("maz_type")
    field = browse.get("field")

    if provider == "ماز" and subject:
        if subject.startswith("آزمون جامع"):
            subject = "آزمون جامع"
        else:
            for g in ["دهم", "یازدهم", "دوازدهم"]:
                if subject.endswith(f" {g}"):
                    subject = subject.replace(f" {g}", "")
                    break

    if provider == "ماز" and maz_type == "doping" and field:
        exam_rows = get_maz_exams_by_field(field, grade)
    else:
        exam_rows = get_unique_exam_dates(db_provider, subject, grade)
    
    if not exam_rows:
        if provider == "ماز":
            await update.message.reply_text(
                "😔 هنوز آزمونی برای این ترکیب ثبت نشده.\n"
                "لطفاً یه گزینه‌ی دیگه رو امتحان کن:",
                reply_markup=exam_maz_grade_keyboard()
            )
            return CHOOSING_EXAM_MAZ_GRADE

        elif provider == "خیلی سبز":
            await update.message.reply_text(
                "😔 هنوز آزمونی برای این ترکیب ثبت نشده.\n"
                "لطفاً یه گزینه‌ی دیگه رو امتحان کن:",
                reply_markup=exam_subject_keyboard("خیلی سبز")
            )
            return CHOOSING_EXAM_KHEILI_FIELD

        elif is_final_exam_provider(provider):
            back_keyboard = exam_subject_keyboard(provider)
            back_msg = "درس رو انتخاب کن:"
            back_state = CHOOSING_EXAM_SUBJECT
        elif provider == "آرمان":
            back_keyboard = exam_grade_keyboard()
            back_msg = "پایه آزمون آرمان را انتخاب کنید:"
            back_state = CHOOSING_EXAM_AHRAM_GRADE
        else:
            back_keyboard = exam_grade_keyboard()
            back_msg = "پایه رو انتخاب کن:"
            back_state = CHOOSING_EXAM_GRADE
        
        await update.message.reply_text(
            "😔 هنوز آزمونی برای این ترکیب ثبت نشده.\n"
            "لطفاً یه گزینه‌ی دیگه رو امتحان کن:",
            reply_markup=back_keyboard
        )
        return back_state
    
    browse["exam_rows"] = exam_rows
    
    await update.message.reply_text(
        "📅 تاریخ آزمون رو انتخاب کن:",
        reply_markup=exam_date_keyboard(exam_rows)
    )
    return CHOOSING_EXAM_DATE


async def choose_exam_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    restart_state = await _handle_restart(update, context)
    if restart_state is not None:
        return restart_state

    text = update.message.text
    browse = _get_user_dict(context, "exam_browse")
    if not browse:
        await update.message.reply_text(
            "لطفاً دوباره از منوی آزمون‌ها شروع کنید.",
            reply_markup=main_keyboard()
        )
        return ORDER_ENTRY

    if text == BACK_BUTTON:
        provider = browse.get("provider")

        if provider == "آرمان":
            await update.message.reply_text(
                "پایه آزمون آرمان را انتخاب کنید:",
                reply_markup=exam_grade_keyboard()
            )
            return CHOOSING_EXAM_AHRAM_GRADE
        
        if provider == "ماز":
            state, msg, keyboard = _exam_back_target_before_date(browse)
            await update.message.reply_text(msg, reply_markup=keyboard)
            return state
        
        if provider == "خیلی سبز":
            await update.message.reply_text(
                "پایه رو انتخاب کن:",
                reply_markup=exam_grade_keyboard()
            )
            return CHOOSING_EXAM_KHEILI_GRADE
        
        grade = browse.get("grade")
        if is_final_exam_provider(provider):
            await update.message.reply_text(
                "درس رو انتخاب کن:",
                reply_markup=exam_subject_keyboard(provider)
            )
            return CHOOSING_EXAM_SUBJECT
        
        await update.message.reply_text(
            "پایه رو انتخاب کن:",
            reply_markup=exam_grade_keyboard()
        )
        return CHOOSING_EXAM_GRADE

    exam_id = exam_date_from_label(text, browse["exam_rows"])

    if exam_id is None:
        await update.message.reply_text(
            "لطفاً یکی از گزینه‌های زیر را انتخاب کنید.",
            reply_markup=exam_date_keyboard(browse["exam_rows"])
        )
        return CHOOSING_EXAM_DATE

    exam = get_exam(exam_id)
    browse["exam"] = exam

    if exam.get("question_file_id"):
        sent = await _safe_send_document(
            context.bot,
            chat_id=update.effective_chat.id,
            document=exam["question_file_id"],
            caption=f"📄 دفترچه سؤال — {exam['provider']} {exam['exam_date']}",
        )
        if not sent:
            await _safe_reply_text(update, FILE_SEND_FAILED_MESSAGE)

    if exam.get("answer_file_id"):
        sent = await _safe_send_document(
            context.bot,
            chat_id=update.effective_chat.id,
            document=exam["answer_file_id"],
            caption=f"📝 پاسخنامه — {exam['provider']} {exam['exam_date']}",
        )
        if not sent:
            await _safe_reply_text(update, FILE_SEND_FAILED_MESSAGE)

    await update.message.reply_text(
        "اگه می‌خوای همین آزمون رو چاپ کنیم، دکمه‌ی زیر رو بزن:",
        reply_markup=exam_after_file_keyboard()
    )
    return CHOOSING_EXAM_ACTION


def _exam_back_target_before_date(browse: dict):
    provider = browse.get("provider")
    if provider == "آرمان":
        return CHOOSING_EXAM_AHRAM_GRADE, "پایه آزمون آرمان را انتخاب کنید:", exam_grade_keyboard()

    
    if provider == "ماز":
        maz_type = browse.get("maz_type")
        if maz_type in ("doping", "jame"):
            return CHOOSING_EXAM_MAZ_GRADE, "پایه رو انتخاب کن:", exam_maz_grade_keyboard()
        else:
            return CHOOSING_EXAM_MAZ_TYPE, "نوع ماز رو انتخاب کن:", exam_maz_type_keyboard()
    
    if is_final_exam_provider(provider):
        return CHOOSING_EXAM_SUBJECT, "درس رو انتخاب کن:", exam_subject_keyboard(provider)
    
    return CHOOSING_EXAM_GRADE, "پایه رو انتخاب کن:", exam_grade_keyboard()


async def choose_exam_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    restart_state = await _handle_restart(update, context)
    if restart_state is not None:
        return restart_state

    text = update.message.text
    browse = _get_user_dict(context, "exam_browse")
    if not browse:
        await update.message.reply_text(
            "لطفاً دوباره از منوی آزمون‌ها شروع کنید.",
            reply_markup=main_keyboard()
        )
        return ORDER_ENTRY

    exam = browse.get("exam")
    if not exam:
        await update.message.reply_text(
            "لطفاً ابتدا یک تاریخ آزمون انتخاب کنید.",
            reply_markup=exam_date_keyboard(browse.get("exam_rows", []))
        )
        return CHOOSING_EXAM_DATE

    if text == BACK_BUTTON:
        await update.message.reply_text(
            "📅 تاریخ آزمون رو انتخاب کن:",
            reply_markup=exam_date_keyboard(browse["exam_rows"])
        )
        return CHOOSING_EXAM_DATE

    if text == PRINT_THIS_FILE_BUTTON:
        if not _exam_question_pages_ready(exam):
            await update.message.reply_text(
                EXAM_PAGES_MISSING_MESSAGE,
                reply_markup=exam_after_file_keyboard()
            )
            return CHOOSING_EXAM_ACTION

        if exam.get("answer_file_id"):
            await update.message.reply_text(
                "آیا پاسخنامه هم چاپ شود؟",
                reply_markup=exam_answer_keyboard()
            )
            return CHOOSING_EXAM_ANSWER_INCLUDE

        browse["answer_include"] = False
        await update.message.reply_text(
            "تعداد نسخه؟",
            reply_markup=exam_quantity_keyboard()
        )
        return CHOOSING_EXAM_QUANTITY

    await update.message.reply_text("لطفاً یکی از گزینه‌های زیر را انتخاب کنید.")
    return CHOOSING_EXAM_ACTION


async def choose_exam_answer_include(update: Update, context: ContextTypes.DEFAULT_TYPE):
    restart_state = await _handle_restart(update, context)
    if restart_state is not None:
        return restart_state

    text = update.message.text
    browse = _get_user_dict(context, "exam_browse")
    if not browse:
        await update.message.reply_text(
            "لطفاً دوباره از منوی آزمون‌ها شروع کنید.",
            reply_markup=main_keyboard()
        )
        return ORDER_ENTRY

    if text == BACK_BUTTON:
        await update.message.reply_text(
            "اگه می‌خوای همین آزمون رو چاپ کنیم، دکمه‌ی زیر رو بزن:",
            reply_markup=exam_after_file_keyboard()
        )
        return CHOOSING_EXAM_ACTION

    if text == WITH_ANSWER_BUTTON:
        browse["answer_include"] = True
    elif text == ONLY_QUESTION_BUTTON:
        browse["answer_include"] = False
    else:
        await update.message.reply_text("لطفاً یکی از گزینه‌های زیر را انتخاب کنید.")
        return CHOOSING_EXAM_ANSWER_INCLUDE

    blocker = _exam_cart_blocker(browse)

    if blocker:
        browse["answer_include"] = False
        await update.message.reply_text(
            blocker,
            reply_markup=exam_answer_keyboard()
        )
        return CHOOSING_EXAM_ANSWER_INCLUDE

    await update.message.reply_text(
        "تعداد نسخه؟",
        reply_markup=exam_quantity_keyboard()
    )
    return CHOOSING_EXAM_QUANTITY


EXAM_PAGES_MISSING_MESSAGE = (
    "⚠️ تعداد صفحات دفترچه سؤال این آزمون هنوز در سامانه ثبت نشده است، "
    "بنابراین قیمت‌گذاری و سفارش چاپ آن ممکن نیست.\n"
    "لطفاً آزمون دیگری انتخاب کنید یا بعداً دوباره تلاش کنید."
)

EXAM_ANSWER_PAGES_MISSING_MESSAGE = (
    "⚠️ تعداد صفحات پاسخنامه‌ی این آزمون هنوز ثبت نشده، بنابراین سفارش «همراه پاسخنامه» ممکن نیست.\n"
    "اگر فقط دفترچه سؤال را می‌خواهید، گزینه‌ی «فقط دفترچه سؤال» را بزنید."
)


def _positive_int(value) -> bool:
    try:
        return int(value) > 0
    except (TypeError, ValueError):
        return False


def _exam_question_pages_ready(exam: dict) -> bool:
    return _positive_int(exam.get("question_pages"))


def _exam_answer_pages_ready(exam: dict) -> bool:
    if not exam.get("answer_file_id"):
        return False
    return _positive_int(exam.get("answer_pages"))


def _exam_cart_blocker(browse: dict):
    """
    اگر آزمون انتخاب‌شده صفحه‌ی سؤال یا پاسخنامه‌ی قابل اتکا نداشته باشد، دلیلش را
    برمی‌گرداند تا آیتمی با قیمت ۰ (یا چاپ ۰ صفحه) وارد سبد نشود.
    خروجی: متن خطا یا None
    """
    exam = browse.get("exam")
    if not exam:
        return None
    if not _exam_question_pages_ready(exam):
        return EXAM_PAGES_MISSING_MESSAGE
    if browse.get("answer_include", False) and not _exam_answer_pages_ready(exam):
        return EXAM_ANSWER_PAGES_MISSING_MESSAGE
    return None


class ExamPagesNotReady(ValueError):
    """
    وقتی تعداد صفحات دفترچه سؤال (یا پاسخنامه، در صورت درخواست) برای آزمون
    انتخاب‌شده ثبت نشده باشد، این خطا پرتاب می‌شود.

    این یک «محافظ نهایی» است: حتی اگر مسیری در آینده فراموش کند قبل از
    ساخت آیتم، صفحه‌ها را چک کند، آیتمی با قیمت ۰ وارد سبد نمی‌شود.
    """

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def _build_exam_item(browse: dict, quantity: int) -> dict:
    """
    ساخت آیتم سبد از آزمون انتخاب‌شده.

    محافظ قطعی: اگر question_pages ثبت نشده/صفر/منفی باشد، یا اگر پاسخنامه
    خواسته شده باشد ولی answer_pages معتبر نباشد، این تابع اجازه‌ی ساخت آیتم
    نمی‌دهد و ExamPagesNotReady پرتاب می‌کند. بنابراین قیمت صفر یا قیمت
    ناقص هرگز وارد سبد خرید نمی‌شود.
    """
    exam = browse.get("exam")
    if not exam:
        raise ExamPagesNotReady(EXAM_PAGES_MISSING_MESSAGE)

    answer_include = browse.get("answer_include", False)

    # --- محافظ ۱: دفترچه سؤال حتماً باید تعداد صفحه‌ی معتبر داشته باشد ---
    if not _exam_question_pages_ready(exam):
        raise ExamPagesNotReady(EXAM_PAGES_MISSING_MESSAGE)

    # --- محافظ ۲: اگر پاسخنامه هم خواسته شده، صفحاتش هم باید معتبر باشد ---
    if answer_include and not _exam_answer_pages_ready(exam):
        raise ExamPagesNotReady(EXAM_ANSWER_PAGES_MISSING_MESSAGE)

    side = "پشت‌ورو"

    question_pages = exam.get("question_pages") or 0

    answer_pages = 0
    if answer_include and exam.get("answer_pages"):
        answer_pages = exam["answer_pages"]

    pages = question_pages + answer_pages

    per_page = get_exam_print_price_per_page(side)
    units = math.ceil(question_pages / 2) + math.ceil(answer_pages / 2)
    price = per_page * units * quantity

    chapter = f"{exam['subject']} - {exam['exam_date']}"
    if answer_include:
        chapter += " + پاسخنامه"

    return {
        "type": "exam",
        "teacher": exam["provider"],
        "grade": exam["grade"],
        "chapter": chapter,
        "print_type": f"سیاه‌وسفید - {side}",
        "price": price,
        "pages": pages,
        "quantity": quantity,
        "exam_id": exam["id"],
    }


async def choose_exam_quantity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    restart_state = await _handle_restart(update, context)
    if restart_state is not None:
        return restart_state

    text = update.message.text
    browse = _get_user_dict(context, "exam_browse")
    if not browse:
        await update.message.reply_text(
            "لطفاً دوباره از منوی آزمون‌ها شروع کنید.",
            reply_markup=main_keyboard()
        )
        return ORDER_ENTRY

    exam = browse.get("exam")
    if not exam:
        await update.message.reply_text(
            "لطفاً ابتدا یک تاریخ آزمون انتخاب کنید.",
            reply_markup=exam_date_keyboard(browse.get("exam_rows", []))
        )
        return CHOOSING_EXAM_DATE

    if text == BACK_BUTTON:
        if browse["exam"].get("answer_file_id"):
            await update.message.reply_text(
                "آیا پاسخنامه هم چاپ شود؟",
                reply_markup=exam_answer_keyboard()
            )
            return CHOOSING_EXAM_ANSWER_INCLUDE

        await update.message.reply_text(
            "اگه می‌خوای همین آزمون رو چاپ کنیم، دکمه‌ی زیر رو بزن:",
            reply_markup=exam_after_file_keyboard()
        )
        return CHOOSING_EXAM_ACTION

    if text == CUSTOM_QUANTITY_BUTTON:
        await update.message.reply_text(
            "تعداد نسخه مورد نظر رو به‌صورت عدد بفرست:",
            reply_markup=restart_keyboard()
        )
        return WAITING_EXAM_QUANTITY_CUSTOM

    quantity = quantity_from_label(text)

    if quantity is None:
        await update.message.reply_text(
            "لطفاً یکی از گزینه‌های زیر را انتخاب کنید.",
            reply_markup=exam_quantity_keyboard()
        )
        return CHOOSING_EXAM_QUANTITY

    blocker = _exam_cart_blocker(browse)

    if blocker:
        await update.message.reply_text(
            blocker,
            reply_markup=exam_date_keyboard(browse.get("exam_rows", []))
        )
        return CHOOSING_EXAM_DATE

    try:
        item = _build_exam_item(browse, quantity)
    except ExamPagesNotReady as exc:
        await update.message.reply_text(
            exc.message,
            reply_markup=exam_date_keyboard(browse.get("exam_rows", []))
        )
        return CHOOSING_EXAM_DATE

    context.user_data["order"] = item
    context.user_data.pop("exam_browse", None)

    return await _finish_item(update, context)


async def receive_exam_quantity_custom(update: Update, context: ContextTypes.DEFAULT_TYPE):
    restart_state = await _handle_restart(update, context)
    if restart_state is not None:
        return restart_state

    text = update.message.text

    if text == BACK_BUTTON:
        await update.message.reply_text(
            "تعداد نسخه؟",
            reply_markup=exam_quantity_keyboard()
        )
        return CHOOSING_EXAM_QUANTITY

    if not text.strip().isdigit():
        await update.message.reply_text(
            "لطفاً فقط یه عدد بفرست (مثلاً 15).",
            reply_markup=restart_keyboard()
        )
        return WAITING_EXAM_QUANTITY_CUSTOM

    quantity = int(text.strip())

    if quantity < 1 or quantity > 500:
        await update.message.reply_text(
            "عدد باید بین ۱ تا ۵۰۰ باشه. دوباره بفرست:",
            reply_markup=restart_keyboard()
        )
        return WAITING_EXAM_QUANTITY_CUSTOM

    browse = _get_user_dict(context, "exam_browse")
    if not browse:
        await update.message.reply_text(
            "لطفاً دوباره از منوی آزمون‌ها شروع کنید.",
            reply_markup=main_keyboard()
        )
        return ORDER_ENTRY

    blocker = _exam_cart_blocker(browse)

    if blocker:
        await update.message.reply_text(
            blocker,
            reply_markup=exam_date_keyboard(browse.get("exam_rows", []))
        )
        return CHOOSING_EXAM_DATE

    try:
        item = _build_exam_item(browse, quantity)
    except ExamPagesNotReady as exc:
        await update.message.reply_text(
            exc.message,
            reply_markup=exam_date_keyboard(browse.get("exam_rows", []))
        )
        return CHOOSING_EXAM_DATE

    context.user_data["order"] = item
    context.user_data.pop("exam_browse", None)

    return await _finish_item(update, context)


# ================================================================
# 📚 مراحل ماز (دوپینگ و جامع)
# ================================================================

async def choose_exam_maz_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    restart_state = await _handle_restart(update, context)
    if restart_state is not None:
        return restart_state

    text = update.message.text

    if text == BACK_BUTTON:
        await update.message.reply_text(
            "مؤسسه رو انتخاب کن:",
            reply_markup=exam_provider_keyboard()
        )
        return CHOOSING_EXAM_PROVIDER

    browse = _get_user_dict(context, "exam_browse")
    if not browse:
        await update.message.reply_text(
            "لطفاً دوباره از منوی آزمون‌ها شروع کنید.",
            reply_markup=main_keyboard()
        )
        return ORDER_ENTRY

    if text == "📘 دوپینگ ماز":
        browse["maz_type"] = "doping"
        await update.message.reply_text(
            "رشته تحصیلی خود را انتخاب کنید:",
            reply_markup=exam_field_keyboard()
        )
        return CHOOSING_EXAM_MAZ_FIELD

    if text == "📚 آزمون‌های جامع":
        browse["maz_type"] = "jame"
        await update.message.reply_text(
            "رشته تحصیلی خود را انتخاب کنید:",
            reply_markup=exam_field_keyboard()
        )
        return CHOOSING_EXAM_MAZ_FIELD

    await update.message.reply_text("لطفاً یکی از گزینه‌های زیر را انتخاب کنید.")
    return CHOOSING_EXAM_MAZ_TYPE


async def choose_exam_maz_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    restart_state = await _handle_restart(update, context)
    if restart_state is not None:
        return restart_state

    text = update.message.text

    if text == BACK_BUTTON:
        await update.message.reply_text(
            "نوع ماز رو انتخاب کن:",
            reply_markup=exam_maz_type_keyboard()
        )
        return CHOOSING_EXAM_MAZ_TYPE

    browse = _get_user_dict(context, "exam_browse")
    if not browse:
        await update.message.reply_text(
            "لطفاً دوباره از منوی آزمون‌ها شروع کنید.",
            reply_markup=main_keyboard()
        )
        return ORDER_ENTRY

    field_map = {
        "🧪 تجربی": "تجربی",
        "📐 ریاضی فیزیک": "ریاضی فیزیک",
        "📖 انسانی": "انسانی",
        "هم ریاضی فیزیک هم تجربی": "ریاضی فیزیک,تجربی",
    }

    if text not in field_map:
        await update.message.reply_text(
            "لطفاً یکی از گزینه‌های زیر را انتخاب کنید.",
            reply_markup=exam_field_keyboard()
        )
        return CHOOSING_EXAM_MAZ_FIELD

    field = field_map[text]
    browse["field"] = field

    await update.message.reply_text(
        "پایه رو انتخاب کن:",
        reply_markup=exam_maz_grade_keyboard()
    )
    return CHOOSING_EXAM_MAZ_GRADE


async def choose_exam_maz_grade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    restart_state = await _handle_restart(update, context)
    if restart_state is not None:
        return restart_state

    text = update.message.text

    if text == BACK_BUTTON:
        await update.message.reply_text(
            "رشته تحصیلی خود را انتخاب کنید:",
            reply_markup=exam_field_keyboard()
        )
        return CHOOSING_EXAM_MAZ_FIELD

    browse = _get_user_dict(context, "exam_browse")
    if not browse:
        await update.message.reply_text(
            "لطفاً دوباره از منوی آزمون‌ها شروع کنید.",
            reply_markup=main_keyboard()
        )
        return ORDER_ENTRY

    grade = exam_grade_from_label(text)
    if grade is None:
        await update.message.reply_text(
            "لطفاً یکی از گزینه‌های زیر را انتخاب کنید.",
            reply_markup=exam_maz_grade_keyboard()
        )
        return CHOOSING_EXAM_MAZ_GRADE

    browse["grade"] = grade

    maz_type = browse.get("maz_type")
    field = browse.get("field")

    if maz_type == "jame":
        browse["subject"] = f"آزمون جامع {grade}"
    else:
        browse["subject"] = ""

    return await _load_exam_dates(update, context, grade=grade)


# ---------------------------------------------------------------------------
# مسیر آزمون‌های خیلی سبز
# ---------------------------------------------------------------------------

async def choose_exam_kheili_grade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    restart_state = await _handle_restart(update, context)
    if restart_state is not None:
        return restart_state

    text = update.message.text

    if text == BACK_BUTTON:
        await update.message.reply_text(
            "مؤسسه رو انتخاب کن:",
            reply_markup=exam_provider_keyboard()
        )
        return CHOOSING_EXAM_PROVIDER

    browse = _get_user_dict(context, "exam_browse")
    if not browse:
        await update.message.reply_text(
            "لطفاً دوباره از منوی آزمون‌ها شروع کنید.",
            reply_markup=main_keyboard()
        )
        return ORDER_ENTRY

    grade = exam_grade_from_label(text)
    if grade is None:
        await update.message.reply_text(
            "لطفاً یکی از گزینه‌های زیر را انتخاب کنید.",
            reply_markup=exam_grade_keyboard()
        )
        return CHOOSING_EXAM_KHEILI_GRADE

    browse["grade"] = grade

    await update.message.reply_text(
        "رشته رو انتخاب کن:",
        reply_markup=exam_subject_keyboard("خیلی سبز")
    )
    return CHOOSING_EXAM_KHEILI_FIELD


async def choose_exam_kheili_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    restart_state = await _handle_restart(update, context)
    if restart_state is not None:
        return restart_state

    text = update.message.text
    browse = _get_user_dict(context, "exam_browse")
    if not browse:
        await update.message.reply_text(
            "لطفاً دوباره از منوی آزمون‌ها شروع کنید.",
            reply_markup=main_keyboard()
        )
        return ORDER_ENTRY

    if text == BACK_BUTTON:
        await update.message.reply_text(
            "پایه رو انتخاب کن:",
            reply_markup=exam_grade_keyboard()
        )
        return CHOOSING_EXAM_KHEILI_GRADE

    subject = subject_from_label(text, provider="خیلی سبز")
    if subject is None:
        await update.message.reply_text(
            "لطفاً یکی از گزینه‌های زیر را انتخاب کنید.",
            reply_markup=exam_subject_keyboard("خیلی سبز")
        )
        return CHOOSING_EXAM_KHEILI_FIELD

    browse["subject"] = subject
    return await _load_exam_dates(update, context, grade=browse["grade"])


# ---------------------------------------------------------------------------
# مسیر آرمان — فقط انتخاب پایه (دهم/یازدهم/دوازدهم)، بدون انتخاب درس
# ---------------------------------------------------------------------------

async def choose_exam_ahram_grade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    restart_state = await _handle_restart(update, context)
    if restart_state is not None:
        return restart_state

    text = update.message.text
    browse = _get_user_dict(context, "exam_browse")
    if not browse:
        await update.message.reply_text(
            "لطفاً دوباره از منوی آزمون‌ها شروع کنید.",
            reply_markup=main_keyboard()
        )
        return ORDER_ENTRY

    if text == BACK_BUTTON:
        await update.message.reply_text(
            "موسسه رو انتخاب کن:",
            reply_markup=exam_provider_keyboard()
        )
        return CHOOSING_EXAM_PROVIDER

    grade = exam_grade_from_label(text)
    if grade is None:
        await update.message.reply_text(
            "لطفاً یکی از گزینه‌های زیر را انتخاب کنید.",
            reply_markup=exam_grade_keyboard()
        )
        return CHOOSING_EXAM_AHRAM_GRADE

    return await _load_exam_dates(update, context, grade=grade)


# ---------------------------------------------------------------------------
# مسیر آرشیو جامع امتحان نهایی
# ---------------------------------------------------------------------------

async def choose_final_exam_archive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    restart_state = await _handle_restart(update, context)
    if restart_state is not None:
        return restart_state

    text = (update.message.text or "").strip()

    # 백 버튼 텍스트의 변형(공백, 이모지 변형 등)을 모두 처리
    if text == BACK_BUTTON or text.replace(" ", "") == BACK_BUTTON.replace(" ", "") or "بازگشت" in text:
        await update.message.reply_text(
            "📚 مؤسسه رو انتخاب کن:",
            reply_markup=exam_provider_keyboard()
        )
        return CHOOSING_EXAM_PROVIDER

    subject = final_exam_archive_from_label(text)
    if subject is None:
        await update.message.reply_text(
            "لطفاً یکی از دروس زیر را انتخاب کنید.",
            reply_markup=final_exam_archive_keyboard()
        )
        return CHOOSING_EXAM_FINAL_ARCHIVE

    from database import get_final_exam_archive

    exam = get_final_exam_archive(subject)
    if not exam or not exam.get("question_file_id"):
        await update.message.reply_text(
            f"❌ فایل آرشیو برای درس «{subject}» هنوز ثبت نشده است.",
            reply_markup=final_exam_archive_keyboard()
        )
        return CHOOSING_EXAM_FINAL_ARCHIVE

    # Store exam info for print action (same as choose_exam_date)
    browse = _get_user_dict(context, "exam_browse")
    if browse is None:
        browse = {}
        context.user_data["exam_browse"] = browse
    browse["exam"] = exam

    # Send question file
    sent = await _safe_send_document(
        context.bot,
        chat_id=update.effective_chat.id,
        document=exam["question_file_id"],
        caption=f"📚 آرشیو جامع امتحان نهایی — {subject}",
    )
    if not sent:
        await _safe_reply_text(update, FILE_SEND_FAILED_MESSAGE)
        return CHOOSING_EXAM_FINAL_ARCHIVE

    # Send answer file if exists
    if exam.get("answer_file_id"):
        sent = await _safe_send_document(
            context.bot,
            chat_id=update.effective_chat.id,
            document=exam["answer_file_id"],
            caption=f"📝 پاسخنامه آرشیو جامع امتحان نهایی — {subject}",
        )
        if not sent:
            await _safe_reply_text(update, FILE_SEND_FAILED_MESSAGE)

    # Show print button (same as other exam flows)
    await update.message.reply_text(
        "اگه می‌خوای همین فایل رو چاپ کنیم، دکمه‌ی زیر رو بزن:",
        reply_markup=exam_after_file_keyboard()
    )
    return CHOOSING_EXAM_ACTION


# ---------------------------------------------------------------------------
# مسیر ارسال جزوه دلخواه (آپلود فایل ورد / پی‌دی‌اف)
# ---------------------------------------------------------------------------

async def start_custom_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["order"] = {"type": "custom"}

    await update.message.reply_text(
        "📎 لطفاً فایل جزوه‌ی خودت رو به‌صورت Word (.docx) یا PDF ارسال کن.\n"
        "تعداد صفحاتش رو خودم می‌شمارم.",
        reply_markup=restart_keyboard()
    )

    return WAITING_FILE


async def receive_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    restart_state = await _handle_restart(update, context)
    if restart_state is not None:
        return restart_state

    if getattr(update.message, "text", None) == BACK_BUTTON:
        await update.message.reply_text(
            "📚 نوع جزوه رو انتخاب کن:",
            reply_markup=main_keyboard()
        )
        return ORDER_ENTRY

    document = update.message.document

    if document is None:
        await update.message.reply_text(
            "لطفاً فایل رو به‌صورت Word (.docx) یا PDF ارسال کن، نه متن یا عکس.",
            reply_markup=restart_keyboard()
        )
        return WAITING_FILE

    file_name = document.file_name or "file"

    if document.file_size and document.file_size > MAX_FILE_SIZE_BYTES:
        await update.message.reply_text(
            f"⚠️ حجم این فایل بیش از حد مجازه (حداکثر {MAX_FILE_SIZE_MB} مگابایت).\n"
            "لطفاً فایل رو فشرده (zip) کن یا به چند بخش تقسیم کن و دوباره بفرست.",
            reply_markup=restart_keyboard()
        )
        return WAITING_FILE

    with tempfile.TemporaryDirectory() as tmp_dir:
        local_path = os.path.join(tmp_dir, file_name)

        if not await _safe_download(context.bot, document.file_id, local_path):
            await _safe_reply_text(
                update, FILE_DOWNLOAD_FAILED_MESSAGE, restart_keyboard()
            )
            return WAITING_FILE

        try:
            pages = count_pages(local_path, file_name)
        except PageCountError as e:
            await update.message.reply_text(str(e))
            return WAITING_FILE

    order = _get_user_dict(context, "order")
    if order is None:
        return await _conversation_expired(update, context, WAITING_FILE)

    order["file_name"] = file_name
    order["pages"] = pages
    order["file_id"] = document.file_id

    await update.message.reply_text(
        f"📄 تعداد صفحات: {pages}\n\nنوع چاپ را انتخاب کنید:",
        reply_markup=file_option_keyboard()
    )

    return CHOOSING_FILE_OPTION


async def choose_file_option(update: Update, context: ContextTypes.DEFAULT_TYPE):
    restart_state = await _handle_restart(update, context)
    if restart_state is not None:
        return restart_state

    text = update.message.text

    if text == BACK_BUTTON:
        await update.message.reply_text(
            "📎 لطفاً فایل جزوه‌ی خودت رو دوباره ارسال کن:",
            reply_markup=restart_keyboard()
        )
        return WAITING_FILE

    result = file_option_from_label(text)

    if result is None:
        await update.message.reply_text("لطفاً یکی از گزینه‌های زیر را انتخاب کنید.")
        return CHOOSING_FILE_OPTION

    color, side = result
    order = _get_user_dict(context, "order")
    pages = (order or {}).get("pages")
    if order is None or not pages:
        return await _conversation_expired(update, context, WAITING_FILE)

    per_unit_price = get_custom_print_price(color, side)

    if side == "پشت‌ورو":
        units = math.ceil(pages / 2)
    else:
        units = pages

    price = units * per_unit_price

    order["print_type"] = f"{color} - {side}"
    order["price"] = price

    await update.message.reply_text(
        f"💰 هزینه چاپ: {format_price(price)} ({pages} صفحه)\n\n"
        "نوع صحافی رو انتخاب کن:",
        reply_markup=binding_keyboard(pages)
    )

    return CHOOSING_BINDING


async def choose_binding(update: Update, context: ContextTypes.DEFAULT_TYPE):
    restart_state = await _handle_restart(update, context)
    if restart_state is not None:
        return restart_state

    text = update.message.text
    order = _get_user_dict(context, "order")
    pages = (order or {}).get("pages")
    if order is None or not pages:
        return await _conversation_expired(update, context, WAITING_FILE)

    if text == BACK_BUTTON:
        await update.message.reply_text(
            "نوع چاپ را انتخاب کنید:",
            reply_markup=file_option_keyboard()
        )
        return CHOOSING_FILE_OPTION

    result = binding_from_label(text, pages)

    if result is None:
        await update.message.reply_text(
            "لطفاً یکی از گزینه‌های زیر را انتخاب کنید.",
            reply_markup=binding_keyboard(pages)
        )
        return CHOOSING_BINDING

    binding_name, binding_price = result
    order["binding"] = binding_name
    order["price"] = order.get("price", 0) + binding_price

    return await _finish_item(update, context)


# ---------------------------------------------------------------------------
# مراحل مشترک: تحویل، آدرس، شماره تماس، رسید پرداخت
# ---------------------------------------------------------------------------

async def choose_delivery(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    restart_state = await _handle_restart(update, context)
    if restart_state is not None:
        return restart_state

    if text == BACK_BUTTON:
        context.user_data.pop("checkout", None)
        return await _show_add_more_prompt(update, context)

    checkout = _get_user_dict(context, "checkout")
    if checkout is None:
        return await _conversation_expired(update, context, ORDER_ENTRY)

    cart = _get_cart(context)
    has_emami = any(item.get("teacher") == "امامی" for item in cart)

    if text == "🏪 تحویل حضوری":
        checkout["delivery"] = "تحویل حضوری"
        checkout["address"] = None
        checkout["delivery_fee"] = 0
        _recompute_price(checkout)
        checkout["_phone_back"] = "delivery"

        await update.message.reply_text(
            "☎️ لطفاً شماره تماس خودتون رو ارسال کنید:",
            reply_markup=restart_keyboard()
        )
        return WAITING_PHONE

    if text.startswith("🚚 ارسال"):
        await update.message.reply_text(
            "توجه: هزینه ارسال جداگانه است و بعد از هماهنگی اعلام می‌شود.\n\n"
            "محل ارسال را انتخاب کنید:",
            reply_markup=delivery_location_keyboard("امامی" if has_emami else None)
        )
        return CHOOSING_DELIVERY_LOCATION

    await update.message.reply_text("لطفاً یکی از گزینه‌های زیر را انتخاب کنید.")
    return CHOOSING_DELIVERY


async def choose_delivery_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    restart_state = await _handle_restart(update, context)
    if restart_state is not None:
        return restart_state

    if text == BACK_BUTTON:
        await update.message.reply_text(
            "روش دریافت سفارش را انتخاب کنید:",
            reply_markup=delivery_keyboard()
        )
        return CHOOSING_DELIVERY

    checkout = _get_user_dict(context, "checkout")
    if checkout is None:
        return await _conversation_expired(update, context, CHOOSING_DELIVERY)

    if text.startswith("🏫 ارسال به آموزشگاه پگاه و پویا"):
        fee = get_delivery_fee()
        checkout["delivery"] = "ارسال به آموزشگاه پگاه و پویا"
        checkout["address"] = "آموزشگاه پگاه و پویا"
        checkout["delivery_fee"] = fee
        _recompute_price(checkout)
        checkout["_phone_back"] = "delivery_location"

        await update.message.reply_text(
            f"💰 مبلغ نهایی سفارش شما: {format_price(checkout.get('price'))}\n"
            f"🚚 هزینه ارسال: {format_price(fee)}\n\n"
            "☎️ لطفاً شماره تماس خودتون رو ارسال کنید:",
            reply_markup=restart_keyboard()
        )
        return WAITING_PHONE

    if text == "🏠 ارسال به آدرس شخصی (هزینه ارسال با خود شماست)":
        checkout["delivery"] = "ارسال به آدرس شخصی"
        checkout["delivery_fee"] = 0
        _recompute_price(checkout)

        await update.message.reply_text(
            f"💰 مبلغ نهایی سفارش شما: {format_price(checkout.get('price'))}\n"
            "ℹ️ هزینه ارسال با خود شماست\n\n"
            "لطفاً آدرس کامل خود را ارسال کنید:",
            reply_markup=restart_keyboard()
        )
        return WAITING_ADDRESS

    await update.message.reply_text("لطفاً یکی از گزینه‌های زیر را انتخاب کنید.")
    return CHOOSING_DELIVERY_LOCATION


async def receive_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    restart_state = await _handle_restart(update, context)
    if restart_state is not None:
        return restart_state

    text = update.message.text
    cart = _get_cart(context)
    has_emami = any(item.get("teacher") == "امامی" for item in cart)

    if text == BACK_BUTTON:
        await update.message.reply_text(
            "محل ارسال را انتخاب کنید:",
            reply_markup=delivery_location_keyboard("امامی" if has_emami else None)
        )
        return CHOOSING_DELIVERY_LOCATION

    checkout = _get_user_dict(context, "checkout")
    if checkout is None:
        return await _conversation_expired(update, context, CHOOSING_DELIVERY)

    checkout["address"] = text
    checkout["_phone_back"] = "address"

    await update.message.reply_text(
        "☎️ لطفاً شماره تماس خودتون رو ارسال کنید:",
        reply_markup=restart_keyboard()
    )

    return WAITING_PHONE


PHONE_RE = re.compile(r"^[\d۰-۹+\s-]{8,15}$")


async def receive_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    restart_state = await _handle_restart(update, context)
    if restart_state is not None:
        return restart_state

    text = update.message.text
    checkout = _get_user_dict(context, "checkout")
    if checkout is None:
        return await _conversation_expired(update, context, CHOOSING_DELIVERY)

    if text == BACK_BUTTON:
        origin = checkout.get("_phone_back")
        cart = _get_cart(context)
        has_emami = any(item.get("teacher") == "امامی" for item in cart)

        if origin == "address":
            await update.message.reply_text(
                "لطفاً آدرس کامل خود را دوباره ارسال کنید:",
                reply_markup=restart_keyboard()
            )
            return WAITING_ADDRESS

        if origin == "delivery_location":
            checkout["delivery"] = None
            checkout["delivery_fee"] = 0
            checkout["address"] = None
            _recompute_price(checkout)
            await update.message.reply_text(
                "محل ارسال را انتخاب کنید:",
                reply_markup=delivery_location_keyboard("امامی" if has_emami else None)
            )
            return CHOOSING_DELIVERY_LOCATION

        checkout["delivery"] = None
        checkout["delivery_fee"] = 0
        _recompute_price(checkout)
        await update.message.reply_text(
            "روش دریافت سفارش را انتخاب کنید:",
            reply_markup=delivery_keyboard()
        )
        return CHOOSING_DELIVERY

    phone = text.strip()

    if not PHONE_RE.match(phone):
        await update.message.reply_text(
            "شماره تماس معتبر نیست، لطفاً دوباره ارسال کنید (مثال: 09123456789)",
            reply_markup=restart_keyboard()
        )
        return WAITING_PHONE

    user = update.effective_user
    checkout["phone"] = phone

    update_user_phone(user.id, phone)

    # Create the order immediately so the customer receives their tracking code
    # in the first order-confirmation message (not after receipt submission).
    from database import (
        save_order_with_items,
        get_tracking_case_by_order,
        connect,
    )
    cart = _get_cart(context)
    order_id = save_order_with_items(
        user_id=user.id,
        items=cart,
        delivery=checkout.get("delivery"),
        address=checkout.get("address"),
        phone=checkout.get("phone"),
        price=checkout.get("price"),
        discount_code=checkout.get("discount_code"),
        discount_amount=checkout.get("discount_amount", 0),
    )
    context.user_data["receipt_order_id"] = order_id

    tc_conn = connect()
    tc_row = get_tracking_case_by_order(order_id, tc_conn)
    tc_conn.close()
    tracking_code = tc_row["tracking_code"] if tc_row else order_id

    from config import CARD_NUMBER, CARD_HOLDER

    if not CARD_NUMBER:
        await update.message.reply_text(
            "✅ اطلاعات سفارش شما ثبت شد.\n\n"
            f"📌 کد پیگیری سفارش: {tracking_code}\n"
            f"💳 مبلغ نهایی {format_price(checkout.get('price'))} — "
            "شماره کارت در حال حاضر تنظیم نشده است؛ لطفاً برای دریافت شماره کارت "
            "با پشتیبانی تماس بگیرید.",
            reply_markup=restart_keyboard()
        )
        return WAITING_RECEIPT

    card_line = f"به نام: {CARD_HOLDER}\n" if CARD_HOLDER else ""

    await update.message.reply_text(
        "✅ اطلاعات سفارش شما ثبت شد.\n\n"
        f"📌 کد پیگیری سفارش: {tracking_code}\n"
        f"💳 لطفاً مبلغ نهایی {format_price(checkout.get('price'))} رو به شماره کارت زیر واریز کنید:\n\n"
        f"{CARD_NUMBER}\n"
        f"{card_line}\n"
        "بعد از واریز، لطفاً عکس فیش/رسید واریزی رو همین‌جا ارسال کنید.",
        reply_markup=restart_keyboard()
    )

    return WAITING_RECEIPT


def _format_cart_summary(user_row, cart: list, checkout: dict) -> str:
    full_name = user_row[3] if user_row else "-"
    username = user_row[2] if user_row else None
    phone = checkout.get("phone", "-")

    lines = [
        "🧾 سفارش جدید",
        f"👤 نام: {full_name}",
        f"🔗 یوزرنیم: @{username}" if username else "🔗 یوزرنیم: ندارد",
        f"☎️ تلفن: {phone}",
        "",
        "📦 آیتم‌های سفارش:",
    ]

    lines.extend(_item_line(item) for item in cart)

    lines.append("")

    if checkout.get("discount_amount"):
        lines.append(f"🧾 جمع قبل از تخفیف: {format_price(checkout.get('base_price'))}")
        lines.append(f"🎟️ تخفیف ({checkout.get('discount_code')}): -{format_price(checkout.get('discount_amount'))}")

    lines.append(f"💰 جمع کل: {format_price(checkout.get('price'))}")
    lines.append(f"🚚 تحویل: {checkout.get('delivery')}")

    delivery_fee = checkout.get("delivery_fee")
    if delivery_fee is not None:
        if delivery_fee == 0:
            lines.append("🚚 هزینه ارسال: هزینه ارسال با خود شماست")
        else:
            lines.append(f"🚚 هزینه ارسال: {format_price(delivery_fee)}")

    if checkout.get("address"):
        lines.append(f"📍 آدرس: {checkout.get('address')}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# ارسال رسید پرداخت به ادمین
#
# نکته‌ی مهم: «ارسال رسید به ادمین» فقط یعنی فایل به گروه رسیده. این کار به‌هیچ‌وجه
# به معنی «تأیید پرداخت» نیست؛ تأیید فقط با ریپلای «تایید» توسط ادمین داخل گروه
# انجام می‌شود (confirm_payment). پس تا وقتی send_photo موفق نشده، نه پرداختی
# تأییدشده حساب می‌شود و نه کاربر جواب «پرداخت تأیید شد» می‌گیرد.
# ---------------------------------------------------------------------------

RECEIPT_SEND_ATTEMPTS = 3
RECEIPT_SEND_BACKOFF = (2, 5)

RECEIPT_SENT_TO_USER = (
    "✅ رسید شما دریافت شد و برای بررسی ادمین ارسال شد.\n"
    "پرداخت پس از تأیید ادمین نهایی می‌شود."
)

RECEIPT_FAILED_TO_USER = (
    "❌ ارسال رسید ناموفق بود؛ هنوز پرداخت شما تأیید نشده است.\n"
    "لطفاً دوباره رسید را ارسال کنید."
)

# ---------------------------------------------------------------------------
# داده‌های Callback دکمه‌های مدیریت رسید در گروه
# فرمت: pay_confirm:{payment_id} / pay_reject:{payment_id} /
#       pay_reject_reason:{reason_key}:{payment_id} /
#       pay_stage_preparing:{payment_id} / pay_stage_ready:{payment_id} /
#       pay_stage_done:{payment_id}
# ---------------------------------------------------------------------------
PAY_CB_CONFIRM = "pay_confirm"
PAY_CB_REJECT = "pay_reject"
PAY_CB_REJECT_REASON = "pay_reject_reason"
PAY_CB_STAGE_PREPARING = "pay_stage_preparing"
PAY_CB_STAGE_READY = "pay_stage_ready"
PAY_CB_STAGE_DONE = "pay_stage_done"

# روش‌های تحویل معتبر (مطابق دیتابیس)
DELIVERY_IN_PERSON = "تحویل حضوری"
DELIVERY_SHIPPING = "ارسال به آدرس شخصی"

# دلایل عدم تأیید پرداخت (۴ مورد)
REJECT_REASON_UNREADABLE = "unreadable"
REJECT_REASON_INVALID = "invalid"
REJECT_REASON_LOW_AMOUNT = "low_amount"
REJECT_REASON_HIGH_AMOUNT = "high_amount"

_ALL_REJECT_REASONS = {
    REJECT_REASON_UNREADABLE,
    REJECT_REASON_INVALID,
    REJECT_REASON_LOW_AMOUNT,
    REJECT_REASON_HIGH_AMOUNT,
}

# نقشِ دکمه‌های رد به پیام مشتری
REJECT_USER_MESSAGES = {
    REJECT_REASON_UNREADABLE: (
        "❌ فیش واریزی شما بررسی شد و ناخوانا یا ناقص است.\n"
        "لطفاً یک فیش واضح و خوانا را برای همین سفارش دوباره ارسال کنید.\n"
        "سفارش شما لغو نشده و در انتظار فیش جدید می‌ماند."
    ),
    REJECT_REASON_INVALID: (
        "❌ فیش واریزی شما بررسی شد و جعلی یا نامعتبر است.\n"
        "لطفاً یک فیش معتبر را برای همین سفارش دوباره ارسال کنید.\n"
        "سفارش شما لغو نشده و در انتظار فیش جدید می‌ماند."
    ),
    REJECT_REASON_LOW_AMOUNT: (
        "❌ فیش واریزی شما بررسی شد و مبلغ واریزی کمتر از مبلغ سفارش است.\n"
        "لطفاً فیش جدید با مبلغ صحیح را برای همین سفارش دوباره ارسال کنید.\n"
        "سفارش شما لغو نشده و در انتظار فیش جدید می‌mands."
    ),
    REJECT_REASON_HIGH_AMOUNT: (
        "❌ فیش واریزی شما بررسی شد و مبلغ واریزی بیشتر از مبلغ سفارش است.\n"
        "لطفاً فیش جدید با مبلغ صحیح را برای همین سفارش دوباره ارسال کنید.\n"
        "سفارش شما لغو نشده و در انتظار فیش جدید می‌mands."
    ),
}

# نقشِ دکمه‌های رد به وضعیت دیتابیس
_REJECT_REASON_TO_PAYMENT_STATUS = {
    REJECT_REASON_UNREADABLE: PAYMENT_STATUS_WAITING_UNREADABLE,
    REJECT_REASON_INVALID: PAYMENT_STATUS_WAITING_INVALID,
    REJECT_REASON_LOW_AMOUNT: PAYMENT_STATUS_WAITING_LOW_AMOUNT,
    REJECT_REASON_HIGH_AMOUNT: PAYMENT_STATUS_WAITING_HIGH_AMOUNT,
}

PAYMENT_ALREADY_CONFIRMED_MESSAGE = (
    "✅ این پرداخت قبلاً تأیید شده بود."
)

PAYMENT_ACTION_SUCCESS_TO_ADMIN = (
    "✅ عملیات با موفقیت انجام شد. نتیجه به مشتری ارسال شد."
)

PAYMENT_ACTION_NOOP_TO_ADMIN = (
    "ℹ️ این پرداخت قبلاً پردازش شده است. هیچ تغییری ایجاد نشد."
)


def _keyboard_for_initial(payment_id: int) -> InlineKeyboardMarkup:
    """کیبورد اولیه: تایید / عدم تایید پرداخت."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ تأیید پرداخت", callback_data=f"{PAY_CB_CONFIRM}:{payment_id}"),
            InlineKeyboardButton("❌ عدم تأیید پرداخت", callback_data=f"{PAY_CB_REJECT}:{payment_id}"),
        ],
    ])


def _keyboard_for_reject_menu(payment_id: int) -> InlineKeyboardMarkup:
    """فهرست دلایل عدم تأیید پرداخت — چهار دلیل، چیدمان ۲×۲."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("فیش ناخوانا", callback_data=f"{PAY_CB_REJECT_REASON}:{REJECT_REASON_UNREADABLE}:{payment_id}"),
            InlineKeyboardButton("فیش نامعتبر", callback_data=f"{PAY_CB_REJECT_REASON}:{REJECT_REASON_INVALID}:{payment_id}"),
        ],
        [
            InlineKeyboardButton("مبلغ کمتر", callback_data=f"{PAY_CB_REJECT_REASON}:{REJECT_REASON_LOW_AMOUNT}:{payment_id}"),
            InlineKeyboardButton("مبلغ بیشتر", callback_data=f"{PAY_CB_REJECT_REASON}:{REJECT_REASON_HIGH_AMOUNT}:{payment_id}"),
        ],
    ])


def _keyboard_for_confirmed(payment_id: int, delivery: str) -> InlineKeyboardMarkup:
    """کیبورد پس از تایید پرداخت — دکمه مرحله بعدی بر اساس روش تحویل."""
    if _delivery_is_in_person(delivery):
        button_text = "آماده تحویل"
        callback = PAY_CB_STAGE_READY
    else:
        button_text = "آماده‌سازی سفارش"
        callback = PAY_CB_STAGE_PREPARING
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(button_text, callback_data=f"{callback}:{payment_id}")],
    ])


def _keyboard_for_pre_stage(payment_id: int, delivery: str) -> InlineKeyboardMarkup:
    """کیبورد پس از انجام مرحله پیش‌فروش — دکمه نهایی بر اساس روش تحویل."""
    if _delivery_is_in_person(delivery):
        button_text = "تحویل داده شد"
    else:
        button_text = "ارسال شد"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(button_text, callback_data=f"{PAY_CB_STAGE_DONE}:{payment_id}")],
    ])


def _receipt_management_keyboard(payment_id: int, order_status: str = None, delivery: str = None) -> InlineKeyboardMarkup:
    """
    کیبورد مدیریت رسید بر اساس وضعیت فعلی سفارش در دیتابیس.
    منبع حقیقت تعیین مرحله است orders.status، نه ظاهر دکمه‌ها.
    """
    if order_status == ORDER_STATUS_WAITING_PAYMENT:
        return _keyboard_for_initial(payment_id)

    if order_status == ORDER_STATUS_EXPIRED:
        # سفارش منقضی شده: هیچ عملیات (تایید/رد/مراحل بعدی) مجاز نیست.
        return InlineKeyboardMarkup([])

    if order_status == ORDER_STATUS_PAYMENT_CONFIRMED:
        return _keyboard_for_confirmed(payment_id, delivery or "تحویل حضوری")

    if order_status in (ORDER_STATUS_READY_HANDOVER, ORDER_STATUS_PREPARING):
        return _keyboard_for_pre_stage(payment_id, delivery or "تحویل حضوری")

    # وضعیت نهایی (تحویل حضوری انجام شد / ارسال شده) — بدون دکمه
    return InlineKeyboardMarkup([])




def _is_retryable_send_error(exc: BaseException) -> bool:
    """
    فقط خطاهای موقتی شبکه/تلگرام دوباره تلاش می‌شوند.

    توجه: در PTB کلاس BadRequest زیرمجموعه‌ی NetworkError است، پس باید صریحاً
    کنار گذاشته شود؛ وگرنه خطاهای permanent مثل file_id نامعتبر هم بی‌جهت
    سه بار تکرار می‌شدند.
    """
    if isinstance(exc, RetryAfter):
        return True
    if isinstance(exc, BadRequest):
        return False
    if isinstance(exc, (NetworkError, httpx.TransportError)):
        return True
    return isinstance(exc, (asyncio.TimeoutError, TimeoutError))


async def _send_photo_with_retry(bot, chat_id, photo, caption, reply_markup=None):
    """
    ارسال فایل به ادمین با چند تلاش مجدد در صورت قطعی لحظه‌ای شبکه.
    اگر همه‌ی تلاش‌ها شکست بخورد، آخرین خطا را raise می‌کند.
    """
    for attempt in range(1, RECEIPT_SEND_ATTEMPTS + 1):
        try:
            return await bot.send_photo(
                chat_id=chat_id, photo=photo, caption=caption, reply_markup=reply_markup
            )
        except Exception as exc:
            if not _is_retryable_send_error(exc) or attempt == RECEIPT_SEND_ATTEMPTS:
                logger.warning(
                    "ارسال رسید به ادمین ناموفق بود (تلاش %s از %s): %s: %s",
                    attempt, RECEIPT_SEND_ATTEMPTS, type(exc).__name__, exc,
                )
                raise

            delay = RECEIPT_SEND_BACKOFF[min(attempt, len(RECEIPT_SEND_BACKOFF)) - 1]
            logger.warning(
                "خطای شبکه در ارسال رسید (تلاش %s از %s): %s: %s — %s ثانیه بعد دوباره تلاش می‌کنیم",
                attempt, RECEIPT_SEND_ATTEMPTS, type(exc).__name__, exc, delay,
            )
            await asyncio.sleep(delay)


FILE_SEND_FAILED_MESSAGE = (
    "❌ ارسال این فایل برای شما ممکن نشد.\n"
    "ممکن است فایل در تلگرام منقضی شده باشد؛ لطفاً دوباره تلاش کنید یا از "
    "گزینه‌ی «فقط دفترچه سؤال» استفاده کنید."
)

FILE_DOWNLOAD_FAILED_MESSAGE = (
    "❌ دریافت این فایل ممکن نشد؛ احتمالاً اتصال اینترنت قطع شده یا فایل در "
    "تلگرام معتبر نیست.\nلطفاً فایل را دوباره ارسال کنید."
)


async def _safe_send_document(bot, chat_id, document=None, filename=None,
                              caption=None, file_obj=None) -> bool:
    """
    ارسال سند با تحمل خطا.

    خطاهای تلگرام (BadRequest مثل file reference expired یا NetworkError) و
    خطاهای فایلِ بسته/پاک‌شده به‌جای crash کردن هندلر، فقط لاگ و False برمی‌گردانند.
    """
    try:
        await bot.send_document(
            chat_id=chat_id,
            document=file_obj if file_obj is not None else document,
            filename=filename,
            caption=caption,
        )
        return True
    except Exception as exc:
        logger.warning(
            "ارسال سند ناموفق بود (chat=%s): %s: %s", chat_id, type(exc).__name__, exc
        )
        return False


async def _safe_download(bot, file_id, local_path) -> bool:
    """
    دانلود فایل از تلگرام با تحمل خطا.

    هر خطای تلگرام/شبکه به‌جای crash کردن، لاگ و False برمی‌گرداند تا هندلر
    بتواند پیام مناسب فارسی به کاربر بدهد.
    """
    try:
        tg_file = await bot.get_file(file_id)
        await tg_file.download_to_drive(local_path)
        return True
    except Exception as exc:
        logger.warning(
            "دانلود فایل ناموفق بود (%s): %s: %s", file_id, type(exc).__name__, exc
        )
        return False


async def _conversation_expired(update: Update, context: ContextTypes.DEFAULT_TYPE,
                                fallback_state):
    """
    وقتی داده‌ی لازم در user_data نیست (گفتگوی ناقص، منقضی‌شده یا پاک‌شده)،
    به کاربر پیام روشن می‌دهد و state پیشنهادی را برمی‌گرداند.

    این تابع جای KeyError را می‌گیرد و هیچ جزئیات فنی نشان نمی‌دهد.
    """
    message = getattr(update, "effective_message", None)
    if message is not None:
        try:
            await message.reply_text(
                "🔄 این مرحله از سفارش دیگه معتبر نیست و از دست رفته است.\n"
                "برای شروع دوباره، دکمه‌ی «شروع سفارش جدید» را بزنید یا پیام "
                "/start را بفرستید.",
                reply_markup=main_keyboard(),
            )
        except Exception as exc:
            logger.error(
                "ارسال پیام «گفتگوی منقضی» ناموفق بود: %s: %s", type(exc).__name__, exc
            )
    return fallback_state


def _get_user_dict(context: ContextTypes.DEFAULT_TYPE, key: str):
    """
    خواندن امن یک دیکشنری از user_data.

    به‌جای user_data[key] که KeyError می‌دهد، اگر کلید نبود یا نوعش دیکشنری
    نبود، None برمی‌گرداند تا هندلر با _conversation_expired مسیر امن را برود.
    """
    value = context.user_data.get(key)
    return value if isinstance(value, dict) else None


def _get_cart(context: ContextTypes.DEFAULT_TYPE) -> list:
    """خواندن امن سبد خرید؛ همیشه یک لیست از دیکشنری‌ها برمی‌گرداند."""
    value = context.user_data.get("cart")
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _ensure_admin_exam(context: ContextTypes.DEFAULT_TYPE) -> dict:
    """
    خودترمیمی گفتگوی ثبت آزمون.

    اگر admin_exam وجود نداشته باشد (مثلاً حافظه‌ی دائمی پاک شده یا گفتگو از
    جای دیگری باز شده)، یک دیکشنری تازه می‌سازد تا ادمین بتواند ادامه دهد،
    به‌جای اینکه با KeyError یا پیام «شروع دوباره» روبه‌رو شود.
    """
    data = _get_user_dict(context, "admin_exam")
    if data is None:
        data = {}
        context.user_data["admin_exam"] = data
    return data


async def _safe_reply_text(update, text, reply_markup=None):
    """
    ارسال پیام به کاربر، با چند تلاش مجدد در صورت قطعی شبکه.

    اگر این پیام هم به هر دلیلی ارسال نشد، خطا را لاگ می‌کند و False برمی‌گرداند
    تا گفتگو crash نکند. داده‌های لازم برای retry دست‌نخورده می‌ماند.
    """
    for attempt in range(1, RECEIPT_SEND_ATTEMPTS + 1):
        try:
            await update.message.reply_text(text, reply_markup=reply_markup)
            return True
        except Exception as exc:
            if not _is_retryable_send_error(exc) or attempt == RECEIPT_SEND_ATTEMPTS:
                logger.error(
                    "ارسال پیام به کاربر ناموفق بود (تلاش %s از %s): %s: %s",
                    attempt, RECEIPT_SEND_ATTEMPTS, type(exc).__name__, exc,
                )
                return False

            delay = RECEIPT_SEND_BACKOFF[min(attempt, len(RECEIPT_SEND_BACKOFF)) - 1]
            logger.warning(
                "ارسال پیام به کاربر به‌خاطر شبکه ناموفق بود (تلاش %s از %s): %s — %s ثانیه بعد دوباره تلاش می‌کنیم",
                attempt, RECEIPT_SEND_ATTEMPTS, type(exc).__name__, delay,
            )
            await asyncio.sleep(delay)


async def receive_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    restart_state = await _handle_restart(update, context)
    if restart_state is not None:
        return restart_state

    if getattr(update.message, "text", None) == BACK_BUTTON:
        await update.message.reply_text(
            "☎️ لطفاً شماره تماس خودتون رو دوباره ارسال کنید:",
            reply_markup=restart_keyboard()
        )
        return WAITING_PHONE

    photo = update.message.photo

    if not photo:
        await update.message.reply_text(
            "لطفاً عکس فیش واریزی رو ارسال کنید (نه متن یا فایل).",
            reply_markup=restart_keyboard()
        )
        return WAITING_RECEIPT

    user = update.effective_user
    cart = _get_cart(context)
    checkout = context.user_data.get("checkout")

    if not checkout:
        # داده‌ی لازم برای ثبت سفارش نیست (مثلاً گفتگو از قبل ری‌استارت شده)
        await _safe_reply_text(
            update,
            "اطلاعات سفارش در دسترس نیست. لطفاً دوباره از ابتدا سفارشتون رو ثبت کنید.",
            reply_markup=main_keyboard(),
        )
        return ConversationHandler.END

    from database import (
        get_payment_by_order,
        get_order,
        PAYMENT_STATUS_CONFIRMED,
        ORDER_STATUS_WAITING_PAYMENT,
        get_tracking_case_by_order,
        connect,
    )

    # شماره سفارش در تلاش‌های قبلی ساخته شده و ذخیره شده تا با هر بار ارسال دوباره‌ی
    # فیش، سفارش تکراری در دیتابیس ثبت نشود.
    order_id = context.user_data.get("receipt_order_id")

    if order_id is not None:
        # وضعیت خود سفارش ملاک است: اگر سفارش از «در انتظار پرداخت» خارج شده
        # (تأیید شده، در حال آماده‌سازی، تحویل/ارسال شده)، هیچ رسید جدیدی —
        # حتی اگر پرداخت قبلی رد شده باشد — نباید ثبت شود.
        order_row = get_order(order_id)
        if order_row is not None and order_row["status"] != ORDER_STATUS_WAITING_PAYMENT:
            logger.info(
                "سفارش %s در وضعیت «%s» است؛ دریافت رسید جدید مسدود شد.",
                order_id, order_row["status"],
            )
            if order_row["status"] == ORDER_STATUS_EXPIRED:
                reply_text = (
                    "⏰ مهلت پرداخت این سفارش به پایان رسیده است و سفارش "
                    "منقضی شده است؛ امکان ارسال رسید جدید وجود ندارد.\n"
                    f"کد پیگیری: {order_id}"
                )
            else:
                reply_text = (
                    "✅ پرداخت این سفارش قبلاً تایید شده است. نیاز به ارسال رسید جدید نیست."
                )
            await _safe_reply_text(
                update,
                reply_text,
                main_keyboard(),
            )
            _clear_receipt_data(context)
            return ConversationHandler.END

        # اگر پرداخت این سفارش قبلاً تایید شده، نه فقط فیش قبلی بلکه هر رسید جدیدی
        # هم برای همین سفارش مجاز نیست (پرداخت نهایی شده است).
        existing_payment = get_payment_by_order(order_id)
        # get_payment_by_order برمی‌گرداند tuple (ستون ۹ = status، ستون ۰ = id)
        if existing_payment and existing_payment[9] == PAYMENT_STATUS_CONFIRMED:
            logger.info(
                "رسید سفارش %s قبلاً تایید شده بود (پرداخت #%s)؛ ارسال دوباره مجاز نیست.",
                order_id, existing_payment[0],
            )
            await _safe_reply_text(
                update,
                "✅ پرداخت این سفارش قبلاً تایید شده است. نیاز به ارسال رسید جدید نیست.",
                main_keyboard(),
            )
            _clear_receipt_data(context)
            return ConversationHandler.END

        # در غیر این صورت (رسید قبلی رد شده یا در انتظار بررسی)، رسید جدید برای
        # همین سفارش ارسال می‌شود و یک رکورد پرداخت مستقل ساخته می‌شود.
        logger.info(
            "ارسال رسید جدید برای سفارش %s (پرداخت قبلی وجود دارد اما تایید نشده).",
            order_id,
        )

    if order_id is None:
        order_id = save_order_with_items(
            user_id=user.id,
            items=cart,
            delivery=checkout.get("delivery"),
            address=checkout.get("address"),
            phone=checkout.get("phone"),
            price=checkout.get("price"),
            discount_code=checkout.get("discount_code"),
            discount_amount=checkout.get("discount_amount", 0),
        )
        context.user_data["receipt_order_id"] = order_id

    # Peckida code (tracking) - barcode order
    tc_conn = connect()
    tc_row = get_tracking_case_by_order(order_id, tc_conn)
    tc_conn.close()
    tracking_code = tc_row["tracking_code"] if tc_row else None

    user_row = get_user(user.id)
    caption = _format_cart_summary(user_row, cart, checkout)
    caption += (
        f"\n\n📌 شماره سفارش: {order_id}\n"
        f"📌 کد پیگیری: {tracking_code or order_id}\n"
    )

    file_id = photo[-1].file_id

    try:
        sent = await _send_photo_with_retry(
            context.bot,
            GROUP_ID,
            file_id,
            caption,
            reply_markup=_receipt_management_keyboard(0),  # payment_id will be set after save
        )
    except Exception:
        # رسید به ادمین نرسیده ⇒ پرداخت تأیید نشده است. سبد و اطلاعات سفارش
        # دست‌نخورده می‌ماند تا کاربر بتواند دوباره فیش را بفرستد.
        await _safe_reply_text(update, RECEIPT_FAILED_TO_USER, restart_keyboard())
        return WAITING_RECEIPT

    # از این لحظه رسید رسیده‌ی گروه است؛ فقط حالا رکورد پرداخت ساخته می‌شود
    # (confirmed=0 ⇒ هنوز تأیید نشده).
    try:
        payment_id = save_payment(order_id, user.id, sent.message_id, group_chat_id=GROUP_ID, operation_type="receipt_submitted", submission_uid=f"receipt:{order_id}:{user.id}")
    except Exception as exc:
        logger.error("ثبت پرداخت سفارش %s در دیتابیس ناموفق بود: %s: %s", order_id, type(exc).__name__, exc)
        await _safe_reply_text(
            update,
            "⚠️ رسید شما به ادمین رسید، اما ثبت آن در سامانه با مشکل مواجه شد.\n"
            "لطفاً به ادمین اطلاع دهید تا پیگیری شود.",
            restart_keyboard(),
        )
        return WAITING_RECEIPT

    # دکمه‌های مدیریت را بر اساس payment_id واقعی روی پیام گروه اعمال می‌کنیم.
    try:
        await context.bot.edit_message_reply_markup(
            chat_id=GROUP_ID,
            message_id=sent.message_id,
            reply_markup=_receipt_management_keyboard(payment_id),
        )
    except Exception:
        # اگر ویرایش کیبورد شکست خورد، رسید همچنان در گروه است و ادمین می‌تواند
        # از دستور متنی «تایید» استفاده کند. این خطا غیرحдат است.
        logger.warning("ویرایش کیبورد مدیریت رسید #%s ناموفق بود.", payment_id)

    for item in cart:
        if item.get("type") == "custom" and item.get("file_id"):
            await _safe_send_document(
                context.bot,
                chat_id=GROUP_ID,
                document=item["file_id"],
                caption=f"📎 فایل جزوه دلخواه ({item.get('file_name')}) — سفارش {order_id}",
            )

    delivered = await _safe_reply_text(update, RECEIPT_SENT_TO_USER, main_keyboard())
    if not delivered:
        logger.error(
            "رسید سفارش %s به ادمین رسید و ثبت شد، ولی پیام تأییدیه به کاربر ارسال نشد.",
            order_id,
        )
    _clear_receipt_data(context)
    return WAITING_RECEIPT


def _clear_receipt_data(context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("order", None)
    context.user_data.pop("cart", None)
    context.user_data.pop("checkout", None)
    context.user_data.pop("receipt_order_id", None)


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("order", None)
    context.user_data.pop("cart", None)
    context.user_data.pop("checkout", None)
    await update.message.reply_text(
        "سفارش لغو شد.",
        reply_markup=main_keyboard()
    )
    return ConversationHandler.END


async def handle_receipt_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not await _require_admin(update):
        return

    data = query.data or ""
    if ":" not in data:
        return

    prefix, _, rest = data.partition(":")
    try:
        payment_id = int(rest.split(":")[0])
    except (ValueError, IndexError):
        return

    message = query.message
    if message is None:
        return

    payment = get_payment_by_group_message(
        message.message_id, group_chat_id=message.chat.id
    )
    if not payment or payment["id"] != payment_id:
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        return

    if payment["status"] == PAYMENT_STATUS_CONFIRMED:
        try:
            await query.edit_message_text(
                PAYMENT_ALREADY_CONFIRMED_MESSAGE,
                reply_markup=None,
            )
        except Exception:
            pass
        return

    user_chat_id = payment["user_chat_id"]
    order_ids = [int(x) for x in str(payment["order_id"]).split(",")] if payment["order_id"] else []

    if prefix == PAY_CB_CONFIRM:
        try:
            result = confirm_payment(payment_id)
        except ValueError:
            try:
                await query.edit_message_text(
                    PAYMENT_ACTION_NOOP_TO_ADMIN,
                    reply_markup=None,
                )
            except Exception:
                pass
            return

        if result.get("already_confirmed"):
            try:
                await query.edit_message_text(
                    PAYMENT_ALREADY_CONFIRMED_MESSAGE,
                    reply_markup=None,
                )
            except Exception:
                pass
            return

        for oid in order_ids:
            try:
                advance_order_to_next_stage(oid)
            except ValueError:
                pass

        try:
            await query.edit_message_text(
                f"✅ پرداخت #{payment_id} تایید شد.",
                reply_markup=None,
            )
        except Exception:
            pass

        try:
            await context.bot.send_message(
                chat_id=user_chat_id,
                text="✅ پرداخت شما تایید شد.\nسفارشتون در حال آماده‌سازیه، ممنون از خریدتون 🌸"
            )
        except Exception:
            pass

    elif prefix == PAY_CB_REJECT_REASON:
        parts = data.split(":")
        if len(parts) != 3:
            return
        reason = parts[1]
        if reason not in _ALL_REJECT_REASONS:
            return
        try:
            record_review_result(payment_id, _REJECT_REASON_TO_PAYMENT_STATUS[reason])
        except ValueError:
            try:
                await query.edit_message_text(
                    PAYMENT_ACTION_NOOP_TO_ADMIN,
                    reply_markup=None,
                )
            except Exception:
                pass
            return

        try:
            await query.edit_message_text(
                f"❌ پرداخت #{payment_id} رد شد: {reason}.",
                reply_markup=None,
            )
        except Exception:
            pass

        try:
            await context.bot.send_message(
                chat_id=user_chat_id,
                text=REJECT_USER_MESSAGES[reason],
            )
        except Exception:
            pass

    elif prefix in (PAY_CB_STAGE_READY, PAY_CB_STAGE_PREPARING, PAY_CB_STAGE_DONE):
        for oid in order_ids:
            try:
                advance_order_to_next_stage(oid)
            except ValueError:
                pass

        try:
            stage_label = {
                PAY_CB_STAGE_READY: "آماده تحویل",
                PAY_CB_STAGE_PREPARING: "آماده‌سازی",
                PAY_CB_STAGE_DONE: "انجام شده",
            }.get(prefix, prefix)
            await query.edit_message_text(
                f"✅ مرحله «{stage_label}» برای پرداخت #{payment_id} ثبت شد.",
                reply_markup=None,
            )
        except Exception:
            pass

    elif prefix == PAY_CB_REJECT:
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass

# --- Restored from backup for bot.py import compatibility ---

GROUP_CONFIRM_COMMANDS = ("تایید", "تایید پرداخت", "ارسال شد")

async def handle_group_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message

    if not message or not message.reply_to_message:
        return

    # فقط ادمین اجازهٔ تأیید/ارسال دارد. این بررسی *قبل* از هر خواندنی از
    # دیتابیس انجام می‌شود تا عضو عادی گروه نه بتواند پرداخت را تأیید کند و نه
    # چیزی دربارهٔ سفارش یا دانش‌آموز از این مسیر بفهمد.
    # روش و پیام خطا هم همان روشِ رایج پروژه است (_require_admin).
    if not await _require_admin(update):
        return

    text = (message.text or "").strip()

    if text not in GROUP_CONFIRM_COMMANDS:
        return

    from database import get_payment_by_group_message, confirm_payment, mark_order_shipped

    payment = get_payment_by_group_message(message.reply_to_message.message_id)

    if not payment:
        return

    payment_id = payment["id"]
    user_chat_id = payment["user_chat_id"]
    confirmed = payment["confirmed"]
    shipped = payment["shipped"]

    if text in ("تایید", "تایید پرداخت"):
        if confirmed:
            try:
                await message.reply_text("این پرداخت قبلاً تایید شده بود. ✅")
            except Exception:
                pass
            return

        try:
            confirm_payment(payment_id)
        except ValueError:
            try:
                await message.reply_text(
                    "این پرداخت نمی‌تواند تایید شود (سفارش منقضی شده است). ❌",
                    reply_markup=None,
                )
            except Exception:
                pass
            return

        try:
            await context.bot.send_message(
                chat_id=user_chat_id,
                text="✅ پرداخت شما تایید شد.\nسفارشتون در حال آماده‌سازیه، ممنون از خریدتون 🌸"
            )
        except Exception:
            pass

        try:
            await message.reply_text("تاییدیه برای دانش‌آموز ارسال شد. ✅")
        except Exception:
            pass
        return

    if text == "ارسال شد":
        if not confirmed:
            try:
                await message.reply_text(
                    "⚠️ این سفارش هنوز تایید پرداخت نشده. اول با ریپلای «تایید» پرداختش رو تایید کن."
                )
            except Exception:
                pass
            return

        if shipped:
            try:
                await message.reply_text("قبلاً پیام ارسال سفارش برای این مشتری فرستاده شده بود. 📦")
            except Exception:
                pass
            return

        mark_order_shipped(payment_id)

        try:
            await context.bot.send_message(
                chat_id=user_chat_id,
                text="📦 سفارش شما ارسال شد!\nبه‌زودی بهتون می‌رسه، ممنون از خریدتون 🌸"
            )
        except Exception:
            pass

        try:
            await message.reply_text("پیام ارسال سفارش برای دانش‌آموز فرستاده شد. 📦")
        except Exception:
            pass
        return

async def cmd_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _require_admin(update):
        return

    args = context.args

    if args:
        date_str = args[0].strip()
        if date_str in ("امروز", "today"):
            try:
                from zoneinfo import ZoneInfo
                date_str = datetime.now(ZoneInfo("Asia/Tehran")).strftime("%Y-%m-%d")
            except Exception:
                from datetime import timezone, timedelta
                date_str = datetime.now(timezone(timedelta(hours=3, minutes=30))).strftime("%Y-%m-%d")
    else:
        try:
            from zoneinfo import ZoneInfo
            date_str = datetime.now(ZoneInfo("Asia/Tehran")).strftime("%Y-%m-%d")
        except Exception:
            from datetime import timezone, timedelta
            date_str = datetime.now(timezone(timedelta(hours=3, minutes=30))).strftime("%Y-%m-%d")

    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        await update.message.reply_text(
            "❌ فرمت تاریخ درست نیست.\n"
            "استفاده صحیح: /orders 2026-07-26 (میلادی)، یا فقط /orders برای امروز."
        )
        return

    from export_excel import build_orders_excel

    with tempfile.TemporaryDirectory() as tmp_dir:
        path = os.path.join(tmp_dir, f"orders_{date_str}.xlsx")
        count = build_orders_excel(path, date_str=date_str)

        if count == 0:
            await update.message.reply_text(f"📭 هیچ سفارشی برای تاریخ {date_str} ثبت نشده.")
            return

        with open(path, "rb") as f:
            ok = await _safe_send_document(
                context.bot,
                chat_id=update.effective_chat.id,
                filename=f"orders_{date_str}.xlsx",
                caption=f"🗓️ سفارش‌های {date_str} — {count} سفارش",
                file_obj=f,
            )
        if not ok:
            await _safe_reply_text(update, FILE_SEND_FAILED_MESSAGE)

async def cmd_exam_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from export_excel import build_exams_excel

    with tempfile.TemporaryDirectory() as tmp_dir:
        path = os.path.join(tmp_dir, "exams_export.xlsx")
        count = build_exams_excel(path)

        with open(path, "rb") as f:
            await _safe_send_document(
                context.bot,
                chat_id=update.effective_chat.id,
                filename="exams_export.xlsx",
                caption=(
                    f"📚 لیست آزمون‌های ثبت‌شده — {count} آزمون\n\n"
                    "شیت «خلاصه پوشش» نشون می‌ده کدوم ترکیب مؤسسه/درس/پایه هنوز "
                    "هیچ آزمونی نداره."
                ),
                file_obj=f,
            )

async def cmd_my_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    entries = get_orders_by_user(user.id, limit=5)

    if not entries:
        await update.message.reply_text("هنوز سفارشی برای شما ثبت نشده.")
        return

    blocks = []
    for entry in entries:
        order = entry["order"]
        items = entry["items"]

        lines = [f"📌 سفارش #{order['id']} — {order.get('status')}"]
        for item in items:
            title = item.get("chapter") or item.get("file_name") or "-"
            lines.append(f"  • {title} — {format_price(item.get('price'))}")
        lines.append(f"💰 جمع: {format_price(order.get('price'))}")
        lines.append(f"📅 تاریخ ثبت: {order.get('created_at')}")

        blocks.append("\n".join(lines))

    await update.message.reply_text(
        "🧾 آخرین سفارش‌های شما:\n\n" + "\n\n".join(blocks)
    )

async def cmd_notify_available(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _require_admin(update):
        return

    args = context.args

    if len(args) < 3:
        await update.message.reply_text(
            "استفاده:\n/notify_available <استاد> <پایه> <فصل>\n"
            "مثال: /notify_available امامی دهم فصل ۲"
        )
        return

    teacher, grade = args[0], args[1]
    chapter = " ".join(args[2:])

    interested = get_uninotified_interest(teacher, grade, chapter)

    if not interested:
        await update.message.reply_text("کسی برای این فصل ثبت علاقه نکرده بود.")
        return

    sent = 0
    for row in interested:
        try:
            await context.bot.send_message(
                chat_id=row["user_id"],
                text=(
                    f"🎉 خبر خوب! جزوه استاد {teacher} - پایه {grade} - {chapter} "
                    "الان موجود شد و می‌تونی سفارشش بدی.\n"
                    "برای سفارش، دوباره به ربات پیام بده و از منو انتخابش کن."
                )
            )
            sent += 1
        except Exception:
            pass

    mark_interest_notified([row["id"] for row in interested])

    await update.message.reply_text(
        f"✅ به {sent} نفر از {len(interested)} نفری که منتظر این فصل بودن پیام ارسال شد."
    )

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _require_owner(update):
        return

    today = get_local_date()

    total_users = count_total_users()
    users_with_phone = count_users_with_phone()
    new_today = count_new_users(today)
    total_orders = count_total_orders()
    orders_today = count_orders_today()
    expired_orders = count_orders_by_status(ORDER_STATUS_EXPIRED)
    dau = count_dau(today)
    mau = count_mau(today)

    text = (
        f"📊 آمار ربات — {today}\n\n"
        f"👥 کل کاربران ثبت‌شده: {total_users}\n"
        f"📞 کاربران دارای شماره تلفن: {users_with_phone}\n"
        f"🆕 کاربران جدید امروز: {new_today}\n"
        f"📋 کل سفارش‌ها: {total_orders}\n"
        f"📅 سفارش‌های امروز: {orders_today}\n"
        f"⏳ سفارش‌های منقضی شده: {expired_orders}\n"
        f"🟢 کاربران فعال امروز (DAU): {dau}\n"
        f"📅 کاربران فعال ۳۰ روزه (MAU): {mau}"
    )

    await update.message.reply_text(text)

async def choose_konkur_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    restart_state = await _handle_restart(update, context)
    if restart_state is not None:
        return restart_state

    konkur_state = await _konkur_guard(update, context, need=())
    if konkur_state is not None:
        return konkur_state

    text = update.message.text

    if text == BACK_BUTTON:
        await update.message.reply_text(
            "📚 آزمون‌ها\n\nمؤسسه رو انتخاب کن:",
            reply_markup=exam_provider_keyboard()
        )
        return CHOOSING_EXAM_PROVIDER

    konkur_type = konkur_type_from_label(text)
    if konkur_type is None:
        await update.message.reply_text(
            "لطفاً نوع کنکور را انتخاب کنید.",
            reply_markup=konkur_type_keyboard()
        )
        return CHOOSING_KONKUR_TYPE

    konkur = _get_user_dict(context, "konkur")
    if konkur is None:
        konkur = {}
        context.user_data["konkur"] = konkur

    konkur["exam_type"] = konkur_type
    konkur.pop("year", None)
    konkur.pop("session", None)
    konkur.pop("needs_session", None)
    konkur.pop("subject", None)
    await update.message.reply_text(
        "سال کنکور را انتخاب کنید:",
        reply_markup=konkur_year_keyboard(konkur_type)
    )
    return CHOOSING_KONKUR_YEAR

async def choose_konkur_year(update: Update, context: ContextTypes.DEFAULT_TYPE):
    restart_state = await _handle_restart(update, context)
    if restart_state is not None:
        return restart_state

    konkur_state = await _konkur_guard(update, context)
    if konkur_state is not None:
        return konkur_state

    text = update.message.text

    if text == BACK_BUTTON:
        await update.message.reply_text(
            "نوع کنکور را انتخاب کنید:",
            reply_markup=konkur_type_keyboard()
        )
        return CHOOSING_KONKUR_TYPE

    year = konkur_year_from_label(text)
    konkur = _get_user_dict(context, "konkur")
    if konkur is None:
        return await _conversation_expired(update, context, CHOOSING_EXAM_PROVIDER)

    if year is None:
        await update.message.reply_text(
            "لطفاً سال را انتخاب کنید.",
            reply_markup=konkur_year_keyboard(konkur["exam_type"])
        )
        return CHOOSING_KONKUR_YEAR

    konkur["year"] = year
    sessions = get_konkur_sessions(konkur["exam_type"], year)

    if sessions:
        konkur["needs_session"] = True
        konkur.pop("session", None)
        await update.message.reply_text(
            "نوبت را انتخاب کنید:",
            reply_markup=konkur_session_keyboard()
        )
        return CHOOSING_KONKUR_SESSION

    konkur.pop("needs_session", None)
    konkur.pop("session", None)
    return await _go_to_konkur_subject(update, context)

async def choose_konkur_session(update: Update, context: ContextTypes.DEFAULT_TYPE):
    restart_state = await _handle_restart(update, context)
    if restart_state is not None:
        return restart_state

    konkur_state = await _konkur_guard(update, context)
    if konkur_state is not None:
        return konkur_state

    text = update.message.text

    if text == BACK_BUTTON:
        konkur = context.user_data.get("konkur") or {}
        await update.message.reply_text(
            "سال کنکور را انتخاب کنید:",
            reply_markup=konkur_year_keyboard(konkur.get("exam_type", KONKUR_TYPES[0]))
        )
        return CHOOSING_KONKUR_YEAR

    session = get_konkur_session_value(text)
    if session is None:
        await update.message.reply_text(
            "لطفاً نوبت را انتخاب کنید.",
            reply_markup=konkur_session_keyboard()
        )
        return CHOOSING_KONKUR_SESSION

    konkur = _get_user_dict(context, "konkur")
    if konkur is None:
        return await _conversation_expired(update, context, CHOOSING_EXAM_PROVIDER)

    konkur["session"] = session
    return await _go_to_konkur_subject(update, context)

async def choose_konkur_subject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    restart_state = await _handle_restart(update, context)
    if restart_state is not None:
        return restart_state

    konkur_state = await _konkur_guard(update, context, need=("exam_type", "year"))
    if konkur_state is not None:
        return konkur_state

    text = update.message.text

    if text == BACK_BUTTON:
        konkur = context.user_data.get("konkur") or {}
        if konkur.get("needs_session"):
            await update.message.reply_text(
                "نوبت را انتخاب کنید:",
                reply_markup=konkur_session_keyboard()
            )
            return CHOOSING_KONKUR_SESSION
        await update.message.reply_text(
            "سال کنکور را انتخاب کنید:",
            reply_markup=konkur_year_keyboard(konkur.get("exam_type", KONKUR_TYPES[0]))
        )
        return CHOOSING_KONKUR_YEAR

    subject = konkur_subject_from_label(text)
    if subject is None:
        await update.message.reply_text(
            "لطفاً رشته را انتخاب کنید.",
            reply_markup=konkur_subject_keyboard()
        )
        return CHOOSING_KONKUR_SUBJECT

    konkur = _get_user_dict(context, "konkur")
    if konkur is None:
        return await _conversation_expired(update, context, CHOOSING_EXAM_PROVIDER)

    konkur["subject"] = subject

    exam = get_konkur_exam(
        konkur["exam_type"],
        konkur["year"],
        konkur.get("session"),
        subject
    )

    if not exam:
        await update.message.reply_text(
            "❌ هنوز این آزمون ثبت نشده است.",
            reply_markup=main_keyboard()
        )
        context.user_data.pop("konkur", None)
        return ConversationHandler.END

    has_answer = bool(exam.get("answer_file_id"))
    await update.message.reply_text(
        "آزمون پیدا شد. چه کاری می‌خواهید انجام دهید؟",
        reply_markup=konkur_action_keyboard(has_answer=has_answer)
    )
    return CHOOSING_KONKUR_ACTION

async def choose_konkur_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    restart_state = await _handle_restart(update, context)
    if restart_state is not None:
        return restart_state

    konkur_state = await _konkur_guard(update, context, need=("exam_type", "year"))
    if konkur_state is not None:
        return konkur_state

    text = update.message.text

    if text == BACK_BUTTON:
        return await _go_to_konkur_subject(update, context)

    action = konkur_action_from_label(text)
    if action is None:
        konkur = context.user_data.get("konkur")
        exam = get_konkur_exam(
            konkur["exam_type"],
            konkur["year"],
            konkur.get("session"),
            konkur["subject"]
        )
        has_answer = bool(exam.get("answer_file_id")) if exam else False
        await update.message.reply_text(
            "لطفاً یکی از گزینه‌ها را انتخاب کنید.",
            reply_markup=konkur_action_keyboard(has_answer=has_answer)
        )
        return CHOOSING_KONKUR_ACTION

    konkur = _get_user_dict(context, "konkur")
    if konkur is None or not konkur.get("subject"):
        return await _conversation_expired(update, context, CHOOSING_EXAM_PROVIDER)

    exam = get_konkur_exam(
        konkur["exam_type"],
        konkur["year"],
        konkur.get("session"),
        konkur["subject"]
    )

    if not exam:
        await update.message.reply_text(
            "❌ این آزمون دیگر وجود ندارد.",
            reply_markup=main_keyboard()
        )
        context.user_data.pop("konkur", None)
        return ConversationHandler.END

    if action == "question":
        file_id = exam.get("question_file_id")
        if not file_id:
            await update.message.reply_text(
                "❌ فایل دفترچه آزمون برای این آزمون ثبت نشده است.",
                reply_markup=konkur_action_keyboard(has_answer=bool(exam.get("answer_file_id")))
            )
            return CHOOSING_KONKUR_ACTION

        await _safe_send_document(
            context.bot,
            chat_id=update.effective_chat.id,
            document=file_id,
            caption="📘 دفترچه آزمون",
        )
    elif action == "answer":
        file_id = exam.get("answer_file_id")
        if not file_id:
            await update.message.reply_text(
                "❌ فایل کلیدنامه برای این آزمون ثبت نشده است.",
                reply_markup=konkur_action_keyboard(has_answer=bool(exam.get("answer_file_id")))
            )
            return CHOOSING_KONKUR_ACTION

        await _safe_send_document(
            context.bot,
            chat_id=update.effective_chat.id,
            document=file_id,
            caption="📕 کلیدنامه",
        )

    return CHOOSING_KONKUR_ACTION

async def cmd_add_exam(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _require_admin(update):
        return ConversationHandler.END

    context.user_data["admin_exam"] = {}

    await update.message.reply_text(
        "➕ ثبت آزمون جدید\n\nمؤسسه رو انتخاب کن:",
        reply_markup=exam_provider_keyboard()
    )
    return ADMIN_EXAM_PROVIDER

async def admin_cancel_exam(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("admin_exam", None)
    await update.message.reply_text("لغو شد.", reply_markup=remove_keyboard())
    return ConversationHandler.END

async def admin_choose_provider(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _require_admin(update):
        return ConversationHandler.END

    text = update.message.text

    if text == BACK_BUTTON:
        return await admin_cancel_exam(update, context)

    provider = provider_from_label(text)

    if provider is None:
        clean_text = re.sub(r'[^\w\s]', '', text).strip()
        for p in EXAM_PROVIDERS:
            if clean_text == p:
                provider = p
                break

    if provider is None:
        await update.message.reply_text("لطفاً یکی از گزینه‌های زیر را انتخاب کنید.")
        return ADMIN_EXAM_PROVIDER

    data = _ensure_admin_exam(context)

    if is_final_exam_provider(provider):
        data["provider"] = "نهایی"
        data["grade"] = FINAL_EXAM_GRADE
        await update.message.reply_text(
            "درس رو انتخاب کن:",
            reply_markup=exam_subject_keyboard(provider, grade=FINAL_EXAM_GRADE)
        )
        return ADMIN_EXAM_SUBJECT

    if provider == "ماز":
        data["provider"] = "ماز"
        await update.message.reply_text(
            "رشته رو انتخاب کن:",
            reply_markup=exam_admin_field_keyboard()
        )
        return ADMIN_EXAM_FIELD

    data["provider"] = provider
    await update.message.reply_text(
        "پایه رو انتخاب کن:",
        reply_markup=exam_grade_keyboard()
    )
    return ADMIN_EXAM_GRADE

async def admin_choose_exam_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _require_admin(update):
        return ConversationHandler.END

    text = (update.message.text or "").strip()
    data = _ensure_admin_exam(context)

    if text == BACK_BUTTON:
        await update.message.reply_text("مؤسسه رو انتخاب کن:", reply_markup=exam_provider_keyboard())
        return ADMIN_EXAM_PROVIDER

    if text == "هم ریاضی فیزیک هم تجربی":
        field = "ریاضی فیزیک,تجربی"
    elif text == "📐 ریاضی فیزیک":
        field = "ریاضی فیزیک"
    elif text == "🧪 تجربی":
        field = "تجربی"
    elif text == "📖 انسانی":
        field = "انسانی"
    else:
        await update.message.reply_text(
            "لطفاً یکی از گزینه‌های زیر را انتخاب کنید.",
            reply_markup=exam_admin_field_keyboard()
        )
        return ADMIN_EXAM_FIELD

    data["field"] = field
    await update.message.reply_text(
        "پایه رو انتخاب کن:",
        reply_markup=exam_grade_keyboard()
    )
    return ADMIN_EXAM_GRADE

async def admin_choose_grade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _require_admin(update):
        return ConversationHandler.END

    text = update.message.text
    data = _ensure_admin_exam(context)

    if not data.get("provider"):
        await update.message.reply_text(
            "اول مؤسسه را انتخاب کنید:", reply_markup=exam_provider_keyboard()
        )
        return ADMIN_EXAM_PROVIDER

    provider = data["provider"]

    if text == BACK_BUTTON:
        if provider == "ماز":
            await update.message.reply_text("رشته رو انتخاب کن:", reply_markup=exam_admin_field_keyboard())
            return ADMIN_EXAM_FIELD
        await update.message.reply_text("مؤسسه رو انتخاب کن:", reply_markup=exam_provider_keyboard())
        return ADMIN_EXAM_PROVIDER

    grade = exam_grade_from_label(text)
    if grade is None:
        await update.message.reply_text("لطفاً یکی از گزینه‌های زیر را انتخاب کنید.")
        return ADMIN_EXAM_GRADE

    data["grade"] = grade
    if provider == "ماز":
        if data.get("field") == "انسانی":
            await update.message.reply_text(
                "نام درس رو به‌صورت متن بفرست (پسوند پایه لازم نیست):",
                reply_markup=restart_keyboard()
            )
            return ADMIN_EXAM_SUBJECT
        await update.message.reply_text(
            "درس رو انتخاب کن:",
            reply_markup=exam_subject_keyboard(provider, grade=grade)
        )
        return ADMIN_EXAM_SUBJECT

    await update.message.reply_text(
        "درس رو انتخاب کن:",
        reply_markup=exam_subject_keyboard(provider, grade=grade)
    )
    return ADMIN_EXAM_SUBJECT

async def admin_choose_subject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _require_admin(update):
        return ConversationHandler.END

    text = update.message.text
    data = _ensure_admin_exam(context)

    if not data.get("provider"):
        await update.message.reply_text(
            "اول مؤسسه را انتخاب کنید:", reply_markup=exam_provider_keyboard()
        )
        return ADMIN_EXAM_PROVIDER

    provider = data["provider"]
    grade = data.get("grade")

    if text == BACK_BUTTON:
        if is_final_exam_provider(provider):
            await update.message.reply_text("مؤسسه رو انتخاب کن:", reply_markup=exam_provider_keyboard())
            return ADMIN_EXAM_PROVIDER
        await update.message.reply_text("پایه رو انتخاب کن:", reply_markup=exam_grade_keyboard())
        return ADMIN_EXAM_GRADE

    if provider == "ماز" and data.get("field") == "انسانی":
        subject = (text or "").strip()
        if grade:
            suffix = f" {grade}"
            if subject.endswith(suffix):
                subject = subject[: -len(suffix)].strip()
        if not subject:
            await update.message.reply_text(
                "نام درس خالی است. لطفاً نام درس را بفرست (پسوند پایه لازم نیست):",
                reply_markup=restart_keyboard()
            )
            return ADMIN_EXAM_SUBJECT
        data["subject"] = subject
    else:
        subject = subject_from_label(text, provider, grade=grade)
        if subject is None:
            if provider == "ماز" and data.get("field") == "انسانی":
                await update.message.reply_text(
                    "نام درس رو به‌صورت متن بفرست (پسوند پایه لازم نیست):",
                    reply_markup=restart_keyboard()
                )
            else:
                await update.message.reply_text(
                    "لطفاً یکی از گزینه‌های زیر را انتخاب کنید.",
                    reply_markup=exam_subject_keyboard(provider, grade=grade)
                )
            return ADMIN_EXAM_SUBJECT
        if provider == "ماز" and grade:
            suffix = f" {grade}"
            if subject.endswith(suffix):
                subject = subject[: -len(suffix)].strip()
        data["subject"] = subject
    await update.message.reply_text(
        "تاریخ آزمون رو به‌صورت متن بفرست (مثلاً «۲۸ فروردین ۱۴۰۵»):",
        reply_markup=restart_keyboard()
    )
    return ADMIN_EXAM_DATE

async def admin_receive_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _require_admin(update):
        return ConversationHandler.END

    text = update.message.text
    data = _ensure_admin_exam(context)

    if not data.get("provider"):
        await update.message.reply_text(
            "اول مؤسسه را انتخاب کنید:", reply_markup=exam_provider_keyboard()
        )
        return ADMIN_EXAM_PROVIDER

    provider = data["provider"]

    if text == BACK_BUTTON:
        if provider == "ماز":
            if data.get("field") == "انسانی":
                await update.message.reply_text(
                    "نام درس رو به‌صورت متن بفرست (پسوند پایه لازم نیست):",
                    reply_markup=restart_keyboard()
                )
            else:
                await update.message.reply_text(
                    "درس رو انتخاب کن:",
                    reply_markup=exam_subject_keyboard(provider, grade=data.get("grade"))
                )
            return ADMIN_EXAM_SUBJECT
        if is_final_exam_provider(provider):
            await update.message.reply_text("درس رو انتخاب کن:", reply_markup=exam_subject_keyboard(provider))
            return ADMIN_EXAM_SUBJECT

        await update.message.reply_text("پایه رو انتخاب کن:", reply_markup=exam_grade_keyboard())
        return ADMIN_EXAM_GRADE

    data["exam_date"] = text.strip()

    await update.message.reply_text(
        "📄 فایل PDF دفترچه سؤال رو بفرست:",
        reply_markup=restart_keyboard()
    )
    return ADMIN_EXAM_QUESTION_FILE

async def admin_receive_question_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _require_admin(update):
        return ConversationHandler.END

    text = getattr(update.message, "text", None)

    if text == BACK_BUTTON:
        await update.message.reply_text(
            "تاریخ آزمون رو به‌صورت متن بفرست:",
            reply_markup=restart_keyboard()
        )
        return ADMIN_EXAM_DATE

    document = update.message.document

    if document is None:
        await update.message.reply_text("لطفاً فایل PDF دفترچه سؤال رو ارسال کن.")
        return ADMIN_EXAM_QUESTION_FILE

    if document.file_size and document.file_size > MAX_FILE_SIZE_BYTES:
        await update.message.reply_text(
            f"⚠️ حجم این فایل بیش از حد مجازه (حداکثر {MAX_FILE_SIZE_MB} مگابایت)."
        )
        return ADMIN_EXAM_QUESTION_FILE

    file_name = os.path.basename(document.file_name or "").strip() or "question.pdf"

    with tempfile.TemporaryDirectory() as tmp_dir:
        local_path = os.path.normpath(os.path.join(tmp_dir, file_name))
        try:
            if os.path.commonpath([tmp_dir, local_path]) != os.path.commonpath([tmp_dir]):
                file_name = "question.pdf"
                local_path = os.path.normpath(os.path.join(tmp_dir, file_name))
        except Exception:
            file_name = "question.pdf"
            local_path = os.path.normpath(os.path.join(tmp_dir, file_name))

        if not await _safe_download(context.bot, document.file_id, local_path):
            await _safe_reply_text(
                update, FILE_DOWNLOAD_FAILED_MESSAGE, admin_skip_keyboard()
            )
            return ADMIN_EXAM_QUESTION_FILE

        try:
            pages = count_pages(local_path, file_name)
        except PageCountError as e:
            await update.message.reply_text(str(e))
            return ADMIN_EXAM_QUESTION_FILE

    data = _get_user_dict(context, "admin_exam")
    if data is None:
        return await _conversation_expired(update, context, ADMIN_EXAM_PROVIDER)

    data["question_file_id"] = document.file_id
    data["question_pages"] = pages

    await update.message.reply_text(
        f"✅ دفترچه سؤال ثبت شد ({pages} صفحه).\n\n"
        "📝 فایل PDF پاسخنامه رو بفرست (اگه نداری، دکمه‌ی زیر رو بزن):",
        reply_markup=admin_skip_keyboard()
    )
    return ADMIN_EXAM_ANSWER_FILE

async def admin_receive_answer_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _require_admin(update):
        return ConversationHandler.END

    text = getattr(update.message, "text", None)

    if text == BACK_BUTTON:
        await update.message.reply_text(
            "📄 فایل PDF دفترچه سؤال رو بفرست:",
            reply_markup=restart_keyboard()
        )
        return ADMIN_EXAM_QUESTION_FILE

    if text == ADMIN_SKIP_BUTTON:
        return await _save_admin_exam(update, context, answer_file_id=None, answer_pages=None)

    document = update.message.document

    if document is None:
        await update.message.reply_text("لطفاً فایل PDF پاسخنامه رو بفرست، یا دکمه‌ی «رد کردن» رو بزن.")
        return ADMIN_EXAM_ANSWER_FILE

    if document.file_size and document.file_size > MAX_FILE_SIZE_BYTES:
        await update.message.reply_text(
            f"⚠️ حجم این فایل بیش از حد مجازه (حداکثر {MAX_FILE_SIZE_MB} مگابایت)."
        )
        return ADMIN_EXAM_ANSWER_FILE

    file_name = os.path.basename(document.file_name or "").strip() or "answer.pdf"

    with tempfile.TemporaryDirectory() as tmp_dir:
        local_path = os.path.normpath(os.path.join(tmp_dir, file_name))
        try:
            if os.path.commonpath([tmp_dir, local_path]) != os.path.commonpath([tmp_dir]):
                file_name = "answer.pdf"
                local_path = os.path.normpath(os.path.join(tmp_dir, file_name))
        except Exception:
            file_name = "answer.pdf"
            local_path = os.path.normpath(os.path.join(tmp_dir, file_name))

        if not await _safe_download(context.bot, document.file_id, local_path):
            await _safe_reply_text(
                update, FILE_DOWNLOAD_FAILED_MESSAGE, admin_skip_keyboard()
            )
            return ADMIN_EXAM_ANSWER_FILE

        try:
            pages = count_pages(local_path, file_name)
        except PageCountError as e:
            await update.message.reply_text(str(e))
            return ADMIN_EXAM_ANSWER_FILE

    return await _save_admin_exam(update, context, answer_file_id=document.file_id, answer_pages=pages)

async def cmd_add_booklet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _require_admin(update):
        return ConversationHandler.END

    context.user_data["admin_booklet"] = {}

    await update.message.reply_text(
        "➕ ثبت جزوه جدید\n\nاستاد رو انتخاب کن:",
        reply_markup=main_keyboard()
    )
    return ADMIN_BOOKLET_TEACHER

async def admin_cancel_booklet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("admin_booklet", None)
    await update.message.reply_text("لغو شد.", reply_markup=remove_keyboard())
    return ConversationHandler.END

async def admin_choose_booklet_teacher(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _require_admin(update):
        return ConversationHandler.END

    text = update.message.text

    if text == BACK_BUTTON:
        return await admin_cancel_booklet(update, context)

    teacher = teacher_from_label(text)
    if teacher is None:
        await update.message.reply_text("لطفاً یکی از گزینه‌های زیر را انتخاب کنید.")
        return ADMIN_BOOKLET_TEACHER

    data = _ensure_admin_booklet(context)
    data["teacher"] = teacher

    # برای استاد نظری، درس‌های از پیش تعریف شده هستند
    if teacher == "نظری":
        data["subject"] = "نظری"
        await update.message.reply_text(
            "پایه رو انتخاب کن:",
            reply_markup=grade_keyboard()
        )
        return ADMIN_BOOKLET_GRADE

    # برای امامی و کوشکی، درس انتخاب می‌شود
    await update.message.reply_text(
        "درس رو انتخاب کن:",
        reply_markup=ReplyKeyboardMarkup(
            [[s] for s in ["ریاضی", "فیزیک", "شیمی", "زیست", "زمین", "تجربی", "انسانی"]] + _nav_rows(),
            resize_keyboard=True
        )
    )
    return ADMIN_BOOKLET_SUBJECT

async def admin_choose_booklet_subject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _require_admin(update):
        return ConversationHandler.END

    text = update.message.text
    data = _ensure_admin_booklet(context)

    if not data.get("teacher"):
        await update.message.reply_text("اول استاد را انتخاب کنید:", reply_markup=main_keyboard())
        return ADMIN_BOOKLET_TEACHER

    if text == BACK_BUTTON:
        await update.message.reply_text("استاد رو انتخاب کن:", reply_markup=main_keyboard())
        return ADMIN_BOOKLET_TEACHER

    data["subject"] = text

    await update.message.reply_text(
        "پایه رو انتخاب کن:",
        reply_markup=grade_keyboard()
    )
    return ADMIN_BOOKLET_GRADE

async def admin_choose_booklet_grade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _require_admin(update):
        return ConversationHandler.END

    text = update.message.text
    data = _ensure_admin_booklet(context)

    if not data.get("teacher") or not data.get("subject"):
        await update.message.reply_text(
            "اول استاد و درس را انتخاب کنید:", reply_markup=main_keyboard()
        )
        return ADMIN_BOOKLET_TEACHER

    if text == BACK_BUTTON:
        teacher = data["teacher"]
        if teacher == "نظری":
            await update.message.reply_text("استاد رو انتخاب کن:", reply_markup=main_keyboard())
            return ADMIN_BOOKLET_TEACHER
        else:
            await update.message.reply_text(
                "درس رو انتخاب کن:",
                reply_markup=ReplyKeyboardMarkup(
                    [[s] for s in ["ریاضی", "فیزیک", "شیمی", "زیست", "زمین", "تجربی", "انسانی"]] + _nav_rows(),
                    resize_keyboard=True
                )
            )
            return ADMIN_BOOKLET_SUBJECT

    grade = grade_from_label(text)
    if grade is None:
        await update.message.reply_text("لطفاً یکی از گزینه‌های زیر را انتخاب کنید.")
        return ADMIN_BOOKLET_GRADE

    data["grade"] = grade

    await update.message.reply_text(
        "فصل رو انتخاب کن:",
        reply_markup=chapter_keyboard(grade=grade, teacher=data["teacher"])
    )
    return ADMIN_BOOKLET_CHAPTER

async def admin_choose_booklet_chapter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _require_admin(update):
        return ConversationHandler.END

    text = update.message.text
    data = _ensure_admin_booklet(context)

    if not data.get("teacher") or not data.get("grade"):
        await update.message.reply_text(
            "اطلاعات ناقص است؛ لطفاً از ابتدا /booklet را بفرستید."
        )
        return ADMIN_BOOKLET_TEACHER

    if text == BACK_BUTTON:
        await update.message.reply_text("پایه رو انتخاب کن:", reply_markup=grade_keyboard())
        return ADMIN_BOOKLET_GRADE

    # Extract chapter from label (e.g., "📄 فصل ۱ دهم" -> "فصل ۱")
    chapter = None
    for c in CHAPTERS:
        if c in text:
            chapter = c
            break
    
    if not chapter or chapter not in CHAPTERS:
        await update.message.reply_text("لطفاً یکی از گزینه‌های زیر را انتخاب کنید.")
        return ADMIN_BOOKLET_CHAPTER

    data["chapter"] = chapter

    await update.message.reply_text(
        "عنوان جزوه رو به‌صورت متن بفرست (مثلاً «فصل اول — جبر و هندسه»):",
        reply_markup=restart_keyboard()
    )
    return ADMIN_BOOKLET_TITLE

async def admin_receive_booklet_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _require_admin(update):
        return ConversationHandler.END

    text = update.message.text
    data = _ensure_admin_booklet(context)

    if not data.get("chapter"):
        await update.message.reply_text("اول فصل را انتخاب کنید.")
        return ADMIN_BOOKLET_CHAPTER

    if text == BACK_BUTTON:
        await update.message.reply_text(
            "فصل رو انتخاب کن:",
            reply_markup=chapter_keyboard(grade=data["grade"], teacher=data["teacher"])
        )
        return ADMIN_BOOKLET_CHAPTER

    data["title"] = text.strip()

    # Check duplicate
    if booklet_exists(data["teacher"], data["subject"], data["grade"], data["chapter"], data["title"]):
        await update.message.reply_text(
            f"❌ این جزوه قبلاً ثبت شده است:\n"
            f"{data['teacher']} - {data['subject']} - {data['grade']} - {data['chapter']} - {data['title']}"
        )
        return await admin_cancel_booklet(update, context)

    await update.message.reply_text(
        "کدوم نسخه‌ها موجوده؟ (هر دو رو می‌تونی انتخاب کنی)",
        reply_markup=ReplyKeyboardMarkup(
            [
                ["✅ سیاه‌وسفید"],
                ["✅ رنگی"],
                ["✅ هر دو"],
            ] + _nav_rows(),
            resize_keyboard=True
        )
    )
    return ADMIN_BOOKLET_VERSIONS

async def admin_choose_booklet_versions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _require_admin(update):
        return ConversationHandler.END

    text = update.message.text
    data = _ensure_admin_booklet(context)

    if not data.get("title"):
        await update.message.reply_text("اول عنوان را وارد کنید.")
        return ADMIN_BOOKLET_TITLE

    # اگر قبلاً از ادمین قیمت خواسته شده، ورودی فعلی (عدد یا «بازگشت»)
    # مربوط به قیمت است نه انتخاب نسخه
    # (admin_receive_booklet_price به‌صورت مستقیم در
    # admin_booklet_conv ثبت نشده، پس از اینجا نمایندگی می‌کنیم)
    if "awaiting_price_for" in data:
        return await admin_receive_booklet_price(update, context)

    if text == BACK_BUTTON:
        await update.message.reply_text(
            "عنوان جزوه رو بفرست:",
            reply_markup=restart_keyboard()
        )
        return ADMIN_BOOKLET_TITLE

    has_bw = "سیاه‌وسفید" in text or "هر دو" in text
    has_color = "رنگی" in text or "هر دو" in text

    if not has_bw and not has_color:
        await update.message.reply_text("لطفاً یکی از گزینه‌ها را انتخاب کنید.")
        return ADMIN_BOOKLET_VERSIONS

    data["has_bw"] = has_bw
    data["has_color"] = has_color

    # Get prices
    prices_needed = []
    if has_bw:
        prices_needed.append("سیاه‌وسفید")
    if has_color:
        prices_needed.append("رنگی")

    if not prices_needed:
        await update.message.reply_text("لطفاً حداقل یک نسخه را انتخاب کنید.")
        return ADMIN_BOOKLET_VERSIONS

    # Ask for price(s)
    if len(prices_needed) == 1:
        data["awaiting_price_for"] = prices_needed[0]
        await update.message.reply_text(
            f"قیمت نسخه {prices_needed[0]} رو به تومان بفرست (مثلاً 380000):",
            reply_markup=restart_keyboard()
        )
    else:
        data["awaiting_price_for"] = prices_needed[0]
        await update.message.reply_text(
            f"قیمت نسخه {prices_needed[0]} رو به تومان بفرست (مثلاً 380000):",
            reply_markup=restart_keyboard()
        )
    return ADMIN_BOOKLET_VERSIONS

async def admin_receive_booklet_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _require_admin(update):
        return ConversationHandler.END

    text = update.message.text
    data = _ensure_admin_booklet(context)

    if "awaiting_price_for" not in data:
        await update.message.reply_text("اطلاعات ناقص است؛ لطفاً از ابتدا /booklet را بفرستید.")
        return ADMIN_BOOKLET_TEACHER

    if text == BACK_BUTTON:
        # Go back to version selection
        data.pop("awaiting_price_for", None)
        await update.message.reply_text(
            "کدوم نسخه‌ها موجوده؟",
            reply_markup=ReplyKeyboardMarkup(
                [
                    ["✅ سیاه‌وسفید"],
                    ["✅ رنگی"],
                    ["✅ هر دو"],
                ] + _nav_rows(),
                resize_keyboard=True
            )
        )
        return ADMIN_BOOKLET_VERSIONS

    try:
        price = int(text.strip().replace(",", "").replace("٬", ""))
    except ValueError:
        await update.message.reply_text("لطفاً قیمت رو به عدد بفرست (مثلاً 380000).")
        return ADMIN_BOOKLET_VERSIONS

    color_key = data["awaiting_price_for"]
    if color_key == "سیاه‌وسفید":
        data["price_bw"] = price
    else:
        data["price_color"] = price

    # Check if more prices needed
    remaining = []
    if data.get("has_bw") and "price_bw" not in data:
        remaining.append("سیاه‌وسفید")
    if data.get("has_color") and "price_color" not in data:
        remaining.append("رنگی")

    if remaining:
        data["awaiting_price_for"] = remaining[0]
        await update.message.reply_text(
            f"قیمت نسخه {remaining[0]} رو به تومان بفرست (مثلاً 580000):",
            reply_markup=restart_keyboard()
        )
        return ADMIN_BOOKLET_VERSIONS

    # All prices received, save booklet
    return await _save_admin_booklet(update, context)

