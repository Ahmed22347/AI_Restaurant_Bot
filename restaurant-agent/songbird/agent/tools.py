import os
import requests
from urllib.parse import urlencode
from typing import Optional, Dict, Any
from datetime import datetime



# Constants
BASE_URL = "http://localhost:8547/api/ConsumerApi/v1/Restaurant/"
RESTAURANT_NAME = "TheHungryUnicorn"
BEARER_TOKEN = os.getenv("BEARER_TOKEN")
HEADERS = {
    "Authorization": f"Bearer {BEARER_TOKEN}",
    "Content-Type": "application/x-www-form-urlencoded"
}


class ToolError(Exception):
    """Custom exception for tool failures."""
    pass


def call_api(endpoint: str, params: dict) -> dict:
    """Helper function to make API requests with error handling."""
    url = f"{BASE_URL}{RESTAURANT_NAME}/{endpoint}"
    data = params.copy()

    try:
        response = requests.post(url, headers=HEADERS, data=data)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        raise ToolError(f"API request failed: {str(e)}")
    except ValueError:
        raise ToolError("Invalid JSON response from server.")
    


def call_api_get(endpoint: str, params: dict, func_name : str) -> dict:
    """Helper function to make API requests with error handling."""
    reference = params["booking_reference"]
    url = f"{BASE_URL}{RESTAURANT_NAME}/{endpoint}/{reference}"
    header = {
    "Authorization": f"Bearer {BEARER_TOKEN}"
}
    try:
        if func_name == "check_reservation":
            response = requests.get(url, headers=header)
        elif func_name:
            del params["booking_reference"]
            response = requests.patch(url, headers=header, data=params)
        else: 
            del params["booking_reference"]
            url = f"{BASE_URL}{RESTAURANT_NAME}/{endpoint}/{reference}/Cancel"
            response = requests.post(url, headers=header, data=params)
        response.raise_for_status()
        print(response)
        return response.json()
    except requests.RequestException as e:
        raise ToolError(f"API request failed: {str(e)}")
    except ValueError:
        raise ToolError("Invalid JSON response from server.")

# === TOOL FUNCTIONS ===

def check_availability(date: str, people) -> str:
    """Tool: Check availability for a specific date and time."""
    if not date or not people:
        raise ToolError("Missing date people for availability check.")

    response = call_api("AvailabilitySearch", {"VisitDate": date, "PartySize": people, "ChannelCode": "ONLINE"})
    #print(f"availability response {response'available_slots'}")

    return response['available_slots']


def _bool_to_str(value: bool) -> str:
    # Many form-encoded APIs expect 'true'/'false' strings
    return "true" if value else "false"

def _validate_date(date_str: str) -> None:
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        raise ToolError("VisitDate must be in YYYY-MM-DD format.")

def _validate_time(time_str: str) -> None:
    try:
        datetime.strptime(time_str, "%H:%M:%S")
    except ValueError:
        raise ToolError("VisitTime must be in HH:MM:SS format.")
    
def _normalize_time(time_str: str) -> str:
    """Ensure time is in HH:MM:SS format."""
    parts = time_str.split(":")
    if len(parts) == 2:  # HH:MM
        return f"{time_str}:00"
    elif len(parts) == 3:  # already HH:MM:SS
        return time_str
    else:
        raise ToolError("VisitTime must be in HH:MM or HH:MM:SS format.")


