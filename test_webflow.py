import requests
import json
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_webflow_connection():
    token = os.getenv('WEBFLOW_TOKEN')
    
    # Print token for verification
    print(f"Using token: {token[:10]}...")
    
    # Set up headers
    headers = {
        "accept": "application/json",
        "authorization": f"Bearer {token}"
    }
    
    print("\nTesting connection to Webflow API...")
    
    try:
        # Get sites list
        response = requests.get(
            "https://api.webflow.com/sites",
            headers=headers
        )
        
        print(f"\nStatus Code: {response.status_code}")
        print(f"Response Headers: {json.dumps(dict(response.headers), indent=2)}")
        print(f"Response Body: {json.dumps(response.json(), indent=2)}")
        
    except Exception as e:
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    test_webflow_connection()