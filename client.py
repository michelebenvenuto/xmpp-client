
import asyncio
from asyncio.tasks import sleep
import logging
from getpass import getpass
from ssl import SSL_ERROR_INVALID_ERROR_CODE
from aioconsole import ainput, aprint

import slixmpp
from slixmpp import jid
from slixmpp.exceptions import IqError, IqTimeout
from argparse import ArgumentParser

class UserClient(slixmpp.ClientXMPP):
    
    def __init__(self, jid, password):
        super().__init__(jid, password)

        self.add_event_handler("session_start", self.start)
        self.add_event_handler("change_status", self.wait_for_presences)
        self.add_event_handler("message", self.message)
        self.add_event_handler("groupchat_message",self.group_message)

        

        self.talking_to = None
        self.current_group = None

        self.nick = "Micks"

        self.received = set()
        self.presences_received = asyncio.Event()

    async def start(self,event):
        try:
            await self.get_roster()
        except IqError as err:
            print('Error: %s' %err.iq['error']['condition'])
        except IqTimeout:
            print('Error: Request timed out')
        self.send_presence()
        
        print('Geting your Roster...\n')
        await asyncio.sleep(10)

        await self.show_roster()
        
        await self.client_loop()
        self.disconnect()
    
    async def show_roster(self):
        groups = self.client_roster.groups()
        for group in groups:
            print('\n%s' % group)
            print('-' * 72)
            for jid in groups[group]:
                sub = self.client_roster[jid]['subscription']
                name = self.client_roster[jid]['name']
                if self.client_roster[jid]['name']:
                    print(' %s (%s) [%s]' % (name, jid))
                else:
                    print(' %s [%s]' % (jid, sub))

    def start_conv(self, jid):
        if "@" not in jid:
            jid += "@alumchat.xyz"
        if jid in self.client_roster.keys() or jid =='echobot@alumchat.xyz':
                self.talking_to = jid
                return True
        else:
            return False

    async def message(self,msg):
        if msg['type'] in ('chat', 'normal'):
            await aprint(msg['from'], ':',msg['body'])
        
    async def group_message(self,msg):
        if msg['type'] in ('groupchat'):
            await aprint("@", msg['mucroom'], ' ', msg['from'], ' : ', msg['body'])
    
    async def get_groups(self):
        result = await self['xep_0030'].get_items(jid='conference.alumchat.xyz', iterator=True)
        rooms = []
        for room in result['disco_items']:
            print(room['jid'])
            rooms.append(room['jid'])
        return rooms

    def group_exists(self, rooms, join):
        if "@" not in join:
            join += "@conference.alumchat.xyz"
        if join in rooms:
            self.current_group = join
            return True
        else:
            return False

    def wait_for_presences(self, pres):
        self.received.add(pres['from'].bare)
        if len(self.received) >= len(self.client_roster.keys()):
            self.presences_received.set()
        else:
            self.presences_received.clear()
    
    async def handle_conv(self):
        print("Chating with ", self.talking_to)
        print("\n"*3)
        continueConv = True
        while continueConv:
            user_input = await ainput('-> ')
            if user_input != "/quit":
                self.send_message(mto = self.talking_to, mbody=user_input, mtype="chat")
                await sleep(0.5)
            else:
                self.talking_to = None
                continueConv = False
    
    async def handle_group_conv(self):
        print("Chating in ", self.current_group)
        print("\n"*3)
        continueConv = True
        while continueConv:
            user_input = await ainput('-> ')
            if user_input != "/quit":
                self.send_message(mto = self.current_group, mbody=user_input, mtype="groupchat")
                await sleep(0.5)
            else:
                self.current_group = None
                continueConv = False

    def show_menu(self):
        menu = """
        1)Individual Chats
        2)Group Chats
        3)Show Roster
        4)Add a Friend
        5)Join a chat room
        6)Set presence message
        7)Exit
        """
        return menu

    async def client_loop(self):
        wants_to_continue = True
        while wants_to_continue:
            print(self.show_menu())
            menu_choice = await ainput("-> ")
            menu_choice = int(menu_choice)
            
            if menu_choice == 1:
                print("Your contacts")
                await self.show_roster()
                talk_to = await ainput("-> ")
                known = self.start_conv(talk_to)
                if known:
                    await self.handle_conv()
                else:
                    print(talk_to, "is not in your contacts")
            
            elif menu_choice == 2:
                rooms = await self.get_groups()
                to_join = await ainput('Choose a room to chat in: ')
                succes = self.group_exists(rooms, to_join)
                if succes:
                    await self.handle_group_conv()
                else:
                    print("The room you want to join doesnt exists")

            elif menu_choice == 3:
                print('Your contacts %s' % self.boundjid.bare)
                await self.show_roster()
            
            elif menu_choice == 4:
                to = await ainput("Friend to Add:")
                await self.send_friend_request(to)
            
            elif menu_choice == 5:
                rooms = await self.get_groups()
                to_join = await ainput('Choose a chat room to join:')
                succes = self.group_exists(rooms, to_join)
                if succes:
                    self.plugin['xep_0045'].join_muc(self.current_group, self.nick)
                    await sleep(0.5)
                    print("Succesfully joined: ", self.current_group)
                    self.talking_to = None
                else:
                    print("The room you want to join doesnt exists")
            
            elif menu_choice == 6:
                status_message= await ainput("Place your wanted status message: ")
                self.send_presence(pstatus=status_message)
                await sleep(0.5)
            else:
                wants_to_continue = False
                
        self.disconnect()
    
    async def send_friend_request(self, to):
        if "@" not in to:
            to += "@alumchat.xyz"
        print("Sending friend request to: ",to)
        try:
            self.send_presence_subscription(to,self.boundjid.bare)
            await sleep(0.5)
            print("Friend Request succesfully sent to: ", to)
        except:
            print("Couldn't add friend, are you sure ", to, " is on the server?")

