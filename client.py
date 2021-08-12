
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

#Class that will be used to control comunication
class UserClient(slixmpp.ClientXMPP):
    
    def __init__(self, jid, password):
        super().__init__(jid, password)

        #Usefull event handlers
        self.add_event_handler("session_start", self.start)
        self.add_event_handler("change_status", self.wait_for_presences)
        self.add_event_handler("message", self.message)
        self.add_event_handler("groupchat_message",self.group_message)
        self.add_event_handler("chatstate", self.show_chatstate)

        
        #Atributes used to provide a better User experience
        self.talking_to = None
        self.current_group = None
        self.stored_group_chats = {}
        self.stored_direct_chats = {}

        self.nick = None

        self.received = set()
        self.presences_received = asyncio.Event()

    #This function is called when the connection to the server starts
    #it shows the users roster and starts the UI
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
    
    #Shows the friends list of the user
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
    #Function used to check if a jid is known by the user 
    #Params:
    #jid: jid to check if known
    def start_conv(self, jid):
        if "@" not in jid:
            jid += "@alumchat.xyz"
        if jid in self.client_roster.keys() or jid =='echobot@alumchat.xyz':
                self.talking_to = jid
                return True
        else:
            return False
    #Function used whenever a message stanza of type nomal or chat is received, checks  
    #if the received message is from the user that we are currently chatting with, 
    #if it isnt it stores the message on stored_direct_chats to print whenever
    #the user moves to the desired conversation
    #Params:
    #msg: received message stanza
    async def message(self,msg):
        if msg['type'] in ('chat', 'normal') and self.talking_to!=None and self.talking_to in  str(msg['from']):
            await aprint(msg['from'], ':',msg['body'])
        elif msg['type'] in ('chat', 'normal'):
            print("New message from: ", msg['from'] )
            if msg['from'] not in self.stored_direct_chats.keys():
                self.stored_direct_chats[msg['from']] = []    
            self.stored_direct_chats[msg['from']].append((msg['from'],msg['body']))
    #Function used whenever a message stanza of type groupchat is received, 
    #checks if the received message is from the current active room, 
    #if it isnt it stores the message on stored_direct_chats to print whenever the user moves 
    #to the desired chatroom
    #Params:
    #msg: received message stanza
    async def group_message(self,msg):
        if msg['type'] in ('groupchat') and self.current_group!=None and self.current_group in  str(msg['mucroom']):
            if msg['mucnick'] != self.nick:
                await aprint("@", msg['mucroom'], ' ', msg['mucnick'], ' : ', msg['body'])
        elif msg['type'] in ('groupchat'):
            print("New messages at: ", msg['mucroom'])
            if msg['mucroom'] not in self.stored_group_chats.keys():
                self.stored_group_chats[msg['mucroom']] = []
            
            self.stored_group_chats[msg['mucroom']].append((msg['mucnick'],msg['body']))
    #Function used to print all the available chat rooms in the server using xep_0030   
    async def get_groups(self):
        result = await self['xep_0030'].get_items(jid='conference.alumchat.xyz', iterator=True)
        rooms = []
        for room in result['disco_items']:
            print(room['jid'])
            rooms.append(room['jid'])
        return rooms
    #Function used to check if a wanted room exists on the server, if it exists it sets the room 
    #as the active chat room
    #Params:
    #rooms: rooms on the server
    #join: room that the user wants to join
    def group_exists(self, rooms, join):
        if "@" not in join:
            join += "@conference.alumchat.xyz"
        if join in rooms:
            self.current_group = join
            return True
        else:
            return False

    #Function called whenever a presence stanza is received
    #Params:
    #pres: the received presence stanza
    def wait_for_presences(self, pres):
        self.received.add(pres['from'].bare)
        if len(self.received) >= len(self.client_roster.keys()):
            self.presences_received.set()
        else:
            self.presences_received.clear()
    
    #Function used whenever, it reads a user input and acts acordingly to what the user types
    async def handle_conv(self):
        print("Chating with ", self.talking_to)
        print("\n"*3)
        self.status_notification(self.talking_to, 'chat','active')
        stored_key = None
        for user in self.stored_direct_chats.keys():
            if self.talking_to in str(user):
                stored_key = user
        if stored_key != None:
            for stored_message in self.stored_direct_chats[stored_key]:
                print(stored_message[0],":" ,stored_message[1])
            self.stored_direct_chats.pop(stored_key)
        continueConv = True
        while continueConv:
            user_input = await ainput('-> ')
            if user_input == "/quit":
                self.status_notification(self.talking_to, 'chat','paused')
                self.talking_to = None
                continueConv = False
            elif "/file" in user_input:
                file_name = user_input.split()[1]
                url = await self['xep_0363'].upload_file(file_name, domain='alumchat.xyz', timeout=10)
                message = self.make_message(mto=self.talking_to, mbody=url)
                message.send()
            else:
                self.send_message(mto = self.talking_to, mbody=user_input, mtype="chat")
                await sleep(0.5)
    #Similar to handle_conv but used in a group chat environment
    async def handle_group_conv(self):
        print("Chating in ", self.current_group)
        print("\n"*3)
        stored_key = None
        for room in self.stored_group_chats.keys():
            if self.current_group in str(room):
                stored_key = room
        if stored_key != None:
            for stored_message in self.stored_group_chats[stored_key]:
                print(stored_message[0],":" ,stored_message[1])
            self.stored_group_chats.pop(stored_key)
        continueConv = True
        while continueConv:
            user_input = await ainput('-> ')
            if user_input != "/quit":
                self.send_message(mto = self.current_group, mbody=user_input, mtype="groupchat")
                await sleep(0.5)
            else:
                self.current_group = None
                continueConv = False
    #Function used to print the starting menu
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
    #The main loop of our client app, used as UI
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
                    nick = await ainput("Pick A nickname: ")
                    self.nick = nick
                    self.plugin['xep_0045'].join_muc(self.current_group, nick)
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
    #Function used to send a presence_subscription to a desired JID
    #Params:
    #to: jid to send the presence_subscription
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
    #Function used to send notifications whenever the user sets a chat as the active chat
    #Params:
    #to: JID to send the status notification
    #chat: type of chat 'chat' or 'groupchat'
    #status: the status of the client
    def status_notification(self, to, chat ,status):
        status_to_send = self.make_message(mto=to,mfrom=self.boundjid.bare, mtype=chat)
        status_to_send['chat_state'] = status
        status_to_send.send()
    #Function used to show the client whenever a receiver leaves the active chat
    #Params:
    #msg: received message stanza
    def show_chatstate(self,msg):
        if self.talking_to!=None and self.talking_to in  str(msg['from']):
            print(msg['from'],' is ',msg['chat_state'])

