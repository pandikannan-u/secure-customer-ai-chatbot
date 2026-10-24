
from app.database import SessionLocal
from app.models import Customer, Invoice


def seed_data():
    db = SessionLocal()

    try:
        customers = [
            {"name": "Pandikannan", "mobile": "9876543210"},
            {"name": "Dhamodharan", "mobile": "9876543211"},
        ]

        for item in customers:
            customer = db.query(Customer).filter_by(
                mobile=item["mobile"]
            ).first()

            if not customer:
                customer = Customer(**item)
                db.add(customer)
                db.flush()

            for i in range(1, 6):
                invoice_number = f"INV-{customer.id}-{i}"

                exists = db.query(Invoice).filter_by(
                    customer_id=customer.id,
                    invoice_number=invoice_number,
                ).first()

                if not exists:
                    db.add(
                        Invoice(
                            customer_id=customer.id,
                            invoice_number=invoice_number,
                            description=f"Sample invoice {i}",
                            amount=i * 1000,
                            status="pending",
                        )
                    )

        db.commit()
        print("Seed data created successfully!")

    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_data()
