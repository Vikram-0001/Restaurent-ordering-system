import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    raise ValueError(
        "GEMINI_API_KEY not found."
    )
else :
    print("API Key loaded successfully")

# LLM

llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    google_api_key=GEMINI_API_KEY,
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