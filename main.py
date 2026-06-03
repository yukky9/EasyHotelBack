from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel
from typing import List, Optional
import sqlite3
from datetime import datetime, timedelta
import base64
import csv
from io import StringIO
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_NAME = "easyhotel.db"


def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS staff (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            first_name TEXT,
            last_name TEXT,
            role TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS guests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            phone TEXT,
            country TEXT,
            city TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS room_types (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            base_price REAL NOT NULL
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS rooms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room_number TEXT UNIQUE NOT NULL,
            room_type_id INTEGER NOT NULL,
            status TEXT DEFAULT 'available',
            FOREIGN KEY (room_type_id) REFERENCES room_types(id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guest_id INTEGER NOT NULL,
            room_id INTEGER NOT NULL,
            staff_id INTEGER NOT NULL,
            check_in_date TEXT NOT NULL,
            check_out_date TEXT NOT NULL,
            total_price REAL NOT NULL,
            status TEXT DEFAULT 'confirmed',
            amount_paid REAL DEFAULT 0,
            balance_due REAL DEFAULT 0,
            adults INTEGER DEFAULT 1,
            children INTEGER DEFAULT 0,
            special_requests TEXT,
            room_type TEXT,
            payment_status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            source TEXT,
            FOREIGN KEY (guest_id) REFERENCES guests(id),
            FOREIGN KEY (room_id) REFERENCES rooms(id),
            FOREIGN KEY (staff_id) REFERENCES staff(id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            period_start TEXT NOT NULL,
            period_end TEXT NOT NULL,
            format TEXT NOT NULL,
            size TEXT,
            file_data TEXT,
            file_name TEXT
        )
    ''')

    cursor.execute("PRAGMA table_info(bookings)")
    existing_cols = [col[1] for col in cursor.fetchall()]

    if 'adults' not in existing_cols:
        cursor.execute("ALTER TABLE bookings ADD COLUMN adults INTEGER DEFAULT 1")
    if 'children' not in existing_cols:
        cursor.execute("ALTER TABLE bookings ADD COLUMN children INTEGER DEFAULT 0")
    if 'special_requests' not in existing_cols:
        cursor.execute("ALTER TABLE bookings ADD COLUMN special_requests TEXT")
    if 'room_type' not in existing_cols:
        cursor.execute("ALTER TABLE bookings ADD COLUMN room_type TEXT")
    if 'payment_status' not in existing_cols:
        cursor.execute("ALTER TABLE bookings ADD COLUMN payment_status TEXT DEFAULT 'pending'")
    if 'source' not in existing_cols:
        cursor.execute("ALTER TABLE bookings ADD COLUMN source TEXT")
    if 'created_at' not in existing_cols:
        cursor.execute("ALTER TABLE bookings ADD COLUMN created_at TIMESTAMP")
        cursor.execute("UPDATE bookings SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL")

    cursor.execute("PRAGMA table_info(staff)")
    staff_cols = [col[1] for col in cursor.fetchall()]
    if 'email' not in staff_cols:
        cursor.execute("ALTER TABLE staff ADD COLUMN email TEXT")
    if 'phone' not in staff_cols:
        cursor.execute("ALTER TABLE staff ADD COLUMN phone TEXT")
    if 'birth_date' not in staff_cols:
        cursor.execute("ALTER TABLE staff ADD COLUMN birth_date TEXT")
    if 'avatar' not in staff_cols:
        cursor.execute("ALTER TABLE staff ADD COLUMN avatar TEXT")

    cursor.execute("SELECT COUNT(*) FROM staff WHERE username='admin'")
    if cursor.fetchone()[0] == 0:
        cursor.execute('''
            INSERT INTO staff (username, password, first_name, last_name, role, email, phone, birth_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', ('admin', 'admin123', 'Admin', 'User', 'manager', 'admin@hotel.com', '+7 (999) 123-45-67', '1990-01-01'))

    cursor.execute("SELECT COUNT(*) FROM room_types")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO room_types (name, base_price) VALUES (?, ?)", ('Deluxe', 250.0))
        cursor.execute("INSERT INTO room_types (name, base_price) VALUES (?, ?)", ('Standard', 150.0))

    cursor.execute("SELECT COUNT(*) FROM rooms")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO rooms (room_number, room_type_id, status) VALUES (?, ?, ?)",
                       ('101', 1, 'available'))
        cursor.execute("INSERT INTO rooms (room_number, room_type_id, status) VALUES (?, ?, ?)",
                       ('102', 2, 'available'))

    conn.commit()
    conn.close()
    print("✅ База данных инициализирована")


init_db()


# ========== МОДЕЛИ ==========
class GuestIn(BaseModel):
    first_name: str
    last_name: str
    email: str
    phone: Optional[str] = None
    country: Optional[str] = None
    city: Optional[str] = None


class GuestOut(GuestIn):
    id: int


class BookingIn(BaseModel):
    guest_id: int
    room_id: int
    staff_id: int
    check_in_date: str
    check_out_date: str
    adults: Optional[int] = 1
    children: Optional[int] = 0
    special_requests: Optional[str] = None
    room_type: Optional[str] = None
    source: Optional[str] = None


class BookingOut(BaseModel):
    id: int
    guest_id: int
    room_id: int
    staff_id: int
    check_in_date: str
    check_out_date: str
    total_price: float
    status: str
    amount_paid: float
    balance_due: float
    adults: Optional[int] = 1
    children: Optional[int] = 0
    special_requests: Optional[str] = None
    room_type: Optional[str] = None
    payment_status: Optional[str] = 'pending'
    created_at: Optional[str] = None
    source: Optional[str] = None


class ReportGenerate(BaseModel):
    type: str
    start_date: str
    end_date: str
    format: str


# ========== АВТОРИЗАЦИЯ ==========
@app.get("/api/auth/login")
def login(username: str, password: str):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, username, first_name, last_name, role, 
               COALESCE(email, '') as email,
               COALESCE(phone, '') as phone,
               COALESCE(birth_date, '') as birth_date,
               COALESCE(avatar, '') as avatar
        FROM staff WHERE username=? AND password=?
    """, (username, password))
    user = cursor.fetchone()
    conn.close()
    if not user:
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")
    return {
        "access_token": f"fake-token-{user[0]}",
        "token_type": "bearer",
        "user": {
            "id": user[0],
            "username": user[1],
            "first_name": user[2],
            "last_name": user[3],
            "role": user[4],
            "email": user[5],
            "phone": user[6],
            "birth_date": user[7],
            "avatar": user[8]
        }
    }


# ========== ГОСТИ ==========
@app.get("/api/guests", response_model=List[GuestOut])
def get_guests():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT id, first_name, last_name, email, phone, country, city FROM guests")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


@app.get("/api/guests/{guest_id}", response_model=GuestOut)
def get_guest(guest_id: int):
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT id, first_name, last_name, email, phone, country, city FROM guests WHERE id=?", (guest_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "Guest not found")
    return dict(row)


@app.post("/api/guests", response_model=GuestOut)
def create_guest(guest: GuestIn):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO guests (first_name, last_name, email, phone, country, city)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (guest.first_name, guest.last_name, guest.email, guest.phone, guest.country, guest.city))
        conn.commit()
        new_id = cursor.lastrowid
        cursor.execute("SELECT id, first_name, last_name, email, phone, country, city FROM guests WHERE id=?",
                       (new_id,))
        new_guest = cursor.fetchone()
        conn.close()
        return {
            "id": new_guest[0],
            "first_name": new_guest[1],
            "last_name": new_guest[2],
            "email": new_guest[3],
            "phone": new_guest[4],
            "country": new_guest[5],
            "city": new_guest[6],
        }
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=400, detail="Гость с таким email уже существует")


# ========== КОМНАТЫ ==========
@app.get("/api/rooms")
def get_rooms():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT id, room_number, room_type_id, status FROM rooms")
    rooms = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rooms


@app.get("/api/rooms/available")
def get_available_rooms():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT id, room_number, status FROM rooms WHERE status='available'")
    rooms = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rooms


@app.get("/api/rooms/available-by-dates")
def get_available_rooms_by_dates(check_in: str, check_out: str):
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT r.id, r.room_number, rt.name as room_type, rt.base_price
        FROM rooms r
        JOIN room_types rt ON r.room_type_id = rt.id
        WHERE r.status = 'available'
        AND r.id NOT IN (
            SELECT room_id FROM bookings
            WHERE status IN ('confirmed', 'checked_in')
            AND (check_in_date < ? AND check_out_date > ?)
        )
    """, (check_out, check_in))
    rooms = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rooms


@app.get("/api/room-types")
def get_room_types():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, base_price FROM room_types")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


@app.put("/api/rooms/{room_id}/status")
def update_room_status(room_id: int, data: dict):
    new_status = data.get('status')
    if new_status not in ['available', 'occupied', 'maintenance', 'cleaning']:
        raise HTTPException(400, "Invalid status")
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE rooms SET status=? WHERE id=?", (new_status, room_id))
    if cursor.rowcount == 0:
        conn.close()
        raise HTTPException(404, "Room not found")
    conn.commit()
    conn.close()
    return {"message": "Room status updated"}


# ========== БРОНИРОВАНИЯ ==========
@app.get("/api/bookings", response_model=List[BookingOut])
def get_bookings():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, guest_id, room_id, staff_id, check_in_date, check_out_date,
               total_price, status, amount_paid, balance_due,
               COALESCE(adults,1) as adults,
               COALESCE(children,0) as children,
               COALESCE(special_requests,'') as special_requests,
               COALESCE(room_type,'') as room_type,
               COALESCE(payment_status,'pending') as payment_status,
               created_at,
               COALESCE(source,'') as source
        FROM bookings
    ''')
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


@app.get("/api/bookings/{booking_id}")
def get_booking(booking_id: int):
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('''
        SELECT b.*, 
               g.first_name, g.last_name, g.email, g.phone,
               r.room_number
        FROM bookings b
        JOIN guests g ON b.guest_id = g.id
        JOIN rooms r ON b.room_id = r.id
        WHERE b.id = ?
    ''', (booking_id,))
    booking = cursor.fetchone()
    conn.close()
    if not booking:
        raise HTTPException(404, "Booking not found")
    return dict(booking)


@app.post("/api/bookings", response_model=BookingOut)
def create_booking(booking: BookingIn):
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT room_type_id FROM rooms WHERE id=?", (booking.room_id,))
    room = cursor.fetchone()
    if not room:
        conn.close()
        raise HTTPException(status_code=404, detail="Номер не найден")
    cursor.execute("SELECT base_price FROM room_types WHERE id=?", (room[0],))
    room_type = cursor.fetchone()
    price_per_night = room_type[0]
    check_in = datetime.strptime(booking.check_in_date, "%Y-%m-%d")
    check_out = datetime.strptime(booking.check_out_date, "%Y-%m-%d")
    nights = (check_out - check_in).days
    total = price_per_night * nights

    cursor.execute('''
        INSERT INTO bookings 
        (guest_id, room_id, staff_id, check_in_date, check_out_date, total_price, balance_due,
         adults, children, special_requests, room_type, source, payment_status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (booking.guest_id, booking.room_id, booking.staff_id,
          booking.check_in_date, booking.check_out_date, total, total,
          booking.adults or 1, booking.children or 0, booking.special_requests,
          booking.room_type, booking.source, 'pending'))

    conn.commit()
    new_id = cursor.lastrowid
    cursor.execute('''
        SELECT id, guest_id, room_id, staff_id, check_in_date, check_out_date,
               total_price, status, amount_paid, balance_due,
               COALESCE(adults,1) as adults,
               COALESCE(children,0) as children,
               COALESCE(special_requests,'') as special_requests,
               COALESCE(room_type,'') as room_type,
               COALESCE(payment_status,'pending') as payment_status,
               created_at,
               COALESCE(source,'') as source
        FROM bookings WHERE id=?
    ''', (new_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row)


@app.put("/api/bookings/{booking_id}")
def update_booking(booking_id: int, data: dict):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    allowed = ['room_id', 'check_in_date', 'check_out_date', 'status', 'total_price',
               'amount_paid', 'balance_due', 'adults', 'children', 'special_requests',
               'room_type', 'payment_status']
    updates = {k: v for k, v in data.items() if k in allowed and v is not None}
    if not updates:
        raise HTTPException(400, "No valid fields to update")
    set_clause = ", ".join([f"{k}=?" for k in updates])
    values = list(updates.values()) + [booking_id]
    cursor.execute(f"UPDATE bookings SET {set_clause} WHERE id=?", values)
    if cursor.rowcount == 0:
        conn.close()
        raise HTTPException(404, "Booking not found")
    conn.commit()
    conn.close()
    return {"message": "Booking updated"}


@app.put("/api/bookings/{booking_id}/cancel")
def cancel_booking(booking_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE bookings SET status='cancelled', payment_status='refunded' WHERE id=?", (booking_id,))
    if cursor.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Бронирование не найдено")
    conn.commit()
    conn.close()
    return {"message": "Бронирование отменено"}


@app.post("/api/bookings/{booking_id}/checkout")
def checkout_booking(booking_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE bookings SET status='checked_out' WHERE id=?", (booking_id,))
    if cursor.rowcount == 0:
        conn.close()
        raise HTTPException(404, "Booking not found")
    conn.commit()
    conn.close()
    return {"message": "Checked out"}


# ========== СТАТИСТИКА ==========
@app.get("/api/statistics")
def get_statistics():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM bookings")
    total = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM bookings WHERE status='confirmed'")
    active = cursor.fetchone()[0]
    cursor.execute("SELECT SUM(total_price) FROM bookings WHERE status='confirmed'")
    revenue = cursor.fetchone()[0] or 0.0
    cursor.execute("SELECT COUNT(*) FROM rooms WHERE status='available'")
    available_rooms = cursor.fetchone()[0]
    occupancy = (active / total * 100) if total > 0 else 0
    conn.close()
    return {
        "total_bookings": total,
        "active_bookings": active,
        "total_revenue": revenue,
        "available_rooms": available_rooms,
        "occupancy_rate": occupancy
    }


# ========== ПРОФИЛЬ ==========
def get_current_user_id(authorization: str):
    token = authorization.replace("Bearer ", "")
    if not token.startswith("fake-token-"):
        raise HTTPException(status_code=401, detail="Invalid token")
    try:
        user_id = int(token.split('-')[-1])
        return user_id
    except:
        raise HTTPException(status_code=401, detail="Invalid token")


@app.get("/api/users/me")
def get_current_user(authorization: str = Header(...)):
    user_id = get_current_user_id(authorization)
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, username, first_name, last_name, role,
               COALESCE(email, '') as email,
               COALESCE(phone, '') as phone,
               COALESCE(birth_date, '') as birth_date,
               COALESCE(avatar, '') as avatar
        FROM staff WHERE id = ?
    """, (user_id,))
    user = cursor.fetchone()
    conn.close()
    if not user:
        raise HTTPException(404, "User not found")
    return dict(user)


@app.put("/api/users/me")
def update_current_user(user_data: dict, authorization: str = Header(...)):
    user_id = get_current_user_id(authorization)
    allowed_fields = ['first_name', 'last_name', 'email', 'phone', 'birth_date', 'avatar']
    if 'birthDate' in user_data:
        user_data['birth_date'] = user_data.pop('birthDate')
    updates = {k: v for k, v in user_data.items() if k in allowed_fields and v is not None}
    if not updates:
        raise HTTPException(400, "No valid fields to update")
    set_clause = ", ".join([f"{k}=?" for k in updates])
    values = list(updates.values()) + [user_id]
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(f"UPDATE staff SET {set_clause} WHERE id=?", values)
    if cursor.rowcount == 0:
        conn.close()
        raise HTTPException(404, "User not found")
    conn.commit()
    conn.close()
    return {"message": "Profile updated"}


@app.post("/api/users/change-password")
def change_password(data: dict, authorization: str = Header(...)):
    user_id = get_current_user_id(authorization)
    old_password = data.get('old_password')
    new_password = data.get('new_password')
    if not old_password or not new_password:
        raise HTTPException(400, "Old and new passwords required")
    if len(new_password) < 6:
        raise HTTPException(400, "New password too short")
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT password FROM staff WHERE id=?", (user_id,))
    row = cursor.fetchone()
    if not row or row[0] != old_password:
        conn.close()
        raise HTTPException(401, "Incorrect old password")
    cursor.execute("UPDATE staff SET password=? WHERE id=?", (new_password, user_id))
    conn.commit()
    conn.close()
    return {"message": "Password changed"}


# ========== ОТЧЕТЫ ==========
@app.get("/api/reports/stats")
def get_report_stats(start: str, end: str):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT 
            COUNT(*) as total_bookings,
            COALESCE(SUM(total_price), 0) as total_revenue,
            COALESCE(AVG(total_price), 0) as avg_check
        FROM bookings
        WHERE created_at BETWEEN ? AND ?
    """, (start, end))
    current = cursor.fetchone()

    total_rooms = cursor.execute("SELECT COUNT(*) FROM rooms").fetchone()[0]
    cursor.execute("""
        SELECT COUNT(DISTINCT room_id) FROM bookings
        WHERE status IN ('confirmed', 'checked_in')
        AND check_in_date <= ? AND check_out_date >= ?
    """, (end, start))
    occupied = cursor.fetchone()[0] or 0
    occupancy = (occupied / total_rooms * 100) if total_rooms > 0 else 0

    conn.close()

    return {
        "occupancy_rate": round(occupancy, 1),
        "occupancy_change": 0,
        "average_check": round(current[2] or 0, 2),
        "check_change": 0,
        "new_guests": 0,
        "guests_change": 0,
        "cancellations": 0,
        "cancellations_change": 0
    }


@app.get("/api/reports")
def get_reports():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, name, type, created_at, period_start, period_end, format, size FROM reports ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


@app.post("/api/reports/generate")
def generate_report(data: ReportGenerate):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    report_name = {
        'financial': 'Финансовый отчет',
        'occupancy': 'Отчет по заполняемости',
        'guests': 'Отчет по гостям',
        'bookings': 'Отчет по бронированиям'
    }.get(data.type, 'Отчет')

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow([report_name])
    writer.writerow(['Период', data.start_date, data.end_date])
    writer.writerow(['Дата формирования', datetime.now().strftime('%Y-%m-%d %H:%M:%S')])
    writer.writerow([])
    writer.writerow(['Параметр', 'Значение'])

    if data.type == 'financial':
        cursor.execute("""
            SELECT date(created_at), COUNT(*), SUM(total_price), AVG(total_price)
            FROM bookings
            WHERE created_at BETWEEN ? AND ?
            GROUP BY date(created_at)
        """, (data.start_date, data.end_date))
        for row in cursor.fetchall():
            writer.writerow([row[0], row[1], f"{row[2] or 0:.2f}", f"{row[3] or 0:.2f}"])
    else:
        total_bookings = cursor.execute("SELECT COUNT(*) FROM bookings WHERE created_at BETWEEN ? AND ?",
                                        (data.start_date, data.end_date)).fetchone()[0]
        total_revenue = \
        cursor.execute("SELECT COALESCE(SUM(total_price), 0) FROM bookings WHERE created_at BETWEEN ? AND ?",
                       (data.start_date, data.end_date)).fetchone()[0]
        writer.writerow(['Всего бронирований', total_bookings])
        writer.writerow(['Общая выручка', f"{total_revenue:.2f}"])

    csv_content = output.getvalue()
    file_data = base64.b64encode(csv_content.encode()).decode()
    file_size = len(csv_content.encode())
    size_mb = round(file_size / (1024 * 1024), 2)

    cursor.execute("""
        INSERT INTO reports (name, type, period_start, period_end, format, size, file_data, file_name)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (report_name, data.type, data.start_date, data.end_date, data.format, f"{size_mb} MB", file_data,
          f"report_{datetime.now().timestamp()}.csv"))
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()

    return {
        "id": new_id,
        "name": report_name,
        "type": data.type,
        "created_at": datetime.now().isoformat(),
        "period_start": data.start_date,
        "period_end": data.end_date,
        "format": data.format,
        "size": f"{size_mb} MB"
    }


@app.get("/api/reports/{report_id}/download")
def download_report(report_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT file_data, file_name FROM reports WHERE id = ?", (report_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "Report not found")

    file_data = base64.b64decode(row[0])
    return Response(
        content=file_data,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={row[1]}"}
    )


@app.post("/api/bookings/mass-checkout")
def mass_checkout(data: dict):
    booking_ids = data.get('booking_ids', [])
    if not booking_ids:
        raise HTTPException(400, "No booking IDs provided")

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    updated = 0

    for booking_id in booking_ids:
        # Обновляем статус бронирования
        cursor.execute("UPDATE bookings SET status='checked_out' WHERE id=?", (booking_id,))
        if cursor.rowcount > 0:
            updated += 1
            # Получаем room_id для обновления статуса комнаты
            cursor.execute("SELECT room_id FROM bookings WHERE id=?", (booking_id,))
            room = cursor.fetchone()
            if room:
                cursor.execute("UPDATE rooms SET status='available' WHERE id=?", (room[0],))

    conn.commit()
    conn.close()

    return {"message": f"Checked out {updated} bookings", "updated": updated}

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)
