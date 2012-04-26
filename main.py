from datetime import datetime
from client import PFCClient

__author__ = 'cseebach'

class HarmonicaRobot(PFCClient):

    def __init__(self):
        PFCClient.__init__(self)
        self.log_date = datetime.utcnow()
        self.log = []

    @PFCClient.all_fields_responder
    def gimmeBeer(self, msg_number, msg_date, msg_time, msg_sender, msg_room,
                  msg_type, msg_content):
        splits = msg_content.split()
        if len(splits) == 1:
            self.send("Here's a beer for ya, {}!".format(msg_sender))
        elif len(splits) > 1:
            self.send("Here's a {} for ya, {}!".format(splits[1], msg_sender))

    @PFCClient.content_responder
    def endLog(self, msg_content):
        pass

    def message_received(self, msg_number, msg_date, msg_time, msg_sender,
                         msg_room, msg_type, msg_content):
        PFCClient.message_received(self, msg_number, msg_date, msg_time,
                                   msg_sender, msg_room, msg_type, msg_content)
        self.log.append([msg_number, msg_date, msg_time, msg_sender, msg_room,
                         msg_type, msg_content])


#now = datetime.utcnow().strftime("%Y_%m_%d_%H;%M;%S")
chat_url = "http://kiberion.net/chat/index.php"

bot = HarmonicaRobot()
bot.connect(chat_url, "Harmonica Robot")
bot.schedule_update()
bot.run()