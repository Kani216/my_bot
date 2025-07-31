import google.generativeai as genai
import requests
import os
import uuid
import re

# Hardcoded API keys
GEMINI_API_KEY = 'AIzaSyBaGu4wTsNODCMz1lcvAAGi_GQFStsntiU'
FRESHSALES_API_KEY = '2Wa6pZBwZmAzgIVeeflv5A'
FRESHSALES_DOMAIN = 'kambaa1.myfreshworks.com'
FRESHSALES_BASE_URL = f'https://{FRESHSALES_DOMAIN}/crm/sales/api'

# Configure Gemini API
os.environ["GEMINI_API_KEY"] = GEMINI_API_KEY
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# In-memory contacts and state
contacts = []
chat_history = [
    {"role": "model", "parts": [{"text": "Welcome to the Customer Support Chatbot! Try commands like 'add contact', 'list contacts', 'list contact details', 'get details <name or email>', 'update contact <identifier>', 'delete contact <email>', or 'reset'."}]}
]
conversation_state = {
    "mode": None,
    "new_contact": {},
    "step": None,
    "update_identifier": None
}

# Intent mapping
intent_mapping = {
    'add_contact': ['add contact', 'create contact', 'new contact'],
    'list_contacts': ['list contacts', 'show contacts', 'view contacts'],
    'list_contact_details': ['list contact details', 'show contact details'],
    'get_details': ['get details', 'view details', 'show details'],
    'update_contact': ['update contact', 'edit contact'],
    'delete_contact': ['delete contact', 'remove contact']
}

def is_valid_email(email):
    """Validate email format using regex."""
    return re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email)

def is_valid_phone(phone):
    """Validate phone number format using regex (international format)."""
    return re.match(r'^\+?[1-9]\d{1,14}$', phone)

