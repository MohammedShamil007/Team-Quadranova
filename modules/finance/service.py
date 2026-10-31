
from datetime import date

from core.database import DatabaseManager


class FinanceService:
    def __init__(self, database=None, billing_service=None):
        self.db = database or DatabaseManager()
        self.billing_service = billing_service

    def record_payment(
        self,
        invoice_id: int,
        customer_id: int,
        recorded_by_user_id: int,
        amount_minor_units: int,
        payment_method: str,
        transaction_reference: str | None = None,
        notes: str | None = None,
    ):
        if amount_minor_units <= 0:
            raise ValueError("Payment amount must be greater than zero")

        allowed_methods = {
            "BANK_TRANSFER",
            "CREDIT_CARD",
            "GATEWAY",
            "CHECK",
        }

        if payment_method not in allowed_methods:
            raise ValueError("Invalid payment method")

        if self.billing_service is None:
            raise ValueError("Billing service is not configured")

        with self.db.transaction() as connection:
            invoice = connection.execute(
                """
                SELECT id, customer_id, status, currency,
                       balance_due_minor_units
                FROM invoices
                WHERE id = ? AND customer_id = ?
                """,
                (invoice_id, customer_id),
            ).fetchone()

            if invoice is None:
                raise ValueError("Invoice not found")

            if invoice["status"] != "CONFIRMED":
                raise ValueError(
                    "Payments can only be recorded for confirmed invoices"
                )

            balance = invoice["balance_due_minor_units"]

            if amount_minor_units > balance:
                raise ValueError("Payment exceeds outstanding balance")

            connection.execute(
                """
                INSERT INTO payments (
                    invoice_id,
                    customer_id,
                    amount_minor_units,
                    currency,
                    payment_date,
                    payment_method,
                    transaction_reference,
                    notes,
                    recorded_by_user_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    invoice_id,
                    customer_id,
                    amount_minor_units,
                    invoice["currency"],
                    date.today().isoformat(),
                    payment_method,
                    transaction_reference,
                    notes,
                    recorded_by_user_id,
                ),
            )

            new_balance = balance - amount_minor_units

            connection.execute(
                """
                UPDATE invoices
                SET balance_due_minor_units = ?
                WHERE id = ?
                """,
                (new_balance, invoice_id),
            )

            if new_balance == 0:
                self.billing_service.mark_invoice_paid(
                    connection,
                    invoice_id,
                )

        return {
            "invoice_id": invoice_id,
            "payment_amount_minor_units": amount_minor_units,
            "remaining_balance_minor_units": new_balance,
            "invoice_status": "PAID" if new_balance == 0 else "CONFIRMED",
            "message": "Payment recorded successfully",
        }
