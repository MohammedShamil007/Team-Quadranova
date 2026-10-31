
import uuid

from core.database import DatabaseManager


class MockGateway:
    def __init__(self, database=None):
        self.db = database or DatabaseManager()

    def create_attempt(
        self,
        invoice_id: int,
        customer_id: int,
        user_id: int,
    ):
        with self.db.transaction() as connection:
            invoice = connection.execute(
                """
                SELECT id, customer_id, status,
                       currency, balance_due_minor_units
                FROM invoices
                WHERE id = ? AND customer_id = ?
                """,
                (invoice_id, customer_id),
            ).fetchone()

            if invoice is None:
                raise ValueError("Invoice not found")

            if invoice["status"] != "CONFIRMED":
                raise ValueError(
                    "Only confirmed invoices can be paid"
                )

            amount = invoice["balance_due_minor_units"]

            if amount <= 0:
                raise ValueError("Invoice has no outstanding balance")

            reference = "MOCK-" + uuid.uuid4().hex.upper()

            cursor = connection.execute(
                """
                INSERT INTO payment_attempts (
                    invoice_id,
                    customer_id,
                    initiated_by_user_id,
                    amount_minor_units,
                    currency,
                    gateway_reference
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    invoice_id,
                    customer_id,
                    user_id,
                    amount,
                    invoice["currency"],
                    reference,
                ),
            )

            return {
                "attempt_id": cursor.lastrowid,
                "invoice_id": invoice_id,
                "amount_minor_units": amount,
                "currency": invoice["currency"],
                "gateway": "MOCK",
                "gateway_reference": reference,
                "status": "PENDING",
                "message": "Payment attempt created",
            }

    def get_attempt(
        self,
        attempt_id: int,
        customer_id: int,
    ):
        connection = self.db.get_connection()

        try:
            attempt = connection.execute(
                """
                SELECT *
                FROM payment_attempts
                WHERE id = ? AND customer_id = ?
                """,
                (attempt_id, customer_id),
            ).fetchone()

            if attempt is None:
                raise ValueError("Payment attempt not found")

            return dict(attempt)

        finally:
            connection.close()

    def simulate(
        self,
        attempt_id: int,
        customer_id: int,
        user_id: int,
        outcome: str,
        finance_service,
    ):
        if outcome not in ("SUCCESS", "FAILED"):
            raise ValueError("Invalid simulation outcome")

        # Claim the attempt exactly once.
        with self.db.transaction() as connection:
            attempt = connection.execute(
                """
                SELECT *
                FROM payment_attempts
                WHERE id = ? AND customer_id = ?
                """,
                (attempt_id, customer_id),
            ).fetchone()

            if attempt is None:
                raise ValueError("Payment attempt not found")

            if attempt["status"] != "PENDING":
                raise ValueError(
                    "This payment attempt has already been processed"
                )

            connection.execute(
                """
                UPDATE payment_attempts
                SET status = 'PROCESSING'
                WHERE id = ? AND status = 'PENDING'
                """,
                (attempt_id,),
            )

        if outcome == "FAILED":
            with self.db.transaction() as connection:
                connection.execute(
                    """
                    UPDATE payment_attempts
                    SET status = 'FAILED',
                        failure_reason = 'Mock payment declined',
                        completed_at = CURRENT_TIMESTAMP
                    WHERE id = ? AND status = 'PROCESSING'
                    """,
                    (attempt_id,),
                )

            return {
                "attempt_id": attempt_id,
                "status": "FAILED",
                "message": "Mock payment was declined",
            }

        # A successful simulation uses the existing FinanceService.
        try:
            payment_result = finance_service.record_payment(
                invoice_id=attempt["invoice_id"],
                customer_id=customer_id,
                recorded_by_user_id=user_id,
                amount_minor_units=attempt["amount_minor_units"],
                payment_method="GATEWAY",
                transaction_reference=attempt["gateway_reference"],
                notes="Successful mock gateway payment",
            )

            connection = self.db.get_connection()

            try:
                payment = connection.execute(
                    """
                    SELECT id
                    FROM payments
                    WHERE transaction_reference = ?
                    """,
                    (attempt["gateway_reference"],),
                ).fetchone()

                if payment is None:
                    raise ValueError(
                        "Payment record was not found after processing"
                    )

                with self.db.transaction() as transaction:
                    transaction.execute(
                        """
                        UPDATE payment_attempts
                        SET status = 'SUCCEEDED',
                            payment_id = ?,
                            completed_at = CURRENT_TIMESTAMP
                        WHERE id = ? AND status = 'PROCESSING'
                        """,
                        (payment["id"], attempt_id),
                    )

            finally:
                connection.close()

            return {
                "attempt_id": attempt_id,
                "status": "SUCCEEDED",
                "payment": payment_result,
                "message": "Mock payment completed successfully",
            }

        except Exception:
            # Do not mark a failed or uncertain database operation
            # as a successful payment.
            with self.db.transaction() as connection:
                connection.execute(
                    """
                    UPDATE payment_attempts
                    SET status = 'FAILED',
                        failure_reason = 'Payment processing error',
                        completed_at = CURRENT_TIMESTAMP
                    WHERE id = ? AND status = 'PROCESSING'
                    """,
                    (attempt_id,),
                )

            raise
