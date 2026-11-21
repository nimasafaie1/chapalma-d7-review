"""
خروجی اکسل از اطلاعات جمع‌آوری‌شده (کاربران، سفارش‌ها و آیتم‌های هر سفارش).

نحوه اجرا مستقیم (توی همون پوشه پروژه، کنار bot.py) — خروجی کامل همه‌ی سفارش‌ها:
    python export_excel.py

می‌شود از build_orders_excel() برای گرفتن خروجی یک تاریخ خاص هم استفاده کرد
(همین کار را دستور /orders داخل خود ربات هم انجام می‌دهد).
"""

import pandas as pd

from database import connect


def build_orders_excel(path="export.xlsx", date_str=None):
    """
    اکسل سفارش‌ها را می‌سازد. اگه date_str (به فرمت YYYY-MM-DD) داده بشه،
    فقط سفارش‌های همون روز صادر می‌شن، وگرنه همه‌ی سفارش‌ها.
    تعداد سفارش‌های پیدا شده را برمی‌گرداند.
    """
    conn = connect()

    date_clause = "WHERE date(orders.created_at, '+3 hours', '+30 minutes') = ?" if date_str else ""
    params = (date_str,) if date_str else ()

    users_df = pd.read_sql_query("SELECT * FROM users", conn)

    orders_df = pd.read_sql_query(f"""
        SELECT
            orders.id            AS "شماره سفارش",
            users.full_name      AS "نام دانش‌آموز",
            users.phone          AS "شماره تماس (ثبت‌نام)",
            orders.phone         AS "شماره تماس (سفارش)",
            orders.copies        AS "تعداد جزوه‌ها",
            orders.price         AS "قیمت کل (تومان)",
            orders.delivery      AS "نحوه تحویل",
            orders.address       AS "آدرس",
            orders.status        AS "وضعیت",
            orders.created_at    AS "تاریخ ثبت"
        FROM orders
        LEFT JOIN users ON users.telegram_id = orders.user_id
        {date_clause}
        ORDER BY orders.id DESC
    """, conn, params=params)

    items_clause = (
        "WHERE order_items.order_id IN (SELECT id FROM orders WHERE date(created_at, '+3 hours', '+30 minutes') = ?)"
        if date_str else ""
    )

    items_df = pd.read_sql_query(f"""
        SELECT
            order_items.order_id  AS "شماره سفارش",
            order_items.teacher   AS "استاد",
            order_items.grade     AS "پایه",
            order_items.chapter   AS "فصل / فایل",
            order_items.print_type AS "نوع چاپ",
            order_items.binding   AS "صحافی",
            order_items.quantity  AS "تعداد نسخه",
            order_items.price     AS "قیمت (تومان)",
            order_items.pages     AS "تعداد صفحات"
        FROM order_items
        {items_clause}
        ORDER BY order_items.order_id DESC, order_items.id ASC
    """, conn, params=params)

    conn.close()

    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        if not date_str:
            users_df.to_excel(writer, sheet_name="کاربران", index=False)
        orders_df.to_excel(writer, sheet_name="سفارش‌ها", index=False)
        items_df.to_excel(writer, sheet_name="آیتم‌های سفارش", index=False)

    return len(orders_df)


def _session_label(value):
    """تبدیل مقدار session به برچسب نمایشی."""
    if value == "1":
        return "نوبت اول"
    if value == "2":
        return "نوبت دوم"
    return ""


