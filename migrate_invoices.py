from sqlalchemy import text
from app.database import engine

try:
    with engine.begin() as connection:
        connection.execute(text("""
            ALTER TABLE invoices
            ADD COLUMN IF NOT EXISTS invoice_date DATE
        """))

        connection.execute(text("""
            ALTER TABLE invoices
            ADD COLUMN IF NOT EXISTS currency VARCHAR(3)
            NOT NULL DEFAULT 'INR'
        """))

        connection.execute(text("""
            UPDATE invoices
            SET invoice_date = DATE '2026-10-22'
            WHERE invoice_date IS NULL
        """))

        connection.execute(text("""
            ALTER TABLE invoices
            ALTER COLUMN invoice_date SET NOT NULL
        """))

    print("Migration successful!")

except Exception as error:
    print("Migration failed:", error)
    raise

finally:
    engine.dispose()