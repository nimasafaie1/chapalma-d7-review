"""DEPRECATED / منسوخ — این تست دیگر اجرا نمی‌شود.

دلیل انسداد:
  • این فایل از `handlers.handle_receipt_button` استفاده می‌کرد که در بازطراحی
    مسیر رسید پرداخت حذف شد و با `handle_receipt_callback` جایگزین شد.
  • فرمت callbackهای این تست (`receipt:confirm|ready|pickup|ship`) دیگر وجود
    ندارد؛ معماری فعلی از `pay_*` و دکمه‌های per-order استفاده می‌کند.
  • فیلدهای `confirmed/shipped/ready` در تست‌های قدیمی با مدل وضعیت فعلی
    (`status` + `rejected*`) هم‌خوان نیستند.

جایگزین:
  • `tests/test_reject_idempotency.py` — idempotency و concurrency رد پرداخت،
    رد→تأیید، تأیید→رد، رد چندسفارشی، تأیید رسید جدید.
  • سوئیت ۲۳تستی `%TEMP%/kilo/test_keyboard.py` — تأیید، منوی رد، مراحل
    تحویل، بلغ/عدم‌تأیید، پرداخت چندسفارشی، دکمه‌های per-order.

این فایل عمداً هیچ Handler قدیمی را احیا نمی‌کند.
"""

import unittest

NOTICE = (
    "test_receipt_buttons: DEPRECATED/SKIPPED — "
    "removed API handle_receipt_button and legacy receipt:* callbacks; "
    "see tests/test_reject_idempotency.py and the 23-test suite."
)


class TestReceiptButtonsDeprecated(unittest.TestCase):
    @unittest.skip(NOTICE)
    def test_deprecated(self):
        pass


def run():
    print(NOTICE)


if __name__ == "__main__":
    run()