
from qdrant_client import QdrantClient, models
from sentence_transformers import SentenceTransformer
from sqlalchemy.orm import Session

from app.models import Customer, Invoice

COLLECTION_NAME = "customer_invoices"
VECTOR_SIZE = 384

# Persistent local storage inside the project folder
qdrant = QdrantClient(path="./qdrant_storage")

# Downloads the embedding model on first use if it isn't cached.
embedding_model = SentenceTransformer("all-MiniLM-L6-v2")


def ensure_collection():
    if not qdrant.collection_exists(COLLECTION_NAME):
        qdrant.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=models.VectorParams(
                size=VECTOR_SIZE,
                distance=models.Distance.COSINE,
            ),
        )


def index_customer_invoices(db: Session, customer: Customer):
    ensure_collection()

    invoices = (
        db.query(Invoice)
        .filter(Invoice.customer_id == customer.id)
        .order_by(Invoice.id)
        .all()
    )

    points = []

    for invoice in invoices:
        text = (
            f"Invoice number: {invoice.invoice_number}. "
            f"Description: {invoice.description}. "
            f"Amount: {invoice.amount}. Status: {invoice.status}."
        )

        vector = embedding_model.encode(text).tolist()

        points.append(
            models.PointStruct(
                id=invoice.id,
                vector=vector,
                payload={
                    "customer_id": customer.id,
                    "invoice_id": invoice.id,
                    "invoice_number": invoice.invoice_number,
                    "description": invoice.description,
                    "amount": invoice.amount,
                    "status": invoice.status,
                    "text": text,
                },
            )
        )

    if points:
        qdrant.upsert(
            collection_name=COLLECTION_NAME,
            points=points,
            wait=True,
        )

    return len(points)


def retrieve_customer_context(
    db: Session,
    customer: Customer,
    query: str,
) -> list[dict]:
    ensure_collection()

    # Reindex this customer's current invoices before searching.
    index_customer_invoices(db, customer)

    query_vector = embedding_model.encode(query).tolist()

    results = qdrant.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vector,
        query_filter=models.Filter(
            must=[
                models.FieldCondition(
                    key="customer_id",
                    match=models.MatchValue(value=customer.id),
                )
            ]
        ),
        limit=10,
        with_payload=True,
    ).points

    return [
        {
            "invoice_id": point.payload["invoice_id"],
            "invoice_number": point.payload["invoice_number"],
            "description": point.payload["description"],
            "amount": point.payload["amount"],
            "status": point.payload["status"],
            "source_id": str(point.id),
        }
        for point in results
    ]


def format_customer_context(records: list[dict]) -> str:
    if not records:
        return "No invoice records were found for this customer."

    return "\n".join(
        f"Source ID: {record['source_id']}; "
        f"Invoice: {record['invoice_number']}; "
        f"Description: {record['description']}; "
        f"Amount: {record['amount']}; "
        f"Status: {record['status']}"
        for record in records
    )

def close_qdrant():
    qdrant.close()