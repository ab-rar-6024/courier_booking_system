import io
from itertools import groupby
from operator import itemgetter

from flask import Flask, render_template, request, redirect, send_file, jsonify, url_for
import pandas as pd
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER

# Import the database connection from separate module
from db import get_db_connection

app = Flask(__name__)
app.secret_key = __import__('os').environ.get("SECRET_KEY", "dev-secret-change-in-prod")

# ------------------------------------------------------------
# DASHBOARD
# ------------------------------------------------------------
@app.route("/")
def dashboard():
    return render_template("dashboard.html")

# ------------------------------------------------------------
# ZONE ENTRY
# ------------------------------------------------------------
@app.route("/zone-entry", methods=["GET", "POST"])
def zone_entry():
    db = get_db_connection()
    cursor = db.cursor()   # RealDictCursor is already set in connection

    if request.method == "POST":
        action = request.form.get("_action", "add")

        # ---------- DELETE ----------
        if action == "delete":
            del_id = request.form.get("del_id")
            if del_id:
                cursor.execute("DELETE FROM zones WHERE id = %s", (del_id,))
                db.commit()
            db.close()
            return redirect("/zone-entry")

        # ---------- ADD or EDIT ----------
        district = request.form.get("district", "").strip()
        rate_zone = request.form.get("rate_zone", "").strip()

        if not district or not rate_zone:
            db.close()
            return "District and Rate Zone are required", 400

        if action == "edit":
            edit_id = request.form.get("edit_id")
            cursor.execute("""
                UPDATE zones SET district = %s, rate_zone = %s
                WHERE id = %s
            """, (district, rate_zone, edit_id))
        else:  # add
            cursor.execute("""
                INSERT INTO zones (district, rate_zone) VALUES (%s, %s)
            """, (district, rate_zone))

        db.commit()
        db.close()
        return redirect("/zone-entry")

    # ---------- GET: show all zones ----------
    cursor.execute("SELECT * FROM zones ORDER BY id DESC")
    zones = [dict(r) for r in cursor.fetchall()]
    db.close()
    return render_template("zone_entry.html", zones=zones)

# ------------------------------------------------------------
# RATE ENTRY
# ------------------------------------------------------------
@app.route("/rate-entry", methods=["GET", "POST"])
def rate_entry():

    def num(value):
        value = str(value).strip()
        return None if value == "" else float(value)

    db = get_db_connection()
    cursor = db.cursor()

    # ----- GET parameters for pagination & search -----
    search = request.args.get("search", "").strip()
    limit_str = request.args.get("limit", "20")
    page = int(request.args.get("page", 1))

    if limit_str == "all":
        limit = None
    else:
        try:
            limit = int(limit_str)
        except ValueError:
            limit = 20

    # ----- POST (Add / Edit / Delete) -----
    if request.method == "POST":

        action = request.form.get("_action", "add")

        # ----- DELETE -----
        if action == "delete":
            cursor.execute(
                "DELETE FROM rates WHERE id=%s",
                (request.form["del_id"],)
            )

            db.commit()
            db.close()

            return redirect(url_for(
                'rate_entry',
                search=search,
                limit=limit_str,
                page=page
            ))

        # ----- ZONE -----
        zone = int(request.form.get("zone") or 5)

        # ----- COMMON VALUES -----
        code = request.form.get("code", "").strip()
        code_fullform = request.form.get("code_fullform", "").strip()
        place = request.form.get("place", "").strip()

        rate_250g = num(request.form.get("rate_250g", ""))
        rate_500g = num(request.form.get("rate_500g", ""))
        rate_500g_1 = num(request.form.get("rate_500g_1", ""))
        rate_1_to_3kg = num(request.form.get("rate_1_to_3kg", ""))
        rate_3_to_10kg = num(request.form.get("rate_3_to_10kg", ""))
        rate_above_10kg = num(request.form.get("rate_above_10kg", ""))
        fuel = num(request.form.get("fuel", ""))

        # ----- EDIT -----
        if action == "edit":

            cursor.execute("""
                UPDATE rates SET
                    code=%s,
                    code_fullform=%s,
                    place=%s,
                    zone=%s,
                    rate_250g=%s,
                    rate_500g=%s,
                    rate_500g_1=%s,
                    rate_1_to_3kg=%s,
                    rate_3_to_10kg=%s,
                    rate_above_10kg=%s,
                    fuel=%s
                WHERE id=%s
            """, (
                code,
                code_fullform,
                place,
                zone,
                rate_250g,
                rate_500g,
                rate_500g_1,
                rate_1_to_3kg,
                rate_3_to_10kg,
                rate_above_10kg,
                fuel,
                request.form["edit_id"]
            ))

        # ----- ADD -----
        else:

            cursor.execute("""
                INSERT INTO rates (
                    code,
                    code_fullform,
                    place,
                    zone,
                    rate_250g,
                    rate_500g,
                    rate_500g_1,
                    rate_1_to_3kg,
                    rate_3_to_10kg,
                    rate_above_10kg,
                    fuel
                )
                VALUES (
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
                )
            """, (
                code,
                code_fullform,
                place,
                zone,
                rate_250g,
                rate_500g,
                rate_500g_1,
                rate_1_to_3kg,
                rate_3_to_10kg,
                rate_above_10kg,
                fuel
            ))

        db.commit()
        db.close()

        return redirect(url_for(
            'rate_entry',
            search=search,
            limit=limit_str,
            page=1
        ))

    # ----- GET: fetch records with pagination -----

    base_query = "FROM rates"
    params = []

    if search:
        base_query += """
            WHERE code ILIKE %s
            OR code_fullform ILIKE %s
            OR place ILIKE %s
        """

        like = f"%{search}%"
        params = [like, like, like]

    # ----- TOTAL COUNT -----
    cursor.execute(
        f"SELECT COUNT(*) AS total {base_query}",
        params
    )

    total = cursor.fetchone()["total"]

    # ----- PAGINATION -----
    if limit:

        offset = (page - 1) * limit

        query = f"""
            SELECT *
            {base_query}
            ORDER BY id DESC
            LIMIT %s OFFSET %s
        """

        cursor.execute(query, params + [limit, offset])

        total_pages = (total + limit - 1) // limit

    else:

        query = f"""
            SELECT *
            {base_query}
            ORDER BY id DESC
        """

        cursor.execute(query, params)

        total_pages = 1
        page = 1

    rates = [dict(r) for r in cursor.fetchall()]

    db.close()

    return render_template(
        "rate_entry.html",
        rates=rates,
        search=search,
        limit=limit_str,
        page=page,
        total_pages=total_pages,
        total=total
    )

