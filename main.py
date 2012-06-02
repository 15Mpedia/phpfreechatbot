import ConfigParser
from datetime import datetime
import htmlentitydefs
import re
import sched
import smtplib
from email.mime.text import MIMEText
import traceback
import time
import ast

import requests

__author__ = 'cseebach'

def unescape(text):
    def fixup(m):
        text = m.group(0)
        if text[:2] == "&#":
            # character reference
            try:
                if text[:3] == "&#x":
                    return unichr(int(text[3:-1], 16))
                else:
                    return unichr(int(text[2:-1]))
            except ValueError:
                pass
        else:
            # named entity
            try:
                text = unichr(htmlentitydefs.name2codepoint[text[1:-1]])
            except KeyError:
                pass
        return text # leave as is
    return re.sub("&#?\w+;", fixup, text)

class PFCClientError(Exception):
    pass

class PFCClient(sched.scheduler):
    """
    A basic client class that connects to PHP Free Chat and can recieve and
    send messages
    """

    new_msgs_re = re.compile(r"pfc.handleResponse\('getnewmsg', 'ok', (.*)\);")
    all_fields_responders = {}
    content_responders = {}

    @classmethod
    def all_fields_responder(cls, responder):
        """
        A decorator for responders that need access to all the attributes of
        the message recieved.
        """
        cls.all_fields_responders[responder.__name__] = responder
        return responder

    @classmethod
    def content_responder(cls, responder):
        """
        A decorator for responders that need only the message content.
        """
        cls.content_responders[responder.__name__] = responder
        return responder

    def __init__(self):
        sched.scheduler.__init__(self, time.time, time.sleep)

    def connect(self, chat_url, name):
        """
        Establish a connection to the PHP Free Chat running at the specified URL.
        Connect with the given name.
        """

        self.chat_url = chat_url
        r = requests.get(chat_url)
        if not r:
            raise PFCClientError, "could not get a response at {0}".format(chat_url)

        self.cookies = r.cookies
        if "PHPSESSID" not in self.cookies:
            raise PFCClientError, "was not assigned a PHP session ID"

        client_id = re.search(r'var pfc_clientid\s*?= "(\w*)";', r.text)
        if not client_id:
            raise PFCClientError, "could not obtain a client ID"
        self.client_id = client_id.group(1)

        load_chat_params = {"f":"loadChat", "pfc_ajax":1}
        load_chat = requests.get(chat_url, params=load_chat_params,
                                 cookies=self.cookies)

        data = {"pfc_ajax":1, "f":"handleRequest", "_":"",
                "cmd":'/connect {0} 0 "{1}"'.format(self.client_id, name)}
        try:
            room_request = requests.post(chat_url, data=data, cookies=self.cookies)
            self.room_id = re.search(r"'join', 'ok', Array\('([a-z0-9]*)", room_request.text).group(1)
        except AttributeError:
            raise PFCClientError, "could not get a room ID"

    def schedule_update(self):
        """
        Schedule an update.
        """
        self.enter(3, 0, self.update, [])

    def update(self):
        """
        Update the bot and schedule another update.
        """
        self.schedule_update()

        try:
            update_data = {"pfc_ajax":1, "f":"handleRequest", "_":"",
                           "cmd":'/update {0} {1}'.format(self.client_id, self.room_id)}
            update_request = requests.post(self.chat_url, data=update_data,
                                           cookies=self.cookies)
            self.update_received(update_request.text)
        except requests.RequestException:
            print "Exception while updating from the server."
            traceback.print_exc()
            pass #we'll try again on the next update

    def update_received(self, update_content):
        """
        Called when an update has been recieved from the server.
        """
        for line in update_content.splitlines():
            new_msgs = re.match(self.new_msgs_re, line)
            if new_msgs:
                for new_msg in ast.literal_eval(new_msgs.group(1)):
                    new_msg[-3] = unescape(new_msg[-3])
                    self.message_received(*new_msg[:-2])

    def message_received(self, msg_number, msg_date, msg_time, msg_sender,
                         msg_room, msg_type, msg_content):
        """
        Called when a message has been recieved from the server.
        """
        try:
            if msg_content.startswith("!"):
                command = msg_content[1:].split()[0]
                if command in self.all_fields_responders:
                    responder = self.all_fields_responders[command]
                    responder(self, msg_number, msg_date, msg_time, msg_sender,
                              msg_room, msg_type, msg_content)
                if command in self.content_responders:
                    responder = self.content_responders[command]
                    responder(self, msg_content)
        except:
            print "Exception while responding to a message."
            traceback.print_exc()

    def send(self, msg):
        """
        Send a message to the server.
        """
        try:
            send_data = {"pfc_ajax":1, "f":"handleRequest", "_":"",
                         "cmd":"/send {0} {1} {2}".format(self.client_id, self.room_id, msg)}
            send_request = requests.post(self.chat_url, data=send_data,
                                         cookies=self.cookies)
            self.update_received(send_request.text)
        except requests.RequestException:
            print "Exception while trying to send a message."
            traceback.print_exc()
            self.enter(1, 0, self.send, [msg])

class Log(list):
    """
    A simple list subclass which also keeps track of a date and a subject.
    """

    def __init__(self, seq=(), date=datetime.utcnow()):
        super(Log, self).__init__(seq)
        self.date = date
        self.subject = "Chat Log"

