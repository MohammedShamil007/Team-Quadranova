from datetime import date, timedelta
import uuid

from fastapi import HTTPException

from core.database import DatabaseManager


class BillingService:
    def __init__(self, database=None):
        self.db = database or DatabaseManager()

    def generate_invoice(
        self,
        subscription_id: int,
        billing_period_start: date,
        billing_period_end: date,
        due_days: int = 30,
    ):
        if billing_period_end < billing_period_start:
            raise ValueError("Billing period end cannot precede start")

        if due_days < 0:
            raise ValueError("Due days cannot be negative")

        with self.db.transaction() as connection:
            subscription = connection.execute(
                """
                SELECT id, customer_id, currency, status
                FROM subscriptions
                WHERE id = ?
                """,
                (subscription_id,),
            ).fetchone()

            if subscription is None:
                raise ValueError("Subscription not found")

            if subscription["status"] not in ("CONFIRMED", "ACTIVE"):
                raise ValueError(
                    "Only confirmed or active subscriptions can be invoiced"
                )

            existing = connection.execute(
                """
                SELECT id, invoice_number
                FROM invoices
                WHERE subscription_id = ?
                  AND billing_period_start = ?
                  AND billing_period_end = ?
                """,
                (
                    subscription_id,
                    billing_period_start.isoformat(),
                    billing_period_end.isoformat(),
                ),
            ).fetchone()

            if existing:
                raise ValueError(
                    f"Invoice already exists: {existing['invoice_number']}"
                )

            lines = connection.execute(
                """
                SELECT
                    sl.product_id,
                    sl.variant_id,
                    sl.quantity,
                    sl.unit_price_minor_units,
                    sl.tax_rate_basis_points,
                    p.name AS product_name
                FROM subscription_lines sl
                JOIN products p ON p.id = sl.product_id
                WHERE sl.subscription_id = ?
                  AND sl.is_active = 1
                ORDER BY sl.id
                """,
                (subscription_id,),
            ).fetchall()

            if not lines:
                raise ValueError("Subscription has no active line items")

            subtotal = 0
            total_tax = 0
            calculated_lines = []

            for line in lines:
                line_subtotal = (
                    line["quantity"] * line["unit_price_minor_units"]
                )

                tax = (
                    line_subtotal * line["tax_rate_basis_points"] + 5000
                ) // 10000

                line_total = line_subtotal + tax

                subtotal += line_subtotal
                total_tax += tax

                calculated_lines.append(
                    {
                        "product_id": line["product_id"],
                        "variant_id": line["variant_id"],
                        "description": line["product_name"],
                        "quantity": line["quantity"],
                        "unit_price_minor_units": line[
                            "unit_price_minor_units"
                        ],
                        "discount_amount_minor_units": 0,
                        "tax_rate_basis_points": line[
                            "tax_rate_basis_points"
                        ],
                        "tax_amount_minor_units": tax,
                        "line_total_minor_units": line_total,
                    }
                )

            total = subtotal + total_tax

            invoice_number = "INV-" + uuid.uuid4().hex[:12].upper()
            idempotency_key = str(uuid.uuid4())

            issue_date = date.today()
            due_date = issue_date + timedelta(days=due_days)

            cursor = connection.execute(
                """
                INSERT INTO invoices (
                    invoice_number,
                    subscription_id,
                    customer_id,
                    status,
                    issue_date,
                    due_date,
                    currency,
                    subtotal_minor_units,
                    tax_amount_minor_units,
                    discount_amount_minor_units,
                    total_amount_minor_units,
                    balance_due_minor_units,
                    billing_period_start,
                    billing_period_end,
                    idempotency_key
                )
                VALUES (?, ?, ?, 'DRAFT', ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?)
                """,
                (
                    invoice_number,
                    subscription_id,
                    subscription["customer_id"],
                    issue_date.isoformat(),
                    due_date.isoformat(),
                    subscription["currency"],
                    subtotal,
                    total_tax,
                    total,
                    total,
                    billing_period_start.isoformat(),
                    billing_period_end.isoformat(),
                    idempotency_key,
                ),
            )

            invoice_id = cursor.lastrowid

            for line in calculated_lines:
                connection.execute(
                    """
                    INSERT INTO invoice_lines (
                        invoice_id,
                        product_id,
                        variant_id,
                        description,
                        quantity,
                        unit_price_minor_units,
                        discount_amount_minor_units,
                        tax_rate_basis_points,
                        tax_amount_minor_units,
                        line_total_minor_units
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        invoice_id,
                        line["product_id"],
                        line["variant_id"],
                        line["description"],
                        line["quantity"],
                        line["unit_price_minor_units"],
                        line["discount_amount_minor_units"],
                        line["tax_rate_basis_points"],
                        line["tax_amount_minor_units"],
                        line["line_total_minor_units"],
                    ),
                )

        return {
            "invoice_id": invoice_id,
            "invoice_number": invoice_number,
            "status": "DRAFT",
            "currency": subscription["currency"],
            "subtotal_minor_units": subtotal,
            "tax_amount_minor_units": total_tax,
            "total_amount_minor_units": total,
            "balance_due_minor_units": total,
        }
    
    def confirm_invoice(self, invoice_id: int, customer_id: int):
        with self.db.transaction() as connection:
            invoice = connection.execute(
                """
                SELECT id, status
                FROM invoices
                WHERE id = ? AND customer_id = ?
                """,
                (invoice_id, customer_id),
            ).fetchone()

            if invoice is None:
                raise ValueError("Invoice not found")

            if invoice["status"] != "DRAFT":
                raise ValueError("Only draft invoices can be confirmed")

            connection.execute(
                """
                UPDATE invoices
                SET status = 'CONFIRMED'
                WHERE id = ?
                """,
                (invoice_id,),
            )

        return {
            "invoice_id": invoice_id,
            "status": "CONFIRMED",
            "message": "Invoice confirmed successfully",
        }

    def mark_invoice_paid(self, connection, invoice_id: int):
        invoice = connection.execute(
            """
            SELECT status, balance_due_minor_units
            FROM invoices
            WHERE id = ?
            """,
            (invoice_id,),
        ).fetchone()

        if invoice is None:
            raise ValueError("Invoice not found")

        if invoice["status"] != "CONFIRMED":
            raise ValueError("Only confirmed invoices can be marked as paid")

        if invoice["balance_due_minor_units"] != 0:
            raise ValueError("Invoice still has an outstanding balance")

        connection.execute(
            """
            UPDATE invoices
            SET status = 'PAID'
            WHERE id = ?
            """,
            (invoice_id,),
        )