# ------------------------------------------------------------
# BOOKING ENTRY (with AJAX)
# ------------------------------------------------------------
@app.route("/booking-entry", methods=["GET", "POST"])
def booking_entry():

    # ---------- HELPERS ----------
    def txt(value):
        return str(value).strip()

    def num(value):
        value = str(value).strip()
        return 0 if value == "" else float(value)

    def to_date(value):
        value = str(value).strip()
        return None if value == "" else value

    # ---------- POST ----------
    if request.method == "POST":

        db = get_db_connection()
        cursor = db.cursor()

        action = request.form.get("_action", "add")

        # ---------- DELETE ----------
        if action == "delete":

            del_id = request.form.get("del_id")

            if del_id:
                cursor.execute(
                    "DELETE FROM bookings WHERE id=%s",
                    (del_id,)
                )

                db.commit()

            db.close()

            return redirect("/booking-entry?view=recent")

        # ---------- FORM VALUES ----------
        code = txt(request.form.get("code"))

        booking_date = to_date(
            request.form.get("booking_date")
        )

        awb_no = txt(request.form.get("awb_no"))

        destination = txt(
            request.form.get("destination")
        )

        weight = num(
            request.form.get("weight")
        )

        courier = txt(
            request.form.get("courier")
        )

        zone = txt(
            request.form.get("zone")
        )

        auto_amount = num(
            request.form.get("auto_amount")
        )

        fuel = num(
            request.form.get("fuel")
        )

        total_amount = auto_amount + fuel

        client_name = txt(
            request.form.get("client_name")
        )

        inv_no = txt(
            request.form.get("inv_no")
        )

        inv_date = to_date(
            request.form.get("inv_date")
        )

        # ---------- EDIT ----------
        if action == "edit":

            edit_id = request.form.get("edit_id")

            cursor.execute("""
                UPDATE bookings SET
                    code=%s,
                    booking_date=%s,
                    awb_no=%s,
                    destination=%s,
                    weight=%s,
                    courier=%s,
                    zone=%s,
                    auto_amount=%s,
                    fuel=%s,
                    total_amount=%s,
                    client_name=%s,
                    inv_no=%s,
                    inv_date=%s
                WHERE id=%s
            """, (
                code,
                booking_date,
                awb_no,
                destination,
                weight,
                courier,
                zone,
                auto_amount,
                fuel,
                total_amount,
                client_name,
                inv_no,
                inv_date,
                edit_id
            ))

        # ---------- ADD ----------
        else:

            cursor.execute("""
                INSERT INTO bookings (
                    code,
                    booking_date,
                    awb_no,
                    destination,
                    weight,
                    courier,
                    zone,
                    auto_amount,
                    fuel,
                    total_amount,
                    client_name,
                    inv_no,
                    inv_date
                )
                VALUES (
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
                )
            """, (
                code,
                booking_date,
                awb_no,
                destination,
                weight,
                courier,
                zone,
                auto_amount,
                fuel,
                total_amount,
                client_name,
                inv_no,
                inv_date
            ))

        db.commit()
        db.close()

        return redirect("/booking-entry?view=recent")

    # ---------- GET ----------
    return render_template("booking_entry.html")

# ------------------------------------------------------------
# API: bookings (for AJAX datatable)
# ------------------------------------------------------------
@app.route("/api/bookings")
def api_bookings():
    limit = request.args.get("limit")
    db = get_db_connection()
    cursor = db.cursor()

    if limit == "all":
        cursor.execute("""
            SELECT id, code, booking_date, awb_no, destination, weight,
                   courier, zone, auto_amount, fuel, total_amount,
                   client_name, inv_no, inv_date
            FROM bookings
            ORDER BY booking_date DESC, id DESC
        """)
    else:
        cursor.execute("""
            SELECT id, code, booking_date, awb_no, destination, weight,
                   courier, zone, auto_amount, fuel, total_amount,
                   client_name, inv_no, inv_date
            FROM bookings
            ORDER BY booking_date DESC, id DESC
            LIMIT 10
        """)
    rows = cursor.fetchall()
    db.close()
    # Convert to serializable list of dicts (handles date objects too)
    result = []
    for r in rows:
        row = dict(r)
        for k, v in row.items():
            if hasattr(v, 'isoformat'):
                row[k] = v.isoformat()
        result.append(row)
    return jsonify(result)

