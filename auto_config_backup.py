from xmlrpc.client import ResponseError
from ruxit.api.base_plugin import RemoteBasePlugin
from datetime import datetime, timedelta
from math import floor
from time import sleep
import requests
import logging
import base64
import json

logger = logging.getLogger(__name__)

class AutoConfigBackup(RemoteBasePlugin):
    def initialize(self, **kwargs):
        '''
        Required Plugin Function for ActiveGate. Executed on First Run
        '''
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

  
    def get_config_changes(self):
        '''
        Looks for Config Changes and Updates GitHub if supported by Objects API
        '''

        settings_gen_endpoint = "/api/v2/settings/objects"
        audit_logs = self.get_audit_logs()
        for x in range(len(audit_logs)):
            user = str(audit_logs[x]['user'])
            timestamp = int(audit_logs[x]['timestamp'])
            try:
                entityId = str(audit_logs[x]['entityId']).split(sep="(",maxsplit=1)[1].split(sep=")",maxsplit=1)[0]
                entityType = str(audit_logs[x]['entityId']).split(maxsplit=1)[0]
            except IndexError:
                logger.error (f"FAILED TO PARSE ENTITY: {str(audit_logs[x]['entityId'])}")
                continue
            logging.info(f"AUDIT - CHANGES FOUND BETWEEN {self.start_time} & {self.end_time} = {len(audit_logs)}")
            params = {
                "schemaIds": entityType,
                "scopes": entityId,
            }
            setting_object_payload = self.make_dt_api_request("GET", settings_gen_endpoint, params=params)
            
    def query(self, **kwargs):
        '''
        Routine call from the ActiveGate
        '''
        self.end_time = floor(datetime.now().timestamp()*1000)
        if self.end_time - self.start_time >= self.polling_interval:
            audit_logs = self.get_audit_logs()
            logging.info(audit_logs)
            if len(audit_logs) == 0:
                logging.info("No Changes In Time")
            else:
                logger.info("Found Audit Changes %d",len(audit_logs))
                self.get_config_changes()
            self.start_time = self.end_time + 1
