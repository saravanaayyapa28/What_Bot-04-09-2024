# This code is perfect but no updation in date and time function 
# Check the same time and date appoinment are check in database mongodb

from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import openai
import pymongo
from pymongo import MongoClient
from datetime import datetime, time
import re

app = Flask(__name__)

# OpenAI API setup
openai_api_key = "Your Open Api Key"
openai.api_key = openai_api_key

# MongoDB Atlas setup
mongo_connection_string = "mongodb+srv://developers:w5tf9vjygZD645OX@cluster0.v5d97rn.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
client = MongoClient(mongo_connection_string)
db = client["doctor_appointments_db"]
appointments_collection = db["appointments"]
users_collection = db["users"]

# Doctor departments and availability
departments = {
    "cardiology": {"availability": "9 AM - 4 PM"},
    "neurology": {"availability": "10 AM - 2 PM"},
    "pediatrics": {"availability": "1 PM - 6 PM"},
    "orthopedics": {"availability": "8:30 AM - 4 PM"},
    "dermatology": {"availability": "11 AM - 2 PM"},
    "gynecology & obstetrics": {"availability": "11:30 AM - 6 PM"}
}

def generate_answer(question):
    """Generate answers using ChatGPT"""
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": question},
            ],
            temperature=0.5,
            max_tokens=150,
        )
        return response.choices[0].message["content"].strip()
    except Exception as e:
        print(f"Error generating answer: {e}")
        return "I'm sorry, I couldn't process that. Please try again."

def book_appointment(patient_name, department, appointment_time, patient_mobile_number):
    """Store appointment details in MongoDB"""
    appointment = {
        "patient_name": patient_name,
        "department": department,
        "appointment_time": appointment_time,
        "patient_mobile_number": patient_mobile_number,
        "created_at": datetime.utcnow()
    }
    try:
        appointments_collection.insert_one(appointment)
        return "Your appointment has been confirmed."
    except Exception as e:
        print(f"Error booking appointment: {e}")
        return "Sorry, there was an error booking your appointment. Please try again later."

def get_user_state(from_number):
    """Retrieve the user's current state and data"""
    user = users_collection.find_one({"from": from_number})
    if not user:
        # Initialize user state
        users_collection.insert_one({"from": from_number, "state": "start"})
        return {"state": "start", "data": {}}
    return user

def update_user_state(from_number, state, data=None):
    """Update the user's state and data"""
    update_fields = {"state": state}
    if data:
        update_fields["data"] = data
    users_collection.update_one({"from": from_number}, {"$set": update_fields})

def validate_date_time(input_text):
    """Validate date and time for the appointment within availability (9:00 AM - 5:00 PM)"""
    pattern = r'^\d{4}-\d{2}-\d{2} \d{1,2}:\d{2} (AM|PM)$'
    
    if not re.match(pattern, input_text.strip(), re.IGNORECASE):
        return False  # Invalid format
    
    # Parse the date and time
    try:
        appointment_time = datetime.strptime(input_text, '%Y-%m-%d %I:%M %p')
        
        # Check if the time is within the doctor's availability (e.g., 9:00 AM to 5:00 PM)
        opening_time = time(9, 0)  # 9:00 AM
        closing_time = time(17, 0)  # 5:00 PM
        
        if opening_time <= appointment_time.time() <= closing_time:
            return True  # Valid date and time within working hours
        else:
            return False  # Time is outside of working hours
        
    except ValueError:
        return False  # Invalid date or time format

@app.route("/", methods=['GET'])
def home():
    return "Welcome to CMC Hospital Vellore Online WhatsApp Appointment Bot!"

