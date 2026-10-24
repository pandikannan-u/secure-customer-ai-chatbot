
from datetime import date

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import Invoice


def search_records(db: Session, customer, query: str = ""):
    invoices = (
        db.query(Invoice)
        .filter(Invoice.customer_id == customer.id)
        .order_by(Invoice.id)
        .all()
    )

    query = query.strip().lower()

    if query:
        invoices = [
            invoice
            for invoice in invoices
            if query in invoice.invoice_number.lower()
            or query in invoice.description.lower()
            or query in invoice.status.lower()
            or query in invoice.currency.lower()
            or query in invoice.invoice_date.isoformat()
        ]

    return [
        {
            "invoice_id": invoice.id,
            "invoice_number": invoice.invoice_number,
            "invoice_date": invoice.invoice_date.isoformat(),
            "description": invoice.description,
            "amount": invoice.amount,
            "currency": invoice.currency,
            "status": invoice.status,
        }
        for invoice in invoices
    ]


def add_invoice(
    db: Session,
    customer,
    invoice_number: str,
    description: str,
    amount: int,
    invoice_date: date,
    currency: str = "INR",
    confirmed: bool = False,
):
    invoice_number = invoice_number.strip()
    description = description.strip()
    currency = currency.strip().upper()

    if not invoice_number or not description:
        raise HTTPException(
            status_code=400,
            detail="Invoice number and description are required.",
        )

    if amount <= 0:
        raise HTTPException(
            status_code=400,
            detail="Amount must be greater than zero.",
        )

    if not isinstance(invoice_date, date):
        raise HTTPException(
            status_code=400,
            detail="A valid invoice date is required (YYYY-MM-DD).",
        )

    if len(currency) != 3 or not currency.isalpha():
        raise HTTPException(
            status_code=400,
            detail="Currency must be a valid three-letter code, such as INR.",
        )

    if not confirmed:
        return {
            "confirmation_required": True,
            "message": "Ask the customer to confirm before creating this invoice.",
            "invoice_number": invoice_number,
            "invoice_date": invoice_date.isoformat(),
            "description": description,
            "amount": amount,
            "currency": currency,
        }

    existing = (
        db.query(Invoice)
        .filter(
            Invoice.customer_id == customer.id,
            Invoice.invoice_number == invoice_number,
        )
        .first()
    )

    if existing:
        raise HTTPException(
            status_code=409,
            detail="This invoice already exists for this customer.",
        )

    invoice = Invoice(
        customer_id=customer.id,
        invoice_number=invoice_number,
        invoice_date=invoice_date,
        description=description,
        amount=amount,
        currency=currency,
        status="pending",
    )

    try:
        db.add(invoice)
        db.commit()
        db.refresh(invoice)
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Invoice could not be created. Please try again.",
        )

    return {
        "message": "Invoice created successfully.",
        "invoice_id": invoice.id,
        "invoice_number": invoice.invoice_number,
        "invoice_date": invoice.invoice_date.isoformat(),
        "description": invoice.description,
        "amount": invoice.amount,
        "currency": invoice.currency,
        "status": invoice.status,
    }
