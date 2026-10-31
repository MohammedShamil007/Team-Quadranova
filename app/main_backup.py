
from datetime import datetime, timedelta
import sqlite3

from fastapi import FastAPI, HTTPException, Request, Response, Depends
from pydantic import BaseModel, EmailStr, Field

from core.database import DatabaseManager
from core.security import (
    hash_password,
    verify_password,
    generate_session_token,
    hash_session_token,
    generate_csrf_token,
)


app = FastAPI(
    title="Brightloop API",
    description="Subscription Management Backend",
    version="1.0.0",
)

db = DatabaseManager()

SESSION_COOKIE = "brightloop_session"
SESSION_DURATION_DAYS = 7


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=9, max_length=128)
    company_name: str = Field(min_length=2, max_length=150)
    contact_name: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


def create_session(user_id: int):
    raw_token = generate_session_token()
    token_hash = hash_session_token(raw_token)
    csrf_token = generate_csrf_token()

    expires_at = (
        datetime.utcnow() + timedelta(days=SESSION_DURATION_DAYS)
    ).strftime("%Y-%m-%d %H:%M:%S")

    with db.transaction() as connection:
        connection.execute(
            """
            INSERT INTO user_sessions
            (user_id, token_hash, csrf_token, expires_at)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, token_hash, csrf_token, expires_at),
        )

    return raw_token, csrf_token


def get_current_user(request: Request):
    raw_token = request.cookies.get(SESSION_COOKIE)

    if not raw_token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    token_hash = hash_session_token(raw_token)

    connection = db.get_connection()

    try:
        user = connection.execute(
            """
            SELECT users.id, users.email, users.role
            FROM user_sessions
            JOIN users ON users.id = user_sessions.user_id
            WHERE user_sessions.token_hash = ?
              AND user_sessions.expires_at > CURRENT_TIMESTAMP
              AND users.is_active = 1
            """,
            (token_hash,),
        ).fetchone()

        if user is None:
            raise HTTPException(status_code=401, detail="Invalid or expired session")

        return dict(user)

    finally:
        connection.close()


@app.get("/")
def root():
    return {
        "application": "Brightloop",
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.post("/auth/register", status_code=201)
def register(data: RegisterRequest, response: Response):
    email = str(data.email).lower().strip()

    try:
        password_hash, salt = hash_password(data.password)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))

    try:
        with db.transaction() as connection:
            cursor = connection.execute(
                """
                INSERT INTO users (email, password_hash, salt, role)
                VALUES (?, ?, ?, 'CUSTOMER')
                """,
                (email, password_hash, salt),
            )
            user_id = cursor.lastrowid

            cursor = connection.execute(
                """
                INSERT INTO customers (company_name, contact_name)
                VALUES (?, ?)
                """,
                (data.company_name, data.contact_name),
            )
            customer_id = cursor.lastrowid

            connection.execute(
                """
                INSERT INTO customer_members
                (customer_id, user_id, role_within_customer)
                VALUES (?, ?, 'OWNER')
                """,
                (customer_id, user_id),
            )

    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="Email already registered")

    raw_token, csrf_token = create_session(user_id)

    response.set_cookie(
        key=SESSION_COOKIE,
        value=raw_token,
        httponly=True,
        secure=False,  # Set True when deployed behind HTTPS
        samesite="lax",
        max_age=SESSION_DURATION_DAYS * 24 * 60 * 60,
        path="/",
    )

    return {
        "message": "Registration successful",
        "user_id": user_id,
        "customer_id": customer_id,
        "csrf_token": csrf_token,
    }


@app.post("/auth/login")
def login(data: LoginRequest, response: Response):
    email = str(data.email).lower().strip()

    connection = db.get_connection()

    try:
        user = connection.execute(
            """
            SELECT id, email, password_hash, salt, role
            FROM users
            WHERE email = ? AND is_active = 1
            """,
            (email,),
        ).fetchone()
    finally:
        connection.close()

    if user is None or not verify_password(
        data.password,
        user["password_hash"],
        user["salt"],
    ):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    raw_token, csrf_token = create_session(user["id"])

    response.set_cookie(
        key=SESSION_COOKIE,
        value=raw_token,
        httponly=True,
        secure=False,  # Set True when deployed behind HTTPS
        samesite="lax",
        max_age=SESSION_DURATION_DAYS * 24 * 60 * 60,
        path="/",
    )

    return {
        "message": "Login successful",
        "user_id": user["id"],
        "email": user["email"],
        "role": user["role"],
        "csrf_token": csrf_token,
    }


@app.post("/auth/logout")
def logout(request: Request, response: Response):
    raw_token = request.cookies.get(SESSION_COOKIE)

    if raw_token:
        token_hash = hash_session_token(raw_token)

        with db.transaction() as connection:
            connection.execute(
                "DELETE FROM user_sessions WHERE token_hash = ?",
                (token_hash,),
            )

    response.delete_cookie(
        key=SESSION_COOKIE,
        path="/",
        httponly=True,
        samesite="lax",
    )

    return {"message": "Logged out successfully"}


@app.get("/auth/me")
def me(user: dict = Depends(get_current_user)):
    return {"user": user}

#Products, plans and subscriptions


from datetime import date
import uuid


class ProductRequest(BaseModel):
    name: str
    type: str
    sales_price_minor_units: int = Field(default=0, ge=0)
    cost_price_minor_units: int = Field(default=0, ge=0)
    notes: str | None = None


class PlanRequest(BaseModel):
    name: str
    billing_frequency: str
    base_cost_minor_units: int = Field(ge=0)
    minimum_quantity: int = Field(default=1, gt=0)
    available_from: date
    available_until: date | None = None
    currency: str = "USD"


class SubscriptionLineRequest(BaseModel):
    product_id: int
    quantity: int = Field(default=1, gt=0)
    unit_price_minor_units: int = Field(ge=0)
    tax_rate_basis_points: int = Field(default=0, ge=0, le=100000)


class SubscriptionRequest(BaseModel):
    plan_id: int
    start_date: date
    expiry_date: date | None = None
    lines: list[SubscriptionLineRequest] = Field(min_length=1)

def get_customer_id(user_id: int):
    connection = db.get_connection()
    try:
        row = connection.execute(
            "SELECT customer_id FROM customer_members WHERE user_id = ?",
            (user_id,),
        ).fetchone()

        if row is None:
            raise HTTPException(status_code=403, detail="No customer membership")

        return row["customer_id"]
    finally:
        connection.close()


@app.post("/products", status_code=201)
def create_product(
    data: ProductRequest,
    user: dict = Depends(get_current_user),
):
    if data.type not in ("SOFTWARE", "ADD_ON", "SERVICE"):
        raise HTTPException(status_code=400, detail="Invalid product type")

    with db.transaction() as connection:
        cursor = connection.execute(
            """
            INSERT INTO products
            (name, type, sales_price_minor_units,
             cost_price_minor_units, notes)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                data.name,
                data.type,
                data.sales_price_minor_units,
                data.cost_price_minor_units,
                data.notes,
            ),
        )
        product_id = cursor.lastrowid

    return {"message": "Product created", "product_id": product_id}