@app.route("/whatsapp", methods=['POST'])
def wa_reply():
    from_number = request.form.get('From')
    query = request.form.get('Body').strip()
    print(f"User ({from_number}) Query: {query}")
    
    twilio_response = MessagingResponse()
    reply = twilio_response.message()
    
    user = get_user_state(from_number)
    current_state = user.get("state", "start")
    user_data = user.get("data", {})
    
    if current_state == "start":
        reply.body("Welcome to CMC Hospital Vellore!\n If you can Book Appointment type 'book appointment' to schedule a doctor's visit.")
        if "book appointment" in query.lower():
            reply.body("Sure, let's book an appointment. Please provide your Full Name:")
            update_user_state(from_number, "awaiting_name")
        elif "department" in query.lower():
            dept = query.lower().split()[-1]
            if dept in departments:
                availability = departments[dept]["availability"]
                reply.body(f"Doctor availability for {dept.capitalize()}: {availability}")
            else:
                reply.body("Sorry, the department is not available.")
        else:
            answer = generate_answer(query)
            reply.body(answer)
    
    elif current_state == "awaiting_name":
        user_data['patient_name'] = query
        #reply.body("Great, please enter the department you want to book an appointment for (e.g., Cardiology Neurology, Pediatrics, Gynecology & Obstetrics, Dermatology, Orthopedics):")
        reply.body("Great, please enter the department you want to book an appointment for e.g.,\n1.Cardiology\n2.Neurology\n3.Pediatrics\n4.Gynecology & Obstetrics\n5.Dermatology\n6.Orthopedics")
        update_user_state(from_number, "awaiting_department", user_data)
    
    elif current_state == "awaiting_department":
        dept = query.lower()
        if dept in departments:
            user_data['department'] = dept
            availability = departments[dept]["availability"]
            reply.body(f"Doctor availability for {dept.capitalize()}: {availability}\nPlease enter your preferred appointment date and time (format: YYYY-MM-DD HH:MM AM/PM):")
            update_user_state(from_number, "awaiting_time", user_data)
        else:
            reply.body("Sorry, that department is not available. Please enter a valid department (e.g., Cardiology, Neurology, Pediatrics, Gynecology & Obstetrics, Dermatology, Orthopedics):")
            update_user_state(from_number, "awaiting_department", user_data)
    
    elif current_state == "awaiting_time":
        if validate_date_time(query):
            user_data['appointment_time'] = query
            reply.body("Please provide your mobile number for the appointment confirmation:")
            update_user_state(from_number, "awaiting_mobile_number", user_data)
        else:
            reply.body("Invalid date/time format. Please enter in the format: YYYY-MM-DD HH:MM AM/PM (e.g., 2024-09-25 10:00 AM):")
            update_user_state(from_number, "awaiting_time", user_data)

    elif current_state == "awaiting_mobile_number":
        user_data['patient_mobile_number'] = query
        reply.body(f"Please confirm your appointment:\nName: {user_data['patient_name']}\nDepartment: {user_data['department'].capitalize()}\nTime: {user_data['appointment_time']}\nMobile: {user_data['patient_mobile_number']}\nReply with 'confirm' to book or 'cancel' to abort.")
        update_user_state(from_number, "awaiting_confirmation", user_data)
    
    elif current_state == "awaiting_confirmation":
        if query.lower() == "confirm":
            confirmation_message = book_appointment(
                user_data.get('patient_name'),
                user_data.get('department'),
                user_data.get('appointment_time'),
                user_data.get('patient_mobile_number')
            )
            reply.body(confirmation_message)
            reply.body("Would you like to book another appointment or exit the chat?\nReply with 'book again' or 'exit'.")
            update_user_state(from_number, "post_confirmation", user_data)
        elif query.lower() == "cancel":
            reply.body("Your appointment booking has been canceled. Would you like to book again or exit?\nReply with 'book again' or 'exit'.")
            update_user_state(from_number, "post_confirmation", {})
        else:
            reply.body("Please reply with 'confirm' to book the appointment or 'cancel' to abort.")
    
    elif current_state == "post_confirmation":
        if "book again" in query.lower():
            reply.body("Sure, let's start over. Please provide your Full Name:")
            update_user_state(from_number, "awaiting_name")
        elif "exit" in query.lower():
            reply.body("Thank you for using CMC Hospital Vellore Appointment Bot. Have a great day!")
            update_user_state(from_number, "start", {})
        else:
            reply.body("Please reply with 'book again' to book another appointment or 'exit' to end the chat.")
    
    else:
        reply.body("Sorry, I didn't understand that. Can you please rephrase?")

    return str(twilio_response)

if __name__ == "__main__":
    app.run(debug=True)
