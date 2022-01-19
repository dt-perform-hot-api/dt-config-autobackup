from ruxit.api.base_plugin import RemoteBasePlugin
from datetime import datetime, timedelta
from math import floor
from time import sleep
import requests
import logging
import base64
import json
import hashlib

logger = logging.getLogger(__name__)

class AutoConfigBackup(RemoteBasePlugin):
    def initialize(self, **kwargs):
        logger.info("Config: %s", self.config)
        config = kwargs['config']
        
        self.url = config['url'].strip()
        if self.url[-1] == '/':
            self.url = self.url[:-1]

        self.headers = {
            'Authorization': 'Api-Token ' + config['api_token'].strip(),
        }

        self.polling_interval = int(config['polling_interval']) * 60 * 1000

        self.start_time = floor(datetime.now().timestamp()*1000) - self.polling_interval
        self.verify_ssl = config['verify_ssl']
        if not self.verify_ssl:
            requests.packages.urllib3.disable_warnings()

        self.git_url = config['git_url']
        self.git_user = config['git_user']
        self.git_token = config['git_token']

    def make_dt_api_request(self, http_method, endpoint, json_payload=None, params=None):
        '''
        Make API calls with proper error handling

        @param endpoint - endpoint for Dynatrace API call
        @param json_payload - dict payload to pass as JSON body

        @return response - response dictionary for valid API call
        '''
        while True:
            response = requests.request(http_method, f"{self.url}{endpoint}", json=json_payload, headers=self.headers, verify=self.verify_ssl, params=params)
            if response.status_code == 429:
                logging.info("AUDIT - RATE LIMITED! SLEEPING...")
                sleep(response.headers['X-RateLimit-Reset']/1000000)
            else:
                break
        return response.json()

    def get_audit_logs(self):
        '''
        Retrieve API logs from the tenant

        @return audit_logs - List of changes recorded from the audit API
        '''
        audit_log_endpoint = f"/api/v2/auditlogs?filter=eventType(CREATE,UPDATE)&from={self.start_time}&to={self.end_time}&sort=timestamp"
        changes = self.make_dt_api_request("GET", audit_log_endpoint)
        return changes['auditLogs']
    
    def get_previous_sha_git(self, file_path):
        pass

    def push_to_git(self, entityId, entityType, config_json, user, timestamp):
        sanitized_entityType = entityType.replace(":","_")
        config_encoded = json.dumps(config_json, indent=2).encode()
        config_base64 = base64.b64encode(config_encoded)
        config_sha = hashlib.sha1(config_encoded)
        file_path = f"/contents/{entityId}/{sanitized_entityType}.json"
        git_headers = {
            "Accept": "application/vnd.github.v3+json",
        }
        logger.info (f"{self.git_url}{file_path}")
        git_body = {
            "message": f"{user} {timestamp}"[:40],
            "sha": f"{config_sha.hexdigest()}",
            "committer": {
                "name": "Aaron Philipose",
                "email": "aaronphilipose@gmail.com"
            },
            "content": f"{config_base64}"[2:-1]
        }
        logger.info ("Git Body Start")
        logger.info (json.dumps(git_body, indent=2))
        logger.info ("Git Body Stop")
        response = requests.request("PUT", f"{self.git_url}{file_path}", headers=git_headers, json=git_body, auth=(self.git_user, self.git_token))
        logger.info (response.url)
        logger.info (response.json())
        logger.info (response.status_code)

    def get_config_changes(self):

        settings_gen_endpoint = "/api/v2/settings/objects"
        audit_logs = self.get_audit_logs()
        for x in range(len(audit_logs)):
            user = str(audit_logs[x]['user'])
            category = str(audit_logs[x]['category'])
            timestamp = int(audit_logs[x]['timestamp'])
            entityId = str(audit_logs[x]['entityId']).split(sep="(",maxsplit=1)[1].split(sep=")",maxsplit=1)[0]
            entityType = str(audit_logs[x]['entityId']).split(maxsplit=1)[0]
            patch = str(audit_logs[x]['patch'])
            logging.info(f"User: {user}\nCategory: {category}\nTimestamp: {timestamp}\n{entityId}\n{entityType}\n{patch}")
            logging.info(f"AUDIT - CHANGES FOUND BETWEEN {self.start_time} & {self.end_time} = {len(audit_logs)}")
            params = {
                "schemaIds": entityType,
                "scopes": entityId,
            }
            setting_object_payload = self.make_dt_api_request("GET", settings_gen_endpoint, params=params)
            logging.info(f"Settings: {setting_object_payload}")
            self.push_to_git(entityId, entityType, setting_object_payload, user, timestamp)

    def query(self, **kwargs):
        '''
        Routine call from the ActiveGate
        '''
        self.end_time = floor(datetime.now().timestamp()*1000)
        if self.end_time - self.start_time >= self.polling_interval:
            audit_logs = self.get_audit_logs()
            logging.info(audit_logs)
            if len(audit_logs) == 0:
                logging.info("Logs Has Info")
            self.get_config_changes()
            self.start_time = self.end_time + 1