def make_reservation(
    date: str,          # YYYY-MM-DD
    time: str,          # HH:MM:SS
    people: int,
    *,
    channel_code: str = "ONLINE",
    special_requests: Optional[str] = None,
    is_leave_time_confirmed: Optional[bool] = None,
    room_number: Optional[str] = None,
    customer: Optional[Dict[str, Any]] = None,
) -> str:
    """Tool: Make a new booking with optional fields included only when provided."""
    if not all([date, time, people]):
        raise ToolError("Missing one or more booking parameters.")

    if people <= 0:
        raise ToolError("PartySize must be a positive integer.")


    _validate_date(date)
    time = _normalize_time(time)
    _validate_time(time)


    # Required fields
    payload = {
        "VisitDate": date,
        "VisitTime": time,
        "PartySize": str(people),
        "ChannelCode": channel_code,
    }

    # Optional simple fields (included only if given)
    if special_requests:
        payload["SpecialRequests"] = special_requests

    if is_leave_time_confirmed is not None:
        payload["IsLeaveTimeConfirmed"] = _bool_to_str(is_leave_time_confirmed)

    if room_number:
        payload["RoomNumber"] = room_number

    # Optional customer fields: flatten as Customer[Key]=value but only if non-empty
    if customer:
        for key, value in customer.items():
            if value is None:
                continue
            s = str(value).strip()
            if s != "":
                payload[f"Customer[{key}]"] = s

    response = call_api("BookingWithStripeToken", payload)

    booking_ref = response.get("booking_reference")
    if booking_ref:
        return f"Reservation confirmed! Your reference is {booking_ref}."
    else:
        raise ToolError("Failed to book reservation.")
    

def check_reservation(booking_reference: str) -> str:
    """Tool: Check details of an existing reservation."""
    if not booking_reference:
        raise ToolError("Booking reference is required.")

    response = call_api_get("Booking", {"booking_reference": booking_reference}, check_reservation.__name__)

    print(response)
    return response

from datetime import datetime
from typing import Optional

class ToolError(Exception):
    pass

def _normalize_time(time_str: str) -> str:
    parts = time_str.split(":")
    if len(parts) == 2:           # HH:MM -> HH:MM:00
        return f"{time_str}:00"
    if len(parts) == 3:
        return time_str
    raise ToolError("VisitTime must be HH:MM or HH:MM:SS.")

def _validate_date(date_str: str) -> None:
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        raise ToolError("VisitDate must be in YYYY-MM-DD format.")

def _validate_time(time_str: str) -> None:
    try:
        datetime.strptime(time_str, "%H:%M:%S")
    except ValueError:
        raise ToolError("VisitTime must be in HH:MM:SS format.")

def _bool_to_str(value: bool) -> str:
    return "true" if value else "false"

def modify_reservation(
    booking_reference: str,
    VisitDate: Optional[str] = None,
    VisitTime: Optional[str] = None,
    PartySize: Optional[int] = None,
    SpecialRequests: Optional[str] = None,
    IsLeaveTimeConfirmed: Optional[bool] = None,
) -> str:
    """Tool: Modify an existing reservation."""
    if not booking_reference:
        raise ToolError("Booking reference is required to modify a reservation.")

    payload = {"booking_reference": booking_reference}

    # Include only provided fields (with validation/normalization)
    if VisitDate:
        _validate_date(VisitDate)
        payload["VisitDate"] = VisitDate

    if VisitTime:
        VisitTime = _normalize_time(VisitTime)
        _validate_time(VisitTime)
        payload["VisitTime"] = VisitTime

    if PartySize is not None:
        if isinstance(PartySize, bool) or int(PartySize) <= 0:
            raise ToolError("PartySize must be a positive integer.")
        payload["PartySize"] = str(int(PartySize))

    if SpecialRequests:
        payload["SpecialRequests"] = SpecialRequests

    if IsLeaveTimeConfirmed is not None:
        payload["IsLeaveTimeConfirmed"] = _bool_to_str(IsLeaveTimeConfirmed)

    print(f"payload: {payload}")

    if len(payload) == 1:
        raise ToolError("No changes provided. Include at least one field to modify.")

    # Call your API (keep your existing endpoint name)
    response = call_api_get("Booking", payload, modify_reservation.__name__)

    print(f"response: {response}")

    return str(response)


def cancel_reservation(booking_reference: str) -> str:
    """Tool: Cancel an existing reservation."""
    if not booking_reference:
        raise ToolError("Booking reference is required for cancellation.")
    payload = {"micrositeName": RESTAURANT_NAME, "booking_reference": booking_reference, "bookingReference": booking_reference, "cancellationReasonId": 1}
    response = call_api_get("Booking", payload, "")

    return str(response)