class RegisterClient(slixmpp.ClientXMPP):
    def __init__(self, jid, password):
        slixmpp.ClientXMPP.__init__(self, jid, password)

        self.add_event_handler("session_start", self.start)

        self.add_event_handler("register", self.register)
    
    async def start(self, event):
        self.send_presence()
        await self.get_roster()
        self.disconnect()

    async def register(self, iq):

        resp = self.Iq()
        resp['type'] = 'set'
        resp['register']['username'] = self.boundjid.user
        resp['register']['password'] = self.password
        try:
            await resp.send()
            logging.info("Account created for %s!" % self.boundjid)
        except IqError as e:
            logging.error("Could not register account: %s" %
                    e.iq['error']['text'])
            self.disconnect()
        except IqTimeout:
            logging.error("No response from server.")
            self.disconnect()

if __name__ =='__main__':
    parser = ArgumentParser(description=UserClient.__doc__)

    parser.add_argument("-m", dest="mode")
    parser.add_argument("-j", dest="jid")
    parser.add_argument("-p", dest="password")

    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG, format='%(levelname)-8s %(message)s')

    if args.jid is None:
        args.jid = input("Username: ")
    if args.password is None:
        args.password = getpass("Password: ")
    if args.mode is None:
        args.mode = input("Sign Up(U) or Sign in(I):")

    if args.mode == "I":
        xmpp = UserClient(args.jid, args.password)
        xmpp.register_plugin('xep_0199')
        xmpp.register_plugin('xep_0045')
        xmpp.register_plugin('xep_0085')
        xmpp.register_plugin('xep_0030')

        xmpp.connect(address=('alumchat.xyz',5223))
        xmpp.process(forever=False)
    
    if args.mode == "U":
        xmpp = RegisterClient(args.jid, args.password)
        xmpp.connect(address=('alumchat.xyz',5223))
        xmpp.register_plugin('xep_0030')
        xmpp.register_plugin('xep_0004')
        xmpp.register_plugin('xep_0066')
        xmpp.register_plugin('xep_0077')
        xmpp['xep_0077'].force_registration = True
        xmpp.process(forever=False)
        print("If no error was presented run the code again to sign in")