
from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
import ollama
import json
import re

from app.database import get_db
from app.auth import get_current_customer
from app.models import Conversation, Message, Invoice
from app.tools import search_records, add_invoice
from app.rag import retrieve_customer_context, index_customer_invoices

router = APIRouter()
MODEL = "gemma:2b"
HISTORY_LIMIT = 100


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    conversation_id: int | None = None


def ask_gemma(prompt: str) -> str:
    response = ollama.chat(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a helpful customer support assistant. "
                    "Answer general questions accurately and simply. "
                    "RAG means Retrieval-Augmented Generation: retrieving relevant "
                    "information from a knowledge source and using it to generate an answer. "
                    "If you are unsure, say so instead of inventing facts. "
                    "Never invent invoice information. "
                    "Never claim an invoice was created unless the application confirms it."
                ),
            },
            {"role": "user", "content": prompt},
        ],
    )
    return response.message.content or "Please try again."


def is_confirmation(text: str) -> bool:
    return text.strip().lower() in {
        "confirm", "confirmed", "yes confirm", "yes, confirm",
        "i confirm", "approve", "approved",
    }


def extract_invoice_details(text: str):
    number_match = re.search(r"\bINV-[A-Za-z0-9-]+\b", text, re.I)

    amount_match = re.search(
        r"(?:INR|Rs\.?|₹)\s*([0-9]+)|amount\s*(?:is|of|:)?\s*([0-9]+)",
        text,
        re.I,
    )

    date_match = re.search(
        r"(?:invoice\s*)?date\s*(?:is|:)?\s*(\d{4}-\d{2}-\d{2})",
        text,
        re.I,
    )

    currency_match = re.search(r"\bcurrency\s*(?:is|:)?\s*([A-Za-z]{3})\b", text, re.I)

    description_match = re.search(
        r"description\s*(?:is|:)?\s*(.*?)(?=\s+amount\b|\s+invoice\s*date\b|\s+date\b|\s+currency\b|\s+INR\b|\s+Rs\.?\b|₹|$)",
        text,
        re.I,
    )

    number = number_match.group(0) if number_match else None
    amount = None
    if amount_match:
        amount = int(amount_match.group(1) or amount_match.group(2))

    invoice_date = None
    if date_match:
        try:
            invoice_date = date.fromisoformat(date_match.group(1))
        except ValueError:
            invoice_date = None

    currency = currency_match.group(1).upper() if currency_match else "INR"

    description = (
        description_match.group(1).strip().rstrip(" ,;")
        if description_match else None
    )

    return number, description, amount, invoice_date, currency


def get_pending_proposal(db: Session, conversation_id: int):
    previous = (
        db.query(Message)
        .filter(
            Message.conversation_id == conversation_id,
            Message.role == "assistant",
        )
        .order_by(Message.id.desc())
        .limit(HISTORY_LIMIT)
        .all()
    )

    for message in previous:
        marker = "\n[PENDING_INVOICE_JSON]"
        if marker in message.content:
            try:
                data = json.loads(message.content.split(marker, 1)[1])
                return data if data.get("state") == "pending" else None
            except (ValueError, TypeError):
                return None
    return None


def search_customer_invoices(db, customer, query=""):
    return search_records(db, customer, query)


