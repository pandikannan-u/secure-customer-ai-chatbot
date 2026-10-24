# Secure Customer AI Chatbot

A secure AI-powered customer support chatbot built using FastAPI, PostgreSQL, Retrieval-Augmented Generation (RAG), and Ollama.

## Features

- OTP-based customer authentication
- JWT access-token authentication
- Customer invoice management
- Invoice search and status filtering
- Confirmation before invoice creation
- Duplicate invoice prevention
- RAG-based customer information retrieval
- Conversational AI responses using Ollama

## Tech Stack

- **Backend:** FastAPI, Python
- **Database:** PostgreSQL, SQLAlchemy
- **AI Model:** Ollama (Gemma 2B)
- **Retrieval:** Retrieval-Augmented Generation (RAG), Qdrant
- **Authentication:** OTP verification, JWT
- **Testing:** Pytest

## Project Structure

```text
secure-customer-ai-chatbot/
├── app/
│   ├── auth.py
│   ├── chat.py
│   ├── config.py
│   ├── database.py
│   ├── main.py
│   ├── models.py
│   ├── rag.py
│   ├── seed.py
│   └── tools.py
├── tests/
│   └── test_rag_failure.py
├── .gitignore
├── migrate_invoices.py
└── requirements.txt
```

## Setup

1. Clone the repository:

   ```bash
   git clone https://github.com/pandikannan-u/secure-customer-ai-chatbot.git
   cd secure-customer-ai-chatbot
   ```

2. Create and activate a Python virtual environment.

3. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

4. Configure the required environment variables and PostgreSQL database settings.

5. Install and start Ollama, and ensure the required Gemma model is available.

6. Start the FastAPI application:

   ```bash
   uvicorn app.main:app
   ```

7. Open the API documentation:

   http://127.0.0.1:8000/docs

## Security Notes

- Store passwords, API keys, and JWT secrets in environment variables.
- Do not commit `.env` files or sensitive customer data.
- Use a strong JWT secret in deployment environments.

## License

No license has been specified for this project yet.
