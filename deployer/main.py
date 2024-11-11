import os
import requests
import zipfile
import json
from datetime import datetime, timedelta
import shutil
import logging
from flask import Flask, request, jsonify
from threading import Thread, Lock
from dotenv import load_dotenv
import time

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

class WebflowPorkbunDeployer:
    def __init__(self):
        self.webflow_token = os.getenv('WEBFLOW_TOKEN')
        self.porkbun_api_key = os.getenv('PORKBUN_API_KEY')
        self.porkbun_secret_key = os.getenv('PORKBUN_SECRET_KEY')
        self.deploy_domain = os.getenv('DEPLOY_DOMAIN')
        self.webflow_domain = 'maine-mountain-moccasin.webflow.io'
        self.webflow_api_url = "https://api.webflow.com"
        self.porkbun_api_url = "https://porkbun.com/api/json/v3"
        self.logger = logger
        self.last_publish_time = None
        self.publish_lock = Lock()
        self.current_deployments = set()

    def is_already_deploying(self, site_id):
        """Check if a deployment is already in progress for this site."""
        return site_id in self.current_deployments

    def can_publish(self):
        """Check if enough time has passed since last publish."""
        with self.publish_lock:
            if self.last_publish_time is None:
                return True
            elapsed = datetime.now() - self.last_publish_time
            return elapsed > timedelta(seconds=60)

    def update_publish_time(self):
        """Update the last publish time."""
        with self.publish_lock:
            self.last_publish_time = datetime.now()

    def trigger_publish(self, site_id):
        """Trigger a site publish in Webflow."""
        if not self.can_publish():
            wait_time = 60
            self.logger.info(f"Waiting {wait_time} seconds before publishing...")
            time.sleep(wait_time)

        headers = {
            "accept": "application/json",
            "authorization": f"Bearer {self.webflow_token}",
            "Content-Type": "application/json"
        }
        
        publish_data = {
            "domains": [self.webflow_domain]
        }
        
        response = requests.post(
            f"{self.webflow_api_url}/sites/{site_id}/publish",
            headers=headers,
            json=publish_data
        )
        
        if response.status_code == 429:  # Rate limit
            self.logger.info("Hit rate limit, waiting 60 seconds...")
            time.sleep(60)
            return self.trigger_publish(site_id)
        
        if response.status_code != 200:
            raise Exception(f"Failed to trigger publish: {response.text}")
        
        self.update_publish_time()
        return response.json()

    def download_site(self, site_id):
        """Download site files using wget."""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            extract_path = f"webflow_site_{timestamp}"

            site_url = f"https://{self.webflow_domain}"
            self.logger.info(f"Downloading site from: {site_url}")
            
            os.system(f'wget -r -k -l inf -p -N -E -H -P {extract_path} {site_url}')
            
            return extract_path
        except Exception as e:
            raise Exception(f"Failed to download site: {str(e)}")

    def upload_to_porkbun(self, site_path, max_retries=3, retry_delay=5):
        """Upload files to Porkbun hosting with retry logic."""
        files = []
        attempt = 0
        
        try:
            self.logger.info("Preparing files for upload...")
            
            valid_extensions = ('.html', '.css', '.js', '.jpg', '.jpeg', '.png', '.gif', '.svg', '.ico')
            
            for root, dirs, filenames in os.walk(site_path):
                for filename in filenames:
                    if filename.lower().endswith(valid_extensions):
                        file_path = os.path.join(root, filename)
                        relative_path = os.path.relpath(file_path, site_path)
                        
                        if '/maine-mountain-moccasin.webflow.io/' in relative_path:
                            relative_path = relative_path.split('/maine-mountain-moccasin.webflow.io/')[-1]
                        
                        if not relative_path.startswith('/'):
                            relative_path = '/' + relative_path
                        
                        self.logger.info(f"Adding file: {relative_path}")
                        files.append((relative_path, file_path))

            endpoints = [
                f"{self.porkbun_api_url}/domain/uploadFiles/{self.deploy_domain}",
                f"https://porkbun.com/api/json/v3/hosting/uploadFiles/{self.deploy_domain}",
                f"https://api.porkbun.com/api/json/v3/hosting/uploadFiles/{self.deploy_domain}"
            ]

            while attempt < max_retries:
                attempt += 1
                self.logger.info(f"Upload attempt {attempt} of {max_retries}")
                
                for endpoint in endpoints:
                    try:
                        self.logger.info(f"Trying endpoint: {endpoint}")
                        
                        upload_files = []
                        for relative_path, file_path in files:
                            upload_files.append(('files', (relative_path, open(file_path, 'rb'))))

                        data = {
                            'apikey': self.porkbun_api_key,
                            'secretapikey': self.porkbun_secret_key
                        }

                        response = requests.post(
                            endpoint,
                            data=data,
                            files=upload_files,
                            timeout=30
                        )

                        for _, file_tuple in upload_files:
                            file_tuple[1].close()

                        if response.status_code == 200:
                            self.logger.info(f"Successfully uploaded files to Porkbun at {endpoint}")
                            return response.json()
                        elif response.status_code == 503:
                            self.logger.warning(f"Service temporarily unavailable (503) from {endpoint}")
                            continue
                        else:
                            self.logger.warning(f"Upload failed with status {response.status_code} from {endpoint}")
                            self.logger.warning(f"Response: {response.text}")
                            continue

                    except Exception as e:
                        self.logger.warning(f"Error during upload to {endpoint}: {str(e)}")
                        continue
                    finally:
                        for _, file_tuple in upload_files:
                            try:
                                file_tuple[1].close()
                            except:
                                pass

                if attempt < max_retries:
                    self.logger.info(f"All endpoints failed, waiting {retry_delay} seconds before retry...")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff

            raise Exception("Failed to upload to Porkbun after all retries")

        except Exception as e:
            self.logger.error(f"Upload failed: {str(e)}")
            raise

    def handle_webhook(self, site_id):
        if self.is_already_deploying(site_id):
            self.logger.info(f"Deployment already in progress for site {site_id}")
            return False

        try:
            self.current_deployments.add(site_id)
            self.logger.info(f"Starting deployment for site {site_id}")
            
            self.logger.info("Triggering publish...")
            self.trigger_publish(site_id)
            
            self.logger.info("Waiting for publish to complete...")
            time.sleep(15)
            
            self.logger.info("Getting site files...")
            site_path = self.download_site(site_id)
            self.logger.info(f"Downloaded site to {site_path}")
            
            self.logger.info("Uploading to Porkbun...")
            result = self.upload_to_porkbun(site_path)
            self.logger.info("Upload to Porkbun complete")
            
            shutil.rmtree(site_path)
            return True
        except Exception as e:
            self.logger.error(f"Deployment failed: {str(e)}")
            return False
        finally:
            self.current_deployments.remove(site_id)

deployer = WebflowPorkbunDeployer()

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        logger.info("Received webhook request")
        data = request.get_json(silent=True)
        logger.info(f"Webhook data: {data}")
        
        if data is None:
            logger.error("No JSON data received")
            return jsonify({'error': 'No JSON data received'}), 400

        site_id = data.get('payload', {}).get('siteId')
            
        if not site_id:
            logger.error("No site ID found in webhook data")
            return jsonify({'error': 'No site ID provided'}), 400

        if deployer.is_already_deploying(site_id):
            logger.info(f"Deployment already in progress for site {site_id}")
            return jsonify({'message': 'Deployment already in progress'}), 200

        logger.info(f"Processing webhook for site ID: {site_id}")
        Thread(target=deployer.handle_webhook, args=(site_id,)).start()
        return jsonify({'message': 'Deployment started'}), 200
    
    except Exception as e:
        logger.error(f"Error processing