@app.get("/products")
def list_products(user: dict = Depends(get_current_user)):
    connection = db.get_connection()
    try:
        rows = connection.execute(
            "SELECT * FROM products WHERE is_active = 1 ORDER BY id DESC"
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


@app.post("/plans", status_code=201)
def create_plan(
    data: PlanRequest,
    user: dict = Depends(get_current_user),
):
    if data.billing_frequency not in (
        "DAILY", "WEEKLY", "MONTHLY", "YEARLY"
    ):
        raise HTTPException(status_code=400, detail="Invalid billing frequency")

    if data.available_until and data.available_until < data.available_from:
        raise HTTPException(status_code=400, detail="Invalid availability dates")

    if len(data.currency) != 3 or not data.currency.isalpha():
        raise HTTPException(status_code=400, detail="Invalid currency")

    with db.transaction() as connection:
        cursor = connection.execute(
            """
            INSERT INTO subscription_plans
            (name, billing_frequency, base_cost_minor_units,
             minimum_quantity, available_from, available_until, currency)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data.name,
                data.billing_frequency,
                data.base_cost_minor_units,
                data.minimum_quantity,
                data.available_from.isoformat(),
                data.available_until.isoformat() if data.available_until else None,
                data.currency.upper(),
            ),
        )
        plan_id = cursor.lastrowid

    return {"message": "Plan created", "plan_id": plan_id}


@app.get("/plans")
def list_plans(user: dict = Depends(get_current_user)):
    connection = db.get_connection()
    try:
        rows = connection.execute(
            "SELECT * FROM subscription_plans WHERE is_active = 1 ORDER BY id DESC"
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


@app.post("/subscriptions", status_code=201)
@app.post("/subscriptions", status_code=201)
def create_subscription(
    data: SubscriptionRequest,
    user: dict = Depends(get_current_user),
):
    customer_id = get_customer_id(user["id"])

    if data.expiry_date and data.expiry_date < data.start_date:
        raise HTTPException(status_code=400, detail="Invalid subscription dates")

    with db.transaction() as connection:
        plan = connection.execute(
            """
            SELECT id, currency, available_from, available_until
            FROM subscription_plans
            WHERE id = ? AND is_active = 1
            """,
            (data.plan_id,),
        ).fetchone()

        if plan is None:
            raise HTTPException(status_code=404, detail="Plan not found")

        if data.start_date < date.fromisoformat(plan["available_from"]):
            raise HTTPException(status_code=400, detail="Plan not yet available")

        if plan["available_until"] and data.start_date > date.fromisoformat(
            plan["available_until"]
        ):
            raise HTTPException(status_code=400, detail="Plan no longer available")

        subscription_number = "SUB-" + uuid.uuid4().hex[:12].upper()

        cursor = connection.execute(
            """
            INSERT INTO subscriptions
            (subscription_number, customer_id, plan_id, status,
             start_date, expiry_date, currency, created_by_user_id)
            VALUES (?, ?, ?, 'DRAFT', ?, ?, ?, ?)
            """,
            (
                subscription_number,
                customer_id,
                data.plan_id,
                data.start_date.isoformat(),
                data.expiry_date.isoformat() if data.expiry_date else None,
                plan["currency"],
                user["id"],
            ),
        )

        subscription_id = cursor.lastrowid

        for line in data.lines:
            product = connection.execute(
                """
                SELECT id FROM products
                WHERE id = ? AND is_active = 1
                """,
                (line.product_id,),
            ).fetchone()

            if product is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"Active product {line.product_id} not found",
                )

            connection.execute(
                """
                INSERT INTO subscription_lines
                (
                    subscription_id, product_id, quantity,
                    unit_price_minor_units, tax_rate_basis_points
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    subscription_id,
                    line.product_id,
                    line.quantity,
                    line.unit_price_minor_units,
                    line.tax_rate_basis_points,
                ),
            )

    return {
        "message": "Subscription created with line items",
        "subscription_id": subscription_id,
        "subscription_number": subscription_number,
        "status": "DRAFT",
        "line_count": len(data.lines),
    }

@app.get("/subscriptions")
def list_subscriptions(user: dict = Depends(get_current_user)):
    customer_id = get_customer_id(user["id"])

    connection = db.get_connection()
    try:
        rows = connection.execute(
            """
            SELECT * FROM subscriptions
            WHERE customer_id = ?
            ORDER BY id DESC
            """,
            (customer_id,),
        ).fetchall()

        return [dict(row) for row in rows]
    finally:
        connection.close()

