import os
from dotenv import load_dotenv
from langchain_groq import ChatGroq

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not GROQ_API_KEY:
    raise ValueError(
        "GROQ_API_KEY not found in environment variables."
    )
else :
    print("Groq API Key loaded successfully")

# LLM

llm = ChatGroq(
    model="llama-3.3-70b-versatile",
    groq_api_key=GROQ_API_KEY,
    temperature=0,
)
# Default Thread ID

DEFAULT_THREAD_ID = "customer_001"

# Restaurant Settings

RESTAURANT_NAME = "AI Restaurant"
MANAGER_NAME = "Restaurant Manager"

# Order Status Constants

STATUS_DRAFT = "DRAFT"
STATUS_PENDING = "PENDING_APPROVAL"
STATUS_APPROVED = "APPROVED"
STATUS_REJECTED = "REJECTED"
STATUS_DELIVERED = "DELIVERED"
STATUS_COOKED = "COOKED"