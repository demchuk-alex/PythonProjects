#!/usr/bin/python2.7
# -*- coding: utf-8 -*-
#
#  Copyright 2013 DemchukAA <demchukaa@gmail.com>
#  
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2 of the License, or
#  (at your option) any later version.
#  
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#  
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#  MA 02110-1301, USA.
#  
import socket
import sys,re,time
import threading,os,os.path
import multiprocessing
import select,Queue
 
##############################VARAIBLES#######################################
login = """Action: login
Username: %(username)s
Secret: %(password)s
"""
originate = """Action: Originate
Channel: Local/%(local_user)s@%(context)s
CallerId: %(local_user)s 
Timeout:%(calltimeout)s
Application: Playback
Data: /var/lib/asterisk/sounds/%(playfile)s
Async: yes
"""
logoff="""Action: Logoff
"""
#tokens for configuration settings
token_value={'bindaddr':'127.0.0.1',
				'port':44444,
				'attempts':3,
				'log_path':'/var/log/asterisk',
				'delay':3,
				'rbindaddr':'127.0.0.1',
				'rport':55555,
				'amiport':5038}
reasonList=[0, 1, 3, 5, 8]
pid_file="/var/run/originate.pid"
########################Read conffiles#######################################
def Initialconf(procpid):
	global token_value
	file_pid=open("/var/run/originate.pid", "w")
	file_pid.write(str(procpid))
	file_pid.close()
	#tokens={'bindaddr':"bindaddr=(\d+\.\d+\.\d+\.\d+)", 
	#        'port':"port=(\d+)",
	#        'password':"password=(admin1234)",
	#        'attempts':"attempts=(\d+)",
	#        'log_path':'log_path=(.*)/',
	#        'rbindaddr':"rbindaddr=(\d+\.\d+\.\d+\.\d+)",
	#        'rport':"rport=(\d+)",
	#        'delay':"delay=(\d+)",
	#        'amiport':"amiport=(\d+)",
	#        'playfile':"playfile=(\w+)",
	#        'context':"context=(\w+-?(\w+)?)",
	#	'calltimeout':"calltimeout=(\d+)"}
	file=open("/etc/asterisk/origserver.conf", "r")
	#text=file.readlines()
	#for line in text:
	#	for item in tokens:
	#		if re.match(tokens[item], line):
	#			token_value[item]=re.search(tokens[item], line).group(1)
	value,key,end_word=None,None,None
	while True:
		text=file.readline()
		if text and (text[0] != "#"):
			for indexw in xrange(0, len(text)):
				if text[indexw] == "=":
					end_word=indexw
					key = text[0:end_word].strip()
			for indexk in xrange(end_word, len(text)):
				if text[indexk] == "\n" or text[indexk] == "#":
					value = text[end_word+1:indexk].strip()
					break
			token_value[key] = value
		elif not text: break			
	loging(os.getpid(), "Read settings........\n", str(token_value))
	file.close()
	return 0
########################Send Action additional function######################
def replay_status(attemt_count, order, attempt, proc):
	status = "Complete"
	if attempt == attemt_count-1:
		status="Incomplete"
		loging(proc, "Amount of attempts has expired sending status Incomplete")
	else:
		loging(proc, "Call is successed send OK and close client socket")
		
	send_count = 3
	while send_count > 0:
		sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        	nstatus = sock.connect_ex((token_value["rbindaddr"], int(token_value["rport"])))
       	 	if nstatus !=0:
                	loging(proc, "ARM server isn't running now, try later!!!!")
	                sock.close()
        	        break
		sock.send("Message: Result\r\nNumber: %(order)s\r\nStatus: %(status)s\r\n\r\n" % {'order': order, 'status': status})
		sread,swrite,serror = select.select([sock],[],[],5)
		if sread != []:
			data=sread[0].recv(1024)
			res_ok = re.search("Answer: Ok", str(data))
			if res_ok:
				loging(proc, "Received succesfull answer from remote server")
				sock.shutdown(2)
				sock.close()
				break
		sock.shutdown(2)
		sock.close()
		send_count -=1
	
	if send_count == 0:
		loging(proc, "The succesfull answer hasn't been received after 3 attempts")
	return
	
def ami_send(action, sock, **kwargs):######Send command to asterisk
	pattern = action % kwargs
	for command in pattern.split('\n'):
		sock.send(command+'\r\n')

def loging(number="", msg="", data=""):
	if not os.path.exists(token_value["log_path"]):
		os.mkdir(token_value["log_path"])
	logfile=open(token_value["log_path"]+'/callorglog', 'a+')
	timestamp = time.strftime("%d %b %Y %H:%M:%S ", time.localtime())
	logfile.write(str(timestamp)+"["+str(number)+"] "+msg+data+"\n") 
	logfile.close()

#########################Send Login Action################################	
def LoginAct(snet, num_call, username, password):
	credentials = {'username': username, 'password': password}
	ami_send(login, snet, **credentials)
	while True:
		data = snet.recv(4096)
		resp = re.search("Response: (Success)", str(data))
		if resp:
			loging(num_call, "Login action:"+str(resp.group(1)))
			break
	time.sleep(0.01)
#########################Send Logoff Action###################################
def LogoffAct(snet, num_call):
	for command in logoff.split('\n'):
		snet.send(command+'\r\n')
	while True:
		data = snet.recv(1024)
		resp = re.search("Response: (Goodbye)", str(data))
		if resp:
			loging(num_call, "Logoff action:"+str(resp.group(1)))
			break
	time.sleep(0.05)
	snet.close()
