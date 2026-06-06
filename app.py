import io
from itertools import groupby
from operator import itemgetter
from functools import wraps

from flask import (Flask, render_template, request, redirect,
                   send_file, jsonify, url_for, session, flash)
import pandas as pd
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER

from db import get_db_connection

app = Flask(__name__)
app.secret_key = __import__('os').environ.get("SECRET_KEY", "dev-secret-change-in-prod")

# ============================================================
# AUTH DECORATORS
# ============================================================
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "username" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "username" not in session:
            return redirect(url_for("login"))
        if session.get("role") != "admin":
            return "Access denied — admins only.", 403
        return f(*args, **kwargs)
    return decorated

# ============================================================
# LOGIN / LOGOUT  (reads from PostgreSQL app_users table)
# ============================================================
@app.route("/login", methods=["GET", "POST"])
def login():
    if "username" in session:
        return redirect(url_for("dashboard"))

    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        db     = get_db_connection()
        cursor = db.cursor()
        cursor.execute(
            "SELECT username, password, role FROM app_users "
            "WHERE username = %s LIMIT 1",
            (username,)
        )
        user = cursor.fetchone()
        db.close()

        # Plain-text comparison
        # (replace with bcrypt check if you hash passwords)
        if user and user["password"] == password:
            session["username"] = user["username"]
            session["role"]     = user["role"]
            return redirect(url_for("dashboard"))

        error = "Invalid username or password."

    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ============================================================
# DASHBOARD
# ============================================================
@app.route("/")
@login_required
def dashboard():
    return render_template("dashboard.html")

# ============================================================
# ZONE ENTRY
# ============================================================
@app.route("/zone-entry", methods=["GET", "POST"])
@login_required
def zone_entry():
    db     = get_db_connection()
    cursor = db.cursor()

    if request.method == "POST":
        action = request.form.get("_action", "add")

        if action in ("edit", "delete") and session.get("role") != "admin":
            db.close()
            return "Access denied: admins only.", 403

        if action == "delete":
            del_id = request.form.get("del_id")
            if del_id:
                cursor.execute("DELETE FROM zones WHERE id = %s", (del_id,))
                db.commit()
            db.close()
            return redirect("/zone-entry")

        district  = request.form.get("district",  "").strip()
        rate_zone = request.form.get("rate_zone", "").strip()

        if not district or not rate_zone:
            db.close()
            return "District and Rate Zone are required", 400

        if action == "edit":
            edit_id = request.form.get("edit_id")
            cursor.execute(
                "UPDATE zones SET district=%s, rate_zone=%s WHERE id=%s",
                (district, rate_zone, edit_id)
            )
        else:
            cursor.execute(
                "INSERT INTO zones (district, rate_zone) VALUES (%s, %s)",
                (district, rate_zone)
            )

        db.commit()
        db.close()
        return redirect("/zone-entry")

    cursor.execute("SELECT * FROM zones ORDER BY id DESC")
    zones = [dict(r) for r in cursor.fetchall()]
    db.close()
    return render_template("zone_entry.html", zones=zones,
                           role=session.get("role"))

