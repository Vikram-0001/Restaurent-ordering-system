import sys
import db
from graph import graph
from langchain_core.messages import HumanMessage
from langgraph.types import Command

def main():
    # Initialize the database
    db.initialize_database()
    print("Database initialized and seeded.")
    
    config = {"configurable": {"thread_id": "customer_001"}}
    
    print("\n=============================================")
    print("      Welcome to the AI Restaurant!          ")
    print("=============================================")
    
    # Display the menu
    menu = db.get_menu()
    print("\n--- MENU ---")
    for item in menu:
        print(f"- {item['name']}: Rs. {item['price']} (Stock: {item['available_qty']})")
    print("---------------------------------------------\n")
    print("You can chat with the assistant. Type 'exit' to quit.\n")
    
    while True:
        try:
            user_input = input("Customer: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye!")
            break
            
        if user_input.lower() == "exit":
            print("Goodbye!")
            break
            
        if not user_input:
            continue
            
        # Run the graph
        try:
            events = list(graph.stream(
                {"messages": [HumanMessage(content=user_input)]},
                config,
                stream_mode="values"
            ))
        except Exception as e:
            if "RESOURCE_EXHAUSTED" in str(e) or "429" in str(e):
                print("\n[System Notice] Gemini API rate limit or daily quota exceeded. Please wait a few seconds and try again.\n")
            else:
                print(f"\n[System Error] An error occurred: {e}\n")
            continue
        
        # Check if the graph is currently interrupted
        state = graph.get_state(config)
        
        # We need a boolean flag to track if resume fails
        resume_failed = False
        while state.next and state.tasks and state.tasks[0].interrupts and not resume_failed:
            interrupt_val = state.tasks[0].interrupts[0].value
            order_id = interrupt_val.get("order_id")
            items = interrupt_val.get("items")
            status = interrupt_val.get("status")
            
            print("\n" + "="*45)
            print(" SYSTEM INTERRUPT: MANAGER APPROVAL REQUIRED ")
            print("="*45)
            print(f"Order ID: {order_id}")
            print("Items:")
            for item in items:
                print(f"  - {item['item']}: {item['qty']}")
            print(f"Current status: {status}")
            print("="*45)
            
            decision = ""
            while decision not in ["APPROVED", "REJECTED"]:
                choice = input("Manager, approve or reject this order? (a/r/exit): ").strip().lower()
                if choice in ["a", "approve"]:
                    decision = "APPROVED"
                elif choice in ["r", "reject"]:
                    decision = "REJECTED"
                elif choice == "exit":
                    print("Exiting application...")
                    sys.exit(0)
                else:
                    print("Invalid choice. Please enter 'a' or 'r'.")
            
            note = input("Manager note (optional): ").strip()
            
            # Resume the graph
            try:
                events = list(graph.stream(
                    Command(resume={"decision": decision, "note": note}),
                    config,
                    stream_mode="values"
                ))
            except Exception as e:
                if "RESOURCE_EXHAUSTED" in str(e) or "429" in str(e):
                    print("\n[System Notice] Gemini API rate limit or daily quota exceeded. Please wait a few seconds and try again.\n")
                else:
                    print(f"\n[System Error] Failed to resume: {e}\n")
                resume_failed = True
                break
            
            # Get updated state
            state = graph.get_state(config)
            
        if resume_failed:
            continue
            
        # Get final state to show assistant response
        state = graph.get_state(config)
        messages = state.values.get("messages", [])
        if messages:
            ai_msg = next((m for m in reversed(messages) if m.type == "ai"), None)
            if ai_msg:
                content = ai_msg.content
                if isinstance(content, list):
                    text_parts = []
                    for part in content:
                        if isinstance(part, dict):
                            if part.get("type") == "text":
                                text_parts.append(part.get("text", ""))
                            elif "text" in part:
                                text_parts.append(part["text"])
                        elif isinstance(part, str):
                            text_parts.append(part)
                    content = "".join(text_parts)
                print(f"\nAssistant: {content}\n")

if __name__ == "__main__":
    main()