# ------------------------------------------------------------
# INVOICE / STATEMENT
# ------------------------------------------------------------
@app.route("/invoice", methods=["GET", "POST"])
def invoice():
    db = get_db_connection()
    cursor = db.cursor()

    from_date   = request.args.get("from_date", "")
    to_date     = request.args.get("to_date", "")
    code        = request.args.get("code", "ALL")
    fuel_rate   = request.args.get("fuel_rate", "0")
    try:
        fuel_rate = float(fuel_rate)
    except (ValueError, TypeError):
        fuel_rate = 0.0

    limit_str = request.args.get("limit", "20")
    page = int(request.args.get("page", 1))

    if limit_str == "all":
        limit = None
    else:
        try:
            limit = int(limit_str)
        except ValueError:
            limit = 20

    base_query = """
        FROM bookings
        WHERE booking_date IS NOT NULL
    """
    params = []

    if from_date and to_date:
        base_query += " AND booking_date BETWEEN %s AND %s"
        params.extend([from_date, to_date])
    if code and code != "ALL":
        base_query += " AND code = %s"
        params.append(code)

    cursor.execute(f"SELECT COUNT(*) AS total {base_query}", params)
    total = cursor.fetchone()["total"]

    if limit:
        offset = (page - 1) * limit
        query = f"""
            SELECT booking_date, destination, awb_no, weight, total_amount
            {base_query}
            ORDER BY booking_date DESC, id DESC
            LIMIT %s OFFSET %s
        """
        cursor.execute(query, params + [limit, offset])
        total_pages = (total + limit - 1) // limit
    else:
        query = f"""
            SELECT booking_date, destination, awb_no, weight, total_amount
            {base_query}
            ORDER BY booking_date DESC, id DESC
        """
        cursor.execute(query, params)
        total_pages = 1
        page = 1

    rows = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT DISTINCT code FROM bookings ORDER BY code")
    codes = [dict(r) for r in cursor.fetchall()]

    db.close()

    return render_template(
        "invoice.html",
        rows=rows,
        codes=codes,
        from_date=from_date,
        to_date=to_date,
        selected_code=code,
        fuel_rate=fuel_rate,
        limit=limit_str,
        page=page,
        total_pages=total_pages,
        total=total
    )

# ------------------------------------------------------------
# SALES CHECKING
# ------------------------------------------------------------
@app.route("/sales-checking", methods=["GET", "POST"])
def sales_checking():
    db = get_db_connection()
    cursor = db.cursor()
    client_name = request.form.get("client_name")
    awb_no      = request.form.get("awb_no")
    destination = request.form.get("destination")
    from_date   = request.form.get("from_date")
    to_date     = request.form.get("to_date")
    query = """
        SELECT client_name, awb_no, destination,
               COUNT(*) AS sum_count, SUM(total_amount) AS amount
        FROM bookings WHERE 1=1
    """
    params = []
    if client_name:
        query += " AND client_name LIKE %s"; params.append(f"%{client_name}%")
    if awb_no:
        query += " AND awb_no LIKE %s"; params.append(f"%{awb_no}%")
    if destination:
        query += " AND destination LIKE %s"; params.append(f"%{destination}%")
    if from_date and to_date:
        query += " AND booking_date BETWEEN %s AND %s"; params.extend([from_date, to_date])
    query += " GROUP BY client_name, awb_no, destination ORDER BY client_name"
    cursor.execute(query, params)
    rows = [dict(r) for r in cursor.fetchall()]
    total_amount = sum(r["amount"] for r in rows) if rows else 0
    db.close()
    return render_template("sales_checking.html", rows=rows,
                           total_amount=total_amount, filters=request.form)

# ------------------------------------------------------------
# DAY WISE (Manual Entry)
# ------------------------------------------------------------
@app.route("/day-wise", methods=["GET", "POST"])
def day_wise():
    db = get_db_connection()
    cursor = db.cursor()
    if request.method == "POST" and "save" in request.form:
        cursor.execute("""
            INSERT INTO day_wise (entry_date, total_weight, total_sales)
            VALUES (%s,%s,%s)
        """, (request.form["entry_date"],
              float(request.form["total_weight"] or 0),
              float(request.form["total_sales"] or 0)))
        db.commit()
        db.close()
        return redirect("/day-wise")
    from_date = request.form.get("from_date")
    to_date   = request.form.get("to_date")
    query  = "SELECT * FROM day_wise WHERE 1=1"
    params = []
    if from_date and to_date:
        query += " AND entry_date BETWEEN %s AND %s"; params.extend([from_date, to_date])
    query += " ORDER BY entry_date"
    cursor.execute(query, params)
    rows = [dict(r) for r in cursor.fetchall()]
    grand_weight = sum(r["total_weight"] for r in rows) if rows else 0
    grand_sales  = sum(r["total_sales"] for r in rows) if rows else 0
    db.close()
    return render_template("day_wise.html", rows=rows,
                           from_date=from_date, to_date=to_date,
                           grand_weight=grand_weight, grand_sales=grand_sales)

# ------------------------------------------------------------
# DAY BOOK
# ------------------------------------------------------------
@app.route("/day-book", methods=["GET", "POST"])
def day_book():
    db = get_db_connection()
    cursor = db.cursor()
    entry_date  = request.form.get("entry_date")
    weight      = request.form.get("weight")
    awb_no      = request.form.get("awb_no")
    destination = request.form.get("destination")
    query  = "SELECT weight, awb_no, destination, total_amount FROM bookings WHERE 1=1"
    params = []
    if entry_date:
        query += " AND booking_date = %s"; params.append(entry_date)
    if weight:
        query += " AND weight = %s"; params.append(weight)
    if awb_no:
        query += " AND awb_no LIKE %s"; params.append(f"%{awb_no}%")
    if destination:
        query += " AND destination LIKE %s"; params.append(f"%{destination}%")
    query += " ORDER BY awb_no"
    cursor.execute(query, params)
    rows = [dict(r) for r in cursor.fetchall()]
    total_sum = sum(r["total_amount"] for r in rows) if rows else 0
    db.close()
    return render_template("day_book.html", rows=rows,
                           total_sum=total_sum,
                           entry_date=entry_date, weight=weight,
                           awb_no=awb_no, destination=destination)

