import csv
import re
import time
import ast
from datetime import datetime

import requests

__author__ = 'cseebach'

chat_url = "http://kiberion.net/chat/index.php"

#first we need to get our nickname, nick_id and client_id
ids_request = requests.get(chat_url)
ids = ids_request.text

nick = re.search(r'var pfc_nickname\s*?= "(\w*)";', ids).group(1)
nick_id = re.search(r'var pfc_nickid\s*?= "(\w*)";', ids).group(1)
client_id = re.search(r'var pfc_clientid\s*?= "(\w*)";', ids).group(1)

cookies = ids_request.cookies

#then, we "load the chat". may not be necessary for this bot
load_chat = requests.get(chat_url, params={"f":"loadChat", "pfc_ajax":1},
                         cookies=cookies)

#then, we do the first real request. this should return all previous cached
#messages, a list of rooms, and some other stuff
data = {"pfc_ajax":1, "f":"handleRequest", "_":"",
        "cmd":'/connect {} 0 "{}"'.format(client_id, "Harmonica Robot")}

first_request = requests.post(chat_url, data=data, cookies=cookies)
room_id = re.search(r"'join', 'ok', Array\('([a-z0-9]*)", first_request.text).group(1)

# after the first request, we go into a loop where we request all the new messages
# and log them as they arrive
update_data = {"pfc_ajax":1, "f":"handleRequest", "_":"",
               "cmd":'/update {} {}'.format(client_id, room_id)}
new_msgs_re = re.compile(r"pfc.handleResponse\('getnewmsg', 'ok', (.*)\);")

log_number = 0
while True:
    now = datetime.utcnow().strftime("%Y_%m_%d_%H;%M;%S")
    with open("log{}.csv".format(now), "w") as log_csv_file:
        log_csv = csv.writer(log_csv_file, lineterminator="\n")
        no_break = True
        while no_break:
            request = requests.post(chat_url, data=update_data, cookies=cookies)
            for line in request.text.splitlines():
                new_msgs = re.match(new_msgs_re, line)
                if new_msgs:
                    for new_msg in ast.literal_eval(new_msgs.group(1)):
                        log_csv.writerow(new_msg)
                        content = new_msg[6]
                        if content == "!newlog":
                            no_break = False
            time.sleep(4)
    log_number += 1
