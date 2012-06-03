import ConfigParser
import re
import sched
import smtplib
from email.mime.text import MIMEText
import sqlite3
import traceback
import time
from datetime import datetime
import ast

import requests
from dateutil.parser import parse as timeparse
import lxml.html

__author__ = 'cseebach'

def unescape(text):
    return lxml.html.fromstring(text).text_content()

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


def is_email(string):
    return re.match(r"^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,4}$", string)


class BeerLoggerBot(PFCClient):
    """
    An extension of PFCClient that offers the following commands:

    !gimmeBeer [kind]
        give the person who sends this command a beer of the specified kind

    !gimme [thing]
        give the person who sends this command the given thing
    """

    def __init__(self, config):
        """
        Create a new BeerLoggerBot.
        """
        PFCClient.__init__(self)
        self.config = config
        self.log = sqlite3.connect("log.db")
        self.log_marks = {}
        self.create_log_tables()

    def create_log_tables(self):
        self.log.executescript("""
        CREATE TABLE IF NOT EXISTS log (date float, sender text, content text);
        CREATE INDEX IF NOT EXISTS log_time ON log (date ASC);

        CREATE TABLE IF NOT EXISTS marks (name text PRIMARY KEY, start float, end float);
        """)

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

    @PFCClient.content_responder
    def markLog(self, msg_content):
        splits = msg_content.split()

        if len(splits) >= 3:
            max_time_row = self.log.execute("SELECT MAX(date) FROM log;").fetchone()
            if not max_time_row:
                self.send("Nothing logged. Cannot mark.")
                return
            default = datetime.fromtimestamp(max_time_row[0])

            try:
                start_time = time.mktime(timeparse(splits[1], default=default).timetuple())
            except ValueError:
                self.send("Incorrect date format. Cannot mark.")
                return
            try:
                end_time = time.mktime(timeparse(splits[2], default=default).timetuple())
                subject = " ".join(splits[3:])
                self.set_mark(subject, start_time, end_time)
            except ValueError:
                #the end time we tried to parse was actually part of the subject
                end_time = max_time_row[0]
                subject = " ".join(splits[2:])
                self.set_mark(subject, start_time, end_time)
            except IndexError:
                #the subject we tried to get doesn't actually exist
                self.send("No subject specified. Cannot mark.")
        else:
            #give usage help
            self.send("usage: !markLog start_time [end_time] subject")
            self.send("end time defaults to last logged message")
            self.send("specify time like this: DD-MM-YYYY_HH:MM:SS")
            self.send("date defaults to date of last logged message")

    def set_mark(self, subject, start_time, end_time):
        """
        Store a mark in the database.
        """
        self.log.execute("INSERT OR REPLACE INTO marks values (?,?,?)", (subject, start_time, end_time))
        self.log.commit()
        self.send("Mark %s set." % subject)

    @PFCClient.content_responder
    def sendLog(self, msg_content):
        splits = msg_content.split()

        if len(splits) == 2:
            subject = splits[1]
            email = self.config.get("mailing_list", "address")
            if self.mark_exists(subject):
                self.send_log_email(subject, email)
            else:
                self.send("No mark by that name.")
        elif len(splits) >= 3:
            if is_email(splits[-1]):
                email = splits[-1]
                subject = " ".join(splits[1:-1])
            else:
                email = self.config.get("mailing_list", "address")
                subject = " ".join(splits[1:])
            if self.mark_exists(subject):
                self.send_log_email(subject, email)
            else:
                self.send("No mark by that name.")
        else:
            #give usage help
            self.send("usage: !sendLog subject [email]")
            self.send("email defaults to configured mailing list address")

    def mark_exists(self, subject):
        results = self.log.execute("SELECT * FROM marks WHERE name='%s'" % subject)
        return results.fetchone()

    def make_log_email(self, text, subject, to):
        """
        Create a log email message from the given log text.
        """
        msg = MIMEText(text)
        msg["Subject"] = "Chat Log: " + subject
        msg["From"] = self.config.get("email", "fromaddr")
        msg["To"] = to

        return msg

    def send_log_email(self, subject, to_addr):
        mark = self.log.execute("SELECT * FROM marks WHERE name='%s'" % subject).fetchone()

        messages = []
        for row in self.log.execute("SELECT * FROM log WHERE date >= %f AND date <= %f" % (mark[1], mark[2])):
            messages.append("<{0}> {1}".format(row[1], row[2]))

        log_email = self.make_log_email("\n".join(messages), subject, to_addr)

        #email sending machinery
        server = smtplib.SMTP(self.config.get("email", "server"))
        server.starttls()
        server.login(self.config.get("email", "username"),
                     self.config.get("email", "password"))
        try:
            server.sendmail(self.config.get("email", "fromaddr"), to_addr, log_email.as_string())
            self.send("Log emailed to "+to_addr)
        except smtplib.SMTPException:
            self.send("Couldn't send to that email address, sorry.")

    def message_received(self, msg_number, msg_date, msg_time, msg_sender,
                         msg_room, msg_type, msg_content):
        """
        Need to override this method in order to properly log incoming
        messages.
        """
        self.log_message(msg_date, msg_time, msg_sender, msg_content)
        PFCClient.message_received(self, msg_number, msg_date, msg_time,
                                   msg_sender, msg_room, msg_type, msg_content)

    def log_message(self, msg_date, msg_time, msg_sender, msg_content):
        """
        Put this message in a log.
        """
        parsed_time = datetime.strptime(msg_date+" "+msg_time, "%d\\/%m\\/%Y %H:%M:%S")
        timestamp = time.mktime(parsed_time.timetuple())
        self.log.execute("INSERT INTO log VALUES (?,?,?)", (timestamp, msg_sender, msg_content))
        self.log.commit()




config = ConfigParser.ConfigParser()
config.read("robot.cfg")

bot = BeerLoggerBot(config)
bot.start()
