from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import sqlite3
from datetime import date, datetime
import os

app = FastAPI()

# CORS для React (фронтенд на localhost:3000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- Инициализация SQLite ----------
DB_NAME = "easyhotel.db"


def init_db():
    """Создаёт таблицы, если их нет, и добавляет тестового админа"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Таблица сотрудников (для авторизации)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS staff (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            first_name TEXT,
            last_name TEXT,
            role TEXT,
            ALTER TABLE staff ADD COLUMN phone TEXT
        )
    ''')

    # Таблица гостей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS guests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            phone TEXT,
            country TEXT,
            city TEXT
        )
    ''')

    # Таблица типов номеров
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS room_types (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            base_price REAL NOT NULL
        )
    ''')

    # Таблица номеров
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS rooms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room_number TEXT UNIQUE NOT NULL,
            room_type_id INTEGER NOT NULL,
            status TEXT DEFAULT 'available',
            FOREIGN KEY (room_type_id) REFERENCES room_types(id)
        )
    ''')

    # Таблица бронирований
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
            FOREIGN KEY (guest_id) REFERENCES guests(id),
            FOREIGN KEY (room_id) REFERENCES rooms(id),
            FOREIGN KEY (staff_id) REFERENCES staff(id)
        )
    ''')

    # Добавляем тестового администратора, если ещё нет
    cursor.execute("SELECT COUNT(*) FROM staff WHERE username = 'admin'")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO staff (username, password, first_name, last_name, role) VALUES (?, ?, ?, ?, ?)",
                       ('admin', 'admin123', 'Admin', 'User', 'manager'))

    # Добавляем тестовые типы номеров, если пусто
    cursor.execute("SELECT COUNT(*) FROM room_types")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO room_types (name, base_price) VALUES (?, ?)", ('Deluxe', 250.0))
        cursor.execute("INSERT INTO room_types (name, base_price) VALUES (?, ?)", ('Standard', 150.0))

    # Добавляем тестовые номера
    cursor.execute("SELECT COUNT(*) FROM rooms")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO rooms (room_number, room_type_id, status) VALUES (?, ?, ?)",
                       ('101', 1, 'available'))
        cursor.execute("INSERT INTO rooms (room_number, room_type_id, status) VALUES (?, ?, ?)",
                       ('102', 2, 'available'))

    conn.commit()
    conn.close()
    print("✅ База данных инициализирована (таблицы созданы, тестовые данные добавлены)")


# Вызываем инициализацию при старте
init_db()


# ---------- Модели Pydantic для валидации ----------
class LoginData(BaseModel):
    username: str
    password: str


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
    check_in_date: str  # формат YYYY-MM-DD
    check_out_date: str


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


@app.get("/api/auth/login")
def login(username: str, password: str):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, first_name, last_name, role FROM staff WHERE username=? AND password=?",
                   (username, password))
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
            "phone": user[5]
        }
    }


@app.get("/api/guests", response_model=List[GuestOut])
def get_guests():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT id, first_name, last_name, email, phone, country, city FROM guests")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


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


@app.get("/api/rooms")
def get_rooms():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT id, room_number, status FROM rooms")
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


@app.get("/api/bookings", response_model=List[BookingOut])
def get_bookings():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, guest_id, room_id, staff_id, check_in_date, check_out_date, total_price, status, amount_paid, balance_due FROM bookings")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


@app.post("/api/bookings", response_model=BookingOut)
def create_booking(booking: BookingIn):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # Получаем тип номера и цену
    cursor.execute("SELECT room_type_id FROM rooms WHERE id=?", (booking.room_id,))
    room = cursor.fetchone()
    if not room:
        conn.close()
        raise HTTPException(status_code=404, detail="Номер не найден")
    cursor.execute("SELECT base_price FROM room_types WHERE id=?", (room[0],))
    room_type = cursor.fetchone()
    price_per_night = room_type[0]
    # Считаем количество ночей
    check_in = datetime.strptime(booking.check_in_date, "%Y-%m-%d")
    check_out = datetime.strptime(booking.check_out_date, "%Y-%m-%d")
    nights = (check_out - check_in).days
    total = price_per_night * nights
    cursor.execute('''
        INSERT INTO bookings (guest_id, room_id, staff_id, check_in_date, check_out_date, total_price, balance_due)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (booking.guest_id, booking.room_id, booking.staff_id, booking.check_in_date, booking.check_out_date, total,
          total))
    conn.commit()
    new_id = cursor.lastrowid
    cursor.execute(
        "SELECT id, guest_id, room_id, staff_id, check_in_date, check_out_date, total_price, status, amount_paid, balance_due FROM bookings WHERE id=?",
        (new_id,))
    row = cursor.fetchone()
    conn.close()
    return {
        "id": row[0],
        "guest_id": row[1],
        "room_id": row[2],
        "staff_id": row[3],
        "check_in_date": row[4],
        "check_out_date": row[5],
        "total_price": row[6],
        "status": row[7],
        "amount_paid": row[8],
        "balance_due": row[9],
    }


@app.put("/api/bookings/{booking_id}/cancel")
def cancel_booking(booking_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE bookings SET status='cancelled' WHERE id=?", (booking_id,))
    if cursor.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Бронирование не найдено")
    conn.commit()
    conn.close()
    return {"message": "Бронирование отменено"}


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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)