import requests
import json
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_webflow_site():
    token = os.getenv('WEBFLOW_TOKEN')
    site_id = "64e7c16bddef7563aa632f3d"
    
    print(f"Using token: {token[:10]}...")
    print(f"Testing for site ID: {site_id}")
    
    headers = {
        "accept": "application/json",
        "authorization": f"Bearer {token}",
        "Webflow-Version": "2.0.0"  # Specify v2 API
    }
    
    try:
        # Test simple site info first
        print("\nTesting basic site access...")
        test_url = f"https://api.webflow.com/v2/site/{site_id}"  # Note: 'site' not 'sites'
        response = requests.get(test_url, headers=headers)
        
        print(f"URL: {test_url}")
        print(f"Full Headers: {headers}")
        print(f"Status Code: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        
    except Exception as e:
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    test_webflow_site()