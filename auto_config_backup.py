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
    def query(self, **kwargs):
        '''
        Routine call from the ActiveGate
        '''

