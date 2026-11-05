"""Create initial room membership for an existing Auth user using server env only."""
import argparse
import os
from uuid import uuid4
import httpx

parser = argparse.ArgumentParser()
parser.add_argument("--email", required=True)
parser.add_argument("--room", default="Phòng thi demo")
args = parser.parse_args()
url = os.environ["EXAMWATCH_SUPABASE_URL"].rstrip("/")
key = os.environ["EXAMWATCH_SUPABASE_KEY"]
headers = {"apikey": key, "Authorization": "Bearer " + key}
with httpx.Client(timeout=30, headers=headers) as client:
    page, match = 1, None
    while True:
        response = client.get(url + "/auth/v1/admin/users", params={"page": page, "per_page": 100})
        response.raise_for_status()
        users = response.json()["users"]
        match = next((user for user in users if user.get("email", "").casefold() == args.email.casefold()), None)
        if match or len(users) < 100:
            break
        page += 1
    if not match:
        raise SystemExit("Create this account in Supabase Auth Dashboard first")
    room_id = str(uuid4())
    response = client.post(url + "/rest/v1/rooms", json={"id": room_id, "name": args.room})
    response.raise_for_status()
    response = client.post(url + "/rest/v1/room_members", json={"room_id": room_id, "user_id": match["id"], "role": "admin"})
    response.raise_for_status()
    print("Room and admin membership created. room_id=" + room_id)
