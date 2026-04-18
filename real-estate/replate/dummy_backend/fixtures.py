from werkzeug.security import generate_password_hash

PARTNERS = [
    {"id": 1, "name": "SF-Marin Food Bank"},
    {"id": 2, "name": "Glide Memorial Kitchen"},
    {"id": 3, "name": "St. Anthony Foundation"},
]

TASKS = [
    {
        "id": 101,
        "encrypted_id": "enc_abc123",
        "date": "2026-04-18",
        "start_time": "10:00",
        "end_time": "11:00",
        "donor_name": "Google Cafeteria",
        "address": {
            "street": "1600 Amphitheatre Pkwy",
            "city": "Mountain View",
            "state": "CA",
            "zip": "94043",
        },
        "lat": 37.4220, "lon": -122.0841,   # Mountain View — ~48 km from SF
        "contact_name": "Jane Smith",
        "contact_phone": "6505550100",
        "contact_email": "jane@google.com",
        "food_description": "Mixed entrees",
        "tray_type": "full",
        "tray_count": 8,
        "access_instructions": "Check in at lobby reception",
        "status": "available",
        "driver_id": None,
        "completion_details": None,
    },
    {
        "id": 102,
        "encrypted_id": "enc_def456",
        "date": "2026-04-18",
        "start_time": "14:00",
        "end_time": "15:30",
        "donor_name": "LinkedIn Café",
        "address": {
            "street": "222 2nd St",
            "city": "San Francisco",
            "state": "CA",
            "zip": "94105",
        },
        "lat": 37.7877, "lon": -122.3974,   # SoMa SF — ~2.4 km from Alice
        "contact_name": "Bob Lee",
        "contact_phone": "4155550199",
        "contact_email": "bob@linkedin.com",
        "food_description": "Salads and sandwiches",
        "tray_type": "half",
        "tray_count": 12,
        "access_instructions": "Side entrance on Minna St",
        "status": "available",
        "driver_id": None,
        "completion_details": None,
    },
    {
        "id": 103,
        "encrypted_id": "enc_ghi789",
        "date": "2026-04-19",
        "start_time": "09:00",
        "end_time": "10:00",
        "donor_name": "Salesforce Tower Café",
        "address": {
            "street": "415 Mission St",
            "city": "San Francisco",
            "state": "CA",
            "zip": "94105",
        },
        "lat": 37.7895, "lon": -122.3963,   # Financial District SF — ~2.6 km from Alice
        "contact_name": "Maria Chen",
        "contact_phone": "4155550200",
        "contact_email": "maria@salesforce.com",
        "food_description": "Hot meals",
        "tray_type": "full",
        "tray_count": 6,
        "access_instructions": "",
        "status": "available",
        "driver_id": None,
        "completion_details": None,
    },
]

DRIVERS = [
    {
        "id": 1,
        "email": "alice@example.com",
        "password_hash": generate_password_hash("Password1"),
        "first_name": "Alice",
        "last_name": "Driver",
        "phone": "4155550001",
        "partner_id": 1,
        "lat": 37.7749, "lon": -122.4194,   # SF downtown
    },
]
