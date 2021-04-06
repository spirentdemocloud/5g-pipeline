#!/usr/bin/python3 -u

from http.server import HTTPServer, BaseHTTPRequestHandler
from io import BytesIO
import time
import json
import urllib.parse
import requests
import logging
import time
import sys
import argparse
from requests.auth import HTTPBasicAuth

parser = argparse.ArgumentParser()
parser.add_argument('--runListPath', action='store', dest='runListPath', help='velocity runlist path')
results, unknown = parser.parse_known_args()

# create logger and set debugging level
logger = logging.getLogger()
logger.setLevel(logging.WARNING)
#logger.setLevel(logging.DEBUG)
# create console handler and set level
ch = logging.StreamHandler()
# create formatter
formatter = logging.Formatter("%(asctime)s %(levelname)-8s %(message)s")
# add formatter to ch
ch.setFormatter(formatter)
# add ch to logger
logger.addHandler(ch)


class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'Hello, world!')

    def do_POST(self):
        global eventType
        global runlistTerminated
        global runlistGuid
        global exitFail

        content_length = int(self.headers['Content-Length'])
        body = self.rfile.read(content_length)
        self.send_response(200)
        self.end_headers()
        response = BytesIO()
        response.write(b'Callback received')
        self.wfile.write(response.getvalue())
        dbody=json.loads(body.decode('utf-8'))
        if 'runlistGuid' in dbody.keys():
            if dbody['runlistGuid'] == runlistGuid:
                print(json.dumps(dbody,indent=4, sort_keys=True))
                eventType = dbody['eventType']
                if 'runlistTerminated' in dbody.keys():
                    runlistTerminated = dbody['runlistTerminated']

                if 'executionStatus' in dbody.keys():
                    if dbody['executionStatus'] != "PASS":
                        print('Test case failed, exiting...')
                        exitFail = True

baseUrl = 'https://ps-production-velocity.spirenteng.com'
headers={}
#runListPath = 'main%2F_runlists%2FDelete%20Me.vrl'
runListPath = results.runListPath

# get auth token
with open ("/home/velagent/.velagent/velagent1", "r") as velagent:
    data=velagent.read().strip()
    
tResponse = requests.get(baseUrl + '/velocity/api/auth/v2/token', auth=HTTPBasicAuth('apt_demo1', data))
token_data = json.loads(tResponse.text)
token = token_data['token']
headers['X-Auth-Token']=token

# start callback server
httpd = HTTPServer(('0.0.0.0', 0), SimpleHTTPRequestHandler)
eventType = ''
runlistTerminated = False
runlistGuid = ''
callbackPort = httpd.server_port
exitFail = False

# fetch and update runlist
tResponse = requests.get(baseUrl + '/ito/repository/v1/repository/' + runListPath, headers=headers)
r=json.loads(tResponse.text)
r['general']['detailLevel']='ALL_ISSUES_ALL_STEPS'
r['general']['callbackURL']='http://ub-build1-demos.spirenteng.com:' + str(callbackPort)

# message
print("Execution starting...")

# invoke runlist
headers['content-type']='application/json'
tResponse = requests.post(baseUrl + '/ito/executions/v1/runlists/' + runListPath,  data=json.dumps(r), headers=headers)
r=json.loads(tResponse.text)
if 'guid' in r.keys():
    runlistGuid = r['guid']

# wait for first execution to reach IN_PROGRESS
postData=[runlistGuid]
timeout = time.time() + 60*10  # 10 minutes from now
while True:
    rlResponse = requests.post(baseUrl + '/ito/executions/v1/runlists/summary', data=json.dumps(postData), headers=headers)
    r=json.loads(rlResponse.text)
    status = r[0]['status']
    if status not in ('NOT_BEGUN', 'IN_PROGRESS'):
        print('First test status is ' + status)
        sys.exit(1)
    elif time.time() > timeout:
        print('Timed out waiting for first execution to start')
        sys.exit(1)
    elif status == 'IN_PROGRESS':
        break
    else:
        print('Waiting for first test in runlist ' + runlistGuid + ' to start...')

    time.sleep(5)
       
# listen for an incoming webhook that indicates execution complete
timeout = time.time() + 60*30  # 30 minutes from now
while True:
    httpd.handle_request()
    if exitFail:
        sys.exit(1)
    if time.time() > timeout:
        print('Timed out waiting for runlist to complete')
        sys.exit(1)
    elif eventType == 'EXECUTION_COMPLETE' and runlistTerminated == True:
        print('\nRunlist complete!\n')
        break


print('Bye bye!')