# ------------------------------------------------------------
# EXPORTS (Excel) — all use io.BytesIO (Vercel has read-only filesystem)
# ------------------------------------------------------------
@app.route("/invoice-export", methods=["POST"])
def invoice_export():
    db = get_db_connection()
    cursor = db.cursor()
    try:
        fuel_rate = float(request.form.get("fuel_rate", 0))
    except (ValueError, TypeError):
        fuel_rate = 0.0

    query = """SELECT booking_date AS "DATE", destination AS "DESTINATION",
                      awb_no AS "AWB NO", weight AS "WEIGHT",
                      total_amount AS "Total"
               FROM bookings WHERE 1=1"""
    params = []
    if request.form.get("from_date") and request.form.get("to_date"):
        query += " AND booking_date BETWEEN %s AND %s"
        params.extend([request.form["from_date"], request.form["to_date"]])
    if request.form.get("code") and request.form["code"] != "ALL":
        query += " AND code=%s"
        params.append(request.form["code"])
    query += " ORDER BY booking_date"
    cursor.execute(query, params)
    df = pd.DataFrame([dict(r) for r in cursor.fetchall()])

    if fuel_rate > 0 and not df.empty:
        df['Fuel']        = (df['Total'].astype(float) * fuel_rate / 100).round(2)
        df['Grand Total'] = (df['Total'].astype(float) + df['Fuel']).round(2)

    output = io.BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)
    db.close()
    return send_file(output, as_attachment=True,
                     download_name="Invoice_Statement.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

@app.route("/zone-export")
def zone_export():
    db = get_db_connection()
    cursor = db.cursor()
    cursor.execute("SELECT district, rate_zone FROM zones")
    df = pd.DataFrame([dict(r) for r in cursor.fetchall()])
    output = io.BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)
    db.close()
    return send_file(output, as_attachment=True,
                     download_name="Zone_Data.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

@app.route("/rate-export")
def rate_export():
    db = get_db_connection()
    cursor = db.cursor()
    cursor.execute("""
        SELECT code AS "CODE", code_fullform AS "CODE FULL FORM",
               place AS "PLACE", zone AS "ZONE",
               rate_250g AS "250 G Dx", rate_500g AS "0.500 g",
               rate_500g_1 AS "0.500 g 1", rate_1_to_3kg AS "Add 1 to 3 Kg",
               rate_3_to_10kg AS "Above 3-10 Kg", rate_above_10kg AS "Above 10 Kg",
               fuel AS "Fuel"
        FROM rates ORDER BY zone, code
    """)
    df = pd.DataFrame([dict(r) for r in cursor.fetchall()])
    output = io.BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)
    db.close()
    return send_file(output, as_attachment=True,
                     download_name="Rate_Entry.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

@app.route("/booking-export")
def booking_export():
    db = get_db_connection()
    cursor = db.cursor()
    cursor.execute("""
        SELECT code AS "CODE", booking_date AS "DATE", awb_no AS "AWB NO",
               destination AS "DESTINATION", weight AS "WEIGHT", courier AS "COURIER",
               zone AS "ZONE", auto_amount AS "Auto Amount", fuel AS "Fuel",
               total_amount AS "Total Amount", client_name AS "Client Name",
               inv_no AS "INV NO", inv_date AS "INV DATE"
        FROM bookings
    """)
    df = pd.DataFrame([dict(r) for r in cursor.fetchall()])
    output = io.BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)
    db.close()
    return send_file(output, as_attachment=True,
                     download_name="Booking_Data.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

@app.route("/sales-export", methods=["POST"])
def sales_export():
    db = get_db_connection()
    cursor = db.cursor()
    query  = """SELECT client_name AS "Client Name", awb_no AS "AWB No",
                       destination AS "Destination", COUNT(*) AS "Sum",
                       SUM(total_amount) AS "Amount"
                FROM bookings WHERE 1=1"""
    params = []
    if request.form.get("client_name"):
        query += " AND client_name LIKE %s"; params.append(f"%{request.form['client_name']}%")
    if request.form.get("awb_no"):
        query += " AND awb_no LIKE %s"; params.append(f"%{request.form['awb_no']}%")
    if request.form.get("destination"):
        query += " AND destination LIKE %s"; params.append(f"%{request.form['destination']}%")
    if request.form.get("from_date") and request.form.get("to_date"):
        query += " AND booking_date BETWEEN %s AND %s"; params.extend([request.form["from_date"], request.form["to_date"]])
    query += " GROUP BY client_name, awb_no, destination"
    cursor.execute(query, params)
    df = pd.DataFrame([dict(r) for r in cursor.fetchall()])
    output = io.BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)
    db.close()
    return send_file(output, as_attachment=True,
                     download_name="Sales_Checking.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

@app.route("/day-wise-export", methods=["POST"])
def day_wise_export():
    db = get_db_connection()
    cursor = db.cursor()
    query  = """SELECT entry_date AS "DATE", total_weight AS "Total Weight",
                       total_sales AS "Total Sales Amount"
                FROM day_wise WHERE 1=1"""
    params = []
    if request.form.get("from_date") and request.form.get("to_date"):
        query += " AND entry_date BETWEEN %s AND %s"; params.extend([request.form["from_date"], request.form["to_date"]])
    query += " ORDER BY entry_date"
    cursor.execute(query, params)
    df = pd.DataFrame([dict(r) for r in cursor.fetchall()])
    output = io.BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)
    db.close()
    return send_file(output, as_attachment=True,
                     download_name="Day_Wise_Manual.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

@app.route("/day-book-export", methods=["POST"])
def day_book_export():
    db = get_db_connection()
    cursor = db.cursor()
    query  = """SELECT weight AS "WEIGHT", awb_no AS "AWB NO",
                       destination AS "DESTINATION", total_amount AS "Total"
                FROM bookings WHERE 1=1"""
    params = []
    if request.form.get("entry_date"):
        query += " AND booking_date = %s"; params.append(request.form["entry_date"])
    if request.form.get("weight"):
        query += " AND weight = %s"; params.append(request.form["weight"])
    if request.form.get("awb_no"):
        query += " AND awb_no LIKE %s"; params.append(f"%{request.form['awb_no']}%")
    if request.form.get("destination"):
        query += " AND destination LIKE %s"; params.append(f"%{request.form['destination']}%")
    cursor.execute(query, params)
    df = pd.DataFrame([dict(r) for r in cursor.fetchall()])
    output = io.BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)
    db.close()
    return send_file(output, as_attachment=True,
                     download_name="Day_Book.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ------------------------------------------------------------
# INVOICE PDF (Watermark)
# ------------------------------------------------------------
class WatermarkDocTemplate(SimpleDocTemplate):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.watermark_text = "AIKONIX"

    def afterPage(self):
        self.canv.saveState()
        self.canv.setFont('Helvetica', 80)
        self.canv.setFillColor(colors.Color(red=0.5, green=0.5, blue=0.5, alpha=0.25))
        page_width, page_height = A4
        self.canv.translate(page_width / 2, page_height / 2)
        self.canv.rotate(45)
        self.canv.drawCentredString(0, 0, self.watermark_text)
        self.canv.restoreState()

@app.route("/invoice-pdf", methods=["POST"])
def invoice_pdf():
    db = get_db_connection()
    cursor = db.cursor()
    from_date = request.form.get("from_date")
    to_date   = request.form.get("to_date")
    code      = request.form.get("code")
    try:
        fuel_percent = float(request.form.get("fuel_rate", 0))
    except (ValueError, TypeError):
        fuel_percent = 0.0

    query = "SELECT booking_date, destination, awb_no, weight, total_amount FROM bookings WHERE booking_date IS NOT NULL"
    params = []
    if from_date and to_date:
        query += " AND booking_date BETWEEN %s AND %s"
        params.extend([from_date, to_date])
    if code and code != "ALL":
        query += " AND code=%s"
        params.append(code)
    query += " ORDER BY booking_date"
    cursor.execute(query, params)
    rows = [dict(r) for r in cursor.fetchall()]
    db.close()

    buf = io.BytesIO()
    doc = WatermarkDocTemplate(buf, pagesize=A4,
                               leftMargin=10*mm, rightMargin=10*mm,
                               topMargin=12*mm, bottomMargin=12*mm)

    styles = getSampleStyleSheet()
    title_style  = ParagraphStyle('title',  fontSize=13, alignment=TA_CENTER, spaceAfter=4, fontName='Helvetica-Bold')
    sub_style    = ParagraphStyle('sub',    fontSize=9,  alignment=TA_CENTER, spaceAfter=8, textColor=colors.grey)

    elements = []
    title_text = "Invoice / Statement"
    if code and code != "ALL":
        title_text += f"  —  {code}"
    elements.append(Paragraph(title_text, title_style))
    if from_date and to_date:
        elements.append(Paragraph(f"{from_date}  to  {to_date}", sub_style))
    if fuel_percent > 0:
        elements.append(Paragraph(f"Fuel Surcharge: {fuel_percent:.2f}%", sub_style))
    elements.append(Spacer(1, 4*mm))

    header = ['SNO', 'DATE', 'DESTINATION', 'AWB NO', 'WEIGHT', 'Total']
    col_widths = [20*mm, 28*mm, 55*mm, 50*mm, 22*mm, 25*mm]
    data = [header]
    span_cmds = []
    row_idx = 1
    sno = 0
    sum_base = 0.0

    for date_val, grp in groupby(rows, key=itemgetter("booking_date")):
        grp = list(grp)
        date_str = date_val.strftime('%d-%m-%Y') if hasattr(date_val, 'strftime') else str(date_val)
        first = True
        for r in grp:
            sno += 1
            base = float(r["total_amount"])
            sum_base += base
            row_data = [
                str(sno),
                date_str if first else '',
                r["destination"] or '',
                str(r["awb_no"]),
                f"{float(r['weight']):.3f}",
                f"{base:.2f}",
            ]
            data.append(row_data)
            first = False
            row_idx += 1
        if len(grp) > 1:
            start = row_idx - len(grp)
            end   = row_idx - 1
            span_cmds.append(('SPAN', (1, start), (1, end)))
            span_cmds.append(('VALIGN', (1, start), (1, end), 'MIDDLE'))

    if fuel_percent > 0:
        fuel_total = sum_base * fuel_percent / 100
        grand_total = sum_base + fuel_total
        data.append(['', '', '', '', 'Total:', f"{sum_base:.2f}"])
        data.append(['', '', '', '', 'Fuel Surcharge:', f"{fuel_total:.2f}"])
        data.append(['', '', '', '', 'Grand Total:', f"{grand_total:.2f}"])
        total_rows = len(data)
    else:
        data.append(['', '', '', '', 'Total:', f"{sum_base:.2f}"])
        total_rows = len(data)

    t = Table(data, colWidths=col_widths, repeatRows=1)
    style_cmds = [
        ('BACKGROUND',   (0,0), (-1,0),  colors.HexColor('#212529')),
        ('TEXTCOLOR',    (0,0), (-1,0),  colors.white),
        ('FONTNAME',     (0,0), (-1,0),  'Helvetica-Bold'),
        ('FONTSIZE',     (0,0), (-1,0),  8),
        ('ALIGN',        (0,0), (-1,0),  'CENTER'),
        ('BOTTOMPADDING',(0,0), (-1,0),  5),
        ('TOPPADDING',   (0,0), (-1,0),  5),
        ('FONTSIZE',     (0,1), (-1,-1), 8),
        ('FONTNAME',     (0,1), (-1,-1), 'Helvetica'),
        ('GRID',         (0,0), (-1,-2), 0.4, colors.grey),
        ('ROWBACKGROUNDS',(0,1),(-1,-2), [colors.white, colors.HexColor('#f8f9fa')]),
        ('ALIGN',        (4,1), (-1,-2), 'RIGHT'),
        ('ALIGN',        (1,1), (1,-2),  'CENTER'),
        ('TOPPADDING',   (0,1), (-1,-2), 3),
        ('BOTTOMPADDING',(0,1), (-1,-2), 3),
        ('FONTNAME',     (0, total_rows-1), (-1,-1), 'Helvetica-Bold'),
        ('BACKGROUND',   (0, total_rows-1), (-1,-1), colors.HexColor('#e9ecef')),
        ('LINEABOVE',    (0, total_rows-1), (-1, total_rows-1), 1, colors.black),
        ('BOX',          (0,0), (-1,-1), 0.8, colors.black),
    ]
    if fuel_percent > 0:
        style_cmds.append(('LINEABOVE', (0, total_rows-2), (-1, total_rows-2), 1, colors.black))
    style_cmds.extend(span_cmds)
    t.setStyle(TableStyle(style_cmds))
    elements.append(t)

    doc.build(elements)
    buf.seek(0)
    fname = f"Invoice_{code or 'ALL'}_{from_date or ''}_{to_date or ''}.pdf"
    return send_file(buf, as_attachment=True, download_name=fname, mimetype='application/pdf')

# ------------------------------------------------------------
# AJAX Endpoints for Autocomplete & Validation
# ------------------------------------------------------------
@app.route("/day-book/filter")
def day_book_filter():
    db = get_db_connection()
    cursor = db.cursor()
    entry_date = request.args.get("entry_date", "")
    weight = request.args.get("weight", "")
    awb_no = request.args.get("awb_no", "")
    destination = request.args.get("destination", "")
    query = """
        SELECT weight, awb_no, destination, total_amount
        FROM bookings
        WHERE 1=1
    """
    params = []
    if entry_date:
        query += " AND booking_date = %s"
        params.append(entry_date)
    if weight:
        query += " AND weight = %s"
        params.append(float(weight))
    if awb_no:
        query += " AND awb_no LIKE %s"
        params.append(f"%{awb_no}%")
    if destination:
        query += " AND destination LIKE %s"
        params.append(f"%{destination}%")
    query += " ORDER BY awb_no"
    cursor.execute(query, params)
    rows = [dict(r) for r in cursor.fetchall()]
    total_sum = sum(row["total_amount"] for row in rows) if rows else 0
    db.close()
    return jsonify({"rows": rows, "total_sum": float(total_sum)})

@app.route("/api/ac/code")
def api_ac_code():
    q = request.args.get("q", "").strip()
    if not q: return jsonify([])
    db = get_db_connection()
    cur = db.cursor()
    cur.execute(
        "SELECT DISTINCT code, code_fullform FROM rates "
        "WHERE code LIKE %s OR code_fullform LIKE %s LIMIT 10",
        (f"{q}%", f"%{q}%"))
    rows = [dict(r) for r in cur.fetchall()]
    db.close()
    return jsonify(rows)

@app.route("/api/ac/place")
def api_ac_place():
    q = request.args.get("q", "").strip()
    if not q: return jsonify([])
    db = get_db_connection()
    cur = db.cursor()
    cur.execute(
        "SELECT DISTINCT place FROM rates WHERE place LIKE %s ORDER BY place LIMIT 12",
        (f"{q}%",))
    rows = cur.fetchall()
    db.close()
    return jsonify([r["place"] for r in rows])

@app.route("/api/ac/zone")
def api_ac_zone():
    q = request.args.get("q", "").strip()
    if not q: return jsonify([])
    db = get_db_connection()
    cur = db.cursor()
    cur.execute(
        "SELECT DISTINCT place FROM rates WHERE place LIKE %s ORDER BY place LIMIT 12",
        (f"{q}%",))
    rows = cur.fetchall()
    db.close()
    return jsonify([r["place"] for r in rows])

@app.route("/api/ac/destination")
def api_ac_destination():
    q = request.args.get("q", "").strip()
    if not q: return jsonify([])
    db = get_db_connection()
    cur = db.cursor()
    cur.execute(
        "SELECT DISTINCT destination FROM bookings WHERE destination LIKE %s LIMIT 12",
        (f"{q}%",))
    rows = cur.fetchall()
    db.close()
    return jsonify([r["destination"] for r in rows if r["destination"]])

@app.route("/api/ac/client")
def api_ac_client():
    q = request.args.get("q", "").strip()
    if not q: return jsonify([])
    db = get_db_connection()
    cur = db.cursor()
    cur.execute(
        "SELECT DISTINCT client_name FROM bookings WHERE client_name LIKE %s LIMIT 10",
        (f"%{q}%",))
    rows = cur.fetchall()
    db.close()
    return jsonify([r["client_name"] for r in rows if r["client_name"]])

@app.route("/api/rate/lookup")
def api_rate_lookup():
    code = request.args.get("code", "").strip().upper()
    zone_str = request.args.get("zone", "").strip()
    if not code or not zone_str:
        return jsonify({})
    try:
        zone = int(zone_str)
    except ValueError:
        return jsonify({})
    db = get_db_connection()
    cur = db.cursor()
    cur.execute(
        "SELECT * FROM rates WHERE UPPER(code)=%s AND zone = %s LIMIT 1",
        (code, zone))
    row = cur.fetchone()
    db.close()
    return jsonify(dict(row) if row else {})

@app.route("/api/ac/awb_check")
def api_awb_check():
    awb     = request.args.get("awb", "").strip()
    edit_id = request.args.get("edit_id", "").strip()
    if not awb: return jsonify({"exists": False})
    db = get_db_connection()
    cur = db.cursor()
    if edit_id:
        cur.execute(
            "SELECT id, code, booking_date, destination FROM bookings "
            "WHERE awb_no=%s AND id!=%s LIMIT 1", (awb, edit_id))
    else:
        cur.execute(
            "SELECT id, code, booking_date, destination FROM bookings "
            "WHERE awb_no=%s LIMIT 1", (awb,))
    row = cur.fetchone()
    db.close()
    if row:
        return jsonify({"exists": True, "code": row["code"],
                        "date": str(row["booking_date"]), "dest": row["destination"]})
    return jsonify({"exists": False})

@app.route("/api/place/save-zone", methods=["POST"])
def api_place_save_zone():
    data       = request.get_json()
    place      = data.get("place", "").strip().upper()
    zone       = int(data.get("zone", 5))
    place_code = data.get("place_code", "").strip().upper() or None
    if not place:
        return jsonify({"ok": False})
    db  = get_db_connection()
    cur = db.cursor()
    # PostgreSQL ON CONFLICT (place must have unique constraint)
    cur.execute("""
        INSERT INTO place_zones (place, zone, place_code)
        VALUES (%s, %s, %s)
        ON CONFLICT (place) DO UPDATE SET
            zone = EXCLUDED.zone,
            place_code = COALESCE(EXCLUDED.place_code, place_zones.place_code)
    """, (place, zone, place_code))
    db.commit()
    db.close()
    return jsonify({"ok": True})

@app.route("/api/place/get-zone")
def api_place_get_zone():
    place = request.args.get("place", "").strip().upper()
    if not place: return jsonify({})
    db  = get_db_connection()
    cur = db.cursor()
    cur.execute("SELECT zone FROM place_zones WHERE UPPER(place)=%s LIMIT 1", (place,))
    row = cur.fetchone()
    db.close()
    return jsonify(dict(row) if row else {})

@app.route("/api/ac/district")
def api_ac_district():
    q = request.args.get("q", "").strip()
    if not q: return jsonify([])
    db = get_db_connection()
    cursor = db.cursor()
    cursor.execute(
        "SELECT DISTINCT district FROM zones WHERE district LIKE %s ORDER BY district LIMIT 10",
        (f"{q}%",))
    rows = cursor.fetchall()
    db.close()
    return jsonify([r["district"] for r in rows])

@app.route("/api/dest/zone-lookup")
def api_dest_zone_lookup():
    dest = request.args.get("dest", "").strip().upper()
    code = request.args.get("code", "").strip().upper()
    if not dest or not code: return jsonify({})
    db  = get_db_connection()
    cur = db.cursor()
    # 1. Exact match in rates
    cur.execute(
        "SELECT place, zone FROM rates "
        "WHERE UPPER(code)=%s AND UPPER(place)=%s LIMIT 1",
        (code, dest))
    row = cur.fetchone()
    if row:
        db.close()
        return jsonify(dict(row))
    # 2. Match by place_code in place_zones
    cur.execute(
        "SELECT place, zone FROM place_zones "
        "WHERE UPPER(place_code)=%s LIMIT 1",
        (dest,))
    pz_by_code = cur.fetchone()
    if pz_by_code:
        db.close()
        return jsonify({"place": pz_by_code["place"], "zone": pz_by_code["zone"]})
    # 3. Match by place name in place_zones
    cur.execute(
        "SELECT zone FROM place_zones WHERE UPPER(place)=%s LIMIT 1",
        (dest,))
    pz = cur.fetchone()
    # Get all places for this code
    cur.execute(
        "SELECT place, zone FROM rates WHERE UPPER(code)=%s ORDER BY zone ASC",
        (code,))
    all_places = [dict(r) for r in cur.fetchall()]
    zone_place_map = {p["zone"]: p["place"] for p in all_places}
    if pz and pz["zone"] in zone_place_map:
        db.close()
        return jsonify({"place": zone_place_map[pz["zone"]], "zone": pz["zone"]})
    # 4. Partial match against place names in rates
    for p in all_places:
        place_up = p["place"].upper()
        if dest in place_up or place_up in dest:
            db.close()
            return jsonify({"place": p["place"], "zone": p["zone"]})
    # 5. Fallback: place_zones zone -> rates place
    cur.execute(
        "SELECT zone FROM place_zones WHERE UPPER(place)=%s LIMIT 1",
        (dest,))
    pz2 = cur.fetchone()
    if pz2 and pz2["zone"] in zone_place_map:
        db.close()
        return jsonify({"place": zone_place_map[pz2["zone"]], "zone": pz2["zone"]})
    db.close()
    return jsonify({})

# ============================================================
# MISSING ROUTES — paste these into your PostgreSQL app.py
# (anywhere before the `if __name__ == "__main__":` block)
# ============================================================


# ---------------- SMART ZONE API ----------------

@app.route("/api/smart-zone")
def api_smart_zone():
    """
    Detect zone from destination text using keyword matching.
    Priority:
      1. place_zones table  (manually saved overrides, by place_code)
      2. place_zones table  (by exact place name)
      3. rates table        (exact match for this code + place)
      4. rates table        (partial match for this code)
      5. Built-in keyword map (Chennai / TN / South / Metro / ROI)
    Returns: { zone, label, source, place }
    """
    dest = request.args.get("dest", "").strip().upper()
    code = request.args.get("code", "").strip().upper()
    if not dest:
        return jsonify({})

    db  = get_db_connection()
    cur = db.cursor()

    # 1. place_zones override by place_code
    cur.execute(
        "SELECT place, zone FROM place_zones WHERE UPPER(place_code) = %s LIMIT 1",
        (dest,)
    )
    row = cur.fetchone()
    if row:
        db.close()
        return jsonify({**dict(row), "source": "saved", "label": _zone_label(row["zone"])})

    # 2. place_zones override by exact place name
    cur.execute(
        "SELECT zone FROM place_zones WHERE UPPER(place) = %s LIMIT 1",
        (dest,)
    )
    row = cur.fetchone()
    if row:
        db.close()
        return jsonify({
            "place": dest,
            "zone": row["zone"],
            "source": "saved",
            "label": _zone_label(row["zone"])
        })

    # 3. rates table — exact match (code + place)
    if code:
        cur.execute(
            "SELECT place, zone FROM rates "
            "WHERE UPPER(code) = %s AND UPPER(place) = %s LIMIT 1",
            (code, dest)
        )
        row = cur.fetchone()
        if row:
            db.close()
            return jsonify({**dict(row), "source": "rate_exact", "label": _zone_label(row["zone"])})

        # 4. rates table — partial match
        cur.execute(
            "SELECT place, zone FROM rates WHERE UPPER(code) = %s ORDER BY zone",
            (code,)
        )
        all_places = [dict(r) for r in cur.fetchall()]
        for p in all_places:
            pu = p["place"].upper()
            if dest in pu or pu in dest:
                db.close()
                return jsonify({
                    "place": p["place"],
                    "zone":  p["zone"],
                    "source": "rate_partial",
                    "label": _zone_label(p["zone"])
                })

    db.close()

    # 5. Built-in keyword map (no DB needed)
    zone, label = _keyword_zone(dest)
    if zone:
        return jsonify({
            "place":  dest.title(),
            "zone":   zone,
            "source": "keyword",
            "label":  label
        })

    return jsonify({})


# ---------------- HELPER: zone number → label ----------------

def _zone_label(z):
    return {
        1: "Chennai",
        2: "Tamil Nadu",
        3: "South India",
        4: "North Metro",
        5: "ROI",
    }.get(int(z), "ROI")


# ---------------- HELPER: keyword → zone number ----------------

def _keyword_zone(dest):
    """Pure keyword-based zone detection (fallback, no DB call)."""

    ZONE1 = [
        "CHENNAI", "MADRAS", "TAMBARAM", "VELACHERY", "ADYAR",
        "ANNA NAGAR", "T NAGAR", "NUNGAMBAKKAM", "PERAMBUR",
        "ROYAPURAM", "EGMORE", "KODAMBAKKAM", "CHROMPET", "SHOLINGANALLUR",
        "PORUR", "AMBATTUR", "AVADI", "POONAMALLEE", "PALLAVARAM",
        "PERUNGUDI", "THIRUVANMIYUR", "MYLAPORE", "TRIPLICANE",
        "WASHERMANPET", "TONDIARPET",
    ]

    ZONE2_TN = [
        "COIMBATORE", "MADURAI", "TRICHY", "TIRUCHIRAPPALLI",
        "SALEM", "TIRUNELVELI", "VELLORE", "ERODE", "TIRUPPUR",
        "THOOTHUKUDI", "TUTICORIN", "DINDIGUL", "THANJAVUR",
        "KANCHIPURAM", "KUMBAKONAM", "NAGERCOIL", "SIVAGANGAI",
        "NAMAKKAL", "KARUR", "PUDUKOTTAI", "RAMANATHAPURAM",
        "VIRUDHUNAGAR", "CUDDALORE", "NAGAPATTINAM", "OOTY",
        "UDHAGAMANDALAM", "KODAIKANAL", "HOSUR", "RANIPET",
        "TIRUVANNAMALAI", "VILLUPURAM", "ARIYALUR", "PERAMBALUR",
        "KALLAKURICHI", "TENKASI", "KRISHNAGIRI", "DHARMAPURI",
        "THENI", "NILGIRIS", "CHENGALPATTU", "TIRUPATTUR",
    ]

    ZONE3_SOUTH = [
        # Kerala
        "KERALA", "THIRUVANANTHAPURAM", "TRIVANDRUM", "KOCHI", "COCHIN",
        "KOZHIKODE", "CALICUT", "THRISSUR", "KOLLAM", "PALAKKAD",
        "ALAPPUZHA", "ALLEPPEY", "KANNUR", "MALAPPURAM", "KASARAGOD",
        "WAYANAD", "IDUKKI", "PATHANAMTHITTA", "ERNAKULAM", "KOTTAYAM",
        # Karnataka
        "KARNATAKA", "BENGALURU", "BANGALORE", "MYSURU", "MYSORE",
        "HUBLI", "DHARWAD", "MANGALURU", "MANGALORE", "BELAGAVI",
        "BELGAUM", "GULBARGA", "KALABURAGI", "DAVANAGERE", "BELLARY",
        "VIJAYAPURA", "BIJAPUR", "SHIMOGA", "SHIVAMOGGA", "TUMKUR",
        "UDUPI", "HASSAN", "BIDAR", "RAICHUR", "BAGALKOT", "CHITRADURGA",
        # Andhra Pradesh
        "ANDHRA", "VISAKHAPATNAM", "VIZAG", "VIJAYAWADA", "GUNTUR",
        "NELLORE", "KURNOOL", "RAJAHMUNDRY", "KAKINADA", "TIRUPATI",
        "ANANTAPUR", "KADAPA", "CHITTOOR", "ELURU", "ONGOLE", "VIZIANAGARAM",
        # Telangana
        "TELANGANA", "HYDERABAD", "WARANGAL", "NIZAMABAD", "KHAMMAM",
        "KARIMNAGAR", "RAMAGUNDAM", "SECUNDERABAD", "NALGONDA",
        "ADILABAD", "MAHBUBNAGAR", "SANGAREDDY", "SIDDIPET",
    ]

    ZONE4_METRO = [
        # Delhi NCR
        "DELHI", "NEW DELHI", "GURGAON", "GURUGRAM", "NOIDA",
        "FARIDABAD", "GHAZIABAD", "GREATER NOIDA",
        # Mumbai
        "MUMBAI", "BOMBAY", "THANE", "NAVI MUMBAI", "PUNE",
        # Kolkata
        "KOLKATA", "CALCUTTA", "HOWRAH", "DURGAPUR", "ASANSOL",
    ]

    for kw in ZONE1:
        if kw in dest:
            return 1, "Chennai"
    for kw in ZONE2_TN:
        if kw in dest:
            return 2, "Tamil Nadu"
    for kw in ZONE3_SOUTH:
        if kw in dest:
            return 3, "South India"
    for kw in ZONE4_METRO:
        if kw in dest:
            return 4, "North Metro"

    return 5, "ROI"

# ------------------------------------------------------------
# Run the app
# ------------------------------------------------------------
if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0')