def chat(message):
    global chat_history, conversation_state, contacts
    if not message or not message.strip():
        return "Please enter a valid message."

    try:
        # Step-by-step contact creation
        if conversation_state["mode"] == "add_contact":
            step = conversation_state["step"]
            if step == "ask_first_name":
                conversation_state["new_contact"]["first_name"] = message
                conversation_state["step"] = "ask_last_name"
                return "Enter the last name:"
            elif step == "ask_last_name":
                conversation_state["new_contact"]["last_name"] = message
                conversation_state["step"] = "ask_email"
                return "Enter the email address:"
            elif step == "ask_email":
                if not is_valid_email(message):
                    return "Invalid email format. Please enter a valid email (e.g., user@example.com):"
                if any(c["email"].lower() == message.lower() for c in contacts):
                    conversation_state["new_contact"]["email"] = message
                    conversation_state["step"] = "ask_duplicate"
                    return f"Contact with email {message} already exists locally. Update it? (yes/no):"
                try:
                    response = requests.get(
                        f'{FRESHSALES_BASE_URL}/contacts?email={message}',
                        headers={'Authorization': f'Token token={FRESHSALES_API_KEY}'}
                    )
                    if response.ok and response.json()['contacts']:
                        conversation_state["new_contact"]["email"] = message
                        conversation_state["step"] = "ask_duplicate"
                        conversation_state["update_identifier"] = str(response.json()['contacts'][0]['id'])
                        return f"Contact with email {message} already exists in Freshsales (ID: {response.json()['contacts'][0]['id']}). Update it? (yes/no):"
                except Exception as api_err:
                    print(f"API Error: {str(api_err)}")
                conversation_state["new_contact"]["email"] = message
                conversation_state["step"] = "ask_phone"
                return "Enter the phone number:"
            elif step == "ask_duplicate":
                if message.lower() == "yes":
                    conversation_state["mode"] = "update_contact"
                    conversation_state["step"] = "ask_field"
                    return "Enter the field to update (e.g., first_name, last_name, email, phone, company, age, etc.):"
                elif message.lower() == "no":
                    conversation_state = {"mode": None, "new_contact": {}, "step": None, "update_identifier": None}
                    return "Contact creation cancelled. Try a different email or use 'update contact'."
                return "Please respond with 'yes' or 'no':"
            elif step == "ask_phone":
                if not is_valid_phone(message):
                    return "Invalid phone number format. Please enter a valid phone number (e.g., +1234567890 or 1234567890):"
                conversation_state["new_contact"]["phone"] = message
                conversation_state["step"] = "ask_company"
                return "Enter the company name:"
            elif step == "ask_company":
                conversation_state["new_contact"]["company"] = message
                contact = conversation_state["new_contact"]
                contact_id = len(contacts) + 1
                external_id = str(uuid.uuid4())

                try:
                    response = requests.post(
                        f'{FRESHSALES_BASE_URL}/contacts',
                        headers={'Authorization': f'Token token={FRESHSALES_API_KEY}', 'Content-Type': 'application/json'},
                        json={'contact': {
                            'first_name': contact['first_name'],
                            'last_name': contact['last_name'],
                            'email': contact['email'],
                            'mobile_number': contact['phone'],
                            'company': {'name': contact['company']},
                            'external_id': external_id
                        }}
                    )
                    if response.ok:
                        contact_id = response.json().get('contact', {}).get('id', contact_id)
                    else:
                        print(f"API Error: {response.status_code} {response.text}")
                except Exception as api_err:
                    print(f"API Error: {str(api_err)}")

                contact["id"] = contact_id
                contact["external_id"] = external_id
                contacts.append(contact)
                conversation_state = {"mode": None, "new_contact": {}, "step": None, "update_identifier": None}
                return (f"✅ Contact added (ID: {contact_id}):\n"
                        f"Name: {contact['first_name']} {contact['last_name']}\n"
                        f"Email: {contact['email']}\n"
                        f"Phone: {contact['phone']}\n"
                        f"Company: {contact['company']}\n"
                        f"External ID: {external_id}")

        elif conversation_state["mode"] == "update_contact":
            identifier = conversation_state["update_identifier"]
            contact = next((c for c in contacts if str(c["id"]) == identifier or c["email"].lower() == identifier.lower()), None)
            if not contact:
                conversation_state = {"mode": None, "new_contact": {}, "step": None, "update_identifier": None}
                return "❌ Contact not found."
            step = conversation_state["step"]
            if step == "ask_field":
                conversation_state["new_contact"]["field"] = message.lower()
                conversation_state["step"] = "ask_value"
                return f"Enter the new value for {message}:"
            elif step == "ask_value":
                field = conversation_state["new_contact"]["field"]
                contact[field] = message
                try:
                    response = requests.get(
                        f'{FRESHSALES_BASE_URL}/contacts?email={contact["email"]}',
                        headers={'Authorization': f'Token token={FRESHSALES_API_KEY}'}
                    )
                    if response.ok and response.json()['contacts']:
                        contact_id = response.json()['contacts'][0]['id']
                        contact_data = (
                            {'custom_field': {field: message}}
                            if field not in ['first_name', 'last_name', 'email', 'phone', 'mobile_number', 'company']
                            else {field: message} if field != 'company' else {'company': {'name': message}}
                        )
                        response = requests.put(
                            f'{FRESHSALES_BASE_URL}/contacts/{contact_id}',
                            headers={'Authorization': f'Token token={FRESHSALES_API_KEY}', 'Content-Type': 'application/json'},
                            json={'contact': contact_data}
                        )
                        if not response.ok:
                            print(f"API Error: {response.status_code} {response.text}")
                except Exception as api_err:
                    print(f"API Error: {str(api_err)}")
                conversation_state["step"] = "ask_more_updates"
                return (f"✅ Contact updated (ID: {contact['id']}):\n" +
                        "\n".join([f"{key.capitalize()}: {value}" for key, value in contact.items() if key != 'id']) +
                        "\nWould you like to update another field for this contact? (yes/no):")
            elif step == "ask_more_updates":
                if message.lower() == "yes":
                    conversation_state["step"] = "ask_field"
                    conversation_state["new_contact"] = {}
                    return "Enter the field to update (e.g., first_name, last_name, email, phone, company, age, etc.):"
                elif message.lower() == "no":
                    conversation_state = {"mode": None, "new_contact": {}, "step": None, "update_identifier": None}
                    return "Any other help needed?"
                return "Please respond with 'yes' or 'no':"

        intent_response = model.generate_content(
            f"Classify the intent of this command as one of {list(intent_mapping.keys())} or 'general': {message}"
        )
        intent = intent_response.text.strip()

        if intent == 'add_contact':
            conversation_state = {
                "mode": "add_contact",
                "new_contact": {},
                "step": "ask_first_name",
                "update_identifier": None
            }
            return "Let's add a new contact! Enter the first name:"
        
        elif intent == 'list_contacts':
            try:
                response = requests.get(
                    f'{FRESHSALES_BASE_URL}/contacts',
                    headers={'Authorization': f'Token token={FRESHSALES_API_KEY}'}
                )
                if response.ok:
                    api_contacts = response.json()['contacts'][:5]
                    if not api_contacts:
                        return "📭 No contacts found in Freshsales."
                    return "🧾 Contacts:\n" + "\n".join([
                        f"{c['id']}: {c['first_name']} {c['last_name']}" for c in api_contacts
                    ])
                else:
                    print(f"API Error: {response.status_code} {response.text}")
            except Exception as api_err:
                print(f"API Error: {str(api_err)}")
            if not contacts:
                return "📭 No contacts found."
            return "🧾 Contacts:\n" + "\n".join([
                f"{c['id']}: {c['first_name']} {c['last_name']}" for c in contacts
            ])

        elif intent == 'list_contact_details':
            try:
                response = requests.get(
                    f'{FRESHSALES_BASE_URL}/contacts',
                    headers={'Authorization': f'Token token={FRESHSALES_API_KEY}'}
                )
                if response.ok:
                    api_contacts = response.json()['contacts'][:5]
                    if not api_contacts:
                        return "📭 No contacts found in Freshsales."
                    return "📇 Contact Details:\n" + "\n\n".join([
                        f"ID: {c['id']}\n" +
                        f"Name: {c['first_name']} {c['last_name']}\n" +
                        f"Email: {c['email']}\n" +
                        f"Phone: {c.get('mobile_number', 'N/A')}\n" +
                        f"Company: {c.get('company', {}).get('name', 'N/A')}\n" +
                        f"External ID: {c.get('external_id', 'N/A')}\n" +
                        (f"Custom Fields: {', '.join([f'{k}: {v}' for k, v in c.get('custom_field', {}).items()])}"
                         if c.get('custom_field') else "")
                        for c in api_contacts
                    ])
            except Exception as api_err:
                print(f"API Error: {str(api_err)}")
            if not contacts:
                return "📭 No contacts found."
            return "📇 Contact Details:\n" + "\n\n".join([
                f"ID: {c['id']}\n" +
                "\n".join([f"{key.capitalize()}: {value}" for key, value in c.items() if key != 'id'])
                for c in contacts
            ])

        elif intent == 'get_details':
            parts = message.split(maxsplit=2)
            if len(parts) < 3:
                return "❗ Usage: get details <first_name or email>"
            search_value = parts[2].strip().lower()
            try:
                response = requests.get(
                    f'{FRESHSALES_BASE_URL}/contacts?{"email=" + search_value if is_valid_email(search_value) else "first_name=" + search_value}',
                    headers={'Authorization': f'Token token={FRESHSALES_API_KEY}'}
                )
                if response.ok:
                    api_contacts = response.json()['contacts']
                    if not api_contacts:
                        return f"❌ No contact found with the {'email' if is_valid_email(search_value) else 'name'} '{search_value}'."
                    return "🔍 Contact(s) found:\n" + "\n\n".join([
                        f"ID: {c['id']}\n" +
                        f"Name: {c['first_name']} {c['last_name']}\n" +
                        f"Email: {c['email']}\n" +
                        f"Phone: {c.get('mobile_number', 'N/A')}\n" +
                        f"Company: {c.get('company', {}).get('name', 'N/A')}\n" +
                        f"External ID: {c.get('external_id', 'N/A')}\n" +
                        (f"Custom Fields: {', '.join([f'{k}: {v}' for k, v in c.get('custom_field', {}).items()])}"
                         if c.get('custom_field') else "")
                        for c in api_contacts
                    ])
            except Exception as api_err:
                print(f"API Error: {str(api_err)}")
            matches = [c for c in contacts if c["first_name"].lower() == search_value or c["email"].lower() == search_value]
            if not matches:
                return f"❌ No contact found with the {'email' if is_valid_email(search_value) else 'name'} '{search_value}'."
            return "🔍 Contact(s) found:\n" + "\n\n".join([
                f"ID: {c['id']}\n" +
                "\n".join([f"{key.capitalize()}: {value}" for key, value in c.items() if key != 'id'])
                for c in matches
            ])

        elif intent == 'delete_contact':
            parts = message.split()
            if len(parts) < 3:
                return "❌ Usage: delete contact <email>"
            email = parts[-1]
            try:
                response = requests.get(
                    f'{FRESHSALES_BASE_URL}/contacts?email={email}',
                    headers={'Authorization': f'Token token={FRESHSALES_API_KEY}'}
                )
                if response.ok and response.json()['contacts']:
                    contact_id = response.json()['contacts'][0]['id']
                    delete_response = requests.delete(
                        f'{FRESHSALES_BASE_URL}/contacts/{contact_id}',
                        headers={'Authorization': f'Token token={FRESHSALES_API_KEY}'}
                    )
                    if not delete_response.ok:
                        print(f"API Error: {response.status_code} {delete_response.text}")
                else:
                    print(f"API Error: {response.status_code} {response.text}")
            except Exception as api_err:
                print(f"API Error: {str(api_err)}")
            original_len = len(contacts)
            contacts[:] = [c for c in contacts if c["email"] != email]
            return "🗑️ Contact deleted." if len(contacts) < original_len else "❌ Contact not found."

        elif intent == 'update_contact':
            parts = message.split(maxsplit=2)
            if len(parts) < 3:
                return "❌ Usage: update contact <identifier> (ID or email)"
            identifier = parts[2].strip()
            contact = next((c for c in contacts if str(c["id"]) == identifier or c["email"].lower() == identifier.lower()), None)
            try:
                response = requests.get(
                    f'{FRESHSALES_BASE_URL}/contacts?{"id=" + identifier if identifier.isdigit() else "email=" + identifier}',
                    headers={'Authorization': f'Token token={FRESHSALES_API_KEY}'}
                )
                if response.ok and response.json()['contacts']:
                    contact_id = response.json()['contacts'][0]['id']
                    conversation_state = {
                        "mode": "update_contact",
                        "new_contact": {},
                        "step": "ask_field",
                        "update_identifier": str(contact_id)
                    }
                    return "Enter the field to update (e.g., first_name, last_name, email, phone, company, age, etc.):"
            except Exception as api_err:
                print(f"API Error: {str(api_err)}")
            if contact:
                conversation_state = {
                    "mode": "update_contact",
                    "new_contact": {},
                    "step": "ask_field",
                    "update_identifier": str(contact["id"])
                }
                return "Enter the field to update (e.g., first_name, last_name, email, phone, company, age, etc.):"
            return "❌ Contact not found."

        chat_history.append({"role": "user", "parts": [{"text": message}]})
        chat = model.start_chat(history=chat_history)
        response = chat.send_message(message)
        response_text = response.text
        chat_history.append({"role": "model", "parts": [{"text": response_text}]})
        if len(chat_history) > 10:
            chat_history[:] = chat_history[-10:]
        return response_text
    except Exception as e:
        print(f"Error: {str(e)}")
        return f"⚠️ Error: {str(e)}"

def reset():
    global chat_history, conversation_state, contacts
    chat_history = [
        {"role": "model", "parts": [{"text": "Welcome to the Customer Support Chatbot! Try commands like 'add contact', 'list contacts', 'list contact details', 'get details <name or email>', 'update contact <identifier>', 'delete contact <email>', or 'reset'."}]}
    ]
    conversation_state = {"mode": None, "new_contact": {}, "step": None, "update_identifier": None}
    contacts = []
    return "🔄 Reset done. How can I assist you now?"

if __name__ == '__main__':
    print("Customer Support Chatbot CLI. Type 'reset' to clear history, 'exit' to quit.")
    print("Bot: Welcome to the Customer Support Chatbot! Try commands like 'add contact', 'list contacts', 'list contact details', 'get details <name or email>', 'update contact <identifier>', 'delete contact <email>', or 'reset'.")
    while True:
        user_input = input("You: ")
        if user_input.lower() == 'exit':
            print("Bot: Goodbye!")
            break
        if user_input.lower() == 'reset':
            print("Bot:", reset())
        else:
            print("Bot:", chat(user_input))