#########################Send Originate Action#################################
def OriginateAct(snet, local_user, proc):
	res = 0
	extensions = {'local_user': local_user, 'playfile': token_value["playfile"], 'context':token_value["context"], 'calltimeout':token_value["calltimeout"]}
	loging(proc, "Originate is started to ", local_user)
	ami_send(originate, snet, **extensions)
	while True:
		data = snet.recv(1024)
		resp = re.search("Event: OriginateResponse", str(data))
		reason = re.search("Reason: (\d)", str(data))
		channel = re.search("Channel: Local\/(%s)\@.+" % local_user, str(data))
		#print data
		if resp and reason and channel:
			res = int(reason.group(1)) 
			break
	loging(proc, "OriginateResponse of calling number %s with reason %s" % (str(channel.group(1)), str(res)))
	LogoffAct(snet, proc)
	return res
    
######################################Main treaded function#######################################    
def Main(num_call, order, proc):
	attempt=0
	while attempt < int(token_value["attempts"]):
		netw = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		nstatus = netw.connect_ex((token_value["bindaddr"], int(token_value["amiport"])))
		if nstatus != 0:
			loging(proc, "Asterisk isn't running now, try later!!!!!!")
			netw.close()
			return 0
		loging(proc, "Attempt "+str(attempt)+" of call to ", num_call)
		LoginAct(netw, proc, username='admorig', password='admorig2013')
		code = OriginateAct(netw, num_call, proc)
		if (code in reasonList) and attempt < int(token_value["attempts"])-1:
			attempt += 1
			time.sleep(int(token_value["delay"]))
		elif code == 4:
			attempt = int(token_value["attempts"]) 
			break
		else:
			break
	replay_status(int(token_value["attempts"]), order, attempt, proc)
	return 0
#####################################Reaper Class#############################################
class Reaper(threading.Thread):
	def __init__(self, reaper):
		self.pids = reaper
		threading.Thread.__init__(self)
	def run(self):
		while True:
			pidnum = self.pids.get()
			if pidnum != "exit":
				#time.sleep(0.2)
				#os.waitpid(pidnum, os.WNOHANG)
				os.waitpid(0, 0)
				self.pids.task_done()
			else:
				loging(msg="Reaper exit gracefully!!!")
				break
		sys.exit(0)
				
#####################################Server class#############################################	
class Connect(multiprocessing.Process):
	def __init__(self, sock, addr):
		self.sock = sock
		self.addr = addr
		self.secret = token_value["password"]
		multiprocessing.Process.__init__(self)
	def run (self):
		try:
			proc = str(os.getpid())
			while True:
				buf = self.sock.recv(4096)                         #wait for respond data
				message_ping = re.match("^Message: Ping\r\n", str(buf), re.M)
				message = re.search("^Message: Call", str(buf), re.M)
				secret = re.search("^Secret: %(secret)s\r\n" % {'secret': self.secret}, str(buf), re.M) #secret cheking
				order = re.search("^Number: (\d+)", str(buf), re.M)
				callnum = re.search("^CallerId: (\d+)\r\n", str(buf), re.M) #number to call
				if message and secret and order and callnum:				
					Order = str(order.group(1))
					Callnum = str(callnum.group(1))
					loging(proc, "Car has arrived with order "+Order+" initializating call to ", Callnum)
					self.sock.send("Answer: OK\r\nDescription: Successful\r\n\r\n")
					self.sock.shutdown(2)
					self.sock.close()
					res = Main(Callnum, Order, proc)	
					break
				elif message_ping and secret:
					self.sock.send("Answer: OK\r\nDescription: Settings are correct\r\n\r\n")
					self.sock.shutdown(2)
					self.sock.close()
					loging(proc, "Ping message from %s" % str(self.addr),"Settings are correct")
					break
				elif not message or not order or not callnum:
					self.sock.send("Answer: Error\r\nDescription: Wrong format\r\n\r\n")
					self.sock.shutdown(2)
					self.sock.close()
					loging(proc, "Wrong message format from ", str(self.addr))
					break										
				else:
					self.sock.send("Answer: Error\r\nDescription: Access denied\r\n\r\n")
					self.sock.shutdown(2)
					self.sock.close()					
					loging(proc, "Invalid password from ", str(self.addr))
					break
		except Exception, err:
			loging(proc, "Reason of next process falling: %s" % err)
			sys.exit(0)			
		sys.exit(0)

if __name__ == '__main__':
	try:
		Initialconf(os.getpid())
		reaper=Queue.Queue()     #queue of pids in reap thread
		reap = Reaper(reaper)
		reap.deamon = True
		reap.start()
		try:
			s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
			s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
			loging(os.getpid(),"Originate server is started and listening on ",token_value["bindaddr"]+":"+str(token_value["port"]))
			s.bind((token_value["bindaddr"], int(token_value["port"])))
			s.listen(5)
		except socket.error, e:
			loging(os.getpid(),"Originate server started on new pid because of: %s" % e)
			file_pid=open("/var/run/originate.pid", "w")
		        file_pid.write(os.getpid())
		        file_pid.close()
		while True:
			mainsock, writeables, exceptions = select.select([s], [], [])
			if mainsock != []:			
				sock, addr = mainsock[0].accept()	
				loging(os.getpid(),"Incomming connection from "+str(addr))
				con = Connect(sock, addr)
				con.deamon = True
				con.start()
				reaper.put_nowait(con.pid)
				sock.close()
	except KeyboardInterrupt as e:
		loging(os.getpid(),"Originate server is stoped because of:%s" % e)
		s.close()
		os.remove(pid_file)
		reaper.put("exit")
		sys.exit(0)


