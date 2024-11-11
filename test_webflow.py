import requests
import json
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_webflow_site():
    token = os.getenv('WEBFLOW_TOKEN')
    site_id = "64e7c16bddef7563aa632f3d"  # Your site ID
    
    # Print token for verification
    print(f"Using token: {token[:10]}...")
    print(f"Testing for site ID: {site_id}")
    
    # Set up headers
    headers = {
        "accept": "application/json",
        "authorization": f"Bearer {token}"
    }
    
    print("\nTesting connection to Webflow API...")
    
    try:
        # Get site info
        print("\nGetting site info...")
        site_response = requests.get(
            f"https://api.webflow.com/sites/{site_id}",
            headers=headers
        )
        print(f"Site Info Status: {site_response.status_code}")
        print(f"Site Info Response: {json.dumps(site_response.json(), indent=2)}")
        
        # Get site domains
        print("\nGetting site domains...")
        domains_response = requests.get(
            f"https://api.webflow.com/sites/{site_id}/domains",
            headers=headers
        )
        print(f"Domains Status: {domains_response.status_code}")
        print(f"Domains Response: {json.dumps(domains_response.json(), indent=2)}")
        
        # Test publish endpoint
        print("\nTesting publish endpoint...")
        publish_response = requests.get(
            f"https://api.webflow.com/sites/{site_id}/publish",
            headers=headers
        )
        print(f"Publish Status: {publish_response.status_code}")
        print(f"Publish Response: {json.dumps(publish_response.json(), indent=2)}")
        
    except Exception as e:
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    test_webflow_site()