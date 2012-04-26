from client import PFCClient

__author__ = 'cseebach'

class HarmonicaRobot(PFCClient):

    @PFCClient.content_responder
    def gimmeBeer(self, msg):
        self.send("Here's a beer for ya!")

#now = datetime.utcnow().strftime("%Y_%m_%d_%H;%M;%S")
chat_url = "http://kiberion.net/chat/index.php"

bot = HarmonicaRobot()
bot.connect(chat_url, "Harmonica Robot")
bot.schedule_update()
bot.run()