def build_exams_excel(path="exams_export.xlsx"):
    """
    اکسل آزمون‌های ثبت‌شده را می‌سازد: یک شیت با لیست کامل آزمون‌ها,
    و یک شیت خلاصه که نشون میده کدوم ترکیب ( مؤسسه/درس/پایه) هیچ آزمونی
    نداره. تعداد کل آزمون‌های ثبت‌شده را برمی‌گرداند.
    """
    from prices import EXAM_PROVIDERS, EXAM_SUBJECTS, GRADES
    from database import get_all_exams, get_exam_coverage_summary

    exams = get_all_exams()

    exams_df = pd.DataFrame([
        {
            "شماره": e["id"],
            " مؤسسه": e["provider"],
            "درس": e["subject"],
            "پایه": e["grade"],
            "تاریخ آزمون": e["exam_date"],
            "نوع کنکور": e.get("exam_type") or "",
            "سال کنکور": e.get("year") or "",
            "نوبت": _session_label(e.get("session")),
            "صفحات سؤال": e["question_pages"],
            "پاسخنامه دارد": "بله" if e.get("answer_file_id") else "خیر",
            "question_file_id": e.get("question_file_id") or "",
            "answer_file_id": e.get("answer_file_id") or "",
            "تاریخ ثبت": e["created_at"],
        }
        for e in exams
    ])

    if exams_df.empty:
        exams_df = pd.DataFrame(columns=[
            "شماره", " مؤسسه", "درس", "پایه", "تاریخ آزمون",
            "نوع کنکور", "سال کنکور", "نوبت",
            "صفحات سؤال", "پاسخنامه دارد",
            "question_file_id", "answer_file_id", "تاریخ ثبت"
        ])

    counts = get_exam_coverage_summary()

    coverage_rows = []
    for provider in EXAM_PROVIDERS:
        db_provider = "نهایی" if provider == "امتحان نهایی" else provider
        for subject in EXAM_SUBJECTS:
            for grade in GRADES:
                count = counts.get((db_provider, subject, grade), 0)
                coverage_rows.append({
                    " مؤسسه": provider,
                    "درس": subject,
                    "پایه": grade,
                    "تعداد آزمون ثبت‌شده": count,
                    "وضعیت": "✅ موجود" if count > 0 else "❌ هیچ آزمونی ثبت نشده",
                })

    # پوشش رکوردهای کنکور سراسری — به صورت مستقیم از دیتابیس
    _conn = connect()
    _c = _conn.cursor()
    _c.execute("""
        SELECT exam_type, year, COALESCE(session, '') AS session,
               subject, COUNT(*)
        FROM exams
        WHERE provider = 'کنکور سراسری'
        GROUP BY exam_type, year, COALESCE(session, ''), subject
    """)
    konkur_counts = {}
    for et, yr, sess, subj, cnt in _c.fetchall():
        if sess is None:
            sess = ''
        konkur_counts[(et, yr, sess, subj)] = cnt
    _conn.close()

    konkur_types = ["داخلی", "خارجی"]
    konkur_subjects = ["ریاضی", "تجربی", "انسانی"]
    konkur_years = ["1400", "1401", "1402", "1403", "1404"]
    konkur_sessions = [("نوبت اول", "1"), ("نوبت دوم", "2"), ("بدون نوبت", "")]

    for exam_type in konkur_types:
        for year in konkur_years:
            for session_label, session_val in konkur_sessions:
                for subject in konkur_subjects:
                    count = konkur_counts.get((exam_type, year, session_val, subject), 0)
                    coverage_rows.append({
                        " مؤسسه": "کنکور سراسری",
                        "نوع": exam_type,
                        "سال": year,
                        "نوبت": session_label,
                        "درس": subject,
                        "تعداد آزمون ثبت‌شده": count,
                        "وضعیت": "✅ موجود" if count > 0 else "❌ هیچ آزمونی ثبت نشده",
                    })

    coverage_df = pd.DataFrame(coverage_rows)

    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        coverage_df.to_excel(writer, sheet_name="خلاصه پوشش", index=False)
        exams_df.to_excel(writer, sheet_name="لیست آزمون‌ها", index=False)

    return len(exams_df)


if __name__ == "__main__":
    count = build_orders_excel("export.xlsx")
    print(f"✅ خروجی گرفته شد: export.xlsx  ({count} سفارش)")