@router.post("/chat/")
def chat(
    request: ChatRequest,
    db: Session = Depends(get_db),
    customer=Depends(get_current_customer),
):
    text = request.message.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    if request.conversation_id is not None:
        conversation = (
            db.query(Conversation)
            .filter(
                Conversation.id == request.conversation_id,
                Conversation.customer_id == customer.id,
            )
            .first()
        )
        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversation not found.")
    else:
        conversation = Conversation(customer_id=customer.id)
        db.add(conversation)
        db.commit()
        db.refresh(conversation)

    db.add(Message(
        conversation_id=conversation.id,
        role="user",
        content=text,
    ))
    db.commit()

    answer = ""
    marker_to_store = None

    try:
        lower = text.lower()

        if is_confirmation(text):
            proposal = get_pending_proposal(db, conversation.id)
            if not proposal:
                answer = "There is no pending invoice proposal to confirm."
            else:
                result = add_invoice(
                    db=db,
                    customer=customer,
                    invoice_number=proposal["invoice_number"],
                    description=proposal["description"],
                    amount=proposal["amount"],
                    invoice_date=date.fromisoformat(proposal["invoice_date"]),
                    currency=proposal.get("currency", "INR"),
                    confirmed=True,
                )
                answer = result.get("message", "Invoice creation completed.")
                index_customer_invoices(db, customer)
                proposal["state"] = "completed"
                marker_to_store = json.dumps(proposal)

        elif any(word in lower for word in (
            "create invoice", "add invoice", "create a bill", "add a bill"
        )):
            number, description, amount, invoice_date, currency = extract_invoice_details(text)

            existing = None
            if number:
                existing = (
                    db.query(Invoice)
                    .filter(
                        Invoice.customer_id == customer.id,
                        Invoice.invoice_number == number,
                    )
                    .first()
                )

            missing = []
            if not number:
                missing.append("invoice number, e.g. INV-300")
            if not description:
                missing.append("description using 'description: ...'")
            if amount is None or amount <= 0:
                missing.append("positive amount, e.g. INR 1250")
            if invoice_date is None:
                missing.append("invoice date in YYYY-MM-DD format")
            if not re.fullmatch(r"[A-Z]{3}", currency):
                missing.append("a three-letter currency code")

            if missing:
                answer = "Please provide " + ", ".join(missing) + "."
            elif existing:
                answer = (
                    f"Invoice {number} already exists. "
                    "Duplicate creation is not allowed."
                )
            else:
                result = add_invoice(
                    db=db,
                    customer=customer,
                    invoice_number=number,
                    description=description,
                    amount=amount,
                    invoice_date=invoice_date,
                    currency=currency,
                    confirmed=False,
                )
                if result.get("confirmation_required"):
                    marker_to_store = json.dumps({
                        "state": "pending",
                        "invoice_number": number,
                        "description": description,
                        "amount": amount,
                        "invoice_date": invoice_date.isoformat(),
                        "currency": currency,
                    })
                    answer = (
                        "Please confirm this invoice:\n"
                        f"Number: {number}\n"
                        f"Date: {invoice_date.isoformat()}\n"
                        f"Description: {description}\n"
                        f"Amount: {currency} {amount}\n"
                        "No invoice has been created yet. Reply 'confirm' "
                        "only if these exact details are correct."
                    )
                else:
                    answer = result.get("message", json.dumps(result, default=str))

        elif any(word in lower for word in (
            "invoice", "invoices", "unpaid", "pending",
            "paid", "payment", "bill", "bills", "inv-",
        )):
            records = search_customer_invoices(db, customer, "")

            if "unpaid" in lower or "pending" in lower:
                records = [
                    r for r in records
                    if str(r.get("status", "")).lower() in {"pending", "unpaid", "overdue"}
                ]
            elif re.search(r"\bpaid\b", lower):
                records = [
                    r for r in records
                    if str(r.get("status", "")).lower() == "paid"
                ]

            try:
                retrieve_customer_context(db, customer, text)
            except Exception:
                answer = (
                    "Invoice records are temporarily unavailable through "
                    "the retrieval system. Please try again later."
                )
            else:
                if not records:
                    answer = "No matching invoices found in your records."
                else:
                    lines = ["Here are your invoices:"]
                    for invoice in records:
                        lines.append(
                            f"Invoice: {invoice['invoice_number']} | "
                            f"Date: {invoice['invoice_date']} | "
                            f"Description: {invoice['description']} | "
                            f"Amount: {invoice['currency']} {invoice['amount']} | "
                            f"Status: {invoice['status']}"
                        )
                    answer = "\n".join(lines)

        else:
            answer = ask_gemma(text)

    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        answer = "I couldn't process that request right now. Please try again."
        marker_to_store = None

    stored_answer = answer
    if marker_to_store:
        stored_answer += "\n[PENDING_INVOICE_JSON]" + marker_to_store

    db.add(Message(
        conversation_id=conversation.id,
        role="assistant",
        content=stored_answer,
    ))
    db.commit()

    return {
        "conversation_id": conversation.id,
        "response": answer,
    }


@router.get("/chat/history/{conversation_id}")
def get_chat_history(
    conversation_id: int,
    db: Session = Depends(get_db),
    customer=Depends(get_current_customer),
):
    conversation = (
        db.query(Conversation)
        .filter(
            Conversation.id == conversation_id,
            Conversation.customer_id == customer.id,
        )
        .first()
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")

    messages = (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.id)
        .limit(HISTORY_LIMIT)
        .all()
    )

    return {
        "conversation_id": conversation_id,
        "messages": [
            {
                "role": message.role,
                "content": message.content.split("\n[PENDING_INVOICE_JSON]", 1)[0],
            }
            for message in messages
        ],
    }