#Class used whenever the user wants to create a new acount of the server
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

#Class used whenever the user wants to delete an account
class deleteUser(slixmpp.ClientXMPP):
    def __init__(self, jid,password):
        slixmpp.ClientXMPP.__init__(self,jid,password)
        self.add_event_handler("session_start", self.start)
        self.add_event_handler("unregister", self.unregister)

    async def start(self,event):
        self.send_presence()
        await self.get_roster()
        await self.unregister()

        self.disconnect()

    #Sends an IQ stanza to ask the server to remove the acount 
    async def unregister(self):
        resp = self.Iq()
        resp['type'] = 'set'
        resp['from'] = self.boundjid.user
        resp['password'] = self.password
        resp['register']['remove'] = 'remove'

        try:
            await resp.send()
            print("Success! Acount Deleted "+str(self.boundjid))
        except IqError as e:
            print("IQ Error:Account Not Deleted")
            self.disconnect()
        except IqTimeout:
            print("Timeout")
            self.disconnect() 

if __name__ =='__main__':
    parser = ArgumentParser(description=UserClient.__doc__)

    #Arguments needed to start a sesion
    parser.add_argument("-m", dest="mode")
    parser.add_argument("-j", dest="jid")
    parser.add_argument("-p", dest="password")

    args = parser.parse_args()

    #Asking for not given arguments
    if args.mode is None:
        args.mode = input("Sign Up(U), Sign in(I) or Delete Account(D):")
    if args.jid is None:
        args.jid = input("Username: ")
    if args.password is None:
        args.password = getpass("Password: ")
    

    if args.mode == "I":
        xmpp = UserClient(args.jid, args.password)
        #Registering needed plugins
        xmpp.register_plugin('xep_0199')
        xmpp.register_plugin('xep_0045')
        xmpp.register_plugin('xep_0085')
        xmpp.register_plugin('xep_0030')
        xmpp.register_plugin('xep_0363')

        xmpp.connect(address=('alumchat.xyz',5223))
        xmpp.process(forever=False)
    
    if args.mode == "U":
        xmpp = RegisterClient(args.jid, args.password)
        xmpp.connect(address=('alumchat.xyz',5223))
        #Registering needed plugins
        xmpp.register_plugin('xep_0030')
        xmpp.register_plugin('xep_0004')
        xmpp.register_plugin('xep_0066')
        xmpp.register_plugin('xep_0077')
        xmpp['xep_0077'].force_registration = True
        xmpp.process(forever=False)
        print("If no error was presented run the code again to sign in")

    if args.mode == "D":   
        xmpp= deleteUser(args.jid, args.password)
        xmpp.connect(address=('alumchat.xyz',5223))
        xmpp.register_plugin('xep_0030')
        xmpp.register_plugin('xep_0004')
        xmpp.register_plugin('xep_0066')
        xmpp.register_plugin('xep_0077')
        xmpp.process(forever=False)