# ============================================================
# RATE ENTRY
# ============================================================
@app.route("/rate-entry", methods=["GET", "POST"])
@login_required
def rate_entry():

    def num(value):
        value = str(value).strip()
        return None if value == "" else float(value)

    db     = get_db_connection()
    cursor = db.cursor()

    search    = request.args.get("search", "").strip()
    limit_str = request.args.get("limit", "20")
    page      = int(request.args.get("page", 1))

    limit = None if limit_str == "all" else int(limit_str) if limit_str.isdigit() else 20

    if request.method == "POST":
        action = request.form.get("_action", "add")

        if action in ("edit", "delete") and session.get("role") != "admin":
            db.close()
            return "Access denied: admins only.", 403

        if action == "delete":
            cursor.execute("DELETE FROM rates WHERE id=%s",
                           (request.form["del_id"],))
            db.commit()
            db.close()
            return redirect(url_for('rate_entry', search=search,
                                    limit=limit_str, page=page))

        zone            = int(request.form.get("zone") or 5)
        code            = request.form.get("code",          "").strip()
        code_fullform   = request.form.get("code_fullform", "").strip()
        place           = request.form.get("place",         "").strip()
        rate_250g       = num(request.form.get("rate_250g",     ""))
        rate_500g       = num(request.form.get("rate_500g",     ""))
        rate_500g_1     = num(request.form.get("rate_500g_1",   ""))
        rate_1_to_3kg   = num(request.form.get("rate_1_to_3kg",   ""))
        rate_3_to_10kg  = num(request.form.get("rate_3_to_10kg",  ""))
        rate_above_10kg = num(request.form.get("rate_above_10kg", ""))
        fuel            = num(request.form.get("fuel", ""))

        if action == "edit":
            cursor.execute("""
                UPDATE rates SET
                    code=%s, code_fullform=%s, place=%s, zone=%s,
                    rate_250g=%s, rate_500g=%s, rate_500g_1=%s,
                    rate_1_to_3kg=%s, rate_3_to_10kg=%s,
                    rate_above_10kg=%s, fuel=%s
                WHERE id=%s
            """, (code, code_fullform, place, zone,
                  rate_250g, rate_500g, rate_500g_1,
                  rate_1_to_3kg, rate_3_to_10kg, rate_above_10kg, fuel,
                  request.form["edit_id"]))
        else:
            cursor.execute("""
                INSERT INTO rates (
                    code, code_fullform, place, zone,
                    rate_250g, rate_500g, rate_500g_1,
                    rate_1_to_3kg, rate_3_to_10kg, rate_above_10kg, fuel
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (code, code_fullform, place, zone,
                  rate_250g, rate_500g, rate_500g_1,
                  rate_1_to_3kg, rate_3_to_10kg, rate_above_10kg, fuel))

        db.commit()
        db.close()
        return redirect(url_for('rate_entry', search=search,
                                limit=limit_str, page=1))

    # GET — use ILIKE for case-insensitive search in PostgreSQL
    base_query = "FROM rates"
    params     = []
    if search:
        base_query += " WHERE code ILIKE %s OR code_fullform ILIKE %s OR place ILIKE %s"
        like   = f"%{search}%"
        params = [like, like, like]

    cursor.execute(f"SELECT COUNT(*) AS total {base_query}", params)
    total = cursor.fetchone()["total"]

    if limit:
        offset      = (page - 1) * limit
        total_pages = (total + limit - 1) // limit
        cursor.execute(
            f"SELECT * {base_query} ORDER BY id DESC LIMIT %s OFFSET %s",
            params + [limit, offset]
        )
    else:
        total_pages = 1
        page        = 1
        cursor.execute(f"SELECT * {base_query} ORDER BY id DESC", params)

    rates = [dict(r) for r in cursor.fetchall()]
    db.close()

    return render_template(
        "rate_entry.html",
        rates=rates,
        search=search,
        limit=limit_str,
        page=page,
        total_pages=total_pages,
        total=total,
        role=session.get("role")
    )

# ============================================================
# BOOKING ENTRY
# ============================================================
@app.route("/booking-entry", methods=["GET", "POST"])
@login_required
def booking_entry():

    def txt(v):
        if v is None:
            return ""
        return str(v).strip()

    def num(v):
        if v is None:
            return 0.0
        v = str(v).strip()
        return 0.0 if v == "" else float(v)

    def to_date(v):
        if v is None:
            return None
        v = str(v).strip()
        if v == "" or v.lower() == "none":
            return None
        return v

    if request.method == "POST":
        db     = get_db_connection()
        cursor = db.cursor()
        action = request.form.get("_action", "add")

        if action in ("edit", "delete") and session.get("role") != "admin":
            db.close()
            return "Access denied: admins only.", 403

        if action == "delete":
            del_id = request.form.get("del_id")
            if del_id:
                cursor.execute("DELETE FROM bookings WHERE id=%s", (del_id,))
                db.commit()
            db.close()
            return redirect("/booking-entry?view=recent")

        code         = txt(request.form.get("code"))
        booking_date = to_date(request.form.get("booking_date"))
        awb_no       = txt(request.form.get("awb_no"))
        destination  = txt(request.form.get("destination"))
        weight       = num(request.form.get("weight"))
        courier      = txt(request.form.get("courier"))
        zone         = txt(request.form.get("zone"))
        auto_amount  = num(request.form.get("auto_amount"))
        fuel         = num(request.form.get("fuel"))
        total_amount = auto_amount + fuel
        client_name  = txt(request.form.get("client_name"))
        inv_no       = txt(request.form.get("inv_no"))
        inv_date     = to_date(request.form.get("inv_date"))

        if action == "edit":
            cursor.execute("""
                UPDATE bookings SET
                    code=%s, booking_date=%s, awb_no=%s, destination=%s,
                    weight=%s, courier=%s, zone=%s, auto_amount=%s,
                    fuel=%s, total_amount=%s, client_name=%s,
                    inv_no=%s, inv_date=%s
                WHERE id=%s
            """, (code, booking_date, awb_no, destination, weight,
                  courier, zone, auto_amount, fuel, total_amount,
                  client_name, inv_no, inv_date,
                  request.form.get("edit_id")))
        else:
            cursor.execute("""
                INSERT INTO bookings (
                    code, booking_date, awb_no, destination, weight,
                    courier, zone, auto_amount, fuel, total_amount,
                    client_name, inv_no, inv_date
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (code, booking_date, awb_no, destination, weight,
                  courier, zone, auto_amount, fuel, total_amount,
                  client_name, inv_no, inv_date))

        db.commit()
        db.close()
        return redirect("/booking-entry?view=recent")

    return render_template("booking_entry.html", role=session.get("role"))

# ============================================================
# BOOKING IMPORT
# ============================================================
@app.route("/booking-import", methods=["POST"])
@login_required
def booking_import():
    from datetime import datetime

    def zone_name_to_number(zone_text):
        zone_map = {
            'CHENNAI': 1, 'TAMIL NADU': 2, 'TAMILNADU': 2,
            'SOUTH INDIA': 3, 'SOUTH': 3,
            'NORTH METRO': 4, 'NORTH': 4,
            'ROI': 5, 'REST OF INDIA': 5
        }
        z = str(zone_text).strip().upper()
        for k, v in zone_map.items():
            if z == k or (k == 'CHENNAI' and z in ['CHENNAI', 'MADRAS']):
                return v
        for kw, val in zone_map.items():
            if kw in z:
                return val
        return 5

    if 'excel_file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files['excel_file']
    if file.filename == '':
        return jsonify({"error": "Empty filename"}), 400

    try:
        df = pd.read_excel(file)
    except Exception as e:
        return jsonify({"error": f"Failed to read Excel: {str(e)}"}), 400

    required_cols = ['Code', 'Date', 'AWB Number', 'Destination', 'Weight', 'Zone']
    for col in required_cols:
        if col not in df.columns:
            return jsonify({"error": f"Missing column: {col}"}), 400

    db     = get_db_connection()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM rates")
    all_rates  = cursor.fetchall()
    rate_cache = {}
    for r in all_rates:
        rate_cache[(r['code'].upper(), r['zone'])] = dict(r)
    db.close()

    preview_rows = []
    errors       = []
    slabs = [
        (0.25, 'rate_250g'), (0.50, 'rate_500g'), (1.00, 'rate_500g_1'),
        (3.00, 'rate_1_to_3kg'), (10.00, 'rate_3_to_10kg'),
        (float('inf'), 'rate_above_10kg')
    ]

    for idx, row in df.iterrows():
        row_num = idx + 2
        try:
            code     = str(row['Code']).strip().upper()
            date_val = row['Date']
            if pd.isna(date_val):
                raise ValueError("Date is empty")
            if hasattr(date_val, 'strftime'):
                date_str = (date_val.date() if hasattr(date_val, 'date') else date_val).isoformat()
            else:
                date_str = str(date_val).strip().split(' ')[0]
                for fmt in ('%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y'):
                    try:
                        date_str = datetime.strptime(date_str, fmt).date().isoformat()
                        break
                    except:
                        continue
                else:
                    raise ValueError(f"Invalid date format: {date_str}")

            awb_no      = str(row['AWB Number']).strip()
            destination = str(row['Destination']).strip().upper()
            weight      = float(row['Weight'])
            zone_num    = zone_name_to_number(str(row['Zone']).strip())
            rate_row    = rate_cache.get((code, zone_num))
            auto_amount = 0.0

            if rate_row:
                for max_w, col_name in slabs:
                    if weight <= max_w:
                        rate        = float(rate_row.get(col_name) or 0)
                        auto_amount = rate * weight if max_w > 1 else rate
                        break
            auto_amount = round(auto_amount, 2)

            if not rate_row:
                errors.append(
                    f"Row {row_num}: No rate for '{code}' zone {zone_num} — amount set 0.00"
                )

            preview_rows.append({
                "temp_id": row_num, "code": code, "booking_date": date_str,
                "awb_no": awb_no, "destination": destination, "weight": weight,
                "zone": zone_num, "auto_amount": auto_amount,
                "courier": str(row['Courier']).strip()
                    if 'Courier' in df.columns and not pd.isna(row.get('Courier')) else "",
                "valid": True
            })
        except Exception as e:
            errors.append(f"Row {row_num}: {str(e)}")
            preview_rows.append({"temp_id": row_num, "valid": False, "error": str(e)})

    return jsonify({"rows": preview_rows, "errors": errors[:50]})


@app.route("/booking-import-save", methods=["POST"])
@login_required
def booking_import_save():
    data = request.get_json()
    rows = data.get("rows", [])
    if not rows:
        return jsonify({"success": False, "message": "No data to save"})

    db       = get_db_connection()
    cursor   = db.cursor()
    inserted = 0
    errors   = []

    for row in rows:
        if not row.get("valid"):
            errors.append(f"Row {row['temp_id']}: invalid, skipped")
            continue
        try:
            cursor.execute("SELECT id FROM bookings WHERE awb_no=%s LIMIT 1", (row['awb_no'],))
            if cursor.fetchone():
                errors.append(f"Row {row['temp_id']}: AWB '{row['awb_no']}' exists — skipped")
                continue
            cursor.execute("""
                INSERT INTO bookings (
                    code, booking_date, awb_no, destination, weight,
                    courier, zone, auto_amount, fuel, total_amount,
                    client_name, inv_no, inv_date
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                row['code'], row['booking_date'], row['awb_no'],
                row['destination'], row['weight'], row.get('courier', ''),
                str(row['zone']), row['auto_amount'], 0.0, row['auto_amount'],
                '', '', None
            ))
            inserted += 1
        except Exception as e:
            errors.append(f"Row {row['temp_id']}: {str(e)}")

    db.commit()
    db.close()
    return jsonify({"success": True, "inserted": inserted, "errors": errors[:50]})

# ============================================================
# API: bookings (AJAX)
# ============================================================
@app.route("/api/bookings")
@login_required
def api_bookings():
    limit  = request.args.get("limit")
    db     = get_db_connection()
    cursor = db.cursor()
    sql = """
        SELECT id, code, booking_date, awb_no, destination, weight,
               courier, zone, auto_amount, fuel, total_amount,
               client_name, inv_no, inv_date
        FROM bookings
        ORDER BY booking_date DESC, id DESC
    """
    cursor.execute(sql if limit == "all" else sql + " LIMIT 10")
    rows   = cursor.fetchall()
    db.close()
    result = []
    for r in rows:
        row = dict(r)
        for k, v in row.items():
            if hasattr(v, 'isoformat'):
                row[k] = v.isoformat()
        result.append(row)
    return jsonify(result)

# ============================================================
# INVOICE / STATEMENT
# ============================================================
@app.route("/invoice", methods=["GET", "POST"])
@login_required
def invoice():
    db     = get_db_connection()
    cursor = db.cursor()

    from_date = request.args.get("from_date", "")
    to_date   = request.args.get("to_date",   "")
    code      = request.args.get("code",      "ALL")
    try:
        fuel_rate = float(request.args.get("fuel_rate", "0"))
    except (ValueError, TypeError):
        fuel_rate = 0.0

    limit_str = request.args.get("limit", "20")
    page      = int(request.args.get("page", 1))
    limit     = None if limit_str == "all" else (int(limit_str) if limit_str.isdigit() else 20)

    base_query = "FROM bookings WHERE booking_date IS NOT NULL"
    params     = []
    if from_date and to_date:
        base_query += " AND booking_date BETWEEN %s AND %s"
        params.extend([from_date, to_date])
    if code and code != "ALL":
        base_query += " AND code = %s"
        params.append(code)

    cursor.execute(f"SELECT COUNT(*) AS total {base_query}", params)
    total = cursor.fetchone()["total"]

    if limit:
        offset      = (page - 1) * limit
        total_pages = (total + limit - 1) // limit
        cursor.execute(
            f"SELECT booking_date, destination, awb_no, weight, total_amount "
            f"{base_query} ORDER BY booking_date DESC, id DESC LIMIT %s OFFSET %s",
            params + [limit, offset]
        )
    else:
        total_pages = 1
        page        = 1
        cursor.execute(
            f"SELECT booking_date, destination, awb_no, weight, total_amount "
            f"{base_query} ORDER BY booking_date DESC, id DESC",
            params
        )

    rows = [dict(r) for r in cursor.fetchall()]
    cursor.execute("SELECT DISTINCT code FROM bookings ORDER BY code")
    codes = [dict(r) for r in cursor.fetchall()]
    db.close()

    return render_template(
        "invoice.html",
        rows=rows, codes=codes,
        from_date=from_date, to_date=to_date,
        selected_code=code, fuel_rate=fuel_rate,
        limit=limit_str, page=page,
        total_pages=total_pages, total=total,
        role=session.get("role")
    )

# ============================================================
# SALES CHECKING
# ============================================================
@app.route("/sales-checking", methods=["GET", "POST"])
@login_required
def sales_checking():
    db     = get_db_connection()
    cursor = db.cursor()

    show_results = (request.method == "POST")

    client_code = request.form.get("client_code", "").strip()
    awb_no      = request.form.get("awb_no", "").strip()
    destination = request.form.get("destination", "").strip()
    single_date = request.form.get("date", "").strip()

    rows         = []
    total_amount = 0

    if show_results:
        query = """
            SELECT code, awb_no, destination,
                   COUNT(*) AS sum_count, SUM(total_amount) AS amount
            FROM bookings WHERE 1=1
        """
        params = []

        if client_code:
            query += " AND code ILIKE %s"
            params.append(f"%{client_code}%")
        if awb_no:
            query += " AND awb_no ILIKE %s"
            params.append(f"%{awb_no}%")
        if destination:
            query += " AND destination ILIKE %s"
            params.append(f"%{destination}%")
        if single_date:
            query += " AND booking_date = %s"
            params.append(single_date)

        query += " GROUP BY code, awb_no, destination ORDER BY code"
        cursor.execute(query, params)
        rows         = [dict(r) for r in cursor.fetchall()]
        total_amount = sum(r["amount"] for r in rows) if rows else 0

    db.close()
    return render_template(
        "sales_checking.html",
        rows=rows,
        total_amount=total_amount,
        filters=request.form,
        show_results=show_results,
        role=session.get("role")
    )

# ============================================================
# DAY WISE
# ============================================================
@app.route("/day-wise", methods=["GET", "POST"])
@login_required
def day_wise():
    db     = get_db_connection()
    cursor = db.cursor()
    if request.method == "POST" and "save" in request.form:
        cursor.execute(
            "INSERT INTO day_wise (entry_date, total_weight, total_sales) VALUES (%s,%s,%s)",
            (request.form["entry_date"],
             float(request.form["total_weight"] or 0),
             float(request.form["total_sales"]  or 0))
        )
        db.commit()
        db.close()
        return redirect("/day-wise")

    from_date = request.form.get("from_date")
    to_date   = request.form.get("to_date")
    query     = "SELECT * FROM day_wise WHERE 1=1"
    params    = []
    if from_date and to_date:
        query += " AND entry_date BETWEEN %s AND %s"
        params.extend([from_date, to_date])
    query += " ORDER BY entry_date"
    cursor.execute(query, params)
    rows         = [dict(r) for r in cursor.fetchall()]
    grand_weight = sum(r["total_weight"] for r in rows) if rows else 0
    grand_sales  = sum(r["total_sales"]  for r in rows) if rows else 0
    db.close()
    return render_template("day_wise.html", rows=rows,
                           from_date=from_date, to_date=to_date,
                           grand_weight=grand_weight, grand_sales=grand_sales,
                           role=session.get("role"))

# ============================================================
# DAY BOOK
# ============================================================
@app.route("/day-book", methods=["GET", "POST"])
@login_required
def day_book():
    db     = get_db_connection()
    cursor = db.cursor()
    entry_date  = request.form.get("entry_date")
    weight      = request.form.get("weight")
    awb_no      = request.form.get("awb_no")
    destination = request.form.get("destination")
    query  = "SELECT weight, awb_no, destination, total_amount FROM bookings WHERE 1=1"
    params = []
    if entry_date:  query += " AND booking_date = %s";       params.append(entry_date)
    if weight:      query += " AND weight = %s";             params.append(weight)
    if awb_no:      query += " AND awb_no ILIKE %s";         params.append(f"%{awb_no}%")
    if destination: query += " AND destination ILIKE %s";    params.append(f"%{destination}%")
    query += " ORDER BY awb_no"
    cursor.execute(query, params)
    rows      = [dict(r) for r in cursor.fetchall()]
    total_sum = sum(r["total_amount"] for r in rows) if rows else 0
    db.close()
    return render_template("day_book.html", rows=rows, total_sum=total_sum,
                           entry_date=entry_date, weight=weight,
                           awb_no=awb_no, destination=destination,
                           role=session.get("role"))

# ============================================================
# EXPORTS  (admin only)
# ============================================================
@app.route("/invoice-export", methods=["POST"])
@admin_required
def invoice_export():
    db     = get_db_connection()
    cursor = db.cursor()
    try:    fuel_rate = float(request.form.get("fuel_rate", 0))
    except: fuel_rate = 0.0

    from_date = request.form.get("from_date", "")
    to_date   = request.form.get("to_date", "")
    code      = request.form.get("code", "ALL")

    # PostgreSQL uses double-quoted aliases
    query  = """SELECT booking_date AS "DATE", destination AS "DESTINATION",
                       awb_no AS "AWB NO", weight AS "WEIGHT",
                       total_amount AS "Total"
                FROM bookings WHERE 1=1"""
    params = []
    if from_date and to_date:
        query += " AND booking_date BETWEEN %s AND %s"
        params.extend([from_date, to_date])
    if code and code != "ALL":
        query += " AND code=%s"
        params.append(code)
    query += " ORDER BY booking_date"
    cursor.execute(query, params)
    df = pd.DataFrame([dict(r) for r in cursor.fetchall()])

    if fuel_rate > 0 and not df.empty:
        df['Fuel']        = (df['Total'].astype(float) * fuel_rate / 100).round(2)
        df['Grand Total'] = (df['Total'].astype(float) + df['Fuel']).round(2)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        info_df = pd.DataFrame([
            ["Company Name:",       "Professional Couriers"],
            ["Transaction Period:", f"{from_date} to {to_date}"],
            ["Customer Code:",      code],
            ["", ""],
        ])
        info_df.to_excel(writer, index=False, header=False, sheet_name="Invoice", startrow=0)
        df.to_excel(writer, index=False, sheet_name="Invoice", startrow=5)
    output.seek(0)
    db.close()
    return send_file(output, as_attachment=True, download_name="Invoice_Statement.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.route("/zone-export")
@admin_required
def zone_export():
    db = get_db_connection()
    cursor = db.cursor()
    cursor.execute("SELECT district, rate_zone FROM zones")
    df = pd.DataFrame([dict(r) for r in cursor.fetchall()])
    output = io.BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)
    db.close()
    return send_file(output, as_attachment=True, download_name="Zone_Data.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.route("/rate-export")
@admin_required
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
    return send_file(output, as_attachment=True, download_name="Rate_Entry.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.route("/booking-export")
@admin_required
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
    return send_file(output, as_attachment=True, download_name="Booking_Data.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.route("/sales-export", methods=["POST"])
@admin_required
def sales_export():
    db     = get_db_connection()
    cursor = db.cursor()
    query  = """SELECT code AS "Client Code", awb_no AS "AWB No",
                       destination AS "Destination", COUNT(*) AS "Sum",
                       SUM(total_amount) AS "Amount"
                FROM bookings WHERE 1=1"""
    params = []
    if request.form.get("client_code"):
        query += " AND code ILIKE %s"
        params.append(f"%{request.form['client_code']}%")
    if request.form.get("awb_no"):
        query += " AND awb_no ILIKE %s"
        params.append(f"%{request.form['awb_no']}%")
    if request.form.get("destination"):
        query += " AND destination ILIKE %s"
        params.append(f"%{request.form['destination']}%")
    if request.form.get("date"):
        query += " AND booking_date = %s"
        params.append(request.form["date"])
    query += " GROUP BY code, awb_no, destination ORDER BY code"
    cursor.execute(query, params)
    df = pd.DataFrame([dict(r) for r in cursor.fetchall()])
    output = io.BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)
    db.close()
    return send_file(output, as_attachment=True, download_name="Sales_Checking.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.route("/day-wise-export", methods=["POST"])
@admin_required
def day_wise_export():
    db = get_db_connection()
    cursor = db.cursor()
    query  = """SELECT entry_date AS "DATE", total_weight AS "Total Weight",
                       total_sales AS "Total Sales Amount"
                FROM day_wise WHERE 1=1"""
    params = []
    if request.form.get("from_date") and request.form.get("to_date"):
        query += " AND entry_date BETWEEN %s AND %s"
        params.extend([request.form["from_date"], request.form["to_date"]])
    query += " ORDER BY entry_date"
    cursor.execute(query, params)
    df = pd.DataFrame([dict(r) for r in cursor.fetchall()])
    output = io.BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)
    db.close()
    return send_file(output, as_attachment=True, download_name="Day_Wise_Manual.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.route("/day-book-export", methods=["POST"])
@admin_required
def day_book_export():
    db = get_db_connection()
    cursor = db.cursor()
    query  = """SELECT weight AS "WEIGHT", awb_no AS "AWB NO",
                       destination AS "DESTINATION", total_amount AS "Total"
                FROM bookings WHERE 1=1"""
    params = []
    if request.form.get("entry_date"):  query += " AND booking_date = %s";    params.append(request.form["entry_date"])
    if request.form.get("weight"):      query += " AND weight = %s";          params.append(request.form["weight"])
    if request.form.get("awb_no"):      query += " AND awb_no ILIKE %s";      params.append(f"%{request.form['awb_no']}%")
    if request.form.get("destination"): query += " AND destination ILIKE %s"; params.append(f"%{request.form['destination']}%")
    cursor.execute(query, params)
    df = pd.DataFrame([dict(r) for r in cursor.fetchall()])
    output = io.BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)
    db.close()
    return send_file(output, as_attachment=True, download_name="Day_Book.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ============================================================
# INVOICE PDF
# ============================================================
class WatermarkDocTemplate(SimpleDocTemplate):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.watermark_text = "AIKONIX"

    def afterPage(self):
        self.canv.saveState()
        self.canv.setFont('Helvetica', 80)
        self.canv.setFillColor(colors.Color(red=0.5, green=0.5, blue=0.5, alpha=0.25))
        pw, ph = A4
        self.canv.translate(pw / 2, ph / 2)
        self.canv.rotate(45)
        self.canv.drawCentredString(0, 0, self.watermark_text)
        self.canv.restoreState()


@app.route("/invoice-pdf", methods=["POST"])
@login_required
def invoice_pdf():
    def s(v):
        return '' if v is None else str(v)

    db     = get_db_connection()
    cursor = db.cursor()
    from_date    = request.form.get("from_date", "").strip()
    to_date      = request.form.get("to_date", "").strip()
    code         = request.form.get("code", "").strip()
    try:
        fuel_percent = float(request.form.get("fuel_rate", 0) or 0)
    except:
        fuel_percent = 0.0

    filter_code = None if (not code or code == "ALL") else code

    query  = "SELECT booking_date, destination, awb_no, weight, total_amount FROM bookings WHERE booking_date IS NOT NULL"
    params = []
    if from_date and to_date:
        query += " AND booking_date BETWEEN %s AND %s"
        params.extend([from_date, to_date])
    if filter_code:
        query += " AND code = %s"
        params.append(filter_code)
    query += " ORDER BY booking_date"
    cursor.execute(query, params)
    rows = [dict(r) for r in cursor.fetchall()]
    db.close()

    if not rows:
        return "<h3 style='font-family:sans-serif;padding:2rem'>No records found for the selected filters.</h3>", 200

    buf = io.BytesIO()
    doc = WatermarkDocTemplate(buf, pagesize=A4,
                               leftMargin=10*mm, rightMargin=10*mm,
                               topMargin=12*mm, bottomMargin=12*mm)

    title_style = ParagraphStyle('title', fontSize=13, alignment=TA_CENTER,
                                 spaceAfter=4, fontName='Helvetica-Bold')
    sub_style   = ParagraphStyle('sub',   fontSize=9,  alignment=TA_CENTER,
                                 spaceAfter=8, textColor=colors.grey)

    elements = []
    elements.append(Paragraph("Professional Couriers", title_style))
    title_text = "Invoice / Statement"
    if filter_code:
        title_text += f"  -  {filter_code}"
    elements.append(Paragraph(title_text, title_style))
    if from_date and to_date:
        elements.append(Paragraph(f"Transaction Period: {from_date}  to  {to_date}", sub_style))
    if fuel_percent > 0:
        elements.append(Paragraph(f"Fuel Surcharge: {fuel_percent:.2f}%", sub_style))
    elements.append(Spacer(1, 4*mm))

    header      = ['SNO', 'DATE', 'DESTINATION', 'AWB NO', 'WEIGHT', 'Total']
    col_widths  = [20*mm, 28*mm, 55*mm, 50*mm, 22*mm, 25*mm]
    ROW_H       = 6*mm
    HEADER_H    = 8*mm

    data        = [header]
    row_heights = [HEADER_H]
    style_cmds  = []
    row_idx     = 1
    sno         = 0
    sum_base    = 0.0

    for date_val, grp in groupby(rows, key=itemgetter("booking_date")):
        grp      = list(grp)
        date_str = date_val.strftime('%d-%m-%Y') if hasattr(date_val, 'strftime') else str(date_val)
        first    = True
        for r in grp:
            sno      += 1
            base      = float(r["total_amount"] or 0)
            sum_base += base
            bg = colors.white if (row_idx % 2 == 1) else colors.HexColor('#f8f9fa')
            style_cmds.append(('BACKGROUND', (0, row_idx), (-1, row_idx), bg))
            data.append([
                str(sno),
                date_str if first else '',
                s(r["destination"]),
                s(r["awb_no"]),
                f"{float(r['weight'] or 0):.3f}",
                f"{base:.2f}"
            ])
            row_heights.append(ROW_H)
            first    = False
            row_idx += 1

    if fuel_percent > 0:
        fuel_total  = sum_base * fuel_percent / 100
        grand_total = sum_base + fuel_total
        summary_rows = [
            ['', '', '', '', 'Total:',          f"{sum_base:.2f}"],
            ['', '', '', '', 'Fuel Surcharge:', f"{fuel_total:.2f}"],
            ['', '', '', '', 'Grand Total:',    f"{grand_total:.2f}"],
        ]
    else:
        summary_rows = [
            ['', '', '', '', 'Total:', f"{sum_base:.2f}"],
        ]

    for sr in summary_rows:
        data.append(sr)
        row_heights.append(ROW_H)

    total_rows = len(data)

    base_cmds = [
        ('BACKGROUND',    (0, 0),  (-1, 0),  colors.HexColor('#212529')),
        ('TEXTCOLOR',     (0, 0),  (-1, 0),  colors.white),
        ('FONTNAME',      (0, 0),  (-1, 0),  'Helvetica-Bold'),
        ('FONTSIZE',      (0, 0),  (-1, 0),  8),
        ('ALIGN',         (0, 0),  (-1, 0),  'CENTER'),
        ('VALIGN',        (0, 0),  (-1, 0),  'MIDDLE'),
        ('TOPPADDING',    (0, 0),  (-1, 0),  4),
        ('BOTTOMPADDING', (0, 0),  (-1, 0),  4),
        ('FONTSIZE',      (0, 1),  (-1, -1), 8),
        ('FONTNAME',      (0, 1),  (-1, -1), 'Helvetica'),
        ('VALIGN',        (0, 1),  (-1, -1), 'MIDDLE'),
        ('TOPPADDING',    (0, 1),  (-1, -1), 2),
        ('BOTTOMPADDING', (0, 1),  (-1, -1), 2),
        ('GRID',          (0, 0),  (-1, total_rows - len(summary_rows) - 1), 0.4, colors.grey),
        ('ALIGN',         (4, 1),  (-1, -1), 'RIGHT'),
        ('ALIGN',         (0, 1),  (0, -1),  'CENTER'),
        ('ALIGN',         (1, 1),  (1, -1),  'CENTER'),
        ('BOX',           (0, 0),  (-1, -1), 0.8, colors.black),
        ('LINEABOVE',     (0, total_rows - len(summary_rows)),
                          (-1, total_rows - len(summary_rows)), 1.2, colors.black),
    ]

    for i in range(len(summary_rows)):
        r = total_rows - len(summary_rows) + i
        base_cmds.extend([
            ('BACKGROUND', (0, r), (-1, r), colors.HexColor('#e9ecef')),
            ('FONTNAME',   (0, r), (-1, r), 'Helvetica-Bold'),
        ])

    t = Table(data, colWidths=col_widths, rowHeights=row_heights)
    t.setStyle(TableStyle(base_cmds + style_cmds))
    elements.append(t)
    doc.build(elements)
    buf.seek(0)

    fname = f"Invoice_{filter_code or 'ALL'}"
    if from_date and to_date:
        fname += f"_{from_date}_to_{to_date}"
    fname += ".pdf"

    return send_file(buf, as_attachment=True, download_name=fname,
                     mimetype='application/pdf')

# ============================================================
# SALES PDF
# ============================================================
@app.route("/sales-pdf", methods=["POST"])
@login_required
def sales_pdf():
    db     = get_db_connection()
    cursor = db.cursor()

    client_code = request.form.get("client_code", "").strip()
    awb_no      = request.form.get("awb_no", "").strip()
    destination = request.form.get("destination", "").strip()
    single_date = request.form.get("date", "").strip()

    query = """
        SELECT code, awb_no, destination,
               COUNT(*) AS sum_count, SUM(total_amount) AS amount
        FROM bookings WHERE 1=1
    """
    params = []
    if client_code:
        query += " AND code ILIKE %s"
        params.append(f"%{client_code}%")
    if awb_no:
        query += " AND awb_no ILIKE %s"
        params.append(f"%{awb_no}%")
    if destination:
        query += " AND destination ILIKE %s"
        params.append(f"%{destination}%")
    if single_date:
        query += " AND booking_date = %s"
        params.append(single_date)

    query += " GROUP BY code, awb_no, destination ORDER BY code"
    cursor.execute(query, params)
    rows         = [dict(r) for r in cursor.fetchall()]
    total_amount = sum(r["amount"] for r in rows) if rows else 0
    db.close()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=20, rightMargin=20,
                            topMargin=30, bottomMargin=20)

    styles       = getSampleStyleSheet()
    title_style  = ParagraphStyle('Title', parent=styles['Heading1'],
                                  alignment=TA_CENTER, spaceAfter=10)
    normal_style = styles['Normal']
    name_style   = ParagraphStyle('NameStyle', parent=styles['Normal'],
                                  fontSize=9, leading=11)

    elements = []
    elements.append(Paragraph("Sales Checking Report", title_style))

    filter_text = []
    if client_code: filter_text.append(f"Client Code: {client_code}")
    if awb_no:      filter_text.append(f"AWB: {awb_no}")
    if destination: filter_text.append(f"Destination: {destination}")
    if single_date: filter_text.append(f"Date: {single_date}")
    if filter_text:
        elements.append(Paragraph(" | ".join(filter_text), normal_style))
    elements.append(Spacer(1, 12))

    header = ['SNO', 'Client Code', 'AWB No', 'Destination', 'Count', 'Amount (₹)']
    data   = [header]

    for i, row in enumerate(rows, start=1):
        data.append([
            str(i),
            Paragraph(row['code'] or '', name_style),
            row['awb_no'] or '',
            row['destination'] or '',
            str(row['sum_count']),
            f"{row['amount']:.2f}"
        ])

    data.append(['', '', '', '', 'Total:', f"{total_amount:.2f}"])

    col_widths = [30, 140, 90, 130, 45, 70]
    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0),  (-1, 0),  colors.grey),
        ('TEXTCOLOR',     (0, 0),  (-1, 0),  colors.whitesmoke),
        ('ALIGN',         (0, 0),  (-1, 0),  'CENTER'),
        ('FONTNAME',      (0, 0),  (-1, 0),  'Helvetica-Bold'),
        ('FONTSIZE',      (0, 0),  (-1, 0),  10),
        ('BOTTOMPADDING', (0, 0),  (-1, 0),  6),
        ('BACKGROUND',    (0, 1),  (-1, -2), colors.beige),
        ('FONTNAME',      (0, 1),  (-1, -1), 'Helvetica'),
        ('FONTSIZE',      (0, 1),  (-1, -1), 9),
        ('ALIGN',         (0, 1),  (0,  -1), 'CENTER'),
        ('ALIGN',         (4, 1),  (5,  -1), 'RIGHT'),
        ('VALIGN',        (0, 0),  (-1, -1), 'MIDDLE'),
        ('GRID',          (0, 0),  (-1, -2), 0.5, colors.grey),
        ('LINEABOVE',     (0, -1), (-1, -1), 1,   colors.black),
        ('BACKGROUND',    (0, -1), (-1, -1), colors.lavender),
        ('FONTNAME',      (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('ALIGN',         (4, -1), (5,  -1), 'RIGHT'),
    ]))

    elements.append(table)
    doc.build(elements)
    buf.seek(0)

    return send_file(buf, as_attachment=True,
                     download_name="Sales_Checking_Report.pdf",
                     mimetype='application/pdf')

# ============================================================
# AJAX — AUTOCOMPLETE & LOOKUP ENDPOINTS
# ============================================================
@app.route("/day-book/filter")
@login_required
def day_book_filter():
    db = get_db_connection()
    cursor = db.cursor()
    entry_date  = request.args.get("entry_date", "")
    weight      = request.args.get("weight", "")
    awb_no      = request.args.get("awb_no", "")
    destination = request.args.get("destination", "")
    query  = "SELECT weight, awb_no, destination, total_amount FROM bookings WHERE 1=1"
    params = []
    if entry_date:  query += " AND booking_date = %s";       params.append(entry_date)
    if weight:      query += " AND weight = %s";             params.append(float(weight))
    if awb_no:      query += " AND awb_no ILIKE %s";         params.append(f"%{awb_no}%")
    if destination: query += " AND destination ILIKE %s";    params.append(f"%{destination}%")
    query += " ORDER BY awb_no"
    cursor.execute(query, params)
    rows      = [dict(r) for r in cursor.fetchall()]
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
        "SELECT DISTINCT code, code_fullform FROM rates WHERE code ILIKE %s OR code_fullform ILIKE %s LIMIT 10",
        (f"{q}%", f"%{q}%")
    )
    rows = [dict(r) for r in cur.fetchall()]
    db.close()
    return jsonify(rows)


@app.route("/api/ac/place")
def api_ac_place():
    q = request.args.get("q", "").strip()
    if not q: return jsonify([])
    db = get_db_connection()
    cur = db.cursor()
    cur.execute("SELECT DISTINCT place FROM rates WHERE place ILIKE %s ORDER BY place LIMIT 12", (f"{q}%",))
    rows = cur.fetchall()
    db.close()
    return jsonify([r["place"] for r in rows])


@app.route("/api/ac/zone")
def api_ac_zone():
    q = request.args.get("q", "").strip()
    if not q: return jsonify([])
    db = get_db_connection()
    cur = db.cursor()
    cur.execute("SELECT DISTINCT place FROM rates WHERE place ILIKE %s ORDER BY place LIMIT 12", (f"{q}%",))
    rows = cur.fetchall()
    db.close()
    return jsonify([r["place"] for r in rows])


@app.route("/api/ac/destination")
def api_ac_destination():
    q = request.args.get("q", "").strip()
    if not q: return jsonify([])
    db = get_db_connection()
    cur = db.cursor()
    cur.execute("SELECT DISTINCT destination FROM bookings WHERE destination ILIKE %s LIMIT 12", (f"{q}%",))
    rows = cur.fetchall()
    db.close()
    return jsonify([r["destination"] for r in rows if r["destination"]])


@app.route("/api/ac/client")
def api_ac_client():
    q = request.args.get("q", "").strip()
    if not q: return jsonify([])
    db = get_db_connection()
    cur = db.cursor()
    cur.execute("SELECT DISTINCT client_name FROM bookings WHERE client_name ILIKE %s LIMIT 10", (f"%{q}%",))
    rows = cur.fetchall()
    db.close()
    return jsonify([r["client_name"] for r in rows if r["client_name"]])


@app.route("/api/rate/lookup")
def api_rate_lookup():
    code     = request.args.get("code", "").strip().upper()
    zone_str = request.args.get("zone", "").strip()
    if not code or not zone_str: return jsonify({})
    try:    zone = int(zone_str)
    except: return jsonify({})
    db = get_db_connection()
    cur = db.cursor()
    cur.execute("SELECT * FROM rates WHERE UPPER(code)=%s AND zone=%s LIMIT 1", (code, zone))
    row = cur.fetchone()
    db.close()
    return jsonify(dict(row) if row else {})


@app.route("/api/ac/awb_check")
def api_awb_check():
    awb     = request.args.get("awb", "").strip()
    edit_id = request.args.get("edit_id", "").strip()
    if not awb: return jsonify({"exists": False})
    db  = get_db_connection()
    cur = db.cursor()
    if edit_id:
        cur.execute(
            "SELECT id, code, booking_date, destination FROM bookings WHERE awb_no=%s AND id!=%s LIMIT 1",
            (awb, edit_id)
        )
    else:
        cur.execute(
            "SELECT id, code, booking_date, destination FROM bookings WHERE awb_no=%s LIMIT 1",
            (awb,)
        )
    row = cur.fetchone()
    db.close()
    if row:
        return jsonify({"exists": True, "code": row["code"],
                        "date": str(row["booking_date"]), "dest": row["destination"]})
    return jsonify({"exists": False})


@app.route("/api/place/save-zone", methods=["POST"])
@login_required
def api_place_save_zone():
    data       = request.get_json()
    place      = data.get("place", "").strip().upper()
    zone       = int(data.get("zone", 5))
    place_code = data.get("place_code", "").strip().upper() or None
    if not place: return jsonify({"ok": False})
    db  = get_db_connection()
    cur = db.cursor()
    # PostgreSQL upsert syntax
    cur.execute("""
        INSERT INTO place_zones (place, zone, place_code) VALUES (%s,%s,%s)
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
    db     = get_db_connection()
    cursor = db.cursor()
    cursor.execute(
        "SELECT DISTINCT district FROM zones WHERE district ILIKE %s ORDER BY district LIMIT 10",
        (f"{q}%",)
    )
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

    cur.execute("SELECT place, zone FROM place_zones WHERE UPPER(place_code)=%s LIMIT 1", (dest,))
    row = cur.fetchone()
    if row: db.close(); return jsonify(dict(row))

    cur.execute("SELECT zone FROM place_zones WHERE UPPER(place)=%s LIMIT 1", (dest,))
    pz = cur.fetchone()
    if pz: db.close(); return jsonify({"place": dest, "zone": pz["zone"]})

    cur.execute("SELECT place, zone FROM rates WHERE UPPER(code)=%s AND UPPER(place)=%s LIMIT 1", (code, dest))
    row = cur.fetchone()
    if row: db.close(); return jsonify(dict(row))

    cur.execute("SELECT place, zone FROM rates WHERE UPPER(code)=%s ORDER BY zone ASC", (code,))
    all_places = [dict(r) for r in cur.fetchall()]
    for p in all_places:
        pu = p["place"].upper()
        if dest in pu or pu in dest:
            db.close()
            return jsonify({"place": p["place"], "zone": p["zone"]})

    db.close()
    return jsonify({})

# ============================================================
# SMART ZONE API
# ============================================================
@app.route("/api/smart-zone")
def api_smart_zone():
    dest = request.args.get("dest", "").strip().upper()
    code = request.args.get("code", "").strip().upper()
    if not dest: return jsonify({})
    db  = get_db_connection()
    cur = db.cursor()

    cur.execute("SELECT place, zone FROM place_zones WHERE UPPER(place_code)=%s LIMIT 1", (dest,))
    row = cur.fetchone()
    if row:
        db.close()
        return jsonify({**dict(row), "source": "saved", "label": _zone_label(row["zone"])})

    cur.execute("SELECT zone FROM place_zones WHERE UPPER(place)=%s LIMIT 1", (dest,))
    row = cur.fetchone()
    if row:
        db.close()
        return jsonify({"place": dest, "zone": row["zone"], "source": "saved", "label": _zone_label(row["zone"])})

    if code:
        cur.execute("SELECT place, zone FROM rates WHERE UPPER(code)=%s AND UPPER(place)=%s LIMIT 1", (code, dest))
        row = cur.fetchone()
        if row:
            db.close()
            return jsonify({**dict(row), "source": "rate_exact", "label": _zone_label(row["zone"])})

        cur.execute("SELECT place, zone FROM rates WHERE UPPER(code)=%s ORDER BY zone", (code,))
        for p in [dict(r) for r in cur.fetchall()]:
            if dest in p["place"].upper() or p["place"].upper() in dest:
                db.close()
                return jsonify({"place": p["place"], "zone": p["zone"], "source": "rate_partial",
                                "label": _zone_label(p["zone"])})

    db.close()
    zone, label = _keyword_zone(dest)
    if zone:
        return jsonify({"place": dest.title(), "zone": zone, "source": "keyword", "label": label})
    return jsonify({})


def _zone_label(z):
    return {1: "Chennai", 2: "Tamil Nadu", 3: "South India", 4: "North Metro", 5: "ROI"}.get(int(z), "ROI")


def _keyword_zone(dest):
    ZONE1 = ["CHENNAI", "MADRAS", "TAMBARAM", "VELACHERY", "ADYAR", "ANNA NAGAR", "T NAGAR",
             "NUNGAMBAKKAM", "PERAMBUR", "ROYAPURAM", "EGMORE", "KODAMBAKKAM", "CHROMPET",
             "SHOLINGANALLUR", "PORUR", "AMBATTUR", "AVADI", "POONAMALLEE", "PALLAVARAM",
             "PERUNGUDI", "THIRUVANMIYUR", "MYLAPORE", "TRIPLICANE", "WASHERMANPET", "TONDIARPET"]
    ZONE2 = ["COIMBATORE", "MADURAI", "TRICHY", "TIRUCHIRAPPALLI", "SALEM", "TIRUNELVELI",
             "VELLORE", "ERODE", "TIRUPPUR", "THOOTHUKUDI", "TUTICORIN", "DINDIGUL", "THANJAVUR",
             "KANCHIPURAM", "KUMBAKONAM", "NAGERCOIL", "SIVAGANGAI", "NAMAKKAL", "KARUR",
             "PUDUKOTTAI", "RAMANATHAPURAM", "VIRUDHUNAGAR", "CUDDALORE", "NAGAPATTINAM",
             "OOTY", "UDHAGAMANDALAM", "KODAIKANAL", "HOSUR", "RANIPET", "TIRUVANNAMALAI",
             "VILLUPURAM", "ARIYALUR", "PERAMBALUR", "KALLAKURICHI", "TENKASI", "KRISHNAGIRI",
             "DHARMAPURI", "THENI", "NILGIRIS", "CHENGALPATTU", "TIRUPATTUR"]
    ZONE3 = ["KERALA", "THIRUVANANTHAPURAM", "TRIVANDRUM", "KOCHI", "COCHIN", "KOZHIKODE",
             "CALICUT", "THRISSUR", "KOLLAM", "PALAKKAD", "ALAPPUZHA", "ALLEPPEY", "KANNUR",
             "MALAPPURAM", "KASARAGOD", "WAYANAD", "IDUKKI", "PATHANAMTHITTA", "ERNAKULAM",
             "KOTTAYAM", "KARNATAKA", "BENGALURU", "BANGALORE", "MYSURU", "MYSORE", "HUBLI",
             "DHARWAD", "MANGALURU", "MANGALORE", "BELAGAVI", "BELGAUM", "GULBARGA", "KALABURAGI",
             "DAVANAGERE", "BELLARY", "VIJAYAPURA", "BIJAPUR", "SHIMOGA", "SHIVAMOGGA", "TUMKUR",
             "UDUPI", "HASSAN", "BIDAR", "RAICHUR", "BAGALKOT", "CHITRADURGA", "ANDHRA",
             "VISAKHAPATNAM", "VIZAG", "VIJAYAWADA", "GUNTUR", "NELLORE", "KURNOOL",
             "RAJAHMUNDRY", "KAKINADA", "TIRUPATI", "ANANTAPUR", "KADAPA", "CHITTOOR", "ELURU",
             "ONGOLE", "VIZIANAGARAM", "TELANGANA", "HYDERABAD", "WARANGAL", "NIZAMABAD",
             "KHAMMAM", "KARIMNAGAR", "RAMAGUNDAM", "SECUNDERABAD", "NALGONDA", "ADILABAD",
             "MAHBUBNAGAR", "SANGAREDDY", "SIDDIPET"]
    ZONE4 = ["DELHI", "NEW DELHI", "GURGAON", "GURUGRAM", "NOIDA", "FARIDABAD", "GHAZIABAD",
             "GREATER NOIDA", "MUMBAI", "BOMBAY", "THANE", "NAVI MUMBAI", "PUNE",
             "KOLKATA", "CALCUTTA", "HOWRAH", "DURGAPUR", "ASANSOL"]
    for kw in ZONE1:
        if kw in dest: return 1, "Chennai"
    for kw in ZONE2:
        if kw in dest: return 2, "Tamil Nadu"
    for kw in ZONE3:
        if kw in dest: return 3, "South India"
    for kw in ZONE4:
        if kw in dest: return 4, "North Metro"
    return 5, "ROI"

# ============================================================
# RUN
# ============================================================
if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0')