class BeerLoggerBot(PFCClient):
    """
    An extension of PFCClient that offers the following commands:

    !sendLog [number] email [subject]
        stops collecting the top log on the stack and sends it to the given email
        optionally, sends a log at a different position in the stack
        note: logs start when this bot logs in, and do not reach backwards into
        the cache

    !viewLogs
        view all the logs in the stack with their numbers and subjects

    !clearLog number
        remove the log with the specified number from the log stack

    !gimmeBeer [kind]
        give the person who sends this command a beer of the specified kind
    """

    def __init__(self, config):
        PFCClient.__init__(self)
        self.config = config
        self.logs = [Log()]

    def start(self):
        """
        Shorthand for the series of commands you'd normally use to start a
        PFCClient
        """
        self.connect(self.config.get("chat", "chat_url"),
                     self.config.get("chat", "name"))
        self.schedule_update()
        self.run()

    @PFCClient.all_fields_responder
    def gimmeBeer(self, msg_number, msg_date, msg_time, msg_sender, msg_room,
                  msg_type, msg_content):
        """
        The !gimmeBeer command.
        """
        splits = msg_content.split()
        if len(splits) == 1:
            self.send("Here's a beer for ya, {0}!".format(msg_sender))
        elif len(splits) > 1:
            if splits[1][0] in "AEIOUaeiou":
                msg = "Here's an {0} for ya, {1}!"
            else:
                msg = "Here's a {0} for ya, {1}!"
            self.send(msg.format(" ".join(splits[1:]), msg_sender))

    @PFCClient.all_fields_responder
    def gimme(self, msg_number, msg_date, msg_time, msg_sender, msg_room,
              msg_type, msg_content):
        """
        The !gimme command.
        """
        splits = msg_content.split()
        if len(splits) == 1:
            self.send("Here's a cool thingy for ya, {0}!".format(msg_sender))
        elif len(splits) == 2:
            thing = msg_content[len("!gimme "):]
            if thing[0] in "AEIOUaeiou":
                msg = "Here's an {0} for ya, {1}!"
            else:
                msg = "Here's a {0} for ya, {1}!"
            self.send(msg.format(" ".join(splits[1:]), msg_sender))
        else:
            thing = msg_content[len("!gimme "):]
            self.send("Here's {0} for ya, {1}!".format(thing, msg_sender))

    """
    def make_log_email(self, log_num, subject, to):
        """
        Create a log email message from the given log.
        """
        full_log = "\r\n".join("{0} <{1}> {2}".format(*msg[1:]) for msg in self.logs[log_num])
        msg = MIMEText(full_log)
        msg["Subject"] = "Chat Log: " + subject
        msg["From"] = self.config.get("email", "fromaddr")
        msg["To"] = to

        return msg

    @PFCClient.content_responder
    def sendLog(self, msg_content):
        """
        The !sendLog command
        """
        splits = msg_content.split()
        #arguments must be the command itself and an address, at least
        if len(splits) <=2:
            return

        subject = None
        log_num = 0
        #test if format is !sendLog log_num email
        try:
            log_num = int(splits[1])
            to_addr = splits[2]
        except ValueError:
            #format must be !sendLog email or !sendLog email subject
            to_addr = splits[1]
            if len(splits) > 2:
                subject = " ".join(splits[2:])
        log_num -= 1

        # if subject is specified, change the subject of the log
        # otherwise, use the subject from the log
        if subject:
            self.logs[log_num].subject = subject
        else:
            subject = self.logs[log_num].subject
        message = self.make_log_email(log_num, subject, to_addr).as_string()

        #email sending machinery
        server = smtplib.SMTP(self.config.get("email", "server"))
        server.starttls()
        server.login(self.config.get("email", "username"),
                     self.config.get("email", "password"))
        try:
            server.sendmail(self.config.get("email", "fromaddr"),
                            to_addr, message)
            self.send("Log emailed to "+to_addr)
            if log_num == -1:
                self.logs.append(Log())
        except smtplib.SMTPException:
            self.send("Couldn't send to that email address, sorry.")

    @PFCClient.content_responder
    def viewLogs(self, msg):
        """
        The !viewLogs command.
        """
        for i, log in enumerate(reversed(self.logs)):
            self.send("Log {}: {}".format(-i, log.subject))

    @PFCClient.content_responder
    def clearLog(self, msg_content):
        """
        The !clearLog command.
        """
        splits = msg_content.split()
        if len(splits) < 2:
            return
        try:
            log_num = int(splits[1])
            del self.logs[log_num-1]
            self.send("Log {0} cleared.".format(log_num))
        except ValueError:
            self.send("That's not a valid number. :P")
        except IndexError:
            self.send("No log with that number exists.")
    """

    def message_received(self, msg_number, msg_date, msg_time, msg_sender,
                         msg_room, msg_type, msg_content):
        """
        Need to override this method in order to properly log incoming
        messages.
        """
        self.logs[-1].append([msg_date, msg_time, msg_sender, msg_content])
        PFCClient.message_received(self, msg_number, msg_date, msg_time,
                                   msg_sender, msg_room, msg_type, msg_content)

config = ConfigParser.ConfigParser()
config.read("robot.cfg")

bot = BeerLoggerBot(config)
bot.start()
