import requests
import os
from dotenv import load_dotenv

load_dotenv()

token = os.getenv('WEBFLOW_TOKEN')
site_id = "64e7c16bddef7563aa632f3d"

print(f"Testing with token: {token}")

headers = {
    "accept": "application/json",
    "authorization": f"Bearer {token}"
}

response = requests.get(
    f"https://api.webflow.com/site/{site_id}",
    headers=headers
)

print(f"Status: {response.status_code}")
print(f"Response: {response.text}")