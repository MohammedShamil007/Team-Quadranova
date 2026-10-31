
from modules.billing.service import BillingService
from modules.payments.mock_gateway import MockGateway
from typing import Literal
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
from pathlib import Path
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse




app = FastAPI(
   
    title="Brightloop API",
    description="Subscription Management Backend",
    version="1.0.0",
)
PROJECT_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = PROJECT_DIR / "frontend"
app.mount(
    "/assets",
    StaticFiles(directory=FRONTEND_DIR),    
    name="assets"
    )


db = DatabaseManager()
billing_service = BillingService(db)

from modules.finance.service import FinanceService
from modules.payments.mock_gateway import MockGateway

finance_service = FinanceService(
    database=db,
    billing_service=billing_service,
)

mock_gateway = MockGateway(db)

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

@app.get("/dashboard")
def dashboard(user: dict = Depends(get_current_user)):
    return FileResponse(FRONTEND_DIR / "dashboard.html")


@app.get("/")
def root():
    return FileResponse(FRONTEND_DIR / "index.html")

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

class InvoiceGenerateRequest(BaseModel):
    subscription_id: int
    billing_period_start: date
    billing_period_end: date
    due_days: int = Field(default=30, ge=0, le=365)

class PaymentRequest(BaseModel):
    invoice_id: int
    amount_minor_units: int = Field(gt=0)
    payment_method: str
    transaction_reference: str | None = None
    notes: str | None = None

class MockPaymentCreateRequest(BaseModel):
    invoice_id: int


class MockPaymentSimulationRequest(BaseModel):
    outcome: Literal["SUCCESS", "FAILED"]

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

@app.post("/subscriptions/{subscription_id}/confirm")
def confirm_subscription(
    subscription_id: int,
    user: dict = Depends(get_current_user),
):
    customer_id = get_customer_id(user["id"])

    with db.transaction() as connection:
        subscription = connection.execute(
            """
            SELECT id, status
            FROM subscriptions
            WHERE id = ? AND customer_id = ?
            """,
            (subscription_id, customer_id),
        ).fetchone()

        if subscription is None:
            raise HTTPException(
                status_code=404,
                detail="Subscription not found",
            )

        if subscription["status"] != "DRAFT":
            raise HTTPException(
                status_code=400,
                detail="Only draft subscriptions can be confirmed",
            )

        line_count = connection.execute(
            """
            SELECT COUNT(*) AS total
            FROM subscription_lines
            WHERE subscription_id = ? AND is_active = 1
            """,
            (subscription_id,),
        ).fetchone()["total"]

        if line_count == 0:
            raise HTTPException(
                status_code=400,
                detail="Cannot confirm a subscription without active line items",
            )

        connection.execute(
            """
            UPDATE subscriptions
            SET status = 'CONFIRMED',
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND customer_id = ? AND status = 'DRAFT'
            """,
            (subscription_id, customer_id),
        )

    return {
        "message": "Subscription confirmed successfully",
        "subscription_id": subscription_id,
        "status": "CONFIRMED",
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

@app.post("/invoices/generate", status_code=201)
def generate_invoice(
    data: InvoiceGenerateRequest,
    user: dict = Depends(get_current_user),
):
    customer_id = get_customer_id(user["id"])

    connection = db.get_connection()
    try:
        subscription = connection.execute(
            """
            SELECT id FROM subscriptions
            WHERE id = ? AND customer_id = ?
            """,
            (data.subscription_id, customer_id),
        ).fetchone()
    finally:
        connection.close()

    if subscription is None:
        raise HTTPException(
            status_code=404,
            detail="Subscription not found",
        )

    try:
        return billing_service.generate_invoice(
            subscription_id=data.subscription_id,
            billing_period_start=data.billing_period_start,
            billing_period_end=data.billing_period_end,
            due_days=data.due_days,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error

@app.get("/invoices")
def list_invoices(
    user: dict = Depends(get_current_user),
):
    customer_id = get_customer_id(user["id"])

    connection = db.get_connection()
    try:
        rows = connection.execute(
            """
            SELECT
                id,
                invoice_number,
                subscription_id,
                status,
                issue_date,
                due_date,
                currency,
                subtotal_minor_units,
                tax_amount_minor_units,
                total_amount_minor_units,
                balance_due_minor_units
            FROM invoices
            WHERE customer_id = ?
            ORDER BY id DESC
            """,
            (customer_id,),
        ).fetchall()

        return [dict(row) for row in rows]
    finally:
        connection.close()

@app.get("/invoices/{invoice_id}")
def get_invoice(
    invoice_id: int,
    user: dict = Depends(get_current_user),
):
    customer_id = get_customer_id(user["id"])

    connection = db.get_connection()
    try:
        invoice = connection.execute(
            """
            SELECT *
            FROM invoices
            WHERE id = ? AND customer_id = ?
            """,
            (invoice_id, customer_id),
        ).fetchone()

        if invoice is None:
            raise HTTPException(
                status_code=404,
                detail="Invoice not found",
            )

        lines = connection.execute(
            """
            SELECT
                il.id,
                il.product_id,
                il.variant_id,
                il.description,
                il.quantity,
                il.unit_price_minor_units,
                il.discount_amount_minor_units,
                il.tax_rate_basis_points,
                il.tax_amount_minor_units,
                il.line_total_minor_units
            FROM invoice_lines il
            WHERE il.invoice_id = ?
            ORDER BY il.id
            """,
            (invoice_id,),
        ).fetchall()

        result = dict(invoice)
        result["lines"] = [dict(line) for line in lines]

        return result
    finally:
        connection.close()

@app.post("/payments", status_code=201)
def record_payment(
    data: PaymentRequest,
    user: dict = Depends(get_current_user),
):
    customer_id = get_customer_id(user["id"])

    try:
        return finance_service.record_payment(
            invoice_id=data.invoice_id,
            customer_id=customer_id,
            recorded_by_user_id=user["id"],
            amount_minor_units=data.amount_minor_units,
            payment_method=data.payment_method,
            transaction_reference=data.transaction_reference,
            notes=data.notes,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error

@app.post("/invoices/{invoice_id}/confirm")
def confirm_invoice(
    invoice_id: int,
    user: dict = Depends(get_current_user),
):
    customer_id = get_customer_id(user["id"])

    try:
        return billing_service.confirm_invoice(
            invoice_id=invoice_id,
            customer_id=customer_id,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error

    
# MOCK PAYMENT GATEWAY ENDPOINTS

@app.post("/payments/create", status_code=201)
def create_mock_payment(
    data: MockPaymentCreateRequest,
    user: dict = Depends(get_current_user),
):
    customer_id = get_customer_id(user["id"])

    try:
        return mock_gateway.create_attempt(
            invoice_id=data.invoice_id,
            customer_id=customer_id,
            user_id=user["id"],
        )
    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error


@app.get("/payments/{attempt_id}")
def get_mock_payment(
    attempt_id: int,
    user: dict = Depends(get_current_user),
):
    customer_id = get_customer_id(user["id"])

    try:
        return mock_gateway.get_attempt(
            attempt_id=attempt_id,
            customer_id=customer_id,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        ) from error


@app.post("/payments/{attempt_id}/simulate")
def simulate_mock_payment(
    attempt_id: int,
    data: MockPaymentSimulationRequest,
    user: dict = Depends(get_current_user),
):
    customer_id = get_customer_id(user["id"])

    try:
        return mock_gateway.simulate(
            attempt_id=attempt_id,
            customer_id=customer_id,
            user_id=user["id"],
            outcome=data.outcome,
            finance_service=finance_service,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error
