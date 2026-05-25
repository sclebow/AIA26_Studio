from _runtime.bootstrap import bootstrap
from graph import run_agent

def main():
    """Main loop - session persists across turns."""
    print("\n" + "="*60)
    print("🏠 Layout Design Agent")
    print("="*60)
    print("Describe your desired layout or type 'quit' to exit.\n")
    
    ctx = bootstrap()
    session = {}  # Persists across turns
    
    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break
        
        if not user_input:
            continue
        
        if user_input.lower() in ("exit", "quit"):
            print("Goodbye.")
            break
        
        try:
            response, session = run_agent(user_input, ctx, session)
            print(f"\nAgent: {response}\n")
        except Exception as e:
            print(f"\n❌ Error: {e}")
            print("Session still active. Try again or type 'quit'.\n")
            continue

if __name__ == "__